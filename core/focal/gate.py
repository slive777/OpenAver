"""Focal-crop detection gate — precise "requires face detection" verdict.

Ported (verbatim regex/list) from MetaTube common/number gate logic
(archives/metatube-sdk-go/common/number/{number.go,shirouto.go}), but
adapted to act on OpenAver **canonical** `videos.number` + `videos.maker`
instead of raw filenames.

Deliberate divergence from the original port (see
feature/98-focal-crop/TASK-98a-T3.md §⚠️ divergence, Opus-adjudicated):
`trim()` / `_TRIM_*` / `_NUM_ALPHA_RE` are NOT ported. OpenAver canonical
numbers keep leading digits (e.g. `4SSIS-296`, `7IPZ-154`, `3ABW-001`), and
a bare `^\\d+[a-z]+` rule would false-positive real censored numbers into
"requires face detection". Genuine amateur (shirouto) labels are already
covered by `_SHIROUTO_RE`, so dropping the num-alpha rule only trades a
small amount of recall for the precision spec A.6-6 requires (censored
library must stay zero-cost).
"""
import re

from core.scrapers.utils import METATUBE_UNCENSORED

# ---- shirouto (amateur) maker list, verbatim from shirouto.go -------------
_SHIROUTO_LIST = [
    "ara", "bnjc", "dcv", "endx", "eva", "ezd", "gana", "hamenets", "hmdn",
    "hoi", "imdk", "ion", "jac", "jkz", "jotk", "ksko", "luxu", "maan", "mium",
    "mntj", "nama", "ntk", "nttr", "obut", "ore", "orebms", "orec", "oreco",
    "orerb", "oretd", "orex", "per", "pkjd", "scp", "scute", "cute", "shyn",
    "simm", "siro", "srcn", "sqb", "sweet", "svmm", "urf",
]
# Go: shiroutoRe = (?i)(<list>)[-_\d]  -- unanchored search (MatchString).
_SHIROUTO_RE = re.compile(r'(?i)(' + '|'.join(_SHIROUTO_LIST) + r')[-_\d]')

_UNCENSORED_RE = re.compile(
    r'(?i)(\d{4,6}[-_]\d{2,3}|(cz|gedo|k|n|kb|se)\d{2,4}|(heyzo|xxx-av|heydouga|kin8)[-_].+)'
    r'|([hc]0930|h4610|av9898|1000giri)[-_][a-z\d]+$'
)
_FC2_RE = re.compile(r'(?i)^FC2([-_]?PPV)?[-_]?\d+$')
_SPECIAL_RE = re.compile(r'(?i)^(gcolle|getchu|gyutto|pcolle|mywife)[-_]?.+$')

# SSOT: core/scrapers/utils.py METATUBE_UNCENSORED (do not hand-copy).
_UNCENSORED_MAKERS_LC: set[str] = {m.lower() for m in METATUBE_UNCENSORED}


def is_uncensored(s):
    return bool(_UNCENSORED_RE.search(s))


def is_fc2(s):
    return bool(_FC2_RE.match(s))


def is_special(s):
    if is_uncensored(s) or is_fc2(s):
        return True
    return bool(_SPECIAL_RE.match(s))


def requires_face_detection(number: str, maker: str = "") -> bool:
    """Precise "does this need face-aware focal detection" verdict.

    Acts on OpenAver canonical `number` (as stored in `videos.number`) and
    `maker` (as stored in `videos.maker`) — never on filenames, never via
    `trim()`.

    - `number` None/empty -> fall through to maker-whitelist-only check.
    - `maker` None -> treated as "".
    - True if: is_special(number) OR shirouto/amateur label match OR
      maker is in the METATUBE_UNCENSORED whitelist. Else False.
    """
    maker = (maker or "").strip().lower()
    if not number:
        return bool(maker) and maker in _UNCENSORED_MAKERS_LC
    if is_special(number):
        return True
    if _SHIROUTO_RE.search(number):
        return True
    return bool(maker) and maker in _UNCENSORED_MAKERS_LC


def gate_verdict(number: str, maker: str = "") -> tuple[bool, str]:
    """Convenience: (requires_detection, human-readable reason).

    Acts on canonical number+maker (NOT trim(filename)).
    """
    maker_lc = (maker or "").strip().lower()
    if not number:
        if maker_lc and maker_lc in _UNCENSORED_MAKERS_LC:
            return True, 'maker-whitelist'
        return False, 'censored/standard -> right-crop'

    if is_fc2(number):
        return True, 'FC2'
    if is_uncensored(number):
        return True, 'uncensored'
    if _SPECIAL_RE.match(number):
        return True, 'special-maker'
    if _SHIROUTO_RE.search(number):
        return True, 'shirouto/amateur'
    if maker_lc and maker_lc in _UNCENSORED_MAKERS_LC:
        return True, 'maker-whitelist'
    return False, 'censored/standard -> right-crop'
