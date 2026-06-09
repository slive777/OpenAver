"""
Standalone init-order AST 守衛（CD-70c-1 + CD-70c-2 Layer 1 防回退）

確保 windows/standalone.py 中：
  (a) register_cf_transport(...) 與 JL webview.create_window(...) 不在 main() 內
      的 startup FunctionDef 中（AST walk 確認）
  (b) register_cf_transport(...) 與 JL webview.create_window(...) 出現在 main()
      body 且 lineno < min(webview.start lineno)
  (c) jl_win.events.closing += _on_jl_closing 綁定存在，且 _on_jl_closing body
      含 jl_win.hide() + return False（CD-70c-2 Layer 1 close-intercept 不被靜默移除）
  (d) anti-rot: startup FunctionDef 仍存在於 main() 中（rename/move 使守衛響亮失敗）

Mirror 慣例來自 tests/integration/test_async_offload_guard.py：
  Path.read_text() + ast.parse, NO import of the target module; plain pytest class.
"""
import ast
import pathlib
from typing import Optional

STANDALONE_PATH = pathlib.Path(__file__).parents[2] / "windows" / "standalone.py"


# ──────────────────────────────────────────────────────────────
# AST 工具
# ──────────────────────────────────────────────────────────────

def _find_main_func(tree: ast.Module) -> Optional[ast.FunctionDef]:
    """Find the module-level `main` FunctionDef."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    return None


def _find_startup_in_main(main_node: ast.FunctionDef) -> Optional[ast.FunctionDef]:
    """Find the `startup` FunctionDef nested inside main()."""
    for node in ast.walk(main_node):
        if isinstance(node, ast.FunctionDef) and node.name == "startup":
            return node
    return None


def _is_webview_start_call(call: ast.Call) -> bool:
    """True iff call is `webview.start(...)` (not `server_thread.start()` etc.)."""
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "start"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "webview"
    )


def _is_webview_create_window_call(call: ast.Call) -> bool:
    """True iff call is `webview.create_window(...)` (not e.g. `win.create_window`)."""
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "create_window"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "webview"
    )


def _is_jl_create_window_call(call: ast.Call) -> bool:
    """
    True iff call is the JL webview.create_window(...), identified by ANY of:
      - first positional string arg contains 'JavLibrary'
      - keyword hidden=True is present
      - second positional arg is ast.Name(id='JAVLIBRARY_ORIGIN')
    """
    if not _is_webview_create_window_call(call):
        return False
    # Check first positional arg for 'JavLibrary' in the string
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        if "JavLibrary" in call.args[0].value:
            return True
    # Check for hidden=True keyword
    for kw in call.keywords:
        if kw.arg == "hidden" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    # Check second positional arg is Name(id='JAVLIBRARY_ORIGIN')
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Name) and call.args[1].id == "JAVLIBRARY_ORIGIN":
        return True
    return False


def _is_register_cf_transport_call(call: ast.Call) -> bool:
    """True iff call is `register_cf_transport(...)`."""
    return isinstance(call.func, ast.Name) and call.func.id == "register_cf_transport"


def _collect_calls_in_node(node: ast.AST) -> list[ast.Call]:
    """Collect all Call nodes under node (via ast.walk)."""
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _collect_direct_calls_in_main_body(main_node: ast.FunctionDef) -> list[ast.Call]:
    """
    Collect all Call nodes that appear in main()'s body, NOT descending into
    nested FunctionDef or AsyncFunctionDef nodes (i.e., not into startup()).

    This matches the surface-level body of main() only.
    """
    calls: list[ast.Call] = []

    def _walk(nodes):
        for child in nodes:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # do not descend into nested functions (e.g. startup)
            if isinstance(child, ast.Call):
                calls.append(child)
            _walk(ast.iter_child_nodes(child))

    _walk(ast.iter_child_nodes(main_node))
    return calls


def _find_func_def(node: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    """Find a FunctionDef with the given name anywhere under node (ast.walk)."""
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def _is_jl_closing_augassign(node: ast.AST) -> bool:
    """
    True iff node is: jl_win.events.closing += _on_jl_closing
    i.e. AugAssign(
        target=Attribute(attr='closing', value=Attribute(attr='events', value=Name(id='jl_win'))),
        op=Add(),
        value=Name(id='_on_jl_closing'),
    )
    """
    if not isinstance(node, ast.AugAssign):
        return False
    if not isinstance(node.op, ast.Add):
        return False
    if not isinstance(node.value, ast.Name) or node.value.id != "_on_jl_closing":
        return False
    target = node.target
    if not (
        isinstance(target, ast.Attribute)
        and target.attr == "closing"
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "events"
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "jl_win"
    ):
        return False
    return True


# ──────────────────────────────────────────────────────────────
# Guard tests
# ──────────────────────────────────────────────────────────────

class TestStandaloneInitOrderGuard:
    """CD-70c-1 + CD-70c-2 Layer 1: structural ordering guard for standalone.py."""

    @staticmethod
    def _parse() -> tuple[ast.Module, str]:
        src = STANDALONE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(STANDALONE_PATH))
        return tree, src

    def test_anti_rot_startup_still_exists_in_main(self):
        """
        Anti-rot: startup FunctionDef must still exist inside main().
        If startup is renamed or removed, this guard fails loudly instead of
        silently passing with 0 assertions.
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() FunctionDef not found in standalone.py"
        startup_node = _find_startup_in_main(main_node)
        assert startup_node is not None, (
            "startup() FunctionDef not found inside main() — "
            "if it was renamed, update this guard too"
        )

    def test_register_cf_transport_not_inside_startup(self):
        """
        (a) register_cf_transport(...) must NOT be inside startup() — it must be
        in main() body (before webview.start) to avoid SSR registration race.
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"
        startup_node = _find_startup_in_main(main_node)
        assert startup_node is not None, "startup() not found inside main()"

        calls_in_startup = _collect_calls_in_node(startup_node)
        violations = [c for c in calls_in_startup if _is_register_cf_transport_call(c)]
        assert not violations, (
            f"register_cf_transport() found inside startup() at line(s) "
            f"{[c.lineno for c in violations]} — "
            "it must be moved to main() body BEFORE webview.start() (CD-70c-1)"
        )

    def test_jl_create_window_not_inside_startup(self):
        """
        (a) JL webview.create_window(...) must NOT be inside startup() — only the
        main OpenAver window create_window (at module top-level of main) is allowed
        before startup. The second create_window (JL) must be in main() body too.
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"
        startup_node = _find_startup_in_main(main_node)
        assert startup_node is not None, "startup() not found inside main()"

        calls_in_startup = _collect_calls_in_node(startup_node)
        wv_creates_in_startup = [c for c in calls_in_startup if _is_webview_create_window_call(c)]
        assert not wv_creates_in_startup, (
            f"webview.create_window() found inside startup() at line(s) "
            f"{[c.lineno for c in wv_creates_in_startup]} — "
            "JL create_window must be in main() body BEFORE webview.start() (CD-70c-1)"
        )

    def test_register_cf_transport_before_webview_start(self):
        """
        (b) register_cf_transport(...) must appear in main() body AND its lineno
        must be < min lineno of all webview.start(...) calls.
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"

        direct_calls = _collect_direct_calls_in_main_body(main_node)

        register_calls = [c for c in direct_calls if _is_register_cf_transport_call(c)]
        start_calls = [c for c in direct_calls if _is_webview_start_call(c)]

        assert register_calls, (
            "register_cf_transport() not found in main() body — "
            "must be present before webview.start() (CD-70c-1)"
        )
        assert start_calls, (
            "webview.start() not found in main() body — "
            "guard cannot verify ordering (unexpected refactor?)"
        )

        min_register_line = min(c.lineno for c in register_calls)
        min_start_line = min(c.lineno for c in start_calls)
        assert min_register_line < min_start_line, (
            f"register_cf_transport() (line {min_register_line}) must appear "
            f"BEFORE webview.start() (line {min_start_line}) in main() (CD-70c-1)"
        )

    def test_jl_create_window_before_webview_start(self):
        """
        (b) The JL-specific webview.create_window(...) (identified by 'JavLibrary' in
        first arg, hidden=True keyword, or JAVLIBRARY_ORIGIN as second positional arg)
        must appear in main() body with lineno < min lineno of any webview.start(...).

        Fix (P2): previously used min() over ALL create_window calls, which always
        picked the main OpenAver window (always before webview.start) and would NOT
        catch moving the JL create to after webview.start(). Now we pin specifically
        to the JL create call. (CD-70c-1)
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"

        direct_calls = _collect_direct_calls_in_main_body(main_node)
        jl_create_calls = [c for c in direct_calls if _is_jl_create_window_call(c)]
        start_calls = [c for c in direct_calls if _is_webview_start_call(c)]

        assert len(jl_create_calls) == 1, (
            f"Expected exactly 1 JL webview.create_window() call in main() body "
            f"(identified by 'JavLibrary' title / hidden=True / JAVLIBRARY_ORIGIN), "
            f"found {len(jl_create_calls)} — guard cannot verify ordering (CD-70c-1)"
        )
        assert start_calls, "webview.start() not found in main() body"

        jl_create_line = jl_create_calls[0].lineno
        min_start_line = min(c.lineno for c in start_calls)
        assert jl_create_line < min_start_line, (
            f"JL webview.create_window() (line {jl_create_line}) must appear "
            f"BEFORE webview.start() (line {min_start_line}) in main() (CD-70c-1)"
        )

    def test_jl_events_closing_binding_and_handler(self):
        """
        (c) CD-70c-2 Layer 1 anti-regression: assert the JL-specific close-intercept
        is structurally intact (not just that 'events.closing' appears somewhere).

        Fix (P3): previously a bare string match — keeping window.events.closing
        while DELETING jl_win.events.closing += _on_jl_closing would still pass.
        Now asserts via AST:
          1. An AugAssign `jl_win.events.closing += _on_jl_closing` exists in main().
          2. A `def _on_jl_closing` FunctionDef exists in main().
          3. _on_jl_closing body contains a call to jl_win.hide().
          4. _on_jl_closing body contains `return False` (Constant value is False,
             checked with `is False` to avoid 0 == False pitfall). (CD-70c-2)
        """
        tree, src = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"

        # Sanity: source still has events.closing somewhere (fast human-readable check)
        assert "events.closing" in src, (
            "standalone.py missing events.closing entirely — "
            "CD-70c-2 Layer 1 close-intercept was removed (should not be)"
        )

        # 1. Assert jl_win.events.closing += _on_jl_closing AugAssign exists
        jl_closing_bindings = [
            n for n in ast.walk(main_node) if _is_jl_closing_augassign(n)
        ]
        assert len(jl_closing_bindings) == 1, (
            f"Expected exactly 1 `jl_win.events.closing += _on_jl_closing` AugAssign "
            f"in main(), found {len(jl_closing_bindings)} — "
            "JL close-intercept binding is missing or was renamed (CD-70c-2)"
        )

        # 2. Assert def _on_jl_closing exists inside main()
        handler_def = _find_func_def(main_node, "_on_jl_closing")
        assert handler_def is not None, (
            "def _on_jl_closing not found inside main() — "
            "JL close-intercept handler is missing or was renamed (CD-70c-2)"
        )

        # 3. Assert _on_jl_closing body contains jl_win.hide() call
        handler_calls = _collect_calls_in_node(handler_def)
        jl_hide_calls = [
            c for c in handler_calls
            if (
                isinstance(c.func, ast.Attribute)
                and c.func.attr == "hide"
                and isinstance(c.func.value, ast.Name)
                and c.func.value.id == "jl_win"
            )
        ]
        assert jl_hide_calls, (
            "jl_win.hide() call not found in _on_jl_closing body — "
            "close-intercept must call jl_win.hide() to prevent window destruction (CD-70c-2)"
        )

        # 4. Assert _on_jl_closing body contains `return False`
        #    Use `value is False` (not == False) to avoid 0 == False pitfall.
        return_false_nodes = [
            n for n in ast.walk(handler_def)
            if (
                isinstance(n, ast.Return)
                and isinstance(n.value, ast.Constant)
                and n.value.value is False
            )
        ]
        assert return_false_nodes, (
            "`return False` not found in _on_jl_closing body — "
            "close-intercept must return False to cancel the close event (CD-70c-2)"
        )

    def test_on_main_closing_destroys_jl_win(self):
        """
        B1 guard (TASK-70c-B): _on_main_closing must call jl_win.destroy() after
        setting quitting=True, so the hidden JL window is reaped when the main window
        closes. Without this, pywebview only exits when instances==0, but the hidden
        JL window keeps the instance list non-empty → process hangs (zombie).

        AST: find the _on_main_closing FunctionDef inside main(), walk it, assert
        a Call with func.attr=='destroy' and func.value.id=='jl_win'.
        """
        tree, _ = self._parse()
        main_node = _find_main_func(tree)
        assert main_node is not None, "main() not found"

        handler_def = _find_func_def(main_node, "_on_main_closing")
        assert handler_def is not None, (
            "def _on_main_closing not found inside main() — "
            "B1 zombie-process fix requires _on_main_closing (standalone.py)"
        )

        # Walk _on_main_closing body for a Call: jl_win.destroy(...)
        handler_calls = _collect_calls_in_node(handler_def)
        jl_destroy_calls = [
            c for c in handler_calls
            if (
                isinstance(c.func, ast.Attribute)
                and c.func.attr == "destroy"
                and isinstance(c.func.value, ast.Name)
                and c.func.value.id == "jl_win"
            )
        ]
        assert jl_destroy_calls, (
            "jl_win.destroy() call not found in _on_main_closing body — "
            "B1 fix: must destroy the hidden JL window on app close so pywebview "
            "can reach instances==0 and exit cleanly (TASK-70c-B)"
        )
