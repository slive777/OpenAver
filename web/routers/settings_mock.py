"""
Settings Mock router — Visual POC for feature/61-settings-ia-sources B1 (task 61b-1).

Purpose: provide a clickable HTML prototype at `/settings-mock` so the user can
pin down tab IA, source-pill density, and Metatube greyed-area direction before
P3/P4 implementation work begins. Mock data only — no config.json read, no DB
write. Hidden from sidebar nav (CD-61-13); not registered in capabilities.

⚠️ Long-term plan: keep this route until B4 ships as a visual regression
reference; delete with `tools/` after feature/64 (per plan-61 CD-61-13).
"""

from fastapi import APIRouter, Request

from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["settings-mock"])


# 8 builtin sources — order mirrors `core/scraper.py::SCRAPER_CLASSES` + DMM.
# Source of truth for the real feature is `core/source_config.py::get_builtin_sources()`
# (built in P2 task 61a-1). This list is a POC mock only.
#
# `manual_only` is the B1 day-one schema field (design-source-tiers.md v4.2 §2 +
# §5.1 SourceConfig). All builtin sources are False; only B4 javlibrary lands True.
_MOCK_BUILTIN_SOURCES = [
    {"id": "javbus", "name": "JavBus", "is_censored": True, "order": 0, "manual_only": False},
    {"id": "jav321", "name": "Jav321", "is_censored": True, "order": 1, "manual_only": False},
    {"id": "javdb", "name": "JavDB", "is_censored": True, "order": 2, "manual_only": False},
    {"id": "dmm", "name": "DMM", "is_censored": True, "order": 3, "manual_only": False},
    {"id": "d2pass", "name": "D2Pass", "is_censored": False, "order": 4, "manual_only": False},
    {"id": "heyzo", "name": "HEYZO", "is_censored": False, "order": 5, "manual_only": False},
    {"id": "fc2", "name": "FC2", "is_censored": False, "order": 6, "manual_only": False},
    {"id": "avsox", "name": "AVSOX", "is_censored": False, "order": 7, "manual_only": False},
]

# Manual-Only mock — B4 javlibrary preview. In v2 Two-Zone model it sits
# FIXED LAST in the Active Row (Section 2) with a `[BETA]` badge replacing the
# toggle; does NOT count toward cap. See design-source-tiers.v2.md §2.1 + §4.1.
_MOCK_MANUAL_ONLY_SOURCES = [
    {"id": "javlibrary", "name": "JavLibrary",
     "is_censored": True, "order": 99, "manual_only": True, "is_beta": True},
]

# Metatube provider preview — used in viewpoint C "connected preview".
# Names are illustrative for the POC visual only. `recommended=True` surfaces a
# small star hint next to the pill (design-source-tiers.md v4.2 §2 + §9 risk row:
# guides first-time toggle without auto-enabling; epic §2 "控制" axis).
_MOCK_METATUBE_SOURCES = [
    {"id": "mt_fanza", "name": "FANZA", "recommended": True},
    {"id": "mt_mgs", "name": "MGS", "recommended": True},
    {"id": "mt_duga", "name": "DUGA", "recommended": True},
    {"id": "mt_sod", "name": "SOD", "recommended": True},
    {"id": "mt_1pondo", "name": "1Pondo", "recommended": False},
    {"id": "mt_10musume", "name": "10musume", "recommended": False},
    {"id": "mt_caribbeancom", "name": "Caribbeancom", "recommended": False},
    {"id": "mt_heyzo", "name": "HEYZO", "recommended": False},
    {"id": "mt_fc2", "name": "FC2", "recommended": False},
    {"id": "mt_pacopacomama", "name": "Pacopacomama", "recommended": False},
    {"id": "mt_muramura", "name": "Muramura", "recommended": False},
    {"id": "mt_tokyohot", "name": "Tokyo-Hot", "recommended": False},
    {"id": "mt_kin8", "name": "Kin8tengoku", "recommended": False},
    {"id": "mt_naturalhigh", "name": "NaturalHigh", "recommended": False},
    {"id": "mt_xcity", "name": "X-City", "recommended": False},
    {"id": "mt_h4610", "name": "H4610", "recommended": False},
    {"id": "mt_gachinco", "name": "Gachinco", "recommended": False},
    {"id": "mt_javbus", "name": "JavBus", "recommended": False},
    {"id": "mt_arzon", "name": "Arzon", "recommended": False},
    {"id": "mt_avbase", "name": "AVBase", "recommended": False},
    {"id": "mt_aventertainments", "name": "AV-E", "recommended": False},
    {"id": "mt_fc2hub", "name": "FC2Hub", "recommended": False},
    {"id": "mt_jav321", "name": "Jav321", "recommended": False},
    {"id": "mt_javdb", "name": "JavDB", "recommended": False},
    {"id": "mt_njav", "name": "NJav", "recommended": False},
    {"id": "mt_prestige", "name": "Prestige", "recommended": False},
    {"id": "mt_sehuatang", "name": "色花堂", "recommended": False},
    {"id": "mt_tameikegoro", "name": "Tameike Goro", "recommended": False},
    {"id": "mt_xslist", "name": "XsList", "recommended": False},
    {"id": "mt_javlibrary", "name": "JavLibrary", "recommended": False},
]


# Six proposed Settings tabs (CD-61-1).
# id stays single-word; labels here are PLACEHOLDER copy for the mock — final
# i18n keys land in settings.tabs.* at P3 entry.
_MOCK_TABS = [
    {"id": "display", "icon": "bi-palette", "label_key": "settings.mock.tab.display"},
    {"id": "scraping", "icon": "bi-gear", "label_key": "settings.mock.tab.scraping"},
    {"id": "sources", "icon": "bi-collection", "label_key": "settings.mock.tab.sources"},
    {"id": "organize", "icon": "bi-folder", "label_key": "settings.mock.tab.organize"},
    {"id": "translate", "icon": "bi-translate", "label_key": "settings.mock.tab.translate"},
    {"id": "advanced", "icon": "bi-tools", "label_key": "settings.mock.tab.advanced"},
]


@router.get("/settings-mock")
async def settings_mock_page(request: Request):
    """Visual POC for the Settings IA + Source Pills redesign (task 61b-1)."""
    # 延遲 import 避免 circular
    from web.app import get_common_context, templates

    context = get_common_context(request)
    # 故意傳一個不存在於 sidebar 的 page key — base.html `{% if page == ... %}active`
    # 不會 match 任何 nav item，達成 CD-61-13「隱藏於正常導航」的視覺效果。
    context["page"] = "settings-mock"
    context["mock_tabs"] = _MOCK_TABS
    context["mock_builtin_sources"] = _MOCK_BUILTIN_SOURCES
    context["mock_manual_only_sources"] = _MOCK_MANUAL_ONLY_SOURCES
    context["mock_metatube_sources"] = _MOCK_METATUBE_SOURCES
    # Cap=10 — design-source-tiers.v2.md §2.2 (cap basis = enabled && !manual_only;
    # B1 contract core/source_config.py::MAX_ENABLED_SOURCES in P2). Exposed to the
    # template so the magic number lives in one place.
    context["mock_tier1_cap"] = 10
    # Metatube connection mock placeholders — dev-env values per epic §1.6.
    # Safe to expose in this gitignored-from-sidebar POC route (CD-61-13).
    # The "連線" button is a pure Alpine state flip — no real HTTP (decision §2.7).
    context["mock_metatube_url_placeholder"] = "http://192.168.1.177:8080"
    context["mock_metatube_token_placeholder"] = "36885e51a50f...eb944bda"

    return templates.TemplateResponse(request, "settings_mock.html", context)
