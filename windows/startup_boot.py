"""Startup page text, colors, and synchronized boot state."""

import threading

from core.i18n import t
from core.logger import get_logger
from windows.health_probe import STARTUP_TIMEOUT

logger = get_logger(__name__)

THEME_BACKGROUNDS = {
    "light": "#fcfaf6",
    "dim": "#2a303c",
}


def background_color(theme, system_dark=False):
    if theme == "dim" or (theme == "system" and system_dark):
        return THEME_BACKGROUNDS["dim"]
    return THEME_BACKGROUNDS["light"]


def startup_texts(locale):
    try:
        return {
            "starting": t("desktop.startup.starting", locale),
            "message_timeout": t("desktop.startup.message.timeout", locale, seconds=STARTUP_TIMEOUT),
            "message_died": t("desktop.startup.message.died", locale),
            "message_no_port": t("desktop.startup.message.no_port", locale),
            "hint": t("desktop.startup.hint", locale),
            "log_label": t("desktop.startup.log_label", locale),
            "open_log": t("desktop.startup.open_log", locale),
            "close": t("desktop.startup.close", locale),
        }
    except Exception as e:
        logger.warning(f"[startup_boot] startup texts failed ({type(e).__name__})")
        return {}


class BootState:
    def __init__(self, locale, theme, log_path):
        self._lock = threading.Lock()
        with self._lock:
            self._phase = "starting"
            self._quitting = False
            self._navigation_claimed = False
            self._error = None
            self._error_polled = False
            self._theme = theme if theme in ("light", "dim", "system") else "system"
            self._log_path = log_path
            self._texts = startup_texts(locale)

    @property
    def phase(self):
        with self._lock:
            return self._phase

    @property
    def quitting(self):
        with self._lock:
            return self._quitting

    @property
    def error(self):
        with self._lock:
            return self._error

    @property
    def error_polled(self):
        with self._lock:
            return self._error_polled

    def mark_ready(self):
        with self._lock:
            if self._quitting or self._phase == "error":
                return False
            self._phase = "ready"
            return True

    def set_error(self, kind, detail=""):
        with self._lock:
            if self._quitting or self._phase != "starting":
                return False
            self._phase = "error"
            self._error = (kind if kind in ("timeout", "died", "no_port") else "died", detail)
            return True

    def request_quit(self):
        with self._lock:
            if self._phase == "ready":
                return False
            self._quitting = True
            return True

    def claim_navigation(self):
        with self._lock:
            if self._phase != "starting" or self._quitting or self._navigation_claimed:
                return False
            self._navigation_claimed = True
            return True

    def get_state(self):
        with self._lock:
            if self._phase == "error":
                self._error_polled = True
            kind, detail = self._error if self._error is not None else (None, "")
            return {"phase": self._phase, "kind": kind, "detail": detail,
                    "theme": self._theme, "log_path": self._log_path, "texts": dict(self._texts)}
