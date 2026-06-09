# core/cf_transport.py
"""
Platform-agnostic CF transport abstraction seam.

Provides a Protocol interface, two exception types, and module-level
register/get functions so scraper code can call WebView-based CF fetching
without importing anything from ``windows/``.

DI chain (plan-70b §1.1):
  windows/cf_transport_impl.py  →  implements CfTransport
  standalone.py startup          →  calls register_cf_transport()
  dev launcher.py                →  never calls register → get returns None
                                    → scraper raises CfTransportUnavailable
"""
from typing import Protocol, Optional


class CfTransportUnavailable(RuntimeError):
    """CF transport is not initialised in this environment (dev/server).

    User-visible meaning: JavLibrary 僅限桌面應用程式（standalone）可用。
    Scrapers should catch this and surface a friendly message rather than a
    raw traceback.
    """


class CfChallengeRequired(RuntimeError):
    """transport.fetch() received a Cloudflare challenge page instead of content.

    Callers should respond by calling begin_solve() to open the challenge
    window, then poll is_ready() until True, then retry fetch().
    """


class CfTransport(Protocol):
    """Structural protocol for a Cloudflare-capable transport backend.

    Implementations live in ``windows/`` and must not be imported from
    ``core/``.  Consumers depend on this Protocol only.
    """

    def begin_solve(self, origin_url: str, cache_key: str) -> None:
        """**Non-blocking**: display the transport window and navigate to
        *origin_url* so the user can complete the CF challenge + age gate.

        Returns immediately without waiting for the user to finish.
        CD-70b-7: the backend must not hold a thread waiting for the solution.

        *cache_key* is provided for future multi-CF-site expansion
        (currently always ``'javlibrary'``).
        """
        ...

    def is_ready(self, cache_key: str) -> bool:
        """**Non-blocking + fast**: report whether the transport window has
        passed the CF challenge + age gate and is ready to fetch.

        Used by the frontend poll loop.  When this first returns ``True`` the
        host implementation should automatically hide the transport window.
        """
        ...

    def fetch(self, url: str, cache_key: str) -> str:
        """Fetch *url* HTML via a same-origin request inside the transport
        window and return the raw HTML string.

        Raises:
            CfTransportUnavailable: transport is not initialised
                (dev / server environment).
            CfChallengeRequired: fetch completed but the returned HTML is a
                CF challenge page.  Caller should call begin_solve() →
                poll is_ready() → retry fetch().
        """
        ...


_transport: Optional[CfTransport] = None


def register_cf_transport(impl: CfTransport) -> None:
    """Register *impl* as the active CF transport.

    May be called more than once; each call replaces the previous
    registration (idempotent restart semantics for ``standalone.py``).
    """
    global _transport
    _transport = impl


def get_cf_transport() -> Optional[CfTransport]:
    """Return the currently registered CF transport, or ``None`` if none has
    been registered (dev / server environments).
    """
    return _transport
