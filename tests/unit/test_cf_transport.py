"""
Unit tests for core/cf_transport.py — TDD-lite
Tests 6 cases per TASK-70-T1 Test Strategy.
"""
import pytest
import core.cf_transport as m


@pytest.fixture(autouse=True)
def reset_transport():
    """Reset module-level singleton before and after each test to prevent cross-test pollution."""
    m._transport = None
    yield
    m._transport = None


# --- Test 1: register → get round-trip ---

def test_register_get_round_trip():
    """register_cf_transport(impl) → get_cf_transport() returns the same impl."""

    class FakeTransport:
        def begin_solve(self, origin_url: str, cache_key: str) -> None: ...
        def is_ready(self, cache_key: str) -> bool: return True
        def fetch(self, url: str, cache_key: str) -> str: return ""

    impl = FakeTransport()
    m.register_cf_transport(impl)
    assert m.get_cf_transport() is impl


# --- Test 2: get returns None when never registered ---

def test_get_returns_none_when_unregistered():
    """get_cf_transport() returns None when register_cf_transport() was never called."""
    assert m.get_cf_transport() is None


# --- Test 3: CfTransportUnavailable is a RuntimeError subclass ---

def test_cf_transport_unavailable_is_runtime_error():
    """CfTransportUnavailable inherits RuntimeError and can be raised/caught."""
    assert issubclass(m.CfTransportUnavailable, RuntimeError)

    with pytest.raises(m.CfTransportUnavailable):
        raise m.CfTransportUnavailable("transport not initialized")

    # Also catchable as RuntimeError
    with pytest.raises(RuntimeError):
        raise m.CfTransportUnavailable("transport not initialized")


# --- Test 4: CfChallengeRequired is a RuntimeError subclass ---

def test_cf_challenge_required_is_runtime_error():
    """CfChallengeRequired inherits RuntimeError and can be raised/caught."""
    assert issubclass(m.CfChallengeRequired, RuntimeError)

    with pytest.raises(m.CfChallengeRequired):
        raise m.CfChallengeRequired("CF challenge page returned")

    # Also catchable as RuntimeError
    with pytest.raises(RuntimeError):
        raise m.CfChallengeRequired("CF challenge page returned")


# --- Test 5: duck-type Protocol structural check ---

def test_protocol_duck_type_structural():
    """An object with begin_solve/is_ready/fetch can be registered and retrieved (Protocol structural subtyping)."""

    class DuckTransport:
        def begin_solve(self, origin_url: str, cache_key: str) -> None:
            pass

        def is_ready(self, cache_key: str) -> bool:
            return False

        def fetch(self, url: str, cache_key: str) -> str:
            return "<html></html>"

    duck = DuckTransport()
    m.register_cf_transport(duck)
    retrieved = m.get_cf_transport()
    assert retrieved is duck
    # Verify the duck-typed methods are accessible through the retrieved reference
    assert retrieved.is_ready("javlibrary") is False
    assert retrieved.fetch("http://example.com", "javlibrary") == "<html></html>"


# --- Test 6: repeated register overwrites old impl ---

def test_register_overwrites_previous_impl():
    """Calling register_cf_transport() a second time replaces the previous impl."""

    class ImplA:
        def begin_solve(self, origin_url: str, cache_key: str) -> None: ...
        def is_ready(self, cache_key: str) -> bool: return True
        def fetch(self, url: str, cache_key: str) -> str: return "A"

    class ImplB:
        def begin_solve(self, origin_url: str, cache_key: str) -> None: ...
        def is_ready(self, cache_key: str) -> bool: return False
        def fetch(self, url: str, cache_key: str) -> str: return "B"

    impl_a = ImplA()
    impl_b = ImplB()

    m.register_cf_transport(impl_a)
    assert m.get_cf_transport() is impl_a

    m.register_cf_transport(impl_b)
    assert m.get_cf_transport() is impl_b
    assert m.get_cf_transport() is not impl_a
