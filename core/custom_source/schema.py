"""自訂來源 YAML 的安全載入與驗證，產出不可變的 Spec。

載入只做靜態檢查：不連網、不做 DNS、不執行 YAML 內任何內容。
任何輸入只會得到 Spec 或 LoadError。
"""
import hashlib
import ipaddress
import math
import re
import unicodedata
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlsplit

import soupsieve
import yaml
from urllib3.util import parse_url as urllib3_parse_url
from yaml.constructor import ConstructorError
from yaml.nodes import ScalarNode

from core.custom_source.errors import LoadError
from core.scrapers.utils import normalize_number_impl

MAX_BYTES = 65536
MAX_PATTERN_LEN = 200
MAX_CANDIDATES = 8
MAX_CANDIDATE_LEN = 16

RESERVED_IDS = frozenset({
    "auto", "dmm", "javbus", "jav321", "javdb", "d2pass", "heyzo", "fc2",
    "avsox", "javlibrary", "fc-javten", "metatube", "custom",
})

TOP_KEYS = frozenset({"id", "name", "fetch", "number_pattern", "steps", "fields", "tests"})
STEP_KEYS = frozenset({"url", "candidates", "not_found_when", "results"})
FIELD_NAMES = frozenset({
    "number", "title", "cover", "actors", "tags", "date", "duration", "maker",
    "director", "label", "series", "summary", "sample_images",
})
FIELD_KEYS = frozenset({"css", "meta", "jsonld", "attr", "all", "then"})
SOURCE_KEYS = ("css", "meta", "jsonld")
TRANSFORMS = frozenset({"regex", "strip_label", "split", "urljoin", "div"})
LIST_FIELDS = frozenset({"tags", "actors", "sample_images"})
CASE_KEYS = frozenset({"number", "status", "expect"})
CASE_STATUSES = frozenset({"ok", "multiple", "not_found"})
EXPECT_SUFFIXES = ("_contains", "_include", "_exclude", "_max")

ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
_AUTHORITY_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)")
_JSONLD_RE = re.compile(r"[A-Za-z0-9_]+\.[A-Za-z0-9_@:-]+")
_URL_VARS = frozenset({"{number}", "{number_lower}", "{number_digits}"})
_URL_VARS_SUFFIX = _URL_VARS | {"{suffix}"}
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")


@dataclass(frozen=True)
class Results:
    css: str
    keep_if_contains: str


@dataclass(frozen=True)
class Step:
    url: object
    candidates: tuple
    not_found_body: object
    results: object


@dataclass(frozen=True)
class Transform:
    name: str
    arg: object


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    selector: str
    attr: object
    all: bool
    then: tuple


@dataclass(frozen=True)
class Case:
    number: str
    status: str
    expect: tuple


@dataclass(frozen=True)
class Spec:
    id: str
    name: str
    fetch: str
    number_pattern: str | None
    steps: tuple
    fields: tuple
    tests: tuple
    hosts: tuple


# ---------------------------------------------------------------- YAML 載入

class _StrictLoader(yaml.SafeLoader):
    """SafeLoader 子類：每一層重複鍵都拒絕；日期維持字串。"""

    yaml_implicit_resolvers = {
        first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        seen = set()
        for key_node, _value_node in node.value:
            if not isinstance(key_node, ScalarNode):
                raise LoadError("bad_value", "鍵必須是純量", "")
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, Hashable):
                raise ConstructorError(None, None, "found unhashable key", key_node.start_mark)
            if key in seen:
                raise LoadError("duplicate_key", "出現重複的鍵", "")
            seen.add(key)
        return super().construct_mapping(node, deep)


def _error_line(exc):
    """PyYAML 錯誤位置的 1-based 行號；沒有位置資訊回 None。"""
    mark = getattr(exc, "problem_mark", None)
    return mark.line + 1 if mark is not None else None


