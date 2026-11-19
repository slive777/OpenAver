import re
from pathlib import Path

from windows.startup_boot import BootState, THEME_BACKGROUNDS, background_color, startup_texts


def test_startup_texts_never_blank_or_key_name():
    keys = {"starting", "message_timeout", "message_died", "message_no_port",
            "hint", "log_label", "open_log", "close"}
    for locale in ("zh-TW", "ja", "en", "ko", "zh-CN", "xx-YY"):
        texts = startup_texts(locale)
        assert set(texts) == keys
        assert all(isinstance(value, str) and value.strip() and not value.startswith("[")
                   for value in texts.values())
        assert "{" not in texts["message_timeout"]
    assert startup_texts("xx-YY") == startup_texts("zh-TW")


def test_page_css_background_matches_color_table():
    html = (Path(__file__).resolve().parents[2] / "windows/offline/startup.html").read_text()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    media = re.search(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(.*?)\n\}", css, re.S)
    assert media is not None
    outside = css[:media.start()] + css[media.end():]
    for theme, source, expected in (
        ("light", outside, THEME_BACKGROUNDS["light"]),
        ("dim", outside, THEME_BACKGROUNDS["dim"]),
        ("system", outside, THEME_BACKGROUNDS["light"]),
        ("system", media.group(1), THEME_BACKGROUNDS["dim"]),
    ):
        rule = re.search(r':root\[data-theme="' + theme + r'"\]\s*\{([^}]*)\}', source)
        assert rule is not None
        color = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})\b", rule.group(1))
        assert color is not None
        assert color.group(1).lower() == expected.lower()
    assert background_color("light") == THEME_BACKGROUNDS["light"]
    assert background_color("dim") == THEME_BACKGROUNDS["dim"]
    assert background_color("system", system_dark=False) == THEME_BACKGROUNDS["light"]
    assert background_color("system", system_dark=True) == THEME_BACKGROUNDS["dim"]


def test_boot_error_state_reaches_page_poll():
    boot = BootState("zh-TW", "system", "log.txt")
    assert boot.get_state()["phase"] == "starting"
    assert boot.error_polled is False
    assert boot.set_error("timeout", "x") is True
    assert boot.error_polled is False
    state = boot.get_state()
    assert (state["phase"], state["kind"], state["detail"]) == ("error", "timeout", "x")
    assert boot.error_polled is True
    assert boot.mark_ready() is False
    assert boot.set_error("died") is False
    assert boot.phase == "error"
    assert boot.claim_navigation() is False

    starting = BootState("zh-TW", "system", "log.txt")
    assert starting.claim_navigation() is True
    assert starting.claim_navigation() is False

    quitting = BootState("zh-TW", "system", "log.txt")
    assert quitting.request_quit() is True
    assert quitting.claim_navigation() is False
