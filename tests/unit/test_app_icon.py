"""殼程式圖示：依平台挑對圖檔；圖檔缺席時回 None（pywebview 退回預設圖示，不影響啟動）。"""
from pathlib import Path

from PIL import Image

from windows import app_icon

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_icon_path_picks_platform_format(monkeypatch):
    monkeypatch.setattr(app_icon.sys, "platform", "win32")
    assert app_icon.icon_path(REPO_ROOT).endswith("openaver.ico")
    monkeypatch.setattr(app_icon.sys, "platform", "darwin")
    assert app_icon.icon_path(REPO_ROOT).endswith("openaver.icns")


def test_icon_path_missing_file_returns_none(tmp_path):
    assert app_icon.icon_path(tmp_path) is None


def test_windows_ico_uses_bmp_frames_with_small_and_large_sizes():
    """pywebview winforms 以 System.Drawing.Icon 載入且未包 try：BMP 圖格最保守；16px 與 256px 都要在。"""
    ico = REPO_ROOT / "web" / "static" / "openaver.ico"
    with Image.open(ico) as image:
        sizes = image.info["sizes"]
    assert {(16, 16), (32, 32), (256, 256)} <= set(sizes)
    data = ico.read_bytes()
    count = int.from_bytes(data[4:6], "little")
    for k in range(count):
        offset = int.from_bytes(data[6 + 16 * k + 12:6 + 16 * k + 16], "little")
        assert data[offset:offset + 4] != b"\x89PNG", f"frame {k} is PNG-compressed"


def test_set_windows_app_id_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(app_icon.sys, "platform", "linux")
    app_icon.set_windows_app_id()   # 不得拋、不得碰 ctypes.windll
