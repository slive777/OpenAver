"""In-flight generate registry — lets the settings mode-switch refuse while a
`GET /api/gallery/generate` SSE is still running (feature/90 Finding 2 guard).

Why this exists: `switch_external_manager` purges the offline sources' DB cards.
If a readonly `generate` is streaming at the same time, its background producer
thread keeps `_upsert_db`-ing the same readonly rows *after* the purge deletes
them → the "switch mode = clean" contract breaks. The generate handler registers
a unique token for its lifetime; the switch endpoint refuses while any token is
active.

Bidirectional mutex (PR #93 Codex P1): the original guard only blocked switch while
a generate was *already* registered. But a generate that *starts* during the switch's
purge/config-mutation window (after switch's entry check, before it finishes) would
register, read the still-old readonly sources, and `_upsert_db` the just-purged rows
back → cards leak despite the guard. So the switch now holds `_switch_active` for its
WHOLE window (`try_begin_switch` → `end_switch`), and generate's registration
(`try_mark_generate_active`) refuses while a switch is active. Both operations are
atomic under the same `_lock`, so neither direction can slip through.

Thread-safety: `generate()` (async handler / event loop) registers and clears;
`switch_external_manager` (sync def → threadpool) begins/ends the switch. A plain
`threading.Lock` serialises across both. Tokens are the per-request `cancel_event`
objects (unique by identity), so add/discard are idempotent and never collide.

⚠️ Known residual (documented, owner-accepted): the token is cleared in the
disconnect watcher's `finally`, which fires the instant a client disconnect is
detected — the producer thread may process *one more file* before it observes
`should_abort` at the next per-file checkpoint. So a switch fired in that sub-second
window right after a disconnect could still race a single re-insert. This is far
smaller than the original unbounded race and is not perfect serialisation by design.
"""
import threading

_lock = threading.Lock()
_active_tokens: set = set()
_switch_active = False  # True while switch_external_manager is mid-purge (PR #93 P1)


def mark_generate_active(token) -> None:
    """Register a generate as in-flight (call at handler start, before producing).

    Deprecated in favour of `try_mark_generate_active` (which also honours an
    in-progress switch); kept for any caller/test that only needs registration.
    """
    with _lock:
        _active_tokens.add(token)


def try_mark_generate_active(token) -> bool:
    """Atomically register a generate UNLESS a switch is currently in progress.

    Returns False (caller must refuse to start) when `switch_external_manager` holds
    the window — prevents the producer re-inserting rows the switch is purging (P1).
    """
    with _lock:
        if _switch_active:
            return False
        _active_tokens.add(token)
        return True


def try_begin_switch():
    """Atomically begin a switch UNLESS a generate OR another switch is in-flight.

    Returns None on success (switch owns the exclusion window until `end_switch()`;
    new generates are refused meanwhile). Otherwise returns a refusal-reason string
    the caller surfaces to the frontend:
    - 'generate_in_progress' — a generate SSE is registered (original forward guard).
    - 'switch_in_progress'   — another switch already holds the window (PR #93 P2):
      without this, a 2nd overlapping switch would enter, and the 1st's `end_switch()`
      would clear `_switch_active` mid-2nd-window → a generate could slip in and
      re-upsert purged rows. Switches must serialise, not just exclude generates.
    """
    global _switch_active
    with _lock:
        if _active_tokens:
            return 'generate_in_progress'
        if _switch_active:
            return 'switch_in_progress'
        _switch_active = True
        return None


def end_switch() -> None:
    """Release the switch exclusion window (call from switch's `finally`)."""
    global _switch_active
    with _lock:
        _switch_active = False


def is_switch_in_progress() -> bool:
    """True while switch_external_manager holds the purge window (PR #93).

    Read-only getter — lets other config writers (e.g. the full-config save
    `PUT /api/config`) refuse during the sub-second switch window so a stale
    client snapshot can't rewrite the just-purged offline-source entries back.
    """
    with _lock:
        return _switch_active


def mark_generate_done(token) -> None:
    """Clear a generate token (idempotent; call from the watcher `finally` so it
    runs on BOTH normal-completion and client-disconnect paths)."""
    with _lock:
        _active_tokens.discard(token)


def is_generate_in_progress() -> bool:
    """True if any generate SSE is currently registered as in-flight."""
    with _lock:
        return bool(_active_tokens)
