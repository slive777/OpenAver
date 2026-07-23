"""
test_filter_files_inaccessible.py — P2-T6（spec-107 功能 D）

filter-files 的 `rejected.inaccessible` 桶：把「無讀權限（PermissionError）＋未掛載/UNC
（啟發式）」與「檔案真的不存在（not_found）」分流，讓桌面拖入存取不到的 Windows 檔時能顯示
正確訊息（前端 path_inaccessible）而非誤導的「無法識別番號」。

涵蓋：
- `_looks_unmounted_drive` 純函式全分支（mock is_mount 決定性）。
- 端點 stat-early：PermissionError→inaccessible、FileNotFoundError+未掛載→inaccessible、
  FileNotFoundError+已掛載/非 mnt→not_found、SMB ValueError→inaccessible。
- **min_size_mb=0 預設下仍 stat**（原 bug：預設不 stat 則權限/未掛載無從判別）。
- 既有 filter-files 零回歸。
- 故障注入 mutation 自驗（見各測試 docstring）。
"""
import pytest
from pathlib import Path

from web.routers.search import _looks_unmounted_drive, _filter_files_sync


class TestLooksUnmountedDrive:
    """純函式：路徑外觀啟發式（mock is_mount 決定性，不依賴真實 /mnt 狀態）"""

    def test_mnt_letter_unmounted_true(self, monkeypatch):
        """/mnt/<letter>/… 且該碟未掛載（is_mount=False）→ True（存取不到）"""
        monkeypatch.setattr(Path, "is_mount", lambda self: False)
        assert _looks_unmounted_drive("/mnt/z/lan/video.mp4") is True

    def test_mnt_letter_mounted_false(self, monkeypatch):
        """/mnt/<letter>/… 但該碟已掛載（is_mount=True）→ False（檔案真缺 = not_found，不誤報）"""
        monkeypatch.setattr(Path, "is_mount", lambda self: True)
        assert _looks_unmounted_drive("/mnt/c/foo/missing.mp4") is False

    def test_local_unix_path_false(self, monkeypatch):
        """一般本地 Unix 路徑（非 /mnt/<letter>）→ False（真的不存在歸 not_found）"""
        # is_mount 不該被呼叫（regex 先短路），但仍 mock 防萬一
        monkeypatch.setattr(Path, "is_mount", lambda self: True)
        assert _looks_unmounted_drive("/home/me/no_number.mp4") is False

    def test_windows_native_drive_false(self, monkeypatch):
        """Windows 原生 `Z:\\…`（非 /mnt/<letter> 形狀）→ False（dev-only 不涵蓋 Windows 原生）"""
        monkeypatch.setattr(Path, "is_mount", lambda self: False)
        assert _looks_unmounted_drive("Z:\\lan\\video.mp4") is False

    def test_mnt_multichar_not_matched(self, monkeypatch):
        """/mnt/wsl、/mnt/nas 等多字元掛載名不符 `/mnt/<單字母>` → False（不誤判系統掛載）"""
        monkeypatch.setattr(Path, "is_mount", lambda self: False)
        assert _looks_unmounted_drive("/mnt/nas/share/video.mp4") is False


