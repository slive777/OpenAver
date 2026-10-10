"""
OpenAver Windows 打包腳本
在 WSL/Linux 環境下打包出 Windows 可用的 ZIP

使用方式：
    python build.py

原理：
    1. 下載 Windows 嵌入式 Python
    2. 用 pip download 下載 Windows wheel 檔案
    3. 解壓 wheel 到 site-packages
    4. 打包成 ZIP
"""
import sys
import re
import shutil
import zipfile
import urllib.request
import subprocess
from pathlib import Path

# ============ 配置 ============

PYTHON_VERSION = "3.12.4"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"

# 專案結構
PROJECT_ROOT = Path(__file__).resolve().parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
CACHE_DIR = PROJECT_ROOT / ".build_cache"  # 緩存目錄（不會被清理）

# 需要複製的專案目錄/檔案
COPY_ITEMS = [
    "web",
    "core",
    "windows",
    "locales",
    "maker_mapping.json",
    "dmm_prefix_table.json",
]

# ============ Allowlist 模型（T2：棄 pip freeze + denylist） ============
#
# Windows 打包依賴來源 = requirements.txt 顯式 allowlist（程式碼層調整）
# + extra_deps（Windows pywebview backend 專用）。
# 不再 pip freeze dev venv，根除 denylist 漂移與 orphan 污染。

# uvicorn[standard] 裡的 win-safe extras（uvloop 不含，Windows 用不到；PyYAML 已明列於 requirements.txt）
# websockets 已是 requirements.txt 頂層，不重複
# 精確釘版本（==）確保可重現 build：同 git tag = 同 ZIP（與 EXTRA_DEPS_NO_DEPS 同規範）。
# 版本來源：.build_cache/wheels/ 實際解析的 wheel 檔名（cross-check dist/ ZIP site-packages）。
# 升版時與 requirements.txt 的 uvicorn[standard]==X.Y.Z 同步評估。
_UVICORN_WIN_SAFE_EXTRAS = [
    "httptools==0.8.0",
    "watchfiles==1.2.0",
    "python-dotenv==1.2.2",
]

# pure-Python sdist-only 套件（PyPI 從未發 wheel）
SDIST_OK: set[str] = {"proxy-tools"}

# 無 win_amd64 wheel 但 Windows 合法缺席的套件（skip + warning 而非 hard-fail）
# 理論上 uvloop 在機制 1 已不應被請求；此集是防禦性後備
SKIP_IF_NO_WIN_WHEEL: set[str] = {"uvloop"}

# Windows pywebview backend 專用依賴（有 win32 marker，Linux pip 不自動解析）→ Phase 2 逐一 --no-deps
# 所有項目均釘精確版本（==），確保：
#   1. stale-cleanup 能偵測版本不匹配並強制重下（防 CI cache 送出舊版）
#   2. 相同 git tag = 相同 ZIP（可重現 build）
# pythonnet + clr_loader 釘精確版本：3.0.5 + 0.2.10 是已驗證的相容對；
# pythonnet 3.1.0 需要 clr_loader>=0.3.1，不可混版。
# 模組級常數（非函式內 local）：供守衛測試 import 驗證、防新增 extra dep 漏守衛。
EXTRA_DEPS_NO_DEPS: list[str] = [
    "pywebview==6.2.1",       # no-deps：pywebview→proxy-tools 無 wheel 會讓 with-deps 失敗
    "bottle==0.13.4",         # pin：防 CI cache 送舊版（stale-reuse bug fix）
    "proxy-tools==0.1.0",     # SDIST_OK：PyPI 只有 tar.gz；pin 確保 stale-cleanup 作用
    "clr_loader==0.2.10",     # pin：與 pythonnet 3.0.5 的相容版本
    "pythonnet==3.0.5",       # pin：3.1.0 需要 clr_loader>=0.3.1（會破壞現有組合）
    "win32-setctime==1.2.0",  # pin：防 CI cache 送舊版（stale-reuse bug fix）
    "colorama==0.4.6",        # pin：防 CI cache 送舊版（stale-reuse bug fix）
]


