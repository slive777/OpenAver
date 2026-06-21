"""
LAN Listener Manager — process-level singleton for the optional 0.0.0.0 listener.

Dual-Listener architecture: the main loopback listener (127.0.0.1:local_port) runs
as normal. When server_mode is enabled, this manager starts a second uvicorn Server
on 0.0.0.0:lan_port using lifespan="off" (no double init_db / startup_reconnect).

Thread-safe. Module-level singleton: ``lan_listener``.
"""

import socket
import threading
import time
from typing import Optional

import uvicorn

from core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LAN IP helper
# ---------------------------------------------------------------------------

def get_lan_ip():
    """主要區網 IP（預設路由網卡）；取不到回 None。"""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # 不送資料，只查預設路由本地位址
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        if s is not None:
            s.close()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _find_free_port_lan(
    start_port: int,
    exclude: set,
    logger,  # noqa: ANN001
    max_attempts: int = 100,
) -> int:
    """
    Find a free TCP port by probe-binding ``("0.0.0.0", port)``.

    Skips any port that is in the ``exclude`` set.
    Raises ``RuntimeError`` if no port is found within ``max_attempts``.
    """
    attempts = 0
    port = start_port
    while attempts < max_attempts:
        if port in exclude:
            port += 1
            attempts += 1
            continue

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1)
            sock.bind(("0.0.0.0", port))
            sock.close()
            if logger:
                logger.debug("LAN port allocated: %d", port)
            return port
        except OSError:
            port += 1
            attempts += 1
            if logger:
                logger.debug("LAN port %d unavailable, trying next", port - 1)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:  # noqa: BLE001,S110 — cleanup after port probe; socket close failure is harmless
                    pass

    raise RuntimeError(
        f"_find_free_port_lan: no available port found after {max_attempts} attempts "
        f"(starting at {start_port})"
    )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class LanListenerManager:
    """
    Process-level singleton managing the optional LAN (0.0.0.0) uvicorn listener.

    Lifecycle::

        lan_listener.wire(app, local_port=port)   # once, at standalone startup
        lan_port = lan_listener.start()            # enable server mode
        lan_listener.stop()                        # disable server mode
        lan_listener.shutdown()                    # alias; called at app exit

    Thread-safe via ``threading.Lock``.  ``start()`` and ``stop()`` are idempotent.
    ``lifespan="off"`` ensures ``init_db()`` / ``startup_reconnect()`` are NOT called
    a second time on the LAN listener.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._lan_port: Optional[int] = None
        self._app = None
        self._local_port: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wire(self, app, local_port: int) -> None:  # noqa: ANN001
        """
        Store the ASGI app and loopback port.  Must be called once before ``start()``.
        Typically called from ``standalone.py`` after the loopback listener is ready.
        """
        self._app = app
        self._local_port = local_port

    @property
    def lan_port(self) -> Optional[int]:
        """The port the LAN listener is bound to, or ``None`` if not running."""
        return self._lan_port

    @property
    def is_running(self) -> bool:
        """``True`` if the LAN listener thread is active and has not signalled exit."""
        with self._lock:
            return self._server is not None and not self._server.should_exit

    def start(self, _startup_timeout: float = 5.0) -> int:
        """
        Start the LAN listener on ``0.0.0.0:<lan_port>``.

        Returns the allocated ``lan_port`` on success.  Idempotent: if already
        running, returns the current ``lan_port`` without starting a new server.

        ``_startup_timeout`` is exposed for testing so unit tests can pass a short
        value (e.g. ``0.01``) without waiting the full 5 s.

        Raises:
            RuntimeError: if ``wire()`` has not been called, port allocation fails,
                          or the server does not report ``started`` within the timeout.
        """
        with self._lock:
            # Idempotent: already running
            if self._server is not None and not self._server.should_exit:
                return self._lan_port  # type: ignore[return-value]

            if self._app is None:
                raise RuntimeError(
                    "LanListenerManager.wire() must be called before start(). "
                    "This is expected in dev mode (no standalone.py); "
                    "the toggle endpoint should surface this as a user-visible error."
                )

            # Allocate a free LAN port (exclude the loopback port to avoid collision)
            lan_port = _find_free_port_lan(
                start_port=self._local_port + 1,  # type: ignore[operator]
                exclude={self._local_port},
                logger=logger,
            )

            config = uvicorn.Config(
                self._app,
                host="0.0.0.0",
                port=lan_port,
                lifespan="off",       # CRITICAL: no double init_db / startup_reconnect
                log_level="warning",
                access_log=False,
                proxy_headers=False,  # no reverse proxy; aligns with gate design (I.5)
            )
            server = uvicorn.Server(config)
            thread = threading.Thread(
                target=server.run,
                daemon=True,
                name=f"lan-listener-{lan_port}",
            )
            thread.start()

            # Wait for uvicorn to signal readiness (server.started set in serve())
            deadline = time.monotonic() + _startup_timeout
            while not server.started and not server.should_exit:
                if time.monotonic() > deadline:
                    # Startup timed out — clean up and raise
                    server.should_exit = True
                    thread.join(timeout=2.0)
                    raise RuntimeError(
                        f"LAN listener on port {lan_port} failed to start "
                        f"within {_startup_timeout}s timeout"
                    )
                time.sleep(0.05)

            if server.should_exit:
                # Server exited during startup (e.g. bind failed inside uvicorn)
                thread.join(timeout=2.0)
                raise RuntimeError(
                    f"LAN listener on port {lan_port} exited unexpectedly during startup"
                )

            # Success — store state
            self._server = server
            self._thread = thread
            self._lan_port = lan_port
            logger.info("LAN listener started on 0.0.0.0:%d", lan_port)
            return lan_port

    def stop(self) -> None:
        """
        Stop the LAN listener gracefully.

        Signals ``should_exit``, waits up to 5 s for the thread to finish, then
        falls back to ``force_exit`` + 2 s join.  Idempotent: safe to call when
        the listener is not running.
        """
        with self._lock:
            if self._server is None:
                return  # no-op
            server = self._server
            thread = self._thread
            # Clear internal state while holding the lock so rapid stop/start is safe
            self._server = None
            self._thread = None
            self._lan_port = None

        # Signal + join OUTSIDE the lock (join can block; we must not hold the lock)
        server.should_exit = True
        if thread and thread.is_alive():
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning(
                    "LAN listener thread did not terminate within 5 s; forcing exit"
                )
                server.force_exit = True
                thread.join(timeout=2.0)
                if thread.is_alive():
                    logger.warning("LAN listener thread still alive after force_exit")
        logger.info("LAN listener stopped")

    def shutdown(self) -> None:
        """
        Alias for ``stop()``.  Called from ``standalone.py`` at app exit.
        """
        self.stop()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

lan_listener = LanListenerManager()