def _parse_yaml(text):
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent):
                raise LoadError("alias", "不支援 YAML 別名（&／*）", "")
        return yaml.load(text, Loader=_StrictLoader)
    except LoadError:
        raise
    except ConstructorError as exc:
        if (exc.problem or "").startswith("could not determine a constructor"):
            raise LoadError("unsafe_tag", "含有不安全的 YAML tag", "") from None
        raise LoadError("yaml_syntax", "YAML 語法錯誤", "", _error_line(exc)) from None
    except yaml.YAMLError as exc:
        raise LoadError("yaml_syntax", "YAML 語法錯誤", "", _error_line(exc)) from None
    except RecursionError:
        raise LoadError("yaml_syntax", "YAML 語法錯誤", "") from None
    except Exception:
        # SafeConstructor 對 !!int／!!bool 等明確 tag 的壞值會拋原生例外
        raise LoadError("yaml_syntax", "YAML 值無法解析", "") from None


def load_text(text, filename_stem):
    """載入一份 YAML 文字，回傳已驗證的不可變 Spec；失敗拋 LoadError。"""
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise LoadError("yaml_syntax", "含無法編碼的字元", "") from None
    if size > MAX_BYTES:
        raise LoadError("too_large", "檔案超過 64 KiB", "")
    return _build_spec(_parse_yaml(text), filename_stem)


def load_bytes(raw, filename_stem):
    """載入原始 bytes（容許 BOM／CRLF），回傳 (Spec, 原始 bytes 的 sha256 hex)。"""
    if len(raw) > MAX_BYTES:
        raise LoadError("too_large", "檔案超過 64 KiB", "")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise LoadError("yaml_syntax", "檔案不是有效的 UTF-8", "") from None
    spec = _build_spec(_parse_yaml(text), filename_stem)
    return spec, hashlib.sha256(raw).hexdigest()


def load_uploaded(text):
    """載入上傳的 YAML 文字；id 取自 YAML 本身（過 slug／保留字檢查），無檔名可比對。"""
    return load_text(text, None)


def load_file(path):
    """讀檔（容許 BOM／CRLF）並載入；檔名 stem 即 id。OSError 不攔。"""
    p = Path(path)
    return load_bytes(p.read_bytes(), p.stem)[0]


# ---------------------------------------------------------------- 小工具

def _join(path, key):
    return key if path == "" else f"{path}.{key}"


def _check_keys(mapping, allowed, path):
    for key in mapping:
        if not isinstance(key, str):
            raise LoadError("bad_value", "鍵必須是字串", path)
    unknown = [k for k in mapping if k not in allowed]
    if unknown:
        raise LoadError("unknown_key", "未知的鍵", _join(path, unknown[0]))


def _required(mapping, key, path):
    if key not in mapping:
        raise LoadError("bad_value", "缺少必填欄位", _join(path, key))
    return mapping[key]


def _need_str(value, path):
    if not isinstance(value, str) or value == "":
        raise LoadError("bad_value", "須為非空字串", path)
    return value


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_template(text, allowed, path):
    for token in _PLACEHOLDER_RE.findall(text):
        if token not in allowed:
            raise LoadError("bad_template", "不支援的占位符", path)
    leftover = _PLACEHOLDER_RE.sub("", text)
    if "{" in leftover or "}" in leftover:
        raise LoadError("bad_template", "大括號不成對", path)


def _static_host(url, path):
    """回傳 URL 的靜態 host（小寫）；占位符落在 host、非 http(s)、本機／IP 位址皆拒絕。"""
    match = _AUTHORITY_RE.match(url)
    if match is None:
        raise LoadError("bad_template", "URL 須為 http 或 https", path)
    if "{" in match.group(1):
        raise LoadError("bad_template", "占位符不可出現在主機名稱", path)
    if "\\" in match.group(1):
        raise LoadError("bad_template", "主機段不可含反斜線", path)
    probe = _PLACEHOLDER_RE.sub("x", url)
    try:
        parsed = urlparse(probe)
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise LoadError("bad_template", "URL 格式錯誤", path) from None
    if parsed.scheme.lower() not in ("http", "https"):
        raise LoadError("bad_template", "URL 須為 http 或 https", path)
    if not host:
        raise LoadError("bad_template", "URL 缺少主機名稱", path)
    host = host.lower()
    try:
        other = urllib3_parse_url(probe).host
    except Exception:
        raise LoadError("bad_template", "URL 格式錯誤", path) from None
    if (other or "").strip("[]").lower() != host:
        raise LoadError("bad_template", "主機名稱解析結果不一致", path)
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        raise LoadError("bad_template", "不可指向本機或內部主機", path)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise LoadError("bad_template", "不支援 IP 位址", path)