class TestFilterFilesInaccessible:
    """端點層：rejected.inaccessible 分流（透過 _filter_files_sync 直呼，繞過 asyncio）"""

    def _mock_stat_raise(self, monkeypatch, target: str, exc):
        """只對 target 路徑的 Path.stat 拋 exc，其餘走原生（is_file/is_mount 內部 stat 不受影響）"""
        original_stat = Path.stat

        def fake_stat(self_path, *args, **kwargs):
            if str(self_path) == target:
                raise exc
            return original_stat(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", fake_stat)

    def test_permission_error_to_inaccessible(self, tmp_path, monkeypatch):
        """stat PermissionError → inaccessible（非 not_found）。
        mutation：把 `except PermissionError` 分支拿掉 → 落 OSError→not_found，本測試轉紅。
        min_size_mb 為 config 預設（0），本測試同時證明**預設下仍 stat**（否則永不觸發權限例外）。"""
        mp4 = tmp_path / "PERM-001.mp4"
        mp4.write_bytes(b"x")
        self._mock_stat_raise(monkeypatch, str(mp4), PermissionError("denied"))

        result = _filter_files_sync([str(mp4)])
        assert result["rejected"]["inaccessible"] == 1
        assert result["rejected"]["not_found"] == 0
        assert result["files"] == []

    def test_unmounted_drive_to_inaccessible(self, tmp_path, monkeypatch):
        """stat FileNotFoundError + 路徑像未掛載碟（/mnt/z、is_mount=False）→ inaccessible。
        mutation：把 `_looks_unmounted_drive(path)` 換成常數 False → 落 not_found，本測試轉紅。"""
        target = "/mnt/z/lan/UNMOUNTED-001.mp4"
        self._mock_stat_raise(monkeypatch, target, FileNotFoundError("no such"))
        monkeypatch.setattr(Path, "is_mount", lambda self: False)  # /mnt/z 未掛載

        result = _filter_files_sync([target])
        assert result["rejected"]["inaccessible"] == 1
        assert result["rejected"]["not_found"] == 0

    def test_genuinely_missing_local_to_not_found(self, tmp_path, monkeypatch):
        """stat FileNotFoundError + 一般本地路徑（非 /mnt/<letter>）→ not_found（不誤報存取問題）。"""
        target = str(tmp_path / "genuinely_missing.mp4")  # 不建立
        # is_mount 任意（regex 先短路），確保決定性
        monkeypatch.setattr(Path, "is_mount", lambda self: True)

        result = _filter_files_sync([target])
        assert result["rejected"]["not_found"] == 1
        assert result["rejected"]["inaccessible"] == 0

    def test_mounted_missing_file_to_not_found(self, tmp_path, monkeypatch):
        """已掛載碟上檔案真缺（/mnt/c/…、is_mount=True）→ not_found（啟發式不誤報）。"""
        target = "/mnt/c/foo/MOUNTED-MISSING.mp4"
        self._mock_stat_raise(monkeypatch, target, FileNotFoundError("no such"))
        monkeypatch.setattr(Path, "is_mount", lambda self: True)  # /mnt/c 已掛載

        result = _filter_files_sync([target])
        assert result["rejected"]["not_found"] == 1
        assert result["rejected"]["inaccessible"] == 0

    def test_smb_unc_value_error_to_inaccessible(self):
        """SMB/UNC 路徑 → normalize_path 拋 ValueError → inaccessible（WSL 與純 Linux 皆拋 ValueError）。
        mutation：把 `except ValueError` 改回記 not_found → 本測試轉紅。"""
        result = _filter_files_sync(["\\\\server\\share\\video.mp4"])
        assert result["rejected"]["inaccessible"] == 1
        assert result["rejected"]["not_found"] == 0

    def test_valid_file_passes_no_regression(self, tmp_path):
        """既有行為零回歸：可存取的 mp4 → 進 files、inaccessible=0。"""
        mp4 = tmp_path / "ABC-001.mp4"
        mp4.write_bytes(b"fake video")

        result = _filter_files_sync([str(mp4)])
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == str(mp4)
        assert result["rejected"]["inaccessible"] == 0
        assert result["rejected"]["not_found"] == 0

    def test_total_rejected_includes_inaccessible(self, tmp_path, monkeypatch):
        """total_rejected = sum(rejected.values()) 自動含 inaccessible（前端計數依賴）。"""
        mp4 = tmp_path / "PERM.mp4"
        mp4.write_bytes(b"x")
        self._mock_stat_raise(monkeypatch, str(mp4), PermissionError("denied"))

        result = _filter_files_sync([str(mp4)])
        assert result["total_rejected"] == 1
        assert result["total_rejected"] == sum(result["rejected"].values())
