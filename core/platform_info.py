"""core/platform_info.py — 平台環境訊號偵測模組（TASK-159-T3）"""
import os

from core.desktop_env import desktop_kind

DSM_PERMISSION_HINT = "片庫是 DSM 共用資料夾：控制台 → 共用資料夾 → 編輯 → 權限 → 系統內部使用者帳號 → openaver-svc 勾可讀寫；片庫是掛載的遠端資料夾：除了上面那步，也要到提供分享的那台機器確認權限"

LINUX_PERMISSION_HINT = "執行 OpenAver 的 Linux 使用者要對這個資料夾有讀寫權限：用 ls -ld <資料夾路徑> 看擁有者與權限，必要時 chown／chmod，或把該使用者加進擁有這個資料夾的群組；片庫是掛載的遠端資料夾：也要到提供分享的那台機器確認權限"


def is_synology() -> bool:
    """判斷這台機器是不是從 spk 裝起來的 Synology 版。

    讀取由 start-stop-status 腳本設定的 OPENAVER_SYNOLOGY 環境變數。
    """
    return os.environ.get("OPENAVER_SYNOLOGY") == "1"


def is_headless_server() -> bool:
    """判斷是不是無頭 Linux 伺服器版（含 Synology 版）。

    讀取由啟動腳本設定的 OPENAVER_SERVER_ONLY 環境變數，或沿用 is_synology()。
    """
    return os.environ.get("OPENAVER_SERVER_ONLY") == "1" or is_synology()


def server_kind() -> str:
    """伺服器種類，供 /api/client/hello 回報：synology／windows／mac／linux。"""
    return "synology" if is_synology() else (desktop_kind() or "linux")