def _compile_selector(selector, path):
    try:
        soupsieve.compile(selector)
    except Exception:
        raise LoadError("bad_selector", "CSS selector 語法錯誤", path) from None


def _compile_regex(pattern, path):
    try:
        return re.compile(pattern)
    except (re.error, RecursionError, OverflowError):
        raise LoadError("bad_pattern", "正規表達式無法編譯", path) from None


# ---------------------------------------------------------------- 頂層

def _validate_id(data, stem):
    value = _required(data, "id", "")
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise LoadError("bad_id", "id 須為小寫英數與連字號（1–32 字）", "id")
    if value in RESERVED_IDS:
        raise LoadError("reserved_id", "id 與內建來源保留字衝突", "id")
    if stem is not None and value != stem:
        raise LoadError("id_filename_mismatch", "id 必須等於檔名", "id")
    return value


def _validate_name(data):
    value = _required(data, "name", "")
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        raise LoadError("bad_value", "name 須為 1–40 字", "name")
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise LoadError("bad_value", "name 不可含控制字元", "name")
    return value


def _validate_fetch(data):
    value = _required(data, "fetch", "")
    if value == "cf":
        raise LoadError("fetch_cf_unsupported", "此版本不支援 CF 模式", "fetch")
    if value not in ("plain", "tls") or not isinstance(value, str):
        raise LoadError("unknown_fetch", "fetch 只接受 plain 或 tls", "fetch")
    return value


def _validate_pattern(data):
    if "number_pattern" not in data or data["number_pattern"] is None:
        return None, None
    value = data["number_pattern"]
    if not isinstance(value, str):
        raise LoadError("bad_value", "number_pattern 須為字串", "number_pattern")
    if len(value) > MAX_PATTERN_LEN:
        raise LoadError("bad_pattern", "number_pattern 過長", "number_pattern")
    return value, _compile_regex(value, "number_pattern")


def _build_spec(data, stem):
    if not isinstance(data, dict):
        raise LoadError("bad_value", "頂層必須是 mapping", "")
    _check_keys(data, TOP_KEYS, "")
    spec_id = _validate_id(data, stem)
    name = _validate_name(data)
    fetch = _validate_fetch(data)
    pattern, compiled = _validate_pattern(data)
    steps, hosts = _validate_steps(_required(data, "steps", ""))
    fields = _validate_fields(_required(data, "fields", ""))
    tests = _validate_tests(_required(data, "tests", ""), compiled)
    return Spec(spec_id, name, fetch, pattern, steps, fields, tests, hosts)


# ---------------------------------------------------------------- steps

def _validate_candidates(raw, path):
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CANDIDATES:
        raise LoadError("bad_value", "candidates 須為 1–8 個字串", path)
    for i, item in enumerate(raw):
        if not isinstance(item, str) or len(item) > MAX_CANDIDATE_LEN:
            raise LoadError("bad_value", "candidate 須為 16 字以內的字串", f"{path}[{i}]")
    return tuple(raw)


def _validate_results(raw, path):
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "results 須為 mapping", path)
    _check_keys(raw, frozenset({"css", "keep_if_contains"}), path)
    css = _need_str(_required(raw, "css", path), _join(path, "css"))
    _compile_selector(css, _join(path, "css"))
    keep = _need_str(_required(raw, "keep_if_contains", path), _join(path, "keep_if_contains"))
    _check_template(keep, _URL_VARS, _join(path, "keep_if_contains"))
    return Results(css, keep)


def _validate_not_found(raw, path):
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "not_found_when 須為 mapping", path)
    _check_keys(raw, frozenset({"body_contains"}), path)
    return _need_str(_required(raw, "body_contains", path), _join(path, "body_contains"))


