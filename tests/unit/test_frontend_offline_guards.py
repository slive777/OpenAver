"""Frontend offline-reliability static guards — feature/79.

CI-effective protection: CI runs pytest only (not eslint/stylelint).
These pytest guards are the load-bearing backstop for things eslint's JS-AST
cannot reach — HTML template markup strings (CDN hosts, beacon endpoints,
<script> tag attributes, colliding id="" attributes) and one cross-module
router↔capabilities contract. eslint `no-restricted-syntax` walks the JS AST
and structurally cannot touch `.html` markup; it can also only *ban* a JS
pattern, never *require* one to exist. Per CLAUDE.md lint-routing rule +
pre-merge.md "eslint structurally cannot cover" exception (plan-79 CD14 / §3),
these stay in pytest.

All guards are pure static analysis (pathlib + re). No app needed
(except guard 4, which imports a router module's constant).
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIGHTBOX_JS = REPO_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"


# ─── Guard 4 ─────────────────────────────────────────────────────────────────

def test_client_log_excluded_from_capabilities():
    """/api/client-log must NOT be disclosed in the capabilities tool list (CD13).

    Cross-module router↔capabilities contract: /api/client-log is a pure diagnostic
    sink (write-only debug.log), not an AI-usable capability, so it must never appear
    in the disclosed _TOOLS list.
    """
    from web.routers.capabilities import _TOOLS

    assert all(t.get("path") != "/api/client-log" for t in _TOOLS), (
        "/api/client-log must NOT be in capabilities _TOOLS — it is a pure "
        "diagnostic sink, not a disclosed capability (CD13)."
    )


# ─── Guard 5 ─────────────────────────────────────────────────────────────────

def test_lightbox_keydown_guards_delete_modal():
    """handleKeydown must keep the C-1 delete-modal guard (deleteVideoModalOpen + cancelDeleteVideo).

    eslint can BAN the presence of a JS pattern but cannot REQUIRE one to exist → pytest.
    Isolates the handleKeydown(e) body and asserts it references BOTH
    deleteVideoModalOpen AND cancelDeleteVideo: this is the guard that makes Esc close
    only the delete-confirm modal (not the lightbox) and stops arrow keys from
    navigating to the next video while the modal is open. If the guard is deleted,
    Esc closes the lightbox underneath and arrows leak through.
    """
    content = LIGHTBOX_JS.read_text(encoding="utf-8")
    body_m = re.search(r"handleKeydown\s*\(\s*e\s*\)\s*\{(.*?)\n        \}",
                       content, re.DOTALL)
    scope = body_m.group(1) if body_m else content
    assert "deleteVideoModalOpen" in scope, (
        "state-lightbox.js handleKeydown must reference deleteVideoModalOpen (C-1 guard)"
    )
    assert "cancelDeleteVideo" in scope, (
        "state-lightbox.js handleKeydown must call cancelDeleteVideo (C-1 guard)"
    )