def _parse_allowlist_lines(lines: list[str]) -> list[str]:
    """解析 requirements 行 → Windows build 頂層依賴清單。

    extras 處理（fail-closed）：
    - 只有 `uvicorn[standard]==X.Y.Z` 會被改寫成 `uvicorn==X.Y.Z`（其 win-safe 子套件
      由 _UVICORN_WIN_SAFE_EXTRAS 明列補回）。
    - 任何「其他」帶 extra 的依賴（如 `redis[hiredis]`）→ **hard-fail**，不靜默剝除。
      原因：blanket 剝 extra 會讓該 extra 的子依賴從 Windows ZIP 無聲消失——正是 T2
      要根除的漂移。新增帶 extra 的依賴時，須先在 build.py 明列其 win-safe 子依賴再放行。
    """
    extra_re = re.compile(r"\[[^\]]*\]")
    deps: list[str] = []
    for line in lines:
        s = line.split("#", 1)[0].strip()
        if not s or s.startswith("-"):
            continue
        m = extra_re.search(s)
        if m:
            name = re.split(r"[\[=<>!~]", s, maxsplit=1)[0].strip().lower().replace("_", "-")
            if name == "uvicorn" and m.group(0) == "[standard]":
                s = extra_re.sub("", s)  # uvicorn[standard]==X → uvicorn==X
            else:
                raise SystemExit(
                    f"[BUILD ERROR] requirements.txt 有未處理的 extra：{s!r}。\n"
                    f"build.py 只改寫 uvicorn[standard]（win-safe 子套件已在 "
                    f"_UVICORN_WIN_SAFE_EXTRAS 明列）。新增帶 extra 的依賴時，請先在 build.py "
                    f"明列其 win-safe 子依賴再放行——不可讓 extra 被靜默剝除（T2 fail-closed）。"
                )
        deps.append(s)
    return deps


def parse_requirements_allowlist() -> list[str]:
    """從 requirements.txt 解析 Windows build 頂層依賴清單（見 _parse_allowlist_lines）。"""
    req_path = PROJECT_ROOT / "requirements.txt"
    return _parse_allowlist_lines(req_path.read_text(encoding="utf-8").splitlines())


# ============ 工具函數 ============

def download_file(url: str, dest: Path) -> None:
    """下載檔案"""
    print(f"  下載: {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"  完成: {dest.name}")


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """解壓 ZIP"""
    print(f"  解壓: {zip_path.name}")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)


def extract_wheel(wheel_path: Path, dest_dir: Path) -> None:
    """解壓 wheel 檔案到目標目錄"""
    with zipfile.ZipFile(wheel_path, 'r') as zf:
        for member in zf.namelist():
            # 跳過 .dist-info 以外的 metadata
            if member.endswith('/'):
                continue
            # 解壓到目標目錄
            zf.extract(member, dest_dir)


def extract_tar_gz(tar_path: Path, dest_dir: Path) -> None:
    """解壓 tar.gz 原始碼套件到目標目錄（只複製 Python 模組）"""
    import tarfile
    with tarfile.open(tar_path, 'r:gz') as tf:
        # 找出套件目錄（通常是 package_name-version/package_name/）
        members = tf.getnames()
        # 找出實際的 Python 套件目錄
        for member in members:
            parts = member.split('/')
            if len(parts) >= 2 and not parts[1].endswith('.egg-info') and not parts[1].startswith('.'):
                # 可能是套件目錄
                pkg_name = parts[1]
                if any(m.startswith(f"{parts[0]}/{pkg_name}/") and m.endswith('.py') for m in members):
                    # 確認是 Python 套件
                    pkg_prefix = f"{parts[0]}/{pkg_name}/"
                    for m in tf.getmembers():
                        if m.name.startswith(pkg_prefix):
                            # 調整路徑：移除頂層目錄
                            m.name = m.name[len(parts[0]) + 1:]
                            tf.extract(m, dest_dir)
                    return


# ============ 打包步驟 ============