def _validate_first_step(raw, two_stage):
    path = "steps[0]"
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "step 須為 mapping", path)
    _check_keys(raw, STEP_KEYS, path)
    url = _need_str(_required(raw, "url", path), f"{path}.url")
    candidates = ("",)
    if "candidates" in raw:
        if two_stage:
            raise LoadError("bad_value", "兩段式不可使用 candidates", f"{path}.candidates")
        candidates = _validate_candidates(raw["candidates"], f"{path}.candidates")
        _check_template(url, _URL_VARS_SUFFIX, f"{path}.url")
    else:
        _check_template(url, _URL_VARS, f"{path}.url")
    host = _static_host(url, f"{path}.url")
    not_found = None
    if "not_found_when" in raw:
        not_found = _validate_not_found(raw["not_found_when"], f"{path}.not_found_when")
    results = None
    if two_stage:
        results = _validate_results(_required(raw, "results", path), f"{path}.results")
    elif "results" in raw:
        raise LoadError("bad_value", "單段式不可使用 results", f"{path}.results")
    return Step(url, candidates, not_found, results), host


def _validate_steps(raw):
    if not isinstance(raw, list) or len(raw) not in (1, 2):
        raise LoadError("bad_value", "steps 須有 1 或 2 段", "steps")
    first, host = _validate_first_step(raw[0], len(raw) == 2)
    steps = [first]
    if len(raw) == 2:
        if not isinstance(raw[1], dict) or raw[1]:
            raise LoadError("bad_value", "第 2 段必須是空 mapping", "steps[1]")
        steps.append(Step(None, (), None, None))
    return tuple(steps), (host.removeprefix("www."),)


def detail_host_allowed(spec, url):
    """詳情頁網址的 host（去開頭 www.）須是 spec.hosts 的基底 host 或其子網域。"""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    h = host.removeprefix("www.")
    return any(h == b or h.endswith("." + b) for b in spec.hosts)


# ---------------------------------------------------------------- fields

def _validate_transform_arg(name, arg, path):
    if name == "regex":
        if not isinstance(arg, str) or arg == "":
            raise LoadError("bad_value", "regex 參數須為非空字串", path)
        if _compile_regex(arg, path).groups < 1:
            raise LoadError("bad_pattern", "regex 至少需要一個 capture group", path)
    elif name in ("strip_label", "split"):
        _need_str(arg, path)
    elif name == "div":
        if not _is_number(arg):
            raise LoadError("bad_value", "div 須為非零有限數字", path)
        try:
            usable = math.isfinite(arg) and arg != 0
        except OverflowError:
            usable = False
        if not usable:
            raise LoadError("bad_value", "div 須為非零有限數字", path)
    elif arg is not True:
        raise LoadError("bad_value", "urljoin 的參數須為 true", path)
    return arg


def _validate_then(raw, path):
    if not isinstance(raw, list):
        raise LoadError("bad_value", "then 須為 list", path)
    out = []
    for i, item in enumerate(raw):
        item_path = f"{path}[{i}]"
        if not isinstance(item, dict) or len(item) != 1:
            raise LoadError("bad_value", "變換須為恰一個鍵的 mapping", item_path)
        name = next(iter(item))
        if not isinstance(name, str) or name not in TRANSFORMS:
            raise LoadError("unknown_transform", "未知的變換", item_path)
        arg = _validate_transform_arg(name, item[name], _join(item_path, name))
        out.append(Transform(name, arg))
    return tuple(out)


def _validate_field(name, raw, path):
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "欄位須為 mapping", path)
    _check_keys(raw, FIELD_KEYS, path)
    kinds = [k for k in SOURCE_KEYS if k in raw]
    if len(kinds) != 1:
        raise LoadError("bad_value", "須恰有 css／meta／jsonld 其中一個來源", path)
    kind = kinds[0]
    selector = _need_str(raw[kind], _join(path, kind))
    if kind == "css":
        _compile_selector(selector, _join(path, kind))
    if kind == "jsonld" and _JSONLD_RE.fullmatch(selector) is None:
        raise LoadError("bad_value", "jsonld 須寫成 Type.key", _join(path, kind))
    attr = None
    if "attr" in raw:
        if kind != "css":
            raise LoadError("bad_value", "attr 只可搭配 css", _join(path, "attr"))
        attr = _need_str(raw["attr"], _join(path, "attr"))
    all_flag = raw.get("all", False)
    if not isinstance(all_flag, bool):
        raise LoadError("bad_value", "all 須為布林", _join(path, "all"))
    then = _validate_then(raw["then"], _join(path, "then")) if "then" in raw else ()
    return Field(name, kind, selector, attr, all_flag, then)


