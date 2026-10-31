"""
T1e Tests — Fix-1 版本標記測試
測試 core/organizer.py 的 _detect_suffixes(), format_string(), organize_file()
"""
import errno
import io
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests
from PIL import Image

from core.organizer import _detect_suffixes, format_string, organize_file, crop_to_poster, generate_nfo, extract_chinese_title, download_image, truncate_to_chars, _detect_vr_cluster, _poster_window_ratio, generate_jellyfin_images
import core.organizer as organizer
from core.focal.subprocess_runner import RunnerOutcome
from tests.conftest import MOCK_FOCAL_XY


# ============ _detect_suffixes() 測試 ============

class TestDetectSuffixes:
    """_detect_suffixes() 的單元測試"""


    def test_detect_suffixes_case_insensitive(self):
        """大小寫不敏感：SONE-205-4k.mp4 應匹配 -4K（關鍵字大寫）"""
        result = _detect_suffixes("SONE-205-4k.mp4", ["-4K"])
        assert result != ""
        assert "-4k" in result


# ============ format_string() 測試 ============


class TestFormatStringDateVariables:
    """format_string() {year}/{month}/{day}/{date} 變數展開測試"""


    def test_filename_format_ymd_full_date(self):
        """{year}-{month}-{day} + 完整 date → 展開 "2015-06-01"""
        result = format_string("{year}-{month}-{day}", {"date": "2015-06-01"})
        assert result == "2015-06-01"


# ============ organize_file() 整合測試 ============

def _make_config(tmp_path: Path, suffix_keywords=None) -> dict:
    """建立測試用 config dict，使用 tmp_path 作為輸出目錄"""
    if suffix_keywords is None:
        suffix_keywords = ["-cd1", "-cd2", "-4k", "-uc"]
    return {
        "create_folder": False,           # 測試時不建子資料夾，簡化路徑計算
        "filename_format": "[{num}] {title}{suffix}",
        "download_cover": False,          # 不真正下載封面
        "cover_filename": "poster.jpg",
        "create_nfo": False,              # 不生成 NFO，避免依賴
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": suffix_keywords,
    }


def _make_metadata(number: str = "SONE-205", title: str = "Test Title") -> dict:
    """建立測試用 metadata dict"""
    return {
        "number": number,
        "title": title,
        "actors": [],
        "tags": [],
        "maker": "S1",
        "date": "2024-01-15",
        "cover": "",   # 空字串，跳過下載
        "url": "",
    }