def clean_build():
    """清理舊的建置目錄"""
    print("\n[1/6] 清理舊建置...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    # 清 source __pycache__ 避免 stale .pyc：若 Edit 同字數同秒寫入，Python
    # import 時 .pyc header (mtime+size) 與 .py 完全 match 會直接信任 cache，
    # 導致 build.py `from core.version import VERSION` 拿到舊版號當 zip filename
    # （內容是新的，只是檔名錯）。一次曾遇 0.8.8→0.8.9 同字數翻車。
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        # 只清 source 目錄下的 __pycache__，跳 venv / build / dist / node_modules
        rel = pycache.relative_to(PROJECT_ROOT)
        if rel.parts[0] in ("venv", "build", "dist", "node_modules", ".git"):
            continue
        shutil.rmtree(pycache, ignore_errors=True)


def download_embedded_python():
    """下載嵌入式 Python（使用緩存）"""
    print("\n[2/6] 準備嵌入式 Python...")

    python_dir = BUILD_DIR / "OpenAver" / "python"
    python_dir.mkdir(parents=True)

    # 檢查緩存
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_zip = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"

    if cached_zip.exists():
        print(f"  使用緩存: {cached_zip.name}")
    else:
        print("  下載中（首次會較慢）...")
        download_file(PYTHON_EMBED_URL, cached_zip)

    # 從緩存解壓
    extract_zip(cached_zip, python_dir)

    # 修改 _pth 檔案以啟用 site-packages
    pth_files = list(python_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("找不到 ._pth 檔案")

    pth_file = pth_files[0]
    pth_name = pth_file.stem  # e.g., "python312"

    pth_content = f"""{pth_name}.zip
.
Lib/site-packages
../app
import site
"""
    pth_file.write_text(pth_content)
    print(f"  已修改: {pth_file.name}")

    return python_dir


def _pkg_name_from_filename(filename: str) -> str:
    """從 wheel/tar.gz 檔名取標準化套件名（首個 '-' 前，標準化為 lowercase + dash）。"""
    stem = Path(filename).stem
    # tar.gz: strip second .gz extension already removed by .stem on .tar.gz
    # For foo-1.0.tar.gz, Path("foo-1.0.tar.gz").stem = "foo-1.0.tar"
    # So strip trailing .tar if present
    if stem.endswith(".tar"):
        stem = stem[:-4]
    return stem.split("-")[0].lower().replace("_", "-")


def _norm_pkg_name(spec: str) -> str:
    """從 pip spec 字串取標準化套件名（去 extras/版本/標點，lowercase + dash）。"""
    return re.split(r"[=<>!~\[]", spec, maxsplit=1)[0].strip().lower().replace("_", "-")


def _download_one_package(
    pkg_spec: str,
    wheels_dir: Path,
) -> set[Path]:
    """下載單一套件（spec）為 win_amd64 wheel，或 sdist（限 SDIST_OK 成員）。

    Returns set of new file paths downloaded into wheels_dir.
    Raises SystemExit on hard-fail (required dep with no win wheel).
    """
    pkg_name = re.split(r"[=<>!~\[]", pkg_spec, maxsplit=1)[0].strip().lower().replace("_", "-")
    before = set(wheels_dir.glob("*.*"))

    if pkg_name in SDIST_OK:
        # sdist 例外：允許 tar.gz（純 Python，PyPI 無 wheel）
        pip_cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheels_dir),
            "--no-deps",
            pkg_spec,
        ]
        result = subprocess.run(pip_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n[BUILD ERROR] sdist 下載失敗（{pkg_spec}）：\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
    else:
        # 標準路徑：只允許 win_amd64 binary wheel
        pip_cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheels_dir),
            "--platform", "win_amd64",
            "--python-version", "3.12",
            "--only-binary", ":all:",
            "--no-deps",
            pkg_spec,
        ]
        result = subprocess.run(pip_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if pkg_name in SKIP_IF_NO_WIN_WHEEL:
                print(f"  [WARNING] {pkg_name} 無 win_amd64 wheel，已跳過（Windows 合法缺席）")
                return set()
            else:
                # FAIL-CLOSED：必要依賴無 win wheel，硬失敗
                print(
                    f"\n[BUILD ERROR] {pkg_spec!r} 無 win_amd64 wheel 且不在 SDIST_OK / SKIP_IF_NO_WIN_WHEEL。\n"
                    f"請確認此套件是否有 Windows binary wheel，或將其加入 SDIST_OK（純 Python）\n"
                    f"/ SKIP_IF_NO_WIN_WHEEL（Windows 合法缺席）。\n"
                    f"pip stderr：\n{result.stderr}",
                    file=sys.stderr,
                )
                sys.exit(1)

    after = set(wheels_dir.glob("*.*"))
    return after - before


def download_and_install_packages(python_dir: Path):  # noqa: C901 — Windows wheel 兩階段下載 + manifest-based extract 是同一次 build 的單一狀態機（Phase 1／Phase 2／機制 3 manifest-based extract，見 docstring），拆分會讓 phase 之間的隱含依賴（cache/manifest）更難追蹤，非本 Phase 治理範圍（build 工具鏈）
    """下載 Windows wheel 並解壓到 site-packages（allowlist + manifest-based extract）

    兩階段下載策略：
    Phase 1（with-deps）：runtime + win-safe extras（不含 pywebview），讓 pip 解出
      完整 transitive 依賴樹（pydantic_core / anyio / h11 / markupsafe 等）。
      pywebview 從此排除：它的 dep proxy-tools 只有 sdist，--only-binary 會失敗。

    Phase 2（--no-deps each）：pywebview + extra_deps 逐一下載，各自套用
      SDIST_OK（proxy-tools 允許 tar.gz）/ SKIP_IF_NO_WIN_WHEEL / FAIL-CLOSED 規則。

    機制 3（manifest-based extract）：
      extract_manifest = Phase 1 新下載 + Phase 1 cache-hit + Phase 2 新下載 + Phase 2 cache-hit。
      解壓只迭代 manifest，不 glob 整個 cache，orphan 永不被帶入。
    """
    print("\n[3/6] 準備依賴套件...")

    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # 使用緩存目錄存放 wheel
    wheels_dir = CACHE_DIR / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    # ── 機制 1：從 requirements.txt 解析 allowlist（取代 pip freeze） ──
    # uvicorn[standard] → uvicorn（去 extra）+ win-safe extras 明列
    # pywebview 從 requirements.txt 讀入，但在 Phase 1 排除（proxy-tools 無 wheel）
    runtime_deps = parse_requirements_allowlist()
    win_safe_extras = list(_UVICORN_WIN_SAFE_EXTRAS)  # httptools/watchfiles/python-dotenv

    # Phase 1：runtime（去 pywebview）+ win-safe extras → with-deps，解 transitive
    phase1_deps = [d for d in runtime_deps + win_safe_extras
                   if _norm_pkg_name(d) != "pywebview"]

    extra_deps_no_deps = EXTRA_DEPS_NO_DEPS

    print(f"  Phase 1 (with-deps): {len(phase1_deps)} 頂層套件")
    print(f"  Phase 2 (no-deps):   {len(extra_deps_no_deps)} 套件（pywebview + Windows extras）")

    # ⚠️ stale-cleanup Phase 1：版本不匹配的舊 wheel（只清有 == pin 的）
    # Phase 2 套件有 pin 的也一起清；transitive（無 pin）交給 manifest orphan-cleanup
    pinned: dict[str, str] = {}
    for dep in phase1_deps + extra_deps_no_deps:
        name = _norm_pkg_name(dep)
        if "==" in dep:
            pinned[name] = dep.split("==")[1]
    stale_count = 0
    for f in list(wheels_dir.glob("*.*")):
        cached_name = _pkg_name_from_filename(f.name)
        if cached_name in pinned:
            expected_ver = pinned[cached_name]
            # tar.gz 的 .stem 仍含 ".tar"（foo-1.0.tar.gz → "foo-1.0.tar"）→ 先剝除，
            # 否則版本被解析成 "1.0.tar"、永遠 != pin 而誤刪（latent，proxy-tools 目前未 pin）
            stem = f.stem
            if stem.endswith(".tar"):
                stem = stem[:-4]
            parts = stem.split("-")
            if len(parts) >= 2 and parts[1] != expected_ver:
                f.unlink()
                stale_count += 1
    if stale_count:
        print(f"  清除 {stale_count} 個版本不匹配的舊 wheel")

    # ── 機制 3：manifest-based extract ──
    # extract_manifest = Phase 1 + Phase 2 本次下載/cache-hit 的所有檔案集合
    extract_manifest: set[Path] = set()

    # Phase 1：以 pip download（with-deps）解完整 transitive 樹
    # 總是執行（pip 自帶 HTTP metadata cache；--dest 目錄已有的 wheel 瞬間完成）
    # 這是確保 transitive（pydantic_core/anyio/h11/...）不缺少的唯一可靠方式
    # 同時解析 pip stdout 的 "Saved PATH" 行，建立本次 Phase 1 精確 manifest
    print("  Phase 1 執行中（pip 自帶 metadata cache，已緩存項目瞬間完成）...")
    before_p1 = set(wheels_dir.glob("*.*"))
    pip_cmd = [
        sys.executable, "-m", "pip", "download",
        "--dest", str(wheels_dir),
        "--platform", "win_amd64",
        "--python-version", "3.12",
        "--only-binary", ":all:",
    ] + phase1_deps
    result = subprocess.run(pip_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Phase 1 失敗：hard-fail（SKIP_IF_NO_WIN_WHEEL 套件不應出現在 Phase 1）
        print(f"\n[BUILD ERROR] Phase 1 (with-deps) 下載失敗：\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 解析 pip stdout 取得本次 Phase 1 精確解析集
    # pip 行為：
    #   新下載到 --dest → "Saved /abs/path/pkg.whl"
    #   已在 --dest → "  File was already downloaded /abs/path/pkg.whl"
    # 兩種行都計入 manifest（精確反映 pip 本次解析的完整依賴集）
    p1_manifest_files: set[Path] = set()
    for line in result.stdout.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("Saved "):
            p = Path(line_stripped[len("Saved "):].strip()).resolve()
            if p.exists():
                p1_manifest_files.add(p)
        elif line_stripped.startswith("File was already downloaded "):
            p = Path(line_stripped[len("File was already downloaded "):].strip()).resolve()
            if p.exists():
                p1_manifest_files.add(p)

    # N3 防護：Phase 1 有頂層依賴卻解析出空 manifest → pip stdout 格式可能改變
    # （未來 pip 版本 / --quiet 預設）。若放任，下方 orphan-cleanup 會刪光 Phase 1
    # wheel、extract 只剩 Phase 2 → 默默產出缺套件的壞 ZIP。fail-closed 擋下。
    if phase1_deps and not p1_manifest_files:
        print(
            "\n[BUILD ERROR] Phase 1 manifest 為空（pip stdout 無 'Saved'/'File was "
            "already downloaded' 行）。pip 輸出格式可能已變更——中止以免產出缺套件的 ZIP。\n"
            f"--- pip stdout ---\n{result.stdout}",
            file=sys.stderr,
        )
        sys.exit(1)

    after_p1 = set(wheels_dir.glob("*.*"))
    new_p1 = after_p1 - before_p1
    if new_p1:
        print(f"  Phase 1 新增 {len(new_p1)} 個 wheel（含 transitive）；manifest {len(p1_manifest_files)} 個")
    else:
        print(f"  Phase 1 全部已緩存（manifest {len(p1_manifest_files)} 個）")

    # 清除 before_p1 中被 Phase 1 解析選中了不同版本的舊 wheel
    # 例：cache 有 httptools-0.7.1，Phase 1 解析選 httptools-0.8.0 → 清 0.7.1
    p1_resolved_names = {_pkg_name_from_filename(f.name) for f in p1_manifest_files}
    p1_superseded = 0
    for f in list(before_p1):
        name = _pkg_name_from_filename(f.name)
        if name in p1_resolved_names and f not in p1_manifest_files and f.exists():
            f.unlink()
            p1_superseded += 1
    if p1_superseded:
        print(f"  Phase 1 清除 {p1_superseded} 個被升版取代的舊 wheel")

    extract_manifest.update(p1_manifest_files)

    # Phase 2：逐一下載 pywebview + extra_deps（--no-deps，SDIST_OK / fail-closed）
    p2_names_in_cache = {_pkg_name_from_filename(f.name) for f in wheels_dir.glob("*.*")}
    phase2_to_download = [dep for dep in extra_deps_no_deps
                          if _norm_pkg_name(dep) not in p2_names_in_cache]
    if phase2_to_download:
        print(f"  Phase 2 需下載 {len(phase2_to_download)} 個套件")
        for pkg in phase2_to_download:
            new_files = _download_one_package(pkg, wheels_dir)
            extract_manifest.update(new_files)
    else:
        print("  Phase 2 全部已緩存")

    # Phase 2 cache-hit 加入 manifest
    p2_names_set = {_norm_pkg_name(d) for d in extra_deps_no_deps}
    for f in wheels_dir.glob("*.*"):
        if _pkg_name_from_filename(f.name) in p2_names_set:
            extract_manifest.add(f)

    # 延伸 stale-cleanup：移除不在本次 manifest 的 cache 檔（防 cache 無限長大）
    orphan_removed = 0
    for f in list(wheels_dir.glob("*.*")):
        if f not in extract_manifest:
            f.unlink()
            orphan_removed += 1
    if orphan_removed:
        print(f"  清除 {orphan_removed} 個 cache orphan（不在本次 manifest）")

    # ── 防禦性 dedup：每個套件名最多一個檔案進 extract_manifest ──
    # 理論上 stale-cleanup + 版本 pin 已排除重複；此 pass 作為不變式驗證，
    # 防止任何路徑（cache 污染 / 未來程式碼改動）讓兩個不同版本都進入解壓，
    # 否則先寫的被後寫的覆蓋（last-writer-wins corruption）。
    deduped: dict[str, Path] = {}  # 標準化套件名 → 保留的檔案
    for f in sorted(extract_manifest, key=lambda x: x.name):  # 排序讓結果確定
        pkg = _pkg_name_from_filename(f.name)
        if pkg not in deduped:
            deduped[pkg] = f
        else:
            # 若有重複，保留版本號較大者（字串比較對 SemVer 大多數情況足夠）
            existing_stem = deduped[pkg].stem
            if existing_stem.endswith(".tar"):
                existing_stem = existing_stem[:-4]
            new_stem = f.stem
            if new_stem.endswith(".tar"):
                new_stem = new_stem[:-4]
            existing_ver = existing_stem.split("-")[1] if "-" in existing_stem else ""
            new_ver = new_stem.split("-")[1] if "-" in new_stem else ""
            kept, dropped = (f, deduped[pkg]) if new_ver > existing_ver else (deduped[pkg], f)
            deduped[pkg] = kept
            print(
                f"  [WARNING] manifest 含同套件兩個版本（{pkg}）："
                f" 捨棄 {dropped.name}，保留 {kept.name}"
            )
    if len(deduped) < len(extract_manifest):
        extract_manifest = set(deduped.values())

    # ── 解壓：只提取 manifest 內的檔案（不 glob 整個 cache） ──
    print("\n[4/6] 安裝套件到 site-packages...")
    wheel_files = [f for f in extract_manifest if f.suffix == ".whl"]
    tar_files = [f for f in extract_manifest if f.name.endswith(".tar.gz")]
    print(f"  Manifest: {len(wheel_files)} 個 wheel, {len(tar_files)} 個 tar.gz")

    for wheel_file in sorted(wheel_files, key=lambda f: f.name):
        print(f"  安裝: {wheel_file.name}")
        extract_wheel(wheel_file, site_packages)

    for tar_file in sorted(tar_files, key=lambda f: f.name):
        print(f"  安裝: {tar_file.name}")
        extract_tar_gz(tar_file, site_packages)

    # 保留緩存（wheels_dir 只含本次 manifest 需要的套件）


def copy_project_files():
    """複製專案檔案"""
    print("\n[5/6] 複製專案檔案...")

    app_dir = BUILD_DIR / "OpenAver" / "app"
    app_dir.mkdir(parents=True)

    for item in COPY_ITEMS:
        src = PROJECT_ROOT / item
        dst = app_dir / item

        if src.is_dir():
            print(f"  複製目錄: {item}")
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".git", ".gitignore", "config.json"
            ))
        elif src.is_file():
            print(f"  複製檔案: {item}")
            shutil.copy2(src, dst)

    # 複製 config.default.json（預設設定範本）
    # 注意：不複製 config.json，讓目標環境保留自己的設定
    config_default_src = PROJECT_ROOT / "web" / "config.default.json"
    config_default_dst = app_dir / "web" / "config.default.json"
    if config_default_src.exists():
        shutil.copy2(config_default_src, config_default_dst)
        print("  複製檔案: config.default.json")

    # 複製範例檔案到根目錄（讓用戶容易找到）
    samples_src = PROJECT_ROOT / "tests" / "samples" / "basic"
    samples_dst = BUILD_DIR / "OpenAver" / "教學檔案"
    if samples_src.exists():
        shutil.copytree(samples_src, samples_dst)
        print("  複製目錄: 教學檔案 (11 個範例)")


def create_launcher_scripts():
    """建立啟動腳本和說明檔（純英文版本，避免 Big5 編碼地雷字問題）"""
    print("  建立啟動腳本...")

    root_dir = BUILD_DIR / "OpenAver"

    # OpenAver.bat - 正常啟動（顯示啟動提示）
    bat_content = '''@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
echo ==============================
echo    OpenAver Starting...
echo ==============================
echo.
start "" "python\\pythonw.exe" "app\\windows\\standalone.py"
ping -n 2 127.0.0.1 >nul
'''

    # OpenAver_Debug.bat - 偵錯模式（顯示控制台）
    # 使用純英文避免 Big5 地雷字問題（誌、誤、訊、回、將、以、下、置、上 等字會導致亂碼）
    debug_bat_content = '''@echo off
echo ======================================
echo    OpenAver Debug Mode
echo ======================================
echo.

REM Force UTF-8 encoding and detailed error output
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set PYWEBVIEW_LOG=debug
set OPENAVER_DEBUG=1

echo [INFO] Starting OpenAver (Debug Mode)...
echo [INFO] Log location: %USERPROFILE%\\OpenAver\\logs\\debug.log
echo.

cd /d "%~dp0"
"python\\python.exe" "app\\windows\\standalone.py"

if errorlevel 1 (
    echo.
    echo ======================================
    echo [ERROR] Startup failed!
    echo ======================================
    echo.
    echo Please report to GitHub Issues:
    echo 1. Error messages above
    echo 2. Log file: %USERPROFILE%\\OpenAver\\logs\\debug.log
    echo.
)

pause
'''

    readme_en = '''===============================================
  OpenAver Windows Setup Guide
===============================================

Option 1: One-Line Install (Recommended)

  Open PowerShell (search "PowerShell" -> Enter), paste:

  irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex

  After install, double-click the OpenAver shortcut on your desktop.

===============================================

Option 2: Manual Install

  !! IMPORTANT: Use 7-Zip or WinRAR to extract !!
  Windows built-in extraction keeps "Mark of the Web",
  which blocks the app from running.

[Step 1] Extract ZIP
  - Right-click ZIP -> "Extract All..." (use 7-Zip or WinRAR for best results)

[Step 2] Open Command Prompt in the folder
  - Shift + right-click inside the OpenAver folder
  - Select "Open PowerShell window here" or "Open command window here"

[Step 3] Launch
  OpenAver.bat

  If you already extracted with Windows built-in:
  Right-click the ZIP -> Properties -> check "Unblock" -> OK,
  then re-extract.

[Requirements]
- Windows 10/11 64-bit
- Microsoft Edge WebView2 Runtime
  https://go.microsoft.com/fwlink/p/?LinkId=2124703
- Internet connection (required on first run to fetch metadata)

[Upgrading]
- Delete %USERPROFILE%\\OpenAver\\python\\ before extracting a new version
- Your settings and logs are preserved automatically

[Startup Scripts]

OpenAver.bat       — Normal launch (runs in background)
OpenAver_Debug.bat — Debug mode, logs to Command Prompt and %USERPROFILE%\\OpenAver\\logs\\debug.log

[Troubleshooting]

If the app won't start, use OpenAver_Debug.bat:
  1. Double-click OpenAver_Debug.bat
  2. A Command Prompt window shows live logs; also saved to %USERPROFILE%\\OpenAver\\logs\\debug.log
  3. Attach the log content to your GitHub Issue

[Notes]
- First launch may take a moment
- Config & data: app\\output\\ (config.json, database, covers, thumbnails — preserved across updates)
  (Full path example: C:\\Users\\YourName\\OpenAver\\app\\output\\)
- Logs: %USERPROFILE%\\OpenAver\\logs\\debug.log

[Report Issues]
GitHub: https://github.com/slive777/OpenAver/issues
Telegram: https://t.me/+J-U2l96gv0FjZTBl
'''

    readme_zh = '''===============================================
  OpenAver Windows 安裝指南
===============================================

方法一：一行指令安裝（推薦）

  打開 PowerShell（搜尋 PowerShell → Enter），貼上：

  irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex

  安裝完成後雙擊桌面上的 OpenAver 捷徑啟動。

===============================================

方法二：手動安裝

  !! 重要：請使用 7-Zip 或 WinRAR 解壓 !!
  Windows 內建解壓縮會保留「網路標記」(Mark of the Web)，
  導致程式無法正常執行。

[步驟 1] 解壓 ZIP
  - 對 ZIP 按右鍵 → 「解壓縮全部...」（建議使用 7-Zip 或 WinRAR）

[步驟 2] 在資料夾中開啟命令提示字元
  - Shift + 右鍵點擊 OpenAver 資料夾內部空白處
  - 選擇「在此開啟 PowerShell 視窗」或「在此開啟命令視窗」

[步驟 3] 啟動程式
  OpenAver.bat

  如果已經用內建解壓縮：
  對 ZIP 按右鍵 → 內容 → 勾選「解除封鎖」→ 確定，
  再重新解壓。

[系統需求]
- Windows 10/11 64-bit
- Microsoft Edge WebView2 Runtime
  https://go.microsoft.com/fwlink/p/?LinkId=2124703
- 網路連線（首次執行需連線外部服務取得資料）

[升級注意]
- 升級前請先刪除 %USERPROFILE%\\OpenAver\\python\\ 資料夾
- 設定檔和記錄檔會自動保留

[啟動腳本說明]

OpenAver.bat       — 正常啟動（程式在背景運行）
OpenAver_Debug.bat — 調試模式，命令提示字元顯示完整日誌，同時輸出到 %USERPROFILE%\\OpenAver\\logs\\debug.log

[故障排除]

如果程式無法啟動，請使用 OpenAver_Debug.bat 查看詳細日誌：
  1. 雙擊 OpenAver_Debug.bat
  2. 命令提示字元視窗會即時顯示日誌，同時寫入 %USERPROFILE%\\OpenAver\\logs\\debug.log
  3. 將日誌內容附加到 GitHub Issue

[注意事項]
- 首次啟動可能較慢
- 資料與設定：app\\output\\（設定檔、資料庫、封面、縮圖都在這裡，更新時原封不動）
  （完整路徑範例：C:\\Users\\你的帳號\\OpenAver\\app\\output\\）
- 記錄檔：%USERPROFILE%\\OpenAver\\logs\\debug.log

[回報問題]
GitHub: https://github.com/slive777/OpenAver/issues
Telegram: https://t.me/+J-U2l96gv0FjZTBl
'''

    (root_dir / "OpenAver.bat").write_text(bat_content, encoding='ascii')
    (root_dir / "OpenAver_Debug.bat").write_text(debug_bat_content, encoding='ascii')
    (root_dir / "README.txt").write_text(readme_en, encoding='utf-8')
    (root_dir / "README_zh.txt").write_text(readme_zh, encoding='utf-8')

    print("  Created: OpenAver.bat, OpenAver_Debug.bat, README.txt, README_zh.txt")


def get_directory_size(path):
    """計算目錄大小"""
    total = sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())
    return total