def _validate_fields(raw):
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "fields 須為 mapping", "fields")
    _check_keys(raw, FIELD_NAMES, "fields")
    if "title" not in raw and "cover" not in raw:
        raise LoadError("bad_value", "fields 至少要有 title 或 cover", "fields")
    return tuple(_validate_field(name, value, _join("fields", name)) for name, value in raw.items())


# ---------------------------------------------------------------- tests

def _expect_value(suffix, field, value, path):
    if suffix == "_contains":
        return _need_str(value, path)
    if suffix == "_max":
        if field not in LIST_FIELDS or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise LoadError("bad_value", "_max 只可用於 list 欄位且須為非負整數", path)
        return value
    if suffix in ("_include", "_exclude"):
        if field not in LIST_FIELDS:
            raise LoadError("bad_value", f"{suffix} 只可用於 list 欄位", path)
        value_ok = isinstance(value, list) and value and all(isinstance(v, str) for v in value)
        if not value_ok:
            raise LoadError("bad_value", "須為非空字串 list", path)
        return tuple(value)
    if isinstance(value, bool) or not isinstance(value, (str, int, list)):
        raise LoadError("bad_value", "相等斷言的值型別錯誤", path)
    if isinstance(value, list):
        if not all(isinstance(v, str) for v in value):
            raise LoadError("bad_value", "list 內須為字串", path)
        return tuple(value)
    return value


def _split_expect_key(key):
    if key in FIELD_NAMES:
        return key, ""
    for suffix in EXPECT_SUFFIXES:
        if key.endswith(suffix) and key[:-len(suffix)] in FIELD_NAMES:
            return key[:-len(suffix)], suffix
    return None


def _validate_expect(raw, path):
    """回傳 (expect 元組, 有正向斷言, 有負向斷言)。"""
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "expect 須為 mapping", path)
    items, positive, negative = [], False, False
    for key, value in raw.items():
        key_path = _join(path, str(key))
        if not isinstance(key, str):
            raise LoadError("bad_value", "鍵必須是字串", path)
        parsed = _split_expect_key(key)
        if parsed is None:
            raise LoadError("unknown_key", "未知的 expect 鍵", key_path)
        field, suffix = parsed
        items.append((key, _expect_value(suffix, field, value, key_path)))
        if suffix in ("_exclude", "_max"):
            negative = True
        else:
            positive = True
    return tuple(items), positive, negative


def _validate_case(raw, compiled, path):
    if not isinstance(raw, dict):
        raise LoadError("bad_value", "案例須為 mapping", path)
    _check_keys(raw, CASE_KEYS, path)
    number = _need_str(_required(raw, "number", path), f"{path}.number")
    if compiled is not None and compiled.fullmatch(normalize_number_impl(number)) is None:
        raise LoadError("bad_pattern", "番號不符合自己的 number_pattern", f"{path}.number")
    status = raw.get("status", "ok")
    if not isinstance(status, str) or status not in CASE_STATUSES:
        raise LoadError("bad_value", "status 須為 ok／multiple／not_found", f"{path}.status")
    expect, positive, negative = (), False, False
    if "expect" in raw:
        expect, positive, negative = _validate_expect(raw["expect"], f"{path}.expect")
    if status != "not_found" and not positive:
        raise LoadError("bad_value", "ok／multiple 案例至少要有一項正向斷言", f"{path}.expect")
    # AC-4：負向斷言只計 ok／multiple 案
    return Case(number, status, expect), negative and status != "not_found"


def _validate_tests(raw, compiled):
    if not isinstance(raw, list) or not raw:
        raise LoadError("bad_value", "tests 至少要有一案", "tests")
    cases = []
    has_negative = False
    for i, item in enumerate(raw):
        case, negative = _validate_case(item, compiled, f"tests[{i}]")
        cases.append(case)
        has_negative = has_negative or negative
    if not has_negative:
        raise LoadError("missing_negative_assert", "tests 須至少有一項 _exclude 或 _max 負向斷言", "tests")
    if not any(c.status == "not_found" for c in cases):
        raise LoadError("missing_not_found_case", "tests 須至少有一案 status: not_found（用一個不存在的番號，擋站方軟 404）", "tests")
    return tuple(cases)