class TestOrganizeDuplicateDetection:
    """organize_file() 覆蓋偵測測試"""


    def test_organize_duplicate_detection(self, tmp_path):
        """
        目標路徑已存在時：
        - result['duplicate'] == True
        - result['success'] == False
        - 原始檔案未被覆蓋（兩個檔案都應存在）
        """
        # 建立原始檔案
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"source content")

        # 建立目標同名檔案（模擬已存在）
        # format_string 會產生 "[SONE-205] Test Title" -> 去掉 suffix（空）
        # create_folder=False，所以目標在同一目錄
        target_file = tmp_path / "[SONE-205] Test Title.mp4"
        target_file.write_bytes(b"existing content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        result = organize_file(str(src_file), metadata, config)

        assert result.get("duplicate") is True
        assert result["success"] is False
        # 原始檔案應仍存在（未被移動）
        assert src_file.exists(), "原始檔案不應被移動或刪除"
        # 目標檔案內容不應被覆蓋
        assert target_file.read_bytes() == b"existing content"
        assert result.get("duplicate_target") == "[SONE-205] Test Title.mp4"

    def test_organize_suffix_in_filename(self, tmp_path):
        """
        CD1 和 CD2 兩個檔案分別 organize 後應產生不同目標路徑。
        """
        # 建立 CD1 檔案
        cd1_file = tmp_path / "SONE-205-CD1.mp4"
        cd1_file.write_bytes(b"cd1 content")

        # 建立 CD2 檔案
        cd2_file = tmp_path / "SONE-205-CD2.mp4"
        cd2_file.write_bytes(b"cd2 content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        result1 = organize_file(str(cd1_file), metadata, config)
        result2 = organize_file(str(cd2_file), metadata, config)

        assert result1["success"] is True, f"CD1 organize 失敗：{result1.get('error')}"
        assert result2["success"] is True, f"CD2 organize 失敗：{result2.get('error')}"

        # 兩個輸出路徑應不同
        assert result1["new_filename"] != result2["new_filename"], \
            "CD1 和 CD2 產生了相同的目標路徑"

        # CD1 應帶 -cd1 後綴，CD2 應帶 -cd2 後綴
        assert "-cd1" in Path(result1["new_filename"]).name
        assert "-cd2" in Path(result2["new_filename"]).name


class TestOrganizeAtomicReplace:
    """organize_file() 原子佔位與 os.replace 移動測試（TASK-144-T0）"""

    def test_organize_file_uses_os_replace_for_video(self, tmp_path):
        """
        DoD-3: 搬移改用 os.replace，且不得退化成整份複製
        - 正向：os.replace 被呼叫恰好一次，且參數為 (file_path, target_path)
        - 反向 A：shutil.move 的所有呼叫中，沒有任何一次的第一個參數是 file_path
        - 反向 B：shutil.copy2 的所有呼叫中，沒有任何一次的第一個參數是 file_path
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"video content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        with patch("core.atomic_write.os.replace", wraps=os.replace) as spy_replace, \
             patch("core.organizer.shutil.move", wraps=shutil.move) as spy_move, \
             patch("core.organizer.shutil.copy2", wraps=shutil.copy2) as spy_copy2, \
             patch("core.atomic_write.shutil.copy2", wraps=shutil.copy2) as spy_prim_copy2:
            result = organize_file(str(src_file), metadata, config)

        assert result["success"] is True
        target_path = result["new_filename"]

        # 正向：os.replace 被呼叫恰好一次，且參數為 (str(src_file), target_path)
        assert spy_replace.call_count == 1
        assert spy_replace.call_args == ((str(src_file), target_path),)

        # 反向 A：shutil.move 的所有呼叫中，沒有任何一次的第一個參數是 str(src_file)
        for call_item in spy_move.call_args_list:
            assert call_item[0][0] != str(src_file), "shutil.move 不得以影片來源檔作為參數"

        # 反向 B：shutil.copy2 的所有呼叫中，沒有任何一次的第一個參數是 str(src_file)
        # organizer 側（generate_jellyfin_images 的 fanart 是正常呼叫，故比對來源而非次數）
        for call_item in spy_copy2.call_args_list:
            assert call_item[0][0] != str(src_file), "shutil.copy2 不得以影片來源檔作為參數"
        # primitive 側：EXDEV fallback 才會走 copy2，同檔案系統的正常路徑一次都不該碰
        for call_item in spy_prim_copy2.call_args_list:
            assert call_item[0][0] != str(src_file), (
                "同檔案系統的正常路徑不得走 atomic_move 的 EXDEV copy2 fallback"
            )

    def test_organize_file_exdev_fallback_reraises_non_exdev_errors(self, tmp_path):
        """
        DoD-4: 非 EXDEV 的 OSError 必須原樣往外拋（不被 copy2 fallback 吞掉）
        mock os.replace 拋 OSError(ENOSPC)，不應走 copy2 fallback，結果為失敗
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"video content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        non_exdev_err = OSError(errno.ENOSPC, "No space left on device")

        with patch("core.atomic_write.os.replace", side_effect=non_exdev_err), \
             patch("core.atomic_write.shutil.copy2", wraps=shutil.copy2) as spy_copy2:
            result = organize_file(str(src_file), metadata, config)

        assert result["success"] is False
        assert result["error"] == "檔案整理失敗，請查看日誌"
        for call_item in spy_copy2.call_args_list:
            assert call_item[0][0] != str(src_file), "非 EXDEV 錯誤不得走 copy2 fallback"

    def test_organize_file_exdev_fallback_success(self, tmp_path):
        """
        DoD-4 正向: os.replace 拋 OSError(errno.EXDEV) 時，
        走 shutil.copy2 + os.unlink fallback，整理成功。
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"video content for exdev")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        exdev_err = OSError(errno.EXDEV, "Invalid cross-device link")

        with patch("core.atomic_write.os.replace", side_effect=exdev_err), \
             patch("core.atomic_write.shutil.copy2", wraps=shutil.copy2) as spy_copy2, \
             patch("core.atomic_write.os.unlink", wraps=os.unlink) as spy_unlink:
            result = organize_file(str(src_file), metadata, config)

        assert result["success"] is True
        target_path = Path(result["new_filename"])
        assert target_path.exists()
        assert target_path.read_bytes() == b"video content for exdev"
        assert not src_file.exists(), "來源檔應在 fallback 後被 unlink"
        assert any(c[0][0] == str(src_file) for c in spy_copy2.call_args_list)
        assert any(c[0][0] == str(src_file) for c in spy_unlink.call_args_list)

    def test_organize_file_replace_permission_error_falls_to_outer_except(self, tmp_path):
        """
        DoD-1 (BE-ENV-01 / CD-181-3): os.replace 拋 PermissionError（Windows 影片被占用）
        → 整理失敗、落既有外層 except；本次自己佔下的 0 KB 佔位檔被收回，
        關掉播放器再整理一次就成功（不再永遠「目標已存在」）。
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"video content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        perm_err = PermissionError("Access is denied (simulated Windows AV lock)")

        with patch("core.atomic_write.os.replace", side_effect=perm_err):
            result = organize_file(str(src_file), metadata, config)

        assert result["success"] is False
        assert result["error"] == "檔案整理失敗，請查看日誌"
        assert src_file.read_bytes() == b"video content", "來源檔案應原封不動"
        expected_target = tmp_path / "[SONE-205] Test Title.mp4"
        assert not expected_target.exists(), "本次自建的 0 KB 佔位檔應被收回"

        # 取消注入（with 區塊外）再整理一次 → 成功
        retry = organize_file(str(src_file), metadata, config)
        assert retry["success"] is True
        assert expected_target.read_bytes() == b"video content"

    @pytest.mark.parametrize("existing", [b"", b"old residue"], ids=["zero_bytes", "with_content"])
    def test_organize_file_duplicate_keeps_preexisting_target(self, tmp_path, existing):
        """
        DoD-2 (R1): 目標夾裡原有的檔（含 0 bytes 舊殘留）→ duplicate，
        根本沒建佔位檔，存在性與 bytes 都不得被整理動作改動。
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"video content")
        target_file = tmp_path / "[SONE-205] Test Title.mp4"
        target_file.write_bytes(existing)
        baseline = target_file.read_bytes()

        result = organize_file(str(src_file), _make_metadata(), _make_config(tmp_path))

        assert result.get("duplicate") is True
        assert target_file.exists()
        assert target_file.read_bytes() == baseline
        assert src_file.read_bytes() == b"video content"

    def test_organize_file_move_failure_after_source_gone_keeps_target(self, tmp_path):
        """
        DoD-2b (R1): 影片已搬到 target 之後才拋例外、且影片是 0 KB
        → target 是唯一一份，不得刪（來源已不在原路徑）。
        """
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"")
        target_file = tmp_path / "[SONE-205] Test Title.mp4"
        real_replace = os.replace

        def replace_then_fail(src, dest, *a, **kw):
            real_replace(src, dest, *a, **kw)
            raise OSError("late failure after move")

        with patch("core.atomic_write.os.replace", side_effect=replace_then_fail):
            result = organize_file(str(src_file), _make_metadata(), _make_config(tmp_path))

        assert result["success"] is False
        assert not src_file.exists()
        assert target_file.exists(), "唯一一份影片不得被當佔位檔刪掉"


class TestOrganizeTruncateSuffix:
    """organize_file() 長標題時 suffix 不應被截斷"""

    def test_suffix_not_truncated_by_max_chars(self, tmp_path):
        """
        長標題超過 max_filename_length 時，suffix 仍應保留。
        例：max_filename_length=30，title 很長，suffix="-cd1" 不應被截掉。
        """
        # 建立檔案
        src = tmp_path / "SONE-205-CD1.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}][{maker}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 40,  # 故意很短，迫使截斷
            "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
        }
        metadata = {
            "number": "SONE-205",
            "title": "超級無敵長的標題名稱會被截斷但後綴應該保留",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        new_name = Path(result["new_filename"]).name
        # suffix -cd1 必須在檔名中保留
        assert "-cd1" in new_name, f"suffix -cd1 被截斷: {new_name}"


class TestOrganizeFallback:
    """organize_file() fallback 資料夾建立與 used_fallbacks 欄位測試"""


    def test_organize_used_fallbacks_field(self, tmp_path):
        # actors=[], date="" + create_folder=True + folder 含 {actor}/{year}
        # → used_fallbacks 包含 ['女優', '日期']
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{actor}", "{year}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": [], "tags": [], "maker": "S1",
            "date": "", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert result["used_fallbacks"] == ["女優", "日期"]


    def test_organize_fallback_amateur_no_actress(self, tmp_path):
        """素人片（CHN-180）有 title/maker/date 但無演員 — 僅女優觸發 fallback"""
        src = tmp_path / "CHN-180.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{actor}"],
            "filename_format": "[{num}][{maker}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "CHN-180",
            "title": "新・素人娘、お貸しします。 VOL.83",
            "actors": [],
            "tags": ["素人", "美乳"],
            "maker": "プレステージ",
            "date": "2023-05-12",
            "cover": "",
            "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        # 僅女優觸發 fallback（maker/date/title 都有值）
        assert result["used_fallbacks"] == ["女優"]
        # 資料夾名為 fallback 值
        folder_name = Path(result["new_folder"]).name
        assert folder_name == "未知女優"
        # 檔名不含 fallback（檔名不啟用 fallback）
        filename_only = Path(result["new_filename"]).name
        assert "未知女優" not in filename_only
        # 檔名包含片商（有值，正常顯示）
        assert "プレステージ" in filename_only


# ============ organize_file() 錯誤處理測試 (T4 安全修正) ============

class TestOrganizeErrorHandling:
    """organize_file() 錯誤訊息安全性測試 — 確認固定訊息，不洩漏內部細節"""

    def test_permission_error_returns_fixed_message(self, tmp_path):
        """
        os.makedirs 拋出 PermissionError 時：
        - result['success'] == False（保持預設值）
        - result['error'] 是固定中文訊息，不含 traceback 或 exception 字串
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": True,
            "folder_layers": ["{actor}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": ["三上悠亞"],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        with patch("core.organizer.os.makedirs", side_effect=PermissionError("access denied")):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"] == "無法建立資料夾，請確認目標路徑的寫入權限"
        # 確認不含原始 exception 字串（安全規範）
        assert "access denied" not in (result["error"] or "")
        assert "PermissionError" not in (result["error"] or "")


    def test_general_exception_returns_fixed_message(self, tmp_path):
        """
        shutil.move 拋出一般 Exception 時：
        - result['success'] == False（保持預設值）
        - result['error'] 是固定訊息 '檔案整理失敗，請查看日誌'，不含原始 exception 字串
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        secret_msg = "internal disk error XYZ-9999"
        with patch("core.atomic_write.os.replace", side_effect=OSError(secret_msg)):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"] == "檔案整理失敗，請查看日誌"
        # 確認不含原始 exception 字串（安全規範）
        assert secret_msg not in (result["error"] or "")
        assert "OSError" not in (result["error"] or "")

    def test_normalize_path_error_no_leak(self, tmp_path):
        """
        normalize_path 拋出 ValueError 時：
        - result['error'] 為固定中文訊息，不含原始路徑細節
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        with patch("core.organizer.normalize_path",
                   side_effect=ValueError(r"WSL 環境不支援 SMB 路徑: \\192.168.1.177\share")):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert "192.168.1.177" not in (result["error"] or "")
        assert result["error"] == "路徑格式不支援，請確認路徑設定"


# ============ Jellyfin 圖片模式測試 (Fix-6) ============

def _make_test_image(tmp_path, width, height, name="cover.jpg"):
    """建立指定尺寸的純色 JPEG 測試圖片"""
    img_path = tmp_path / name
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    img.save(str(img_path), "JPEG")
    return img_path


def _make_alias_or_skip(link_type: str, real_path: str, alias_path: str) -> None:
    """在 real_path 之外，於 alias_path 建立指向同一份檔案的 hardlink／symlink。

    Codex PR review P1（feature/112a-T2c）：`cover_path`（DB 路徑映射）與
    `poster_path` / `fanart_path`（lexical stem 拼出）之間沒有「不得
    symlink／hardlink」的保證，字串不相等但可能是同一個 inode。這裡動態
    （非 `pytest.mark.skipif`）建立別名——只在當前平台/檔案系統真的無法建立
    時才 skip（例如 Windows CI 缺 symlink 權限），確保能建立的環境（本機
    Linux/WSL）一定會真的跑到鎖，不會被誤判性地靜態跳過。
    """
    try:
        if link_type == "hardlink":
            os.link(real_path, alias_path)
        elif link_type == "symlink":
            os.symlink(real_path, alias_path)
        else:
            raise ValueError(f"unknown link_type: {link_type}")
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"{link_type} 在當前環境無法建立，略過: {e}")


def _mock_download_image_write_jpeg(url, save_path, referer=''):
    """Mock download_image：寫出一個 800x538 JPEG 到 save_path（標準橫向封面尺寸）"""
    img = Image.new("RGB", (800, 538), color=(200, 100, 50))
    img.save(save_path, "JPEG")
    return True


def _make_jellyfin_config(jellyfin_mode):
    # T4 遷移：image block 改由 external_manager 控制；jellyfin_mode=True → 'jellyfin'
    return {
        "create_folder": False,
        "filename_format": "[{num}] {title}",
        "download_cover": True,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": [],
        "external_manager": "jellyfin" if jellyfin_mode else "off",
    }


class TestGenerateJellyfinImagesPosterSameFileShortCircuit:
    """P0-2d（TASK-112-T2c，最重要格）：crop_to_poster(cover, poster) 在 src==dst
    （cover_path 本身就是 `<stem>-poster.jpg`，外部庫 MDCX/Javinizer 常見情境）時必須
    視為成功且完全不執行裁切——絕不可就地覆寫使用者原檔（prd.md 技術決策 #6 承重牆）。
    """

    def test_poster_same_file_reports_success_no_inplace_crop(self, tmp_path):
        base_stem = str(tmp_path / "ABC-123")
        cover = base_stem + "-poster.jpg"
        # 800x538 橫向，若真的被裁切，尺寸會變成 379x538（見卡片 repro 記錄）
        _make_test_image(tmp_path, 800, 538, "ABC-123-poster.jpg")

        before_bytes = Path(cover).read_bytes()
        before_mtime = Path(cover).stat().st_mtime
        with Image.open(cover) as img:
            before_size = img.size

        result = generate_jellyfin_images(cover, base_stem)

        assert result["poster"] is True
        assert result["poster_path"] == base_stem + "-poster.jpg"

        # ① bytes 完全不變 ② mtime 完全不變 ③ 尺寸完全不變
        assert Path(cover).read_bytes() == before_bytes
        assert Path(cover).stat().st_mtime == before_mtime
        with Image.open(cover) as img:
            after_size = img.size
        assert after_size == before_size == (800, 538)


class TestGenerateJellyfinImagesSamefileUnknownErrorNeverDestroysOriginal:
    """Codex PR review 第三輪 P1（2026-08-04）：**`SameFileError` 不能取代 preflight**。

    背景：review 過程中曾把 fanart 側的 `same_target_verdict` preflight 拿掉，改成
    「直接 `copy2`，用 `except shutil.SameFileError` 承接同檔」。那個簡化看起來
    更乾淨（無預先探測 → 無 TOCTOU），但**只在 `os.path.samefile()` 成功辨識出
    同檔時才成立**。

    `shutil.copyfile` 是靠 `shutil._samefile()` 判同檔，而後者
    （`/usr/lib/python3.12/shutil.py:214`）對 `os.path.samefile` 的**任何 `OSError`
    一律吞掉並回傳 `False`**——於是 `copyfile` 認為「不同檔」照常往下走，以 `'wb'`
    開啟 dst。dst 若是 src 的 hardlink／symlink，那一開就**截斷了共用的 inode**，
    接著從已被清空的 src 複製 0 bytes。

    實測（本測試即該重現的固化版）：hardlink 別名 + `samefile` 拋
    `PermissionError` → 封面 **7427 bytes → 0 bytes**，而回傳值仍是 `fanart: True`。
    **比 poster 側的就地裁切更嚴重——那是尺寸變小，這是整份資料歸零。**

    因此 fanart 側必須保留 `same_target_verdict` preflight（它對未知 `OSError`
    fail-closed 回 True，寧可少產一張衍生圖也不寫），`SameFileError` 只是
    preflight 之後才變成同檔的 race backstop。

    mutation 判準：把 fanart 的 `if same_target_verdict(...)` preflight 拿掉、只留
    `try/except SameFileError` → **本支須單獨轉紅**（其他別名鎖因為 `samefile`
    正常運作而仍會綠——那正是它們抓不到這條的原因）。
    """

    def _make_cover_with_hardlinked_fanart(self, tmp_path):
        cover = tmp_path / 'ABC-123.jpg'
        Image.new('RGB', (800, 538), (9, 9, 9)).save(str(cover))
        fanart = tmp_path / 'ABC-123-fanart.jpg'
        # P3-4（pre-merge Stage 2 review）：改用姊妹測試共用的 _make_alias_or_skip，
        # 不支援 hardlink 的檔案系統走 skip 而非直接 error。
        _make_alias_or_skip("hardlink", str(cover), str(fanart))
        return cover, fanart

    def test_samefile_unknown_oserror_must_not_truncate_shared_inode(
        self, tmp_path, monkeypatch
    ):
        """`samefile` 拋未知 OSError 時，同 inode 的封面原檔不得被截斷。"""
        cover, fanart = self._make_cover_with_hardlinked_fanart(tmp_path)
        before_bytes = cover.read_bytes()
        before_size = len(before_bytes)
        assert before_size > 0
        assert os.path.samefile(str(cover), str(fanart))

        def _raise_permission(*args, **kwargs):
            raise PermissionError('simulated network share / permission error')

        monkeypatch.setattr(os.path, 'samefile', _raise_permission)

        generate_jellyfin_images(
            str(cover), str(tmp_path / 'ABC-123'), number='ABC-123'
        )

        after_bytes = cover.read_bytes()
        assert len(after_bytes) == before_size, (
            f'封面原檔被截斷：{before_size} bytes -> {len(after_bytes)} bytes。'
            'shutil._samefile 吞掉 samefile 的 OSError 回 False，copyfile 因此以 '
            "'wb' 開啟同 inode 的 dst 而清空原檔——fanart 側的 same_target_verdict "
            'preflight 不可省略。'
        )
        assert after_bytes == before_bytes


# ============ crop_to_poster 焦點化測試 (TASK-101a-T1) ============

_FOCAL_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos"


def _pad_to_square_with_white_bars(src_path, dst_path):
    """把矩形圖上下 pad 白邊成正方形（測試內即時合成，不進 repo，Opus 裁決見 TASK card）。"""
    with Image.open(src_path) as img:
        w, h = img.size
        assert w > h, "本 helper 只處理橫向圖上下 pad 成方形"
        square = Image.new("RGB", (w, w), (255, 255, 255))
        top = (w - h) // 2
        square.paste(img.convert("RGB"), (0, top))
        square.save(str(dst_path), "JPEG", quality=95)


class TestCropToPosterFocalWiring:
    """DoD②：無碼真圖 poster 對準臉——gate 兩支路徑（fixture A/B）各一，
    分支2/分支3 各一（4 組合）。TASK-102c-T1：改 mock `core.organizer.run_detection`
    成 `RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)`，只驗 consumer（crop_to_poster）收到焦點座標後
    正確平移窗口的 wiring；真的「pigo 對真圖偵出正確焦點」能力已搬到
    test_focal_detector.py::TestDetectFocal（Layer 1，真跑）。

    每組合兩個斷言：
    - 正向：輸出 bytes 等於「測試內獨立以『只平移既有窗』契約（整數 crop_w + focal 平移 x0）裁切存檔」的期望值。
    - 反向：輸出 bytes 與「同圖不傳 number/maker 的原碼輸出」不同（證明焦點真的平移了窗）。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}  # 番號驅動，maker 非白名單
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}  # maker-only 驅動，白名單原樣照抄

    def _assert_focal_applied(self, src_path, tmp_path, tag, **kwargs):
        dst = tmp_path / f"poster_{tag}.jpg"
        baseline_dst = tmp_path / f"poster_{tag}_baseline.jpg"

        # TASK-102c-T1：mock core.organizer.run_detection（consumer binding）成
        # RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)，避免真跑 pigo（~4-5s/呼叫）。
        # baseline 呼叫不傳 number/maker，gate=False，不會呼叫 run_detection，不受此 patch 影響。
        with patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)) as mock_detect:
            result = crop_to_poster(str(src_path), str(dst), **kwargs)
        assert result is True
        assert dst.exists()

        with Image.open(src_path) as img:
            w, h = img.size
        r_window = _poster_window_ratio(w, h)
        assert r_window is not None
        # 比例若傳錯、mock 仍回固定焦點，bytes 比對抓不到，所以直接鎖呼叫參數（158-T9 刪除 test_focal_detect_child 真 spawn 對照測試後的承接），並鎖逾時數值（它是產品端的 5 秒上限，錯了背景偵測不是全放棄就是拖太久）。
        mock_detect.assert_called_once()
        assert mock_detect.call_args.args[:2] == (str(src_path), r_window)
        assert mock_detect.call_args.kwargs["timeout_s"] == organizer._DETECT_TIMEOUT_S

        focal = MOCK_FOCAL_XY

        with Image.open(src_path) as img:
            # 101a P2-1（Codex PR#110）：oracle 改為「只平移既有窗」的真實契約——用與退化路
            # 完全相同的整數 crop_w，只把 x0 平移到臉；不再經 crop_image_position 的 float
            # ratio→px round-trip（該 helper 會 ±1px 改窗寬、已被 crop_to_poster 棄用）。
            crop_w = int(h / 1.5) if (h / w) >= 1.0 else (w - int(w / 1.9))
            x0 = max(min(int(w * focal[0]) - crop_w // 2, w - crop_w), 0)
            expected_cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
        expected_path = tmp_path / f"poster_{tag}_expected.jpg"
        expected_cropped.save(str(expected_path), "JPEG", quality=95, subsampling=0)
        assert dst.read_bytes() == expected_path.read_bytes(), "輸出應與獨立計算的期望裁切位元相同"

        baseline_result = crop_to_poster(str(src_path), str(baseline_dst))
        assert baseline_result is True
        assert dst.read_bytes() != baseline_dst.read_bytes(), "焦點裁切應與原碼（不傳 number/maker）輸出不同"


class TestCropToPosterByteForByteRegression:
    """DoD④：真正的零回歸哨兵（非 TestCropToPoster 三個既有測試，見 plan §C-1 修訂框一）。

    同一測試內兩次呼叫自我比對（不需 git 取舊產物）：有碼 / 無臉 / number='' 三路，
    分支2（方形）與分支3（橫向）各至少覆蓋一次。
    """


    def test_censored_real_face_gate_false_branch3(self, tmp_path):
        """有碼（gate False，真臉分支3，忠實測試）：wide_offcenter_face.jpg 真臉圖 +
        SSIS-001/S1 NO.1 STYLE（實測 gate → False）輸出須等於**獨立計算**的既有裁切算式
        期望值。

        ⚠️ 不能用「呼叫兩次 crop_to_poster 自我比對」（一次不傳 number/maker 當 baseline）：
        對「gate 被整個繞過」（如 mutation `if True:`）這種 mutation，baseline 那次呼叫
        同樣會被同一個 mutation 影響、一樣被平移，兩次呼叫依然相等 → 結構性瞎眼、測試
        不會紅（本 task P2 review 踩過一次）。改成與**不經過 crop_to_poster** 的獨立算式
        比對，才能在 gate 被繞過時偵測到分歧。
        """
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        dst = tmp_path / "poster.jpg"
        assert crop_to_poster(str(src), str(dst), number="SSIS-001", maker="S1 NO.1 STYLE") is True

        with Image.open(src) as img:
            w, h = img.size
            ratio = h / w
            assert ratio < 1.0, "fixture 應落在分支3（橫向）"
            x0 = int(w / 1.9)
            expected_cropped = img.convert("RGB").crop((x0, 0, w, h))
        expected_path = tmp_path / "expected.jpg"
        expected_cropped.save(str(expected_path), "JPEG", quality=95, subsampling=0)
        assert dst.read_bytes() == expected_path.read_bytes(), (
            "gate=False 時輸出應等於既有分支3裁切算式（右裁 x0=int(w/1.9)），"
            "若不同代表 gate 沒有正確擋下偵測"
        )


class TestCropToPosterBranch1NoDetection:
    """DoD⑤：分支1（h/w>=1.4，narrow_face_top.jpg 真圖且真有臉）仍 copy2 不裁，
    且完全不觸發人臉偵測（結構保證：分支1提早 return，不進入 gate/偵測邏輯）。

    patch target 必須是 core.organizer.run_detection（consumer binding，
    見 gotchas-backend.md §測試 Mock Patch Target；patch core.focal.subprocess_runner.run_detection 改不到）。
    """

    def test_branch1_copy2_no_detection_even_with_gate_true(self, tmp_path):
        src = _FOCAL_FIXTURES_DIR / "narrow_face_top.jpg"
        dst = tmp_path / "poster.jpg"

        with patch('core.organizer.run_detection') as mock_detect_focal:
            result = crop_to_poster(str(src), str(dst), number="FC2-1234567")

        assert result is True
        assert dst.exists()
        assert dst.read_bytes() == src.read_bytes(), "分支1應 copy2 直接複製，輸出應與來源位元相同"
        assert mock_detect_focal.call_count == 0, "分支1不應觸發人臉偵測"


_CD7_VERDICT_NEUTRAL_CASES = [
    "fc2-1234567",
    "FC2PPV-1234567",
    "fc2ppv1234567",
    "n0762",
    "heyzo-1234",
    "kin8-1234",
    "gcolle-123456",
    "siro-1234",
    "SSIS-001",
    "4SSIS-296",
    "7IPZ-001",
    "3ABW-001",
    "1sdms00808",
    "ABC-123-UC",
    "  sone-103  ",
    "h0930-1234",
    "022509-995",
]


def _make_ext_config(external_manager: str, create_folder: bool = False,
                     download_sample_images: bool = False) -> dict:
    """T4 測試用：依 external_manager 模式建立 config dict"""
    return {
        "create_folder": create_folder,
        "filename_format": "[{num}] {title}",
        "download_cover": True,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": [],
        "external_manager": external_manager,
        "download_sample_images": download_sample_images,
    }


def _make_ext_metadata(number: str = "SONE-205", cover: str = "http://fake/cover.jpg") -> dict:
    """T4 測試用：標準 metadata"""
    return {
        "number": number,
        "title": "Test Title",
        "actors": [],
        "tags": [],
        "maker": "S1",
        "date": "2024-01-15",
        "cover": cover,
        "url": "",
    }


def _extract_nfo_tag_value(nfo_text: str, tag: str) -> str:
    """從 NFO 字串取出指定 tag 的內容值（不含目錄的檔名字串）。T4 用。"""
    import re
    m = re.search(rf'<{tag}>(.*?)</{tag}>', nfo_text)
    assert m is not None, f"NFO 缺少 <{tag}> tag：\n{nfo_text}"
    return m.group(1)


class TestTable1Row7DirectLock:
    """T4：⑨（CD-112b-2）的直接鎖＝真理表 Table 1 #7。

    organize_file() + 媒體伺服器 flavour → ① result['cover_path'] 本身指向
    `-fanart.jpg` ② NFO 的 <thumb>/<fanart>/<poster> 三個 tag 值各自組成路徑
    後 `.exists()` 必須為真（不只比字串，避免測不到懸空引用或交叉污染）
    ③ 裸 stem 同名封面 `{filename_base}.jpg` 不存在（AC1 的直接反面）。
    # 真理表 Table 1 #7
    """

    def _assert_row7(self, tmp_path, flavour, number):
        src = tmp_path / f"{number}.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config(flavour)
        metadata = _make_ext_metadata(number=number)

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗（{flavour}）: {result.get('error')}"

        # filename_base 從 result['new_filename'] 剝副檔名取得，不從 cover_path
        # 反推（cover_path 此時已是 `{filename_base}-fanart.jpg`，用 .stem 會多
        # 剝出 `-fanart` 尾巴，重蹈 CD-112b-3 推翻掉的反向推導錯誤）。
        filename_base = Path(result["new_filename"]).stem
        target_dir = Path(result["nfo_path"]).parent

        # ① result['cover_path'] 本身指向 -fanart.jpg
        assert Path(result["cover_path"]).name == f"{filename_base}-fanart.jpg", (
            f"[{flavour}] cover_path 應直接指向 -fanart.jpg，實際：{result['cover_path']}"
        )

        # ② NFO 三 tag 各自組出路徑後必須實際存在（不只比字串）
        nfo_text = Path(result["nfo_path"]).read_text(encoding="utf-8")
        for tag in ("thumb", "fanart", "poster"):
            tag_value = _extract_nfo_tag_value(nfo_text, tag)
            tag_path = target_dir / tag_value
            assert tag_path.exists(), f"[{flavour}] <{tag}> 指向的檔案應實際存在：{tag_path}"

        # ③ 裸 stem 同名封面不存在（AC1 的直接反面）
        bare_cover = target_dir / f"{filename_base}.jpg"
        assert not bare_cover.exists(), f"[{flavour}] 裸 stem 封面不應出現：{bare_cover}"

    def test_organize_jellyfin_nfo_tags_point_to_existing_files(self, tmp_path):
        """jellyfin：⑨ 直接鎖。# 真理表 Table 1 #7"""
        self._assert_row7(tmp_path, "jellyfin", "SONE-205")


class TestExternalManagerNfoF3:
    """T4：NFO F3 欄位跟隨 external_manager 模式"""

    def _make_nfo_metadata(self, number: str = "SONE-205") -> dict:
        return {
            "number": number,
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "https://example.com/video",
        }

    def test_jellyfin_nfo_has_f3_fields(self, tmp_path):
        """jellyfin → 產出的 NFO 含 F3 欄位（<country>Japan + <lockdata>）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("jellyfin")
        metadata = self._make_nfo_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("nfo_path") is not None, "NFO 應被產出"

        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "<country>Japan</country>" in nfo_content, \
            "jellyfin NFO 應含 <country>Japan</country>"
        assert "<lockdata>true</lockdata>" in nfo_content, \
            "jellyfin NFO 應含 <lockdata>true</lockdata>"


# ============ Config suffix_keywords 持久化測試 ============

class TestConfigSuffixKeywordsPersistence:
    """suffix_keywords 設定的 save → reload 持久化測試"""

    def test_config_suffix_keywords_persistence(self, client, temp_config_path):
        """
        PUT /api/config 儲存 suffix_keywords 後，GET /api/config 取得的值應不變。
        """
        # 取得當前設定
        response = client.get("/api/config")
        assert response.status_code == 200
        cfg = response.json()["data"]

        # 修改 suffix_keywords
        custom_keywords = ["-cd1", "-cd2", "-4k", "-uc", "-hd"]
        cfg["scraper"]["suffix_keywords"] = custom_keywords

        # 儲存
        put_response = client.put("/api/config", json=cfg)
        assert put_response.status_code == 200
        assert put_response.json()["success"] is True

        # 重新取得，驗證值不變
        get_response = client.get("/api/config")
        assert get_response.status_code == 200
        saved_keywords = get_response.json()["data"]["scraper"]["suffix_keywords"]
        assert saved_keywords == custom_keywords

        # 也直接驗證檔案內容
        with open(temp_config_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["scraper"]["suffix_keywords"] == custom_keywords


# ============ extract_chinese_title() 測試 ============

class TestExtractChineseTitle:
    def test_mixed_title(self):
        result = extract_chinese_title("Beauty Girl ABP-001 美少女初登場.mp4", "ABP-001")
        assert result == "Beauty Girl 美少女初登場"


class TestExtractChineseTitleSubtitleMarkers:
    """spec-48a.md §a2 行為對照表 — 字幕標記 edge cases

    T2 是 strip_subtitle_markers helper 的第一個實際使用場景。
    本 class 的七個 case 不只驗證 T2 的 wiring，也間接守護 T1 helper
    的 'bracket 先剝、長 pattern 優先' 順序契約：若該順序回歸，
    case #6 的 【中文字幕】 剝除會殘留『中文字幕』四個字 → has_chinese=True
    → 誤判為中文片名回傳 → 斷言 fail（預期 None）。
    """

    @pytest.mark.parametrize("filename, number, expected", [
        ("ABC-123【中文字幕】.mp4", "ABC-123", None),                  # 6. 字幕 bracket → None（守護順序契約）
        # 8-9. Codex 指出的 orphan 分隔符殘留 — 剝除 marker 後不應留下尾端 -/_
    ])
    def test_subtitle_marker_cases(self, filename, number, expected):
        result = extract_chinese_title(filename, number)
        assert result == expected, (
            f"extract_chinese_title({filename!r}, {number!r}) = {result!r}，"
            f"期望 {expected!r}"
        )


# ============ generate_nfo() 補充測試 ============


class TestGenerateNfoTitleFormat:
    """generate_nfo() nfo_title_format 參數與記錄行（TASK-154b-T1）。"""


    def test_generate_nfo_custom_format_writes_title_and_record(self, tmp_path):
        """自訂格式寫出新 <title> 與記錄行 <written>/<body>。"""
        nfo_path = tmp_path / "ABC-123.nfo"
        result = generate_nfo(
            number="ABC-123",
            title="片名",
            actors=["三上悠亜"],
            output_path=str(nfo_path),
            nfo_title_format="{num}-{title}-{actor}",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<title>ABC-123-片名-三上悠亜</title>" in content
        root = ET.fromstring(content)
        record = root.find("openaver_title_record")
        assert record is not None
        assert record.find("written").text == "ABC-123-片名-三上悠亜"
        assert record.find("body").text == "片名"


class TestGenerateNfoRatingLine:
    """generate_nfo() rating_line 型別防護（TASK-147c-T2）"""


    def test_generate_nfo_rating_line_valid_float_unchanged(self, tmp_path):
        nfo_path = tmp_path / "TEST-002.nfo"
        result = generate_nfo(
            number="TEST-002",
            title="測試標題",
            output_path=str(nfo_path),
            rating=4.5,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<rating>9.0</rating>" in content


class TestGenerateNfoNoUnescapedInterpolation:
    """generate_nfo() 的 f-string 不得出現未預期的裸插值（NFO-CTRL-01d）。

    # [lint-guard: pytest-justified] Python-AST 源碼語意守衛——CLAUDE.md「Lint 守衛規則」
    # 明列為 pytest 例外（eslint/static_guard_lint 表達不了「這個插值有沒有過 html.escape」）。

    **為什麼要有這條**：PR #191 的外部 review 連三輪在同一個函式找到同一種洞
    （控制字元 → basename 回流 → 容器型別 → duration），每一輪都是「又漏一個欄位」。
    問題不是漏，是**漏了誰都看不出來**：這支函式用 f-string 手組 XML，escape 是
    逐格 opt-in 的，少寫一個 `html.escape()` 沒有任何機制會說話。
    這條守衛把當時的窮舉盤點固化下來——新的裸插值出現就紅，不必等下一個 reviewer。

    **不改成 ElementTree 組 XML 的理由**：那是承重重構（既有 byte-identical NFO 測試
    綁死輸出格式），不在 hotfix 範圍；守衛先把回歸擋住，重構另開。
    """

    # 允許的裸插值 → (預期出現次數, 為什麼安全)。加新項目必須寫得出理由。
    #
    # ⚠️ **key 帶次數不是為了好看**（Codex PR #191 四次審核 P3）：只用名稱當 key 時，
    # 已被允許的名稱在**別的位置**重新出現不會被發現——例如 `number` 因為
    # `display_title = f"[{number}]{_t}"` 這個安全的中間運算而在清單裡，之後若有人寫
    # `nfo_content += f"<foo>{number}</foo>"`（真的裸插進 XML），守衛仍會綠。
    # 綁次數之後，任何**新的一次出現**都會讓對帳不符而轉紅，作者必須回來說明它安全在哪。
    # 次數只在增刪插值時才變動，不隨行號漂移。
    ALLOWED_UNESCAPED = {
        "poster_suffix": (1, "字面常數 '-poster' / ''"),
        "fanart_suffix": (1, "字面常數 '-fanart' / ''"),
        "rating * 2": (1, "有 isinstance 數值守衛 ＋ :.1f 格式 → 只可能是數字"),
        "_duration": (1, "已由 isinstance(int) and not bool 收斂，非整數走空 runtime 分支"),
        "set_tag": (1, "預組 XML 片段，內容組裝時已 html.escape(series)"),
        "label_tag": (1, "預組 XML 片段，內容組裝時已 html.escape(label)"),
        "runtime_tag": (1, "預組 XML 片段，內容是收斂後的 _duration"),
        "director_tag": (1, "預組 XML 片段，內容組裝時已 html.escape(director)"),
        "poster_tag": (1, "預組 XML 片段，內容組裝時已 html.escape(basename)"),
        "fanart_tag": (2, "預組 XML 片段（<thumb> 與 <fanart> 各一），內容已 html.escape(basename)"),
        "rating_line": (1, "預組 XML 片段，內容是數字格式化結果"),
        "external_block": (1, "預組 XML 片段，內容組裝時已 html.escape"),
        "title_record_block": (1, "預組 XML 片段，內容組裝時已 html.escape(display_title)／html.escape(_t)"),
        "e": (1, "logger.error 的例外訊息，不進 XML"),
    }

    def _collect(self):
        import ast
        src = Path(organizer.__file__).read_text(encoding="utf-8")
        fn = next(
            n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "generate_nfo"
        )
        found = {}
        for node in ast.walk(fn):
            if not isinstance(node, ast.JoinedStr):
                continue
            for v in node.values:
                if not isinstance(v, ast.FormattedValue):
                    continue
                expr = ast.unparse(v.value)
                if expr.startswith("html.escape("):
                    continue
                count, first_line = found.get(expr, (0, v.lineno))
                found[expr] = (count + 1, min(first_line, v.lineno))
        return found

    def test_no_new_unescaped_interpolation(self):
        found = self._collect()
        unexpected = {e: v for e, v in found.items() if e not in self.ALLOWED_UNESCAPED}
        assert not unexpected, (
            "generate_nfo() 出現未登記的裸插值——它會直接落進 NFO 的 XML。\n"
            "要嘛包 html.escape()，要嘛加進 ALLOWED_UNESCAPED 並寫出為什麼安全：\n"
            + "\n".join(f"  :{ln}  {e}" for e, (_n, ln) in sorted(unexpected.items(), key=lambda kv: kv[1][1]))
        )

    def test_allowed_occurrence_counts_match(self):
        """已允許的名稱在**新的位置**再出現一次也要紅（Codex PR #191 四次審核 P3）。

        只比對名稱的話，`number` 這種因為安全中間運算而被允許的名稱，
        日後被裸插進真正的 XML 元素時守衛不會說話。綁次數才讓
        「下一個漏掉的插值一定紅」這句話成立。
        """
        found = self._collect()
        drift = []
        for expr, (expected, reason) in self.ALLOWED_UNESCAPED.items():
            actual = found.get(expr, (0, 0))[0]
            if actual != expected:
                drift.append(f"  {expr!r}: 登記 {expected} 次，實際 {actual} 次（{reason}）")
        assert not drift, (
            "generate_nfo() 裡已允許的裸插值出現次數變了——新增的那一次落在哪裡？\n"
            "確認它安全之後再更新 ALLOWED_UNESCAPED 的次數：\n" + "\n".join(drift)
        )


class TestGenerateNfoIllegalXmlChars:
    """generate_nfo() XML 不合法控制字元淨化（NFO-CTRL-01，PR #191 F1 + 加固）。

    每條都真的 ET.parse() 寫出的檔案——只斷言字串裡沒有那個字元驗不到「解析得動」，
    這正是本次要修的病灶（裸控制字元讓 NFO 寫出成功但整份 XML 解析失敗）。
    parse 失敗時轉成明確 assert（不讓 ET.ParseError 原樣穿出去），維持
    「轉紅＝斷言失敗，不是例外崩潰」的形狀。
    """

    def _parse_or_fail(self, nfo_path):
        try:
            return ET.parse(nfo_path), True
        except ET.ParseError as e:
            return e, False

    def test_null_byte_stripped_from_summary(self, tmp_path):
        nfo_path = tmp_path / "TEST-CTRL-001.nfo"
        result = generate_nfo(
            number="TEST-CTRL-001",
            title="測試標題",
            output_path=str(nfo_path),
            summary="before\x00after",
        )
        assert result is True
        tree, ok = self._parse_or_fail(nfo_path)
        assert ok, f"NFO 應可被 XML parser 解析，實際: {tree}"
        plot = tree.getroot().find("plot").text
        assert plot == "beforeafter"


    def test_none_summary_does_not_crash_after_move(self, tmp_path):
        """PR #191 CodeRabbit P2 的真實那一半：`scrape_single` 對 metadata 零驗證，
        AI 送 `{"_summary": null}` 時 `metadata.get('_summary','')` 回 None（key 存在
        ⇒ default 不生效），而 generate_nfo() 在 atomic_move() 之後才跑——舊碼
        `html.escape(None)` 會 AttributeError，畫面說「整理失敗」但影片檔已經搬走。
        與 147c-T2 的 `<rating>` 型別防護同一條 sink、同一個理由（BE-GUARD-01）。"""
        nfo_path = tmp_path / "TEST-CTRL-007.nfo"
        result = generate_nfo(
            number="TEST-CTRL-007",
            title="測試標題",
            output_path=str(nfo_path),
            summary=None,
        )
        assert result is True, "summary=None 不得讓 generate_nfo 崩潰或回 False"
        tree, ok = self._parse_or_fail(nfo_path)
        assert ok, f"NFO 應可被 XML parser 解析，實際: {tree}"
        assert (tree.getroot().find("plot").text or "") == ""


# ============ download_image() 測試 ============


# ============ download_image() fallback / host memory (TASK-126-T4a) ============

_BIG_JPEG = b"x" * 1001


def _ok_resp(content=_BIG_JPEG):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = content
    return resp


def _status_resp(code):
    resp = MagicMock()
    resp.status_code = code
    resp.content = b""
    return resp


class TestDownloadImageFallback:
    """TASK-126-T4a：原址優先、短 connect 逾時、失敗 host 記憶。"""

    @pytest.fixture(autouse=True)
    def _clear_host_failure_memory(self):
        import core.organizer as org
        mem = getattr(org, "_failed_hosts", None)
        lock = getattr(org, "_failed_hosts_lock", None)
        if mem is not None and lock is not None:
            with lock:
                mem.clear()
        yield
        if mem is not None and lock is not None:
            with lock:
                mem.clear()

    @patch("core.organizer.requests.get")
    def test_download_image_no_fallback_success_preserves_args(self, mock_get, tmp_path):
        """邊界 1：無 fallback、原址成功；**參數與改動前逐字元相同，timeout 也包含在內**。

        Codex PR review P2：初版讓所有呼叫端（含自家 9 源）都吃 (5, 30)，
        等於把「連線慢但接得起來」的使用者從「30 秒後成功」改成「5 秒失敗」，
        而且他們沒有代理可退。AC-5 的「逐字元相同」把 timeout 也算在內。
        """
        from core.organizer import HEADERS, REQUEST_TIMEOUT

        mock_get.return_value = _ok_resp()
        save_path = tmp_path / "cover.jpg"
        result = download_image("http://example.com/cover.jpg", str(save_path))

        assert result is True
        assert save_path.read_bytes() == _BIG_JPEG
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "http://example.com/cover.jpg"
        assert kwargs["headers"] == HEADERS.copy()
        assert kwargs["timeout"] == REQUEST_TIMEOUT, (
            "無 fallback 的呼叫端（自家 9 源）必須維持單值 30 秒——"
            "縮成 (5, 30) 會讓慢速連線的使用者從『30 秒後成功』變成『5 秒失敗』"
        )


    @patch("core.organizer.requests.get")
    def test_download_image_fallback_on_connect_timeout(self, mock_get, tmp_path):
        """邊界 3：有 fallback、原址 ConnectTimeout → 改試 fallback 並存檔。"""
        mock_get.side_effect = [
            requests.exceptions.ConnectTimeout("connect timed out"),
            _ok_resp(b"y" * 1001),
        ]
        save_path = tmp_path / "cover.jpg"
        result = download_image(
            "http://example.com/cover.jpg",
            str(save_path),
            fallback_url="http://proxy.example/cover.jpg",
        )
        assert result is True
        assert save_path.read_bytes() == b"y" * 1001
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0].args[0] == "http://example.com/cover.jpg"
        assert mock_get.call_args_list[1].args[0] == "http://proxy.example/cover.jpg"

    @patch("core.organizer.requests.get")
    def test_download_image_primary_success_skips_fallback(self, mock_get, tmp_path):
        """邊界 4：有 fallback、原址成功 → 不呼叫 fallback。"""
        mock_get.return_value = _ok_resp()
        result = download_image(
            "http://example.com/cover.jpg",
            str(tmp_path / "c.jpg"),
            fallback_url="http://proxy.example/cover.jpg",
        )
        assert result is True
        mock_get.assert_called_once()
        assert mock_get.call_args.args[0] == "http://example.com/cover.jpg"


# ============ generate_nfo() 新欄位測試 (T5b) ============


# ============ organize_file() extrafanart 測試 (T5b) ============

class TestOrganizeExtrafanart:
    """organize_file() extrafanart/ 目錄建立與下載測試（由 download_sample_images 控制）"""

    def _make_jellyfin_config_with_nfo(self, jellyfin_mode: bool, create_folder: bool = True,
                                       download_sample_images: bool = None) -> dict:
        # 向後相容：若未指定 download_sample_images，沿用 jellyfin_mode 的值（舊行為）
        if download_sample_images is None:
            download_sample_images = jellyfin_mode
        # T4 遷移：image block 改由 external_manager 控制；jellyfin_mode=True → 'jellyfin'
        return {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "external_manager": "jellyfin" if jellyfin_mode else "off",
            "download_sample_images": download_sample_images,
        }

    def _make_metadata_with_samples(self, sample_images=None) -> dict:
        return {
            "number": "SNOS-143",
            "title": "テスト",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
            "sample_images": sample_images if sample_images is not None else [
                "http://fake/sample1.jpg",
                "http://fake/sample2.jpg",
            ],
        }


    def test_extrafanart_with_sample_dl_without_jellyfin(self, tmp_path):
        """jellyfin_mode=False, download_sample_images=True, create_folder=True → extrafanart 建立（解耦驗證）"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=False, create_folder=True,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert extrafanart_dir.exists(), "download_sample_images=True 時應建立 extrafanart/ 目錄"
        assert (extrafanart_dir / "fanart1.jpg").exists(), "fanart1.jpg 應被下載"
        assert (extrafanart_dir / "fanart2.jpg").exists(), "fanart2.jpg 應被下載"
        # jellyfin_mode=False → 不產生 poster/fanart
        assert result.get("poster_path") is None, "jellyfin_mode=False 時不應產生 poster"
        assert result.get("fanart_path") is None, "jellyfin_mode=False 時不應產生 fanart"

    def test_extrafanart_skipped_when_sample_dl_off(self, tmp_path):
        """jellyfin_mode=True, download_sample_images=False, create_folder=True → 無 extrafanart，但 poster/fanart 存在"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=True,
                                                     download_sample_images=False)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert not extrafanart_dir.exists(), "download_sample_images=False 時不應建立 extrafanart/ 目錄"
        # jellyfin_mode=True → 應產生 poster/fanart
        assert result.get("poster_path") is not None, "jellyfin_mode=True 時應產生 poster"
        assert result.get("fanart_path") is not None, "jellyfin_mode=True 時應產生 fanart"


# ============ find_subtitle_files() 測試 (T37d-1) ============

from core.organizer import find_subtitle_files


class TestFindSubtitleFiles:
    """find_subtitle_files() 的單元測試"""


    def test_exclude_different_name_srt(self, tmp_path):
        """不同名字幕 bbb.srt 不包含"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "bbb.srt"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) not in result
        assert result == []


# ============ organize_file() 字幕搬移測試 (T37d-1) ============

class TestOrganizeSubtitle:
    """organize_file() 字幕偵測 + 搬移整合測試"""

    def _make_config(self, tmp_path, create_folder=False):
        return {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }

    def _make_metadata(self):
        return {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

    def test_subtitle_moves_with_video(self, tmp_path):
        """organize 成功搬移後，字幕跟隨（字幕在目標目錄，名稱正確）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # 影片搬移了（同目錄重命名）
        target_dir = Path(result["new_filename"]).parent
        # 字幕應出現在目標目錄，並以新檔名命名
        new_video_stem = Path(result["new_filename"]).stem
        expected_sub = target_dir / f"{new_video_stem}.srt"
        assert expected_sub.exists(), f"字幕應搬移到 {expected_sub}"
        # 原字幕不應在原位（已搬移）
        assert not sub.exists(), "原始字幕應已搬離原位置"

    def test_subtitle_with_lang_suffix_moves_correctly(self, tmp_path):
        """帶語言後綴的字幕搬移後名稱正確（new-name.cht.srt）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.cht.srt"
        sub.write_text("subtitle cht")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        target_dir = Path(result["new_filename"]).parent
        new_video_stem = Path(result["new_filename"]).stem
        expected_sub = target_dir / f"{new_video_stem}.cht.srt"
        assert expected_sub.exists(), f"帶語言後綴的字幕應搬移到 {expected_sub}"

    def test_subtitle_not_moved_on_duplicate(self, tmp_path):
        """organize 影片 duplicate → 字幕留原處不搬"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"source content")
        # 建立已存在的目標檔（造成 duplicate）
        existing_target = tmp_path / "[SONE-205] Test Title.mp4"
        existing_target.write_bytes(b"existing content")
        # 字幕
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result.get("duplicate") is True
        assert result["success"] is False
        # 字幕應仍在原處
        assert sub.exists(), "duplicate 時字幕不應被搬移"

    def test_subtitle_move_failure_warning_continues(self, tmp_path):
        """字幕搬移失敗 → warning，後續繼續（封面/NFO 正常產生）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }

        import shutil as _shutil_real
        _real_move = _shutil_real.move

        def selective_move(src_path, dst_path):
            if str(src_path).endswith(".srt"):
                raise OSError("字幕搬移模擬失敗")
            return _real_move(src_path, dst_path)

        with patch("core.organizer.shutil.move", side_effect=selective_move), \
             patch("core.organizer.download_image", return_value=False):
            result = organize_file(str(src), metadata, config)

        # 影片整理應仍成功（字幕失敗不影響）
        assert result["success"] is True, f"字幕失敗不應影響 organize 成功: {result.get('error')}"

    def test_check_subtitle_true_no_file_has_subtitle_true(self, tmp_path):
        """check_subtitle() 回傳 True 但無字幕檔 → has_subtitle = True，NFO 有中文字幕 tag"""
        # 檔名含 "-C" → check_subtitle 回傳 True
        src = tmp_path / "SONE-205-C.mp4"
        src.write_bytes(b"fake mp4")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # NFO 應包含中文字幕 tag
        if result.get("nfo_path"):
            nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
            assert "中文字幕" in nfo_content, "check_subtitle=True 時 NFO 應包含中文字幕 tag"


    def test_explicit_false_with_sidecar_subtitle(self, tmp_path):
        """has_subtitle=False 但有 sidecar 字幕 → has_subtitle 應為 True，NFO 有 tag"""
        # 檔名無字幕標記（check_subtitle 為 False），metadata 明確傳 has_subtitle=False
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        # sidecar 字幕與影片同目錄
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
            "has_subtitle": False,  # 上游明確設為 False
        }

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # sidecar 字幕存在 → 應覆寫上游 False → NFO 必須包含中文字幕 tag
        assert result.get("nfo_path"), "NFO 應被建立"
        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "中文字幕" in nfo_content, \
            "has_subtitle=False 但有 sidecar 字幕時，NFO 應包含中文字幕 tag"


# ============ Issue #31 — Windows trailing-dot truncation ============

class TestTruncateWindowsTrailingDot:
    """Issue #31: 截斷後尾端 `...` 在 Windows 會被 NTFS 剝除，導致 shutil.move WinError 3"""

    def test_truncate_to_chars_strips_trailing_dots_on_windows(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = truncate_to_chars("僕が不在の5日間、彼女が他の男と朝から晩までヤリまくっていた胸糞映像 吉高寧々", 40)
        assert not result.endswith('.'), f"Windows: 截斷結果不應以 . 結尾, got {result!r}"
        assert not result.endswith(' '), f"Windows: 截斷結果不應以空格結尾, got {result!r}"


# ============ Issue 181-T5 — Windows 資料夾名段尾句點／控制字元 ============

def _organize_one(tmp_path, maker, title, layers):
    """真檔案系統跑一次 organize_file（create_folder，標題上限放大避免 truncate_title 先動手）"""
    src = tmp_path / "SONE-205.mp4"
    src.write_bytes(b"x")
    config = {**_make_config(tmp_path), "create_folder": True, "folder_layers": layers,
              "filename_format": "{num} {title}", "max_title_length": 100}
    metadata = {**_make_metadata(title=title), "maker": maker}
    return organize_file(str(src), metadata, config)


class TestWindowsFolderNameSanitize:
    """181-T5：Windows 上資料夾名與記錄的路徑要一致；非 Windows 逐字不變"""

    @pytest.mark.parametrize("maker,title,layers,expected", [
        ("Mrs.", "T", ["{maker}"], "Mrs"),
        ("S1", "Hello world...", ["{title}"], "Hello world"),
    ])
    def test_windows_folder_layer_strips_trailing_dot(self, monkeypatch, tmp_path, maker, title, layers, expected):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = _organize_one(tmp_path, maker, title, layers)
        assert result["success"] is True, result["error"]
        assert os.path.basename(result["new_folder"]) == expected
        assert Path(result["new_folder"]).is_dir()

    @pytest.mark.parametrize("title,expected", [("A\x07B", "AB"), ("A\tB", "A B")])
    def test_windows_control_chars_removed(self, monkeypatch, tmp_path, title, expected):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = _organize_one(tmp_path, "S1", title, ["{title}"])
        assert result["success"] is True, result["error"]
        assert os.path.basename(result["new_folder"]) == expected
        for path in (result["new_folder"], result["new_filename"]):
            assert not re.search(r'[\x00-\x08\x0e-\x1b]', os.path.basename(path))

    def test_non_windows_names_unchanged(self, tmp_path):
        for sub, (maker, title, layers) in enumerate([
            ("Mrs.", "T", ["{maker}"]),
            ("S1", "Hello world...", ["{title}"]),
            ("S1", "A\x07B", ["{title}"]),
        ]):
            work = tmp_path / str(sub)
            work.mkdir()
            result = _organize_one(work, maker, title, layers)
            assert result["success"] is True, result["error"]
            expected_folder = {0: "Mrs.", 1: "Hello world...", 2: "A\x07B"}[sub]
            assert os.path.basename(result["new_folder"]) == expected_folder
            assert os.path.basename(result["new_filename"]) == f"SONE-205 {title if sub else 'T'}.mp4"


# ============ Issue 181-T6 — 檔名／資料夾名位元組上限 255 ============

def _nbytes(text):
    return len(text.encode("utf-8"))


def _cover_stub(url, save_path, referer="", **kwargs):
    """不碰網路的 download_image：寫一張 JPEG；寫不出（檔名過長 OSError）回 False，同 _attempt_download_image"""
    try:
        Image.new("RGB", (800, 538), (200, 100, 50)).save(save_path, "JPEG")
    except OSError:
        return False
    return True


def _organize_bytes(tmp_path, filename, number, title, cover="", **overrides):
    src = tmp_path / filename
    src.write_bytes(b"x")
    config = {**_make_config(tmp_path, ["-4k", "-c"]), "filename_format": "{num} {title}{suffix}", **overrides}
    with patch("core.organizer.download_image", side_effect=_cover_stub):
        return organize_file(str(src), {**_make_metadata(number, title), "cover": cover}, config)


class TestUtf8ByteCap:
    """181-T6：每一層資料夾名與檔名都不超過 255 bytes；今天本來就合法的名字逐字不變"""

    @pytest.mark.parametrize("filename,fmt,tail", [
        ("SONE-205.mp4", "{num} {title}", ""),
        ("SONE-205-C_180_LR.mp4", "{num} {title}{suffix}", "-c_180_LR"),
    ])
    def test_long_cjk_names_fit_255_bytes(self, tmp_path, filename, fmt, tail):
        title = "あ" * 110
        shown = organizer.truncate_title(title, 100)
        # 前置：進入最終一步前，資料夾名與 stem 都確實 > 255 bytes（否則假綠，BE-DATA-09）
        assert _nbytes(truncate_to_chars(shown, 120)) > 255
        assert _nbytes(truncate_to_chars(f"SONE-205 {shown}", 116 - len(tail)) + tail) > 255
        result = _organize_bytes(tmp_path, filename, "SONE-205", title, create_folder=True, folder_layers=["{title}"],
                                 filename_format=fmt, max_title_length=100, max_filename_length=120)
        assert result["success"] is True, result["error"]
        for name in (os.path.basename(result["new_folder"]), os.path.basename(result["new_filename"])):
            assert _nbytes(name) <= 255
            assert "\ufffd" not in os.fsencode(name).decode("utf-8")
        assert Path(result["new_filename"]).is_file()

    @pytest.mark.parametrize("filename,title,cfg,cover,expected,pre_stem_bytes", [
        ("SONE-205.mp4", "x" * 108, {}, "", "SONE-205 " + "x" * 44 + "....mp4", None),
        ("SONE-205.mp4", "あ" * 70, {}, "", "SONE-205 " + "あ" * 44 + "....mp4", None),
        ("SONE-205.mp4", "😀" * 70, {}, "", "SONE-205 " + "😀" * 44 + "....mp4", None),
        ("SONE-205.mp4", "あ" * 47, {}, "", "SONE-205 " + "あ" * 47 + ".mp4", None),
        ("SONE-205-4K.mp4", "あ" * 70, {}, "", "SONE-205 " + "あ" * 41 + "...-4k.mp4", None),
        ("SONE-205_180_LR.mp4", "あ" * 70, {}, "", "SONE-205 " + "あ" * 37 + "..._180_LR.mp4", None),
        ("ABC-123.mp4", "あ" * 80, {"external_manager": "off"}, "", "ABC-123 " + "あ" * 80 + ".mp4", 248),
        ("ABC-123.mp4", "あ" * 80, {"external_manager": "jellyfin"}, "", "ABC-123 " + "あ" * 80 + ".mp4", 248),
        ("ABC-123.mp4", "あ" * 80, {"external_manager": "jellyfin"}, "http://fake/c.jpg", "ABC-123 " + "あ" * 80 + ".mp4", 248),
        ("ABC-123-part1.mp4", "あ" * 79, {"external_manager": "jellyfin"}, "", "ABC-123 " + "あ" * 79 + "-part1.mp4", 251),
    ])
    def test_legal_names_unchanged_by_byte_cap(self, tmp_path, filename, title, cfg, cover, expected, pre_stem_bytes):
        overrides = cfg
        if pre_stem_bytes:  # 長名字組：進入最終一步前 stem 就是這個長度；251 組 part_tail 非空
            overrides = {"max_title_length": 80 if pre_stem_bytes == 248 else 100, "max_filename_length": 120,
                         "filename_format": "{num} {title}", "download_cover": True, "create_nfo": True, **cfg}
            assert _nbytes(expected[:-4]) == pre_stem_bytes
            assert ("-part1" in filename) == expected.endswith("-part1.mp4")
        number = "ABC-123" if filename.startswith("ABC") else "SONE-205"
        result = _organize_bytes(tmp_path, filename, number, title, cover, **overrides)
        assert result["success"] is True, result["error"]
        assert os.path.basename(result["new_filename"]) == expected


# ============ _detect_vr_cluster() 測試 ============

class TestDetectVrCluster:
    """_detect_vr_cluster() 的單元測試（TDD-lite RED→GREEN）

    命中列：回傳 raw 子字串（原樣大小寫）
    None 列：回傳 None（守零變化）
    """

    # ---- 命中列（unique 單獨成立）----


    def test_hit_180_lr(self):
        """NAME_180_LR → 180_LR（最主流：ambiguous ×2 共現）"""
        result = _detect_vr_cluster("NAME_180_LR")
        assert result == "180_LR"


    # ---- None 列（守零變化）----

    def test_none_isolated_180(self):
        """MIRD-180 → None（孤立裸 180，真番號，無共現 VR token）"""
        result = _detect_vr_cluster("MIRD-180")
        assert result is None


    # ---- 含副檔名也應一致 ----


    # --- 防禦性 / branch 補洞（review advisory）---


    # ---- Codex P2 修正（Finding 2）：連續 run 偵測 ----


    # ---- Codex P2 二次修正（Finding 2, P3）：多 confirmed run 只取第一個 ----


# ============ organize_file() VR 檔名端到端測試 ============

class TestOrganizeVrFilename:
    """organize_file() VR tail 端到端測試（TDD-lite，T2 DoD）

    驗證：
    - VR cluster 正確接到檔名尾（_{cluster}）
    - suffix × VR 順序 = base + suffix + _vr
    - 超長截斷時 VR cluster 完整不被切
    - 無 VR token 檔案 byte 級零變化（reserve=0）
    - 一般 2D 檔 byte 級零變化
    - 既有 suffix 路徑不回歸（-cd1/-cd2，無 VR，reserve=0 不影響）
    """

    # ---- DoD Row 1: VR 檔名尾正確接 _{cluster} ----


    # ---- DoD Row 2: suffix × VR 順序（base + suffix + _vr） ----


    # ---- DoD Row 3: 超長截斷 VR cluster 完整不被切 ----

    def test_long_title_vr_cluster_preserved(self, tmp_path):
        """超長 title + _180_3dh_LR.mp4：base 被 max_filename_length 截，VR cluster 完整"""
        src = tmp_path / "VR-999_180_3dh_LR.mp4"
        src.write_bytes(b"long vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 30,  # 故意很短，迫使截斷
            "suffix_keywords": ["-4k"],
        }
        metadata = {
            "number": "VR-999",
            "title": "超級無敵長的標題名稱會被截斷但VR尾應完整保留",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        stem = Path(new_name).stem
        # VR cluster 必須完整保留（_180_3dh_LR 原樣）
        assert stem.endswith("_180_3dh_LR"), (
            f"VR cluster _180_3dh_LR 被截斷：{stem}"
        )
        # 核心：reserve budget 真的生效——整個檔名（含 ext）不得超出 max_filename_length。
        # 沒有這行，「不扣 reserve 直接 overflow」也會讓上面的 endswith 通過（假測試）。
        assert len(new_name) <= 30, (
            f"reserve budget 未生效，檔名 {len(new_name)} 字超出 max_filename_length=30：{new_name!r}"
        )
        # base 確實被壓縮：超長標題不可能完整出現（證明 reserve 扣掉了 base 預算）
        assert "超級無敵長的標題名稱會被截斷但VR尾應完整保留" not in stem, (
            f"base 未被截斷，reserve 未壓縮 base：{stem}"
        )


    # ---- DoD Row 4: 無 VR token，byte 級零變化（SIVR-999.mp4，else 分支） ----


    # ---- DoD Row 5: 一般 2D 檔 byte 級零變化 ----


    # ---- DoD Row 6: 既有 suffix 路徑不回歸（無 VR，reserve=0） ----


    # ---- Codex PR P2 回歸：退化 config 最終長度上限保護 ----


# ============ generate_nfo() VR tag/genre 去重測試 (T3) ============


# ============ organize_file() VR 端到端串接測試 (T4) ============

class TestVrEndToEnd:
    """organize_file(create_nfo=True) 端到端 wiring 測試（TASK-68-T4）

    核心 gap：T2 用 create_nfo=False，T3 直呼 generate_nfo——
    未有任何測試同時驗「VR tail 檔名」+「NFO 恰一個 <tag>VR</tag>」。

    本 class 補上這條端到端鏈路：一次 organize_file 呼叫，
    同時斷言 (a) 檔名 stem tail、(b) NFO VR tag count==1 + genre count==1、
    (c) NFO sidecar 檔名 stem 與影片對齊（GB sidecar 跟隨）。
    """

    # ---- 共用 helper ----

    def _base_config(self, tmp_path=None, max_filename_length=60, suffix_keywords=None):
        return {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": max_filename_length,
            "suffix_keywords": suffix_keywords or [],
        }

    def _base_metadata(self, number, title, tags=None):
        return {
            "number": number,
            "title": title,
            "actors": [],
            "tags": tags or [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

    # ---- T4 DoD: VR 檔（KAVR-001_mkx200_LR.mp4）端到端 ----

    def test_vr_file_filename_tail_and_nfo_vr_tag(self, tmp_path):
        """KAVR-001_mkx200_LR.mp4 + tags=['單體']（無 VR）→
        (a) 檔名 stem 結尾 _mkx200_LR
        (b) NFO 含恰一個 <tag>VR</tag> + 一個 <genre>VR</genre>
        (c) NFO sidecar 檔名 stem 與影片 stem 對齊（prove GB sidecar 跟隨）
        """
        src = tmp_path / "KAVR-001_mkx200_LR.mp4"
        src.write_bytes(b"vr content")

        config = self._base_config(tmp_path)
        metadata = self._base_metadata("KAVR-001", "VR Test Title", tags=["單體"])

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        # (a) 檔名 stem 結尾 _mkx200_LR
        new_path = Path(result["new_filename"])
        stem = new_path.stem
        assert stem.endswith("_mkx200_LR"), (
            f"VR tail _mkx200_LR 未接到 stem 尾：{stem!r}"
        )

        # (b) NFO 含恰一個 <tag>VR</tag> + 一個 <genre>VR</genre>
        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        assert Path(nfo_path).exists(), f"NFO 檔不存在：{nfo_path}"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO 應含恰一個 <tag>VR</tag>，count={nfo_content.count('<tag>VR</tag>')}"
        )
        assert nfo_content.count("<genre>VR</genre>") == 1, (
            f"NFO 應含恰一個 <genre>VR</genre>，count={nfo_content.count('<genre>VR</genre>')}"
        )

        # (c) NFO sidecar 檔名 stem 與影片 stem 對齊（VR tail 隨行，prove GB）
        nfo_stem = Path(nfo_path).stem
        assert nfo_stem == stem, (
            f"NFO sidecar stem({nfo_stem!r}) 應與影片 stem({stem!r}) 完全對齊"
        )
        assert nfo_stem.endswith("_mkx200_LR"), (
            f"NFO sidecar stem 應帶 VR tail：{nfo_stem!r}"
        )


    # ---- T4 DoD: 無 VR 檔（SIVR-999.mp4）端到端 ----


    # ---- Codex P2 修正（Finding 1）：中文標題 VR token 雙寫 ----

    def test_chinese_title_vr_no_double_write(self, tmp_path):
        """ABC-123 中文標題_180_LR.mp4 + create_nfo=True + extracted_title 路徑
        → 檔名 stem 僅有單一 _180_LR（不雙寫 _180_LR_180_LR）
        且 NFO sidecar stem 也單一 tail、<tag>VR</tag> count==1。

        Codex P2（Finding 1）：extract_chinese_title 保留 VR token 在 title，
        之後 vr_tail 再接一次 → _180_LR_180_LR 雙寫。
        """
        src = tmp_path / "ABC-123 中文標題_180_LR.mp4"
        src.write_bytes(b"zh title vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 80,
            "suffix_keywords": [],
        }
        # metadata title 空字串 → 迫使走 extracted_title 路徑（title_source=='extracted'）
        metadata = {
            "number": "ABC-123",
            "title": "",         # 空 → 不走 original 路徑
            "translated_title": "",  # 空 → 不走 translated 路徑
            "actors": [],
            "tags": ["單體"],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        # title_source 應為 extracted（確認走了 extract 路徑）
        assert result.get("title_source") == "extracted", (
            f"應走 extracted 路徑，實際 title_source={result.get('title_source')!r}"
        )

        new_path = Path(result["new_filename"])
        stem = new_path.stem

        # 關鍵斷言：stem 中 _180_LR 恰好出現一次（不雙寫）
        assert stem.count("_180_LR") == 1, (
            f"_180_LR 應恰好出現 1 次（不雙寫），實際 stem：{stem!r}，count={stem.count('_180_LR')}"
        )
        # stem 應以 _180_LR 結尾
        assert stem.endswith("_180_LR"), (
            f"VR tail 應在 stem 最末，實際 stem：{stem!r}"
        )

        # NFO sidecar：stem 對齊 + <tag>VR</tag> count==1
        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        nfo_stem = Path(nfo_path).stem
        assert nfo_stem == stem, (
            f"NFO sidecar stem({nfo_stem!r}) 應與影片 stem({stem!r}) 對齊"
        )
        assert nfo_stem.count("_180_LR") == 1, (
            f"NFO sidecar stem _180_LR 也應單一，實際：{nfo_stem!r}"
        )
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO <tag>VR</tag> 應恰一個，count={nfo_content.count('<tag>VR</tag>')}"
        )

    # ---- Codex P2 二次修正（Finding 1, P2）：bracket/paren 包 cluster 不雙寫 ----


# ============ spec §4 DoD 補洞：Row 3/8 檔名端到端 ============

class TestVrCrossCheck:
    """spec §4 DoD 表 cross-check 補洞（T4）

    Row 3（WAVR-456_4096x2048_180_sbs.mp4）和 Row 8（KAVR-001_MKX200_lr.mp4）
    只有 T1 偵測層覆蓋，T2/T3/T4 無 organize_file 檔名層驗證。
    本 class 補上 organize_file 層的斷言，使 spec §4 全表每列在組裝層都有覆蓋。
    """

    def _base_config(self, max_filename_length=80):
        return {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": max_filename_length,
            "suffix_keywords": [],
        }

    def _base_metadata(self, number, title, tags=None):
        return {
            "number": number,
            "title": title,
            "actors": [],
            "tags": tags or [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }


# ============ TestOrganizeMultipart — 72b-T5 多段整合測試 ============


class TestOrganizeMultipart:
    """organize_file() 多段（multipart）整合測試（TASK-72b-T5）

    涵蓋：
    A  cd1 外部模式 → 正常 NFO、part_tail 在 stem 末
    B  cd2 外部模式 → 產 NFO、保留封面/poster/fanart、success True
    C  長標題 + cd1 → 不超 max_filename_length 且 -cd1 不被截
    D  防 {suffix} 雙寫（-cd1-cd1 negative）
    E  off 模式 byte-identical（cd2 也照產 NFO）
    F  VR + cd1 → 順序 {vr_tail}-cd1
    G  kodi cd2 → 產 NFO、保留封面
    H  邊界：apartment1（前緣字母不誤命中）
    """

    # ---- 共用 helper ----

    def _ext_config(self, tmp_path=None, ext_mode='jellyfin', max_len=60,
                    suffix_keywords=None, filename_format=None, create_nfo=True):
        cfg = {
            'create_folder': False,
            'filename_format': filename_format or '[{num}] {title}{suffix}',
            'download_cover': True,
            'cover_filename': 'poster.jpg',
            'create_nfo': create_nfo,
            'max_title_length': 50,
            'max_filename_length': max_len,
            'suffix_keywords': suffix_keywords if suffix_keywords is not None
                               else ['-cd1', '-cd2', '-4k', '-uc'],
            'external_manager': ext_mode,
        }
        return cfg

    def _base_metadata(self, number='MIRD-151', title='Test Title', cover='http://fake/cover.jpg'):
        return {
            'number': number,
            'title': title,
            'actors': [],
            'tags': [],
            'maker': 'Studio',
            'date': '2024-01-15',
            'cover': cover,
            'url': '',
        }

    # ---- A: cd1 外部模式 → 正常 NFO、part_tail 在末 ----

    def test_cd1_external_nfo_written_and_part_tail(self, tmp_path):
        """A：外部模式 cd1 → NFO 產出（nfo_path not None），stem 以 -cd1 結尾"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'cd1 content')

        config = self._ext_config()
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result.get('nfo_path') is not None, 'cd1 應產 NFO（nfo_path not None）'

        stem = Path(result['new_filename']).stem
        import re
        assert re.search(r'-cd1$', stem), f'stem 應以 -cd1 結尾，實際：{stem!r}'

        # NFO sidecar stem 也應帶 -cd1
        nfo_stem = Path(result['nfo_path']).stem
        assert re.search(r'-cd1$', nfo_stem), f'NFO stem 應以 -cd1 結尾，實際：{nfo_stem!r}'

    # ---- B: cd2 外部模式 → 產 NFO、保留封面/poster/fanart ----


    # ---- C: 長標題 + cd1 → 不超 max_filename_length 且 part token 不被截 ----


    # ---- D: 防 {suffix} 雙寫 ----

    def test_no_double_cd1_suffix_and_part_tail(self, tmp_path):
        """D：預設 config（suffix_keywords 含 -cd1）+ 外部模式 + cd1 → -cd1 恰一次，無 -cd1-cd1"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'no double')

        # 預設 config：suffix_keywords 含 -cd1，filename_format 含 {suffix}
        config = self._ext_config(suffix_keywords=['-cd1', '-cd2', '-4k', '-uc'])
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result['new_filename']).name
        assert '-cd1-cd1' not in new_name, f'出現雙寫 -cd1-cd1：{new_name!r}'
        assert new_name.count('-cd1') == 1, f'-cd1 應恰出現一次，實際：{new_name!r}'


    # ---- E: off 模式 byte-identical ----


    # ---- F: VR + cd1 → 順序 {base}{vr_tail}-cd1 ----


    # ---- G: kodi cd2 → 保留封面 ----


    # ---- H: 邊界 negative — apartment1 不誤命中 ----


    # ---- I: P1-A 修正 — extracted_title 殘留多段 token 不雙寫（Codex P1-A）----


# ══════════════════════════════════════════════════════════════════════════════
# 72c-simplify：kodi == jellyfin (emby)（stem 長格式，無 per-folder 切換）
# ══════════════════════════════════════════════════════════════════════════════


class TestKodiStemNamingOrganize:
    """kodi 模式固定使用 stem 長格式，與 jellyfin/emby 行為完全相同"""

    def _make_kodi_config(self, create_folder: bool, folder_layers=None) -> dict:
        cfg = {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "external_manager": "kodi",
        }
        if folder_layers is not None:
            cfg["folder_layers"] = folder_layers
        return cfg

    def _make_kodi_metadata(self, number: str = "SONE-205", actors=None) -> dict:
        return {
            "number": number,
            "title": "Test Title",
            "actors": actors or [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }


# ============ 站1接線測試 (TASK-101a-T2 DoD①④) ============


def _t2_oracle_poster_bytes(fixture_path, focal_xy=MOCK_FOCAL_XY):
    """獨立 oracle：不經過 crop_to_poster / 任何一站的呼叫鏈，直接以「只平移既有窗」
    契約（整數 crop_w + focal 平移 x0）算出「應該要平移到焦點」的期望 bytes。不可用
    「同一站流程呼叫兩次自我比對」——對「呼叫端忘了傳 number/maker」這類 mutation
    結構性瞎眼（gotchas-backend.md #9，101a-T1 已踩過）。

    TASK-102c-T1：改吃 focal_xy 參數（預設 MOCK_FOCAL_XY），不再自己呼叫真
    detect_focal——呼叫端須確保 patch `core.organizer.run_detection` 回傳
    `RunnerOutcome(kind="FOUND", focal=同一個值)`，否則 production 端與 oracle 端會對不上。
    """
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    focal = focal_xy
    with Image.open(fixture_path) as img:
        # 101a P2-1（Codex PR#110）：oracle 改為「只平移既有窗」的真實契約（見 crop_to_poster）——
        # 不再經 crop_image_position 的 float ratio→px round-trip（±1px 改窗寬、已棄用）。
        crop_w = int(h / 1.5) if (h / w) >= 1.0 else (w - int(w / 1.9))
        x0 = max(min(int(w * focal[0]) - crop_w // 2, w - crop_w), 0)
        expected_cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
    buf = io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


class TestOrganizeFileStationWiring:
    """DoD①：站1（core/organizer.py organize_file）接線——真跑 organize_file()，
    fixture A（番號驅動）+ fixture B（maker-only 驅動）各一次，poster 依焦點裁，
    斷言輸出 bytes 等於獨立 oracle（不可自我比對）。

    DoD④ 的站1 number/maker 軸 mutation 皆對這兩個測試單獨驗證（見 TASK card）。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}  # 番號驅動，maker 非白名單
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}  # maker-only 驅動，白名單原樣照抄

    @staticmethod
    def _mock_download_fixture_face(url, save_path, referer=''):
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        Path(save_path).write_bytes(src.read_bytes())
        return True

    def _run_station1(self, tmp_path, tag, fixture):
        src = tmp_path / f"{fixture['number']}_{tag}.mp4"
        src.write_bytes(b"fake mp4")
        config = _make_jellyfin_config(jellyfin_mode=True)
        metadata = {
            "number": fixture["number"],
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": fixture["maker"],
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }
        with patch("core.organizer.download_image", side_effect=self._mock_download_fixture_face), \
             patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("poster_path") is not None, "station1 應產生 poster_path"
        poster_bytes = Path(result["poster_path"]).read_bytes()
        expected = _t2_oracle_poster_bytes(_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg", MOCK_FOCAL_XY)
        assert poster_bytes == expected, "station1 poster 應對準焦點（獨立 oracle 比對）"

    def test_station1_fixture_a(self, tmp_path):
        self._run_station1(tmp_path, "a", self._FIXTURE_A)


# ============ containment 防線測試（TASK-110b-T4） ============

class TestOrganizeContainment:
    """
    organize_file() containment 防線測試 — 阻擋 metadata（actors 等）帶 '..' 逃出
    original_dir，同時確認不誤殺含 '.' 的合法片名（CD-110b-2／CD-110b-8）。
    """

    def test_actors_dotdot_escape_blocked(self, tmp_path):
        """
        actors 三個 ".."（3 層資料夾格式）→ target_dir 逃出 original_dir。
        必須：result['error'] 非空、不寫任何檔案、原始檔仍在原位、逃逸目標無新檔案。
        （feedback_reproduce_over_reasoning：斷言檔案系統實際狀態，不只斷言回傳值）
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"original content")

        config = _make_config(tmp_path)
        config["create_folder"] = True
        config["folder_layers"] = ["{actor}", "{actor}", "{actor}"]
        metadata = _make_metadata()
        metadata["actors"] = ["..", "..", ".."]

        escape_target = tmp_path.parent.parent.parent
        escaped_file = escape_target / "[SONE-205] Test Title.mp4"

        before = sorted(p.name for p in tmp_path.iterdir())

        result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"], "應回傳非空錯誤訊息"
        # 無半完成狀態：拒絕路徑的 result 欄位必須與正常失敗分支一致
        assert result["new_folder"] is None, "拒絕時不應已記下 new_folder"
        assert result["cover_path"] is None
        assert result["nfo_path"] is None

        # 原始檔仍在原位，未被搬走
        assert src.exists(), "原始檔案不應被移動或刪除"
        assert src.read_bytes() == b"original content"

        # 逃逸目標位置不存在任何新檔案（重現定案，不用推理）
        assert not escaped_file.exists(), "逃逸目標不應出現新檔案"

        # original_dir 內容未變（沒有半完成的資料夾/檔案殘留）
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after, "original_dir 內容不應因拒絕而改變"

    def test_cross_drive_mocked_rejected(self, tmp_path):
        """
        跨 drive 情境：mock is_fs_path_under_dir 直接回 False（模擬 containment
        判定為「不在範圍內」後的結果），即使檔名/actors 完全正常也必須拒絕。

        註：跨 drive 在現行演算法下是正常、無例外的 False 判定（不再經由
        commonpath 的 ValueError），本測試鎖的是「拒絕之後呼叫端怎麼做」，
        與判定是怎麼得出來的無關。
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"original content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        with patch("core.organizer.is_fs_path_under_dir", return_value=False):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"], "跨 drive 應回傳非空錯誤訊息"
        assert src.exists(), "原始檔案不應被移動"
        # 無半完成狀態（同 test_actors_dotdot_escape_blocked）
        assert result["new_folder"] is None, "拒絕時不應已記下 new_folder"
        assert result["cover_path"] is None
        assert result["nfo_path"] is None

    def test_dotted_title_not_misfired(self, tmp_path):
        """
        合法片名含 '.'（如 'Vol.2'）不應被 containment 檢查誤殺，資料夾層也含 '.'。
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"original content")

        config = _make_config(tmp_path)
        config["create_folder"] = True
        config["folder_layers"] = ["{title}"]
        metadata = _make_metadata(title="Vol.2")

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"不應誤殺合法片名：{result.get('error')}"
        target_dir = tmp_path / "Vol.2"
        assert target_dir.is_dir()
        assert (target_dir / "[SONE-205] Vol.2.mp4").exists()
        assert not src.exists(), "原始檔應已被搬移"


    def test_unc_bare_share_root_allowed(self, monkeypatch):
        """UNC bare share root：\\\\server\\share 底下的 candidate 必須放行。

        TASK-147a-T2 / CD-147a-7：直接驅動 _containment_error()，用 Windows-style
        mock harness（ntpath realpath/normcase/sep）真的走到 is_fs_path_under_dir
        的前綴比對——不得 mock is_fs_path_under_dir 本身。
        """
        import ntpath
        import types
        import core.path_utils as path_utils
        from core.organizer import _containment_error
        from tests.unit.test_path_utils import _PartialOsPathProxy

        fake_os = types.SimpleNamespace(path=_PartialOsPathProxy(
            realpath=ntpath.realpath,
            normcase=ntpath.normcase,
            sep=ntpath.sep,
        ))
        monkeypatch.setattr(path_utils, 'os', fake_os)
        assert _containment_error(r'\\server\share\x', r'\\server\share') is None


# ============ TASK-126-T4b：代理網址走到 organize 的下載點 ============
#
# owner 2026-08-23 裁決把 organize 這條也納入。**但只有「後端重刮」那條會有值**——
# 前端送來的 metadata 已被 buildOrganizeMetadata() 剝除兩個 preview 欄位
# （TASK-126-T3 / 113c-T3b：那是只對顯示有意義、會隨 metatube 連線狀態失效的網址）。
# 所以下面兩支測的是「metadata 帶得動就用得到」與「帶不動就跟今天一樣」。

class TestT4bOrganizeFallback:

    def _clear_failed_hosts(self):
        import core.organizer as org
        with org._failed_hosts_lock:
            org._failed_hosts.clear()

    def _resp(self, content):
        m = MagicMock()
        m.status_code = 200
        m.content = content
        return m

    def _blocked_unless_proxy(self):
        import requests as _rq

        def _side(url, **kwargs):
            if 'mt.example' in url:
                return self._resp(b'PROXY' + b'\x00' * 2000)
            raise _rq.exceptions.ConnectTimeout('blocked')
        return _side

    def test_organize_cover_uses_preview_fallback(self, tmp_path):
        """邊界 4：organize 入口，原址 ConnectTimeout ＋ metadata 帶得動 preview → 走代理落地。"""
        self._clear_failed_hosts()
        try:
            src = tmp_path / 'ABC-123.mp4'
            src.write_bytes(b'v' * 100)
            metadata = {
                'number': 'ABC-123', 'title': 'T', 'actors': [], 'tags': [],
                'cover': 'https://cdn.blocked/cover.jpg',
                'preview_cover_url': 'http://mt.example/v1/images/primary/MGS/ABC-123?url=cover',
            }
            config = {'output_dir': str(tmp_path / 'out'), 'create_folder': True,
                      'download_cover': True, 'create_nfo': False}
            with patch('core.organizer.requests.get', side_effect=self._blocked_unless_proxy()):
                result = organize_file(str(src), metadata, config)
            assert result.get('cover_path'), '封面應經由代理落地'
            assert open(result['cover_path'], 'rb').read().startswith(b'PROXY')
        finally:
            self._clear_failed_hosts()


# ============ TASK-126 Codex PR review P2-1：preview_* 傳得過去，但不得持久化 ============
#
# 113c-T3b 立的規矩逐字是「preview_* **不能落磁碟**」；當時用「連傳都不傳」達成它。
# 126 把兩件事分開：**傳遞是必要的**（搜尋後按「產生」是最常走的入庫路徑，後端不重新搜尋，
# 不傳等於被牆的使用者永遠拿不到代理退路），**不落磁碟仍然是不變式**——由這個 class 直接驗。
#
# 這是把守衛從「代理指標」（有沒有被傳）換成「真正的不變式」（有沒有被寫下去）。

class TestT6PreviewNotPersisted:
    """preview_* 進得了 POST metadata，但不得出現在 NFO 或任何落磁碟的產物裡。"""

    def _clear_failed_hosts(self):
        import core.organizer as org
        with org._failed_hosts_lock:
            org._failed_hosts.clear()

    _PROXY = 'http://mt.example/v1/images/primary/MGS/ABC-777?url=https%3A%2F%2Fcdn%2Fc.jpg'

    def _metadata(self):
        return {
            'number': 'ABC-777', 'title': 'T', 'actors': ['A'], 'tags': ['t1'],
            'date': '2024-01-01', 'maker': 'M', 'director': 'D', 'series': 'S',
            'label': 'L', 'duration': 120, 'url': 'https://example/detail',
            'cover': 'https://cdn/c.jpg',
            'sample_images': ['https://cdn/s1.jpg'],
            'preview_cover_url': self._PROXY,
            'preview_sample_images': [self._PROXY + '&i=1'],
        }


    def test_preview_urls_never_appear_in_any_written_file(self, tmp_path):
        """更寬的一道：整個輸出資料夾裡的**任何文字檔**都不得含代理網址。

        比只驗 NFO 多守住「日後有人新增別的 sidecar 產物」的情況。
        """
        self._clear_failed_hosts()
        try:
            src = tmp_path / 'ABC-777.mp4'
            src.write_bytes(b'v' * 100)
            config = {'output_dir': str(tmp_path / 'out'), 'create_folder': True,
                      'download_cover': True, 'create_nfo': True,
                      'download_sample_images': True}
            with patch('core.organizer.requests.get',
                       return_value=self._resp_ok()):
                result = organize_file(str(src), self._metadata(), config)

            # ⚠️ organize_file 的產出落在**來源檔旁邊**（`src.parent/<folder>/`），
            # **不是** `output_dir` 底下。初版掃 `out/` 掃到一個空資料夾 ⇒ 假綠。
            # （Opus 自驗 mutation 時抓到：往 NFO 注入代理網址後這支竟然沒紅。）
            scan_root = Path(result['new_folder'])
            assert scan_root.exists(), '沒有產出資料夾就代表這條什麼都沒驗到'
            assert any(scan_root.rglob('*.nfo')), '沒有 NFO 就代表這條什麼都沒驗到'

            offenders = []
            for p in scan_root.rglob('*'):
                if not p.is_file():
                    continue
                try:
                    text = p.read_text(encoding='utf-8')
                except (UnicodeDecodeError, OSError):
                    continue  # 圖片等二進位檔不看
                if 'mt.example' in text or '/v1/images/' in text:
                    offenders.append(str(p))
            assert offenders == [], f'這些落磁碟的檔案含有代理網址：{offenders}'
        finally:
            self._clear_failed_hosts()


    def _resp_ok(self):
        m = MagicMock()
        m.status_code = 200
        m.content = b'IMG' + b'\x00' * 2000
        return m


class TestOrganizeFileSummaryRating:
    """T3 端到端證據：organize_file() 收到 _summary/_rating 時，NFO 確實寫出對應內容（或維持空白）。"""

    def test_organize_file_summary_rating_written_to_nfo_when_source_has_values(self, tmp_path):
        src = tmp_path / 'ABC-777.mp4'
        src.write_bytes(b'v' * 100)
        metadata = {
            'number': 'ABC-777', 'title': 'T', 'actors': [], 'tags': [],
            'date': '2024-01-01', 'maker': 'M', 'director': 'D', 'series': 'S',
            'label': 'L', 'duration': 120, 'url': 'https://example/detail',
            '_summary': 'A great movie plot summary.',
            '_rating': 4.5,
        }
        config = {'output_dir': str(tmp_path / 'out'), 'create_folder': True}
        result = organize_file(str(src), metadata, config)
        assert result['success'] is True
        nfo_path = result.get('nfo_path')
        assert nfo_path
        content = open(nfo_path, encoding='utf-8').read()
        assert '<plot>A great movie plot summary.</plot>' in content
        assert '<rating>9.0</rating>' in content

    def test_organize_file_summary_rating_blank_when_source_has_no_values(self, tmp_path):
        src = tmp_path / 'XYZ-999.mp4'
        src.write_bytes(b'v' * 100)
        metadata = {
            'number': 'XYZ-999', 'title': 'T2', 'actors': [], 'tags': [],
            'date': '2024-01-01', 'maker': 'M', 'director': 'D', 'series': 'S',
            'label': 'L', 'duration': 120, 'url': 'https://example/detail',
            '_summary': '',
            '_rating': None,
        }
        config = {'output_dir': str(tmp_path / 'out'), 'create_folder': True}
        result = organize_file(str(src), metadata, config)
        assert result['success'] is True
        nfo_path = result.get('nfo_path')
        content = open(nfo_path, encoding='utf-8').read()
        assert '<plot></plot>' in content
        assert '<rating>' not in content


class TestVideosSchemaHasNoNfoCarrierColumns:
    """T3 案例 c：videos 表結構性不含 summary/rating 欄位（CD-147c-3 的機械化版本）。"""

    def test_videos_table_schema_has_no_nfo_carrier_columns(self, tmp_path):
        import sqlite3
        from core.database.connection import init_db

        db_path = tmp_path / 'schema_probe_147c.db'
        init_db(db_path)
        with sqlite3.connect(str(db_path)) as conn:
            cols = [r[1] for r in conn.execute('PRAGMA table_info("videos")')]
        for forbidden in ('summary', 'rating'):
            assert forbidden not in cols, (
                f'videos 表出現了 {forbidden!r} 欄位——_summary/_rating 是搜尋結果的 NFO carrier，'
                f'結構性不應該進 DB（spec §3.3），這是它第一次可能被誤加的機械警報'
            )


class TestCropToPosterAbandonedDegrade:
    """DoD②：路徑④ 收到 ABANDONED 時仍寫出 poster，bytes 與同圖 NO_FACE 退化路逐位元相同。

    ABANDONED 不得早退／跳過寫檔——與 NO_FACE 共用「focal 保持 None」的既有裁切路徑。
    """

    def _assert_abandoned_matches_no_face(self, tmp_path, reason: str):
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        dst_abandoned = tmp_path / f"abandoned_{reason}.jpg"
        dst_no_face = tmp_path / f"no_face_{reason}.jpg"

        with patch(
            "core.organizer.run_detection",
            return_value=RunnerOutcome(kind="ABANDONED", reason=reason),
        ):
            result = crop_to_poster(str(src), str(dst_abandoned), number="FC2-1234567")
        assert result is True
        assert dst_abandoned.exists()

        with patch(
            "core.organizer.run_detection",
            return_value=RunnerOutcome(kind="NO_FACE"),
        ):
            assert crop_to_poster(str(src), str(dst_no_face), number="FC2-1234567") is True

        assert dst_abandoned.read_bytes() == dst_no_face.read_bytes()

    def test_abandoned_detect_timeout_matches_no_face(self, tmp_path):
        self._assert_abandoned_matches_no_face(tmp_path, "detect_timeout")


class TestNfoTitleFormatWiring:
    """TASK-154b-T2: organize_file NFO 標題接線與截斷修復測試"""

    def test_organize_file_nfo_title_untruncated_but_filename_truncated(self, tmp_path):
        """CD-154b-5: 標題超過 max_title_length(50) 時，檔名截斷但 NFO <title> 保持完整 60 字元"""
        src = tmp_path / "ABC-123.mp4"
        src.write_bytes(b"dummy video")

        long_title = "T" * 60
        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 200,
        }
        metadata = {
            "number": "ABC-123",
            "title": long_title,
            "actors": [],
            "tags": [],
            "maker": "",
            "date": "2024-01-01",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("new_filename") is not None
        assert "T" * 60 not in result["new_filename"], "檔名標題應被截斷"
        assert "T" * 47 + "..." in result["new_filename"], "檔名應包含截斷後的 47 字元加上省略號"

        assert result.get("nfo_path") is not None
        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert f"<title>[ABC-123]{long_title}</title>" in nfo_content, (
            "NFO 中的 <title> 應包含完整未截斷的 60 字元標題"
        )

    def test_organize_file_applies_custom_nfo_title_format(self, tmp_path):
        """自訂 nfo_title_format 應套用到產出的 NFO <title>"""
        src = tmp_path / "ABC-123.mp4"
        src.write_bytes(b"dummy video")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "nfo_title_format": "{num}-{title}",
        }
        metadata = {
            "number": "ABC-123",
            "title": "My Title",
            "actors": [],
            "tags": [],
            "maker": "",
            "date": "2024-01-01",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("nfo_path") is not None
        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "<title>ABC-123-My Title</title>" in nfo_content, (
            "NFO 中的 <title> 應套用自訂格式 {num}-{title}"
        )



# ============ crop_to_poster: 外部端點焦點是轉正座標 (187a Codex review) ============

def _exif6_cover(path):
    """顯示 500x400（臉塊 x350-450,y100-300 紅）；存成 400x500 + Orientation=6。"""
    shown = Image.new("RGB", (500, 400), (255, 255, 255))
    shown.paste((255, 0, 0), (350, 100, 450, 300))
    stored = shown.rotate(90, expand=True)  # CCW，EXIF 6 會再 CW 轉回
    exif = Image.Exif()
    exif[0x0112] = 6
    stored.save(path, "JPEG", quality=100, subsampling=0, exif=exif)


def _red_count(im):
    return sum(1 for r, g, b in im.convert("RGB").getdata() if r > 200 and g < 80 and b < 80)


def test_crop_to_poster_external_focal_uses_transposed_frame(tmp_path):
    src, dst = tmp_path / "c.jpg", tmp_path / "p.jpg"
    _exif6_cover(src)
    ext = RunnerOutcome(kind="FOUND", focal=(0.8, 0.5), model="m1")
    with patch("core.organizer.run_detection", return_value=ext):
        assert crop_to_poster(str(src), str(dst), number="FC2-1234567") is True
    with Image.open(dst) as out:
        assert out.size == (237, 400)
        assert _red_count(out) >= 0.9 * 20000


def test_crop_to_poster_local_focal_keeps_untransposed_frame(tmp_path):
    src, dst = tmp_path / "c.jpg", tmp_path / "p.jpg"
    _exif6_cover(src)
    local = RunnerOutcome(kind="FOUND", focal=(0.8, 0.5))
    with patch("core.organizer.run_detection", return_value=local):
        assert crop_to_poster(str(src), str(dst), number="FC2-1234567") is True
    with Image.open(dst) as out, Image.open(src) as raw:
        assert out.size == (333, 500)
        from PIL import ImageChops
        expect = raw.convert("RGB").crop((67, 0, 400, 500))
        assert max(hi for _, hi in ImageChops.difference(out.convert("RGB"), expect).getextrema()) < 60