def optimize_package():
    """優化打包體積：清理 __pycache__ / .egg-info

    注意：**不刪 .dist-info** —— curl_cffi 等套件在 import 當下讀自身 metadata
    （importlib.metadata），dist-info 缺失會拋 PackageNotFoundError 導致 released
    版該功能靜默失效（spec-97 根因）。全保留代價壓縮後僅 ~0.5MB。"""
    print("\n[5.5/6] 優化打包體積...")

    app_dir = BUILD_DIR / "OpenAver"
    size_before = get_directory_size(app_dir)

    # 1. 清理 __pycache__ 資料夾
    pycache_count = 0
    pycache_size = 0
    for pycache in app_dir.rglob("__pycache__"):
        if pycache.is_dir():
            size = sum(f.stat().st_size for f in pycache.rglob('*') if f.is_file())
            pycache_size += size
            shutil.rmtree(pycache)
            pycache_count += 1

    if pycache_count > 0:
        print(f"  刪除 {pycache_count} 個 __pycache__ 資料夾，節省 {pycache_size / 1024 / 1024:.2f} MB")

    # 2. 刪除 .egg-info 資料夾
    egg_info_count = 0
    egg_info_size = 0
    for egg_info in app_dir.rglob("*.egg-info"):
        if egg_info.is_dir():
            size = sum(f.stat().st_size for f in egg_info.rglob('*') if f.is_file())
            egg_info_size += size
            shutil.rmtree(egg_info)
            egg_info_count += 1

    if egg_info_count > 0:
        print(f"  刪除 {egg_info_count} 個 .egg-info 資料夾，節省 {egg_info_size / 1024 / 1024:.2f} MB")

    # 統計優化結果
    size_after = get_directory_size(app_dir)
    saved = size_before - size_after
    print(f"  體積優化: {size_before / 1024 / 1024:.1f} MB → {size_after / 1024 / 1024:.1f} MB (節省 {saved / 1024 / 1024:.1f} MB)")


def create_zip_package():
    """打包成 ZIP"""
    print("\n[6/6] 打包成 ZIP...")

    # 讀取版本號
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from core.version import VERSION

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    zip_name = f"OpenAver-v{VERSION}-Windows-x64"
    zip_path = DIST_DIR / f"{zip_name}.zip"

    # 刪除舊的 ZIP
    if zip_path.exists():
        zip_path.unlink()

    # 建立 ZIP
    shutil.make_archive(
        str(DIST_DIR / zip_name),
        'zip',
        BUILD_DIR,
        "OpenAver"
    )

    # 計算檔案大小
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  完成: {zip_path.name} ({size_mb:.1f} MB)")

    return zip_path


def main():
    """主程序"""
    print("=" * 50)
    print("OpenAver Windows 打包工具")
    print("=" * 50)

    try:
        clean_build()
        python_dir = download_embedded_python()
        download_and_install_packages(python_dir)
        copy_project_files()
        create_launcher_scripts()
        optimize_package()
        zip_path = create_zip_package()

        print("\n" + "=" * 50)
        print("打包完成！")
        print(f"輸出檔案: {zip_path}")
        print("=" * 50)

    except Exception as e:
        print(f"\n錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
