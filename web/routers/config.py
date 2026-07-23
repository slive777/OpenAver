"""
設定 API 路由

端點：
- GET    /api/config                    — 取得所有設定
- PUT    /api/config                    — 更新所有設定
- DELETE /api/config                    — 恢復原廠設定（刪除 config.json）
- GET    /api/tutorial-status           — 取得新手引導完成狀態
- POST   /api/tutorial-completed        — 標記新手引導已完成
- POST   /api/tutorial-reset            — 重置新手引導狀態
- PUT    /api/config/general/{field}    — 更新 general 區塊單一欄位（sidebar_collapsed/theme/font_size）
- GET    /api/version                   — 取得應用程式版本資訊
- GET    /api/config/format-variables   — 取得刮削路徑/檔名格式可用變數
- GET    /api/ollama/models             — 取得 Ollama 可用模型列表
- POST   /api/ollama/test               — 測試 Ollama 模型是否能正常回應
- POST   /api/proxy/test                — 測試 Proxy 連線（透過 DMM 驗證）
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, StrictBool, StrictStr
from typing import Literal
from pathlib import Path
import asyncio
import httpx
import threading

from core.logger import get_logger
from core.config import (
    AppConfig,
    load_config,
    mutate_config,
    reset_config_file,
    iter_gallery_sources,
)
from core.database import VideoRepository, get_db_path, init_db
from core import thumbnail_cache
from core.path_utils import uri_to_fs_path, reverse_path_mapping, CURRENT_ENV
from core.generate_state import (
    try_begin_switch,
    end_switch,
    try_begin_config_save,
    end_config_save,
    is_generate_in_progress,
)
from core.readonly_source import is_path_readonly, _canonical_source_prefix
from core.readonly_producer import _write_strm
from core.source_config import MAX_ENABLED_SOURCES
from core.translate_service import LANGUAGE_PROMPTS

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["config"])

# 序列化「server_mode 切換交易」的單一鎖（Codex P2）：toggle（start/persist/stop）與
# reset（clear/stop）共用此鎖，避免併發 enable/disable/reset 交錯導致 config↔listener
# 分離（如 stale enable 在 disable 之後才寫回 true）。鎖序：本鎖 → _config_write_lock
# →lan_listener._lock（單向，無死鎖）。本機端點、執行於 threadpool，故用 threading.Lock。
_server_mode_toggle_lock = threading.Lock()

# Import reset function (避免循環導入，在需要時才導入)
def _reset_translate_service():
    """延遲導入並調用 reset_translate_service()"""
    from web.routers.translate import reset_translate_service
    reset_translate_service()


@router.get("/config")
def get_config() -> dict:
    """取得所有設定"""
    return {"success": True, "data": load_config()}


@router.put("/config")
def update_config(config: AppConfig) -> dict:
    """更新所有設定"""
    # PR #93 P2-e：整份設定儲存納入 switch 互斥窗口（owner 拍板：互斥鎖）。否則另一分頁帶
    # 「切模式前的舊 directories 快照」的整份存檔會與 purge 交錯、把剛被 purge 的離線來源
    # 條目寫回 gallery.directories（DB 卡已刪）→ 殭屍條目。
    # 上一輪的 is_switch_in_progress() preflight 是 TOCTOU（存檔可在 switch 開始前通過檢查、
    # 卻在 switch 做完後才落盤）→ 改真互斥：儲存持有 _config_save_active 整段窗口，
    # try_begin_switch 見此旗標即拒絕；兩者同一 _lock 下原子、不交錯。end_config_save 必於 finally。
    # 已知殘留（owner 接受）：切換「已完全做完」後才到達的舊快照存檔仍會覆寫（純 lost-update、
    # 非交錯，任何 mutex 都擋不到），靠切模式破壞性 confirm 的「其他分頁請重整」提示兜底；
    # 次秒級、可自癒（重 generate 重建卡）、無資料損毀。
    # 只擋整份存檔；update_general_field 只寫單一 general 欄位、不碰 directories → 不納入。
    # PR #93 五審三次 P2（owner 拍板：精準 gate）：掃描/產生進行中，禁止「有動到 strm 播放
    # 映射」的整份存檔。generate 起始時把 config 凍結一場沿用（scanner.generate_avlist 一次
    # load_config → produce_source 全程用該快照），若中途改 scraper.strm_path_mappings 存檔，
    # 該次 generate 之後才產出的 .strm 仍用舊映射，且無任何東西會再自動重寫它們（rewrite 只修
    # 當下已在 DB 的片）→ 靜默半修、永久指錯播放端路徑。精準只擋「真的動到映射」的存檔：
    # is_generate_in_progress() 短路後才 load_config diff，改主題/檔名等其他設定不受影響。
    # 點對點檢查（非全互斥），微秒級殘留窗口同 P2-e 已知限制等級（generate 若在 check 與
    # mutate_config 間隙才起跑，屬同類可接受殘留；掃描本就秒級以上、幾乎不觸發）。
    if is_generate_in_progress() and (
        config.scraper.strm_path_mappings
        != load_config().get("scraper", {}).get("strm_path_mappings", {})
    ):
        return {"success": False, "reason": "generate_in_progress_strm_mapping",
                "error": "掃描／產生進行中，請完成後再修改媒體伺服器播放路徑映射。"}
    save_token = object()  # 每 request 唯一身份 token（比照 generate 的 _active_tokens）
    reason = try_begin_config_save(save_token)
    if reason is not None:
        return {"success": False, "reason": reason,
                "error": "設定切換中，請稍後再儲存。"}
    try:
        # Cap 守衛（CD-61-16，endpoint-level；非 model_validator）：
        # 同時啟用且非 manual_only 的來源數不得超過 MAX_ENABLED_SOURCES。
        # 防止前端繞過 UI 直接 PUT。manual_only 不計入 cap basis（CD-61-17）。
        cap_basis = sum(1 for s in config.sources if s.enabled and not s.manual_only)
        if cap_basis > MAX_ENABLED_SOURCES:
            raise HTTPException(
                status_code=400,
                detail={"error": "cap_exceeded", "max": MAX_ENABLED_SOURCES},
            )
        try:
            payload = config.model_dump()
            # server_mode is toggle-lifecycle state owned exclusively by
            # PUT /api/config/general/server_mode (which calls lan_listener.start/stop
            # atomically with the persist). A full-config save must NEVER overwrite the
            # currently-persisted value — whether the incoming payload omits the field
            # (Pydantic default → False) or contains a stale/incorrect value.
            # Read the canonical persisted value inside mutate_config so the
            # read-preserve-write is atomic under _config_write_lock.
            def _write_preserving_server_mode(cfg: dict) -> None:
                current_server_mode = cfg.get("general", {}).get("server_mode", False)
                payload["general"]["server_mode"] = current_server_mode
                cfg.update(payload)

            mutate_config(_write_preserving_server_mode)
            _reset_translate_service()  # 重置翻譯服務，讓新配置生效
            return {"success": True, "message": "設定已儲存"}
        except Exception as e:
            logger.error("儲存設定失敗: %s", e)
            return {"success": False, "error": "儲存設定失敗"}
    finally:
        end_config_save(save_token)


@router.delete("/config")
def reset_config() -> dict:
    """恢復原廠設定 - 刪除 config.json"""
    try:
        # reset 清除 server_mode（defaults → false）→ listener 必須同步停止，否則
        # runtime（listener 跑）≠ persisted 分離。clear+stop 與 toggle 交易共用
        # _server_mode_toggle_lock 序列化（Codex P2），防 reset 與併發 enable 交錯。
        # stop() idempotent：listener 未跑時 no-op，安全。
        from web.lan_listener import lan_listener
        with _server_mode_toggle_lock:
            reset_config_file()  # 鎖內 exists/unlink，無 TOCTOU（CD-66b-1）
            lan_listener.stop()
        _reset_translate_service()  # 清除舊服務實例（與 server_mode 無關，鎖外）
        return {"success": True, "message": "已恢復預設設定"}
    except Exception as e:
        logger.error("恢復預設設定失敗: %s", e)
        return {"success": False, "error": "恢復預設設定失敗"}


@router.get("/tutorial-status")
def get_tutorial_status() -> dict:
    """取得新手引導完成狀態"""
    config = load_config()
    completed = config.get("general", {}).get("tutorial_completed", False)
    return {"success": True, "completed": completed}


@router.post("/tutorial-completed")
def mark_tutorial_completed() -> dict:
    """標記新手引導已完成（僅在點擊完成時呼叫）"""
    def _mut(cfg):
        cfg.setdefault("general", {})["tutorial_completed"] = True
    mutate_config(_mut)
    return {"success": True}


@router.post("/tutorial-reset")
def reset_tutorial() -> dict:
    """重置新手引導狀態（供設定頁使用）"""
    def _mut(cfg):
        cfg.setdefault("general", {})["tutorial_completed"] = False
    mutate_config(_mut)
    return {"success": True}


class GeneralFieldRequest(BaseModel):
    # StrictBool | StrictStr：strict union 不做型別強制 —— JSON true/false → bool，
    # 字串 → str，數字（如 1）兩者皆不接受 → Pydantic 422。藉此讓 server_mode 的整數
    # 輸入在 schema 層即被擋（避免 `1` 被 lax 模式悄悄轉成 True）。既有 str/bool 欄位
    # （theme/locale/font_size/sidebar_collapsed）值型別本就符合，無回歸。
    value: StrictBool | StrictStr


@router.put("/config/general/{field}")
def update_general_field(field: str, request: GeneralFieldRequest, raw_request: Request) -> dict:
    """更新 general 區塊單一欄位（輕量端點，供 UI toggle 即時同步）

    註：保持同步 def —— body 內 mutate_config 走檔案 I/O，依 async-offload 守衛
    （feature/71）須在 Starlette threadpool 執行，不可改 async def 卡 event loop。
    """
    allowed = {"sidebar_collapsed", "theme", "font_size", "locale", "server_mode", "auto_check_update"}
    if field not in allowed:
        return {"success": False, "error": f"不允許更新欄位: {field}"}
    try:
        # server_mode 嚴格 bool 驗正（TASK-80a-T1）：StrictBool|StrictStr 已擋整數，
        # 此處再擋字串 —— 關鍵安全性：字串 "false" 是 truthy，若存進 config 會讓
        # middleware `bool(server_mode)` 誤判為開啟對外。非 bool 字串 → 400。
        if field == "server_mode" and not isinstance(request.value, bool):
            raise HTTPException(status_code=400, detail="server_mode 必須為布林值")

        # auto_check_update 布林語意欄位擋字串 truthy 反轉（Codex P2），比照 server_mode：
        # 字串 "false" 是 truthy，若落盤 lifespan `not "false"`=False 會誤判 gate 通過、
        # help data-attr 也誤算 true → 使用者關閉卻被當開啟。非 bool → 400。
        if field == "auto_check_update" and not isinstance(request.value, bool):
            raise HTTPException(status_code=400, detail="auto_check_update 必須為布林值")

        # server_mode 是主機決定，遠端連入的客人不得切換（spec「遠端自鎖不防護」的更乾淨版本）。
        # 僅允許 loopback 來源切換；fail-closed：client None → 視為非 loopback → 拒絕。
        # 不信任 X-Forwarded-For，純用 TCP 對端 raw_request.client.host。
        if field == "server_mode":
            _client = raw_request.client
            _client_host = _client.host if _client else None
            if _client_host not in ("127.0.0.1", "::1"):
                logger.warning(
                    "拒絕非本機切換 server_mode（來源 %s）：僅主機可切換", _client_host
                )
                # reason 供前端對應專屬 i18n 訊息（remote_only），而非通用「請稍後再試」
                return {"success": False, "reason": "remote_forbidden",
                        "error": "server_mode 僅能在主機本機切換"}

        # server_mode 專屬分支：start/stop LAN listener，確保 runtime ≠ persisted 不分離。
        # 整個交易在 _server_mode_toggle_lock 內序列化（Codex P2）：防併發 enable/disable
        # /reset 交錯（如 stale enable 在 disable 之後才寫回 true → config 開、listener 關）。
        if field == "server_mode":
            from web.lan_listener import lan_listener
            with _server_mode_toggle_lock:
                if request.value is True:
                    # Enable 順序：先 start()（失敗→乾淨回傳，config 不變），再 persist。
                    # persist 失敗→ rollback stop()（best-effort）避免 listener ON / config false。
                    try:
                        lan_port = lan_listener.start()
                    except Exception as e:                    # noqa: BLE001
                        logger.error("server_mode 啟用失敗: %s", e)
                        return {"success": False, "error": "無法啟動 LAN 伺服器"}
                    try:
                        mutate_config(lambda cfg: cfg.setdefault("general", {}).update({"server_mode": True}))
                    except Exception as e:                    # noqa: BLE001
                        # Rollback：listener 已啟動但 config 寫入失敗 → 停止 listener 保持一致
                        logger.error("server_mode persist 失敗，rollback stop(): %s", e)
                        try:
                            lan_listener.stop()
                        except Exception:                     # noqa: BLE001,S110 — rollback best-effort
                            pass
                        return {"success": False, "error": "無法儲存伺服器模式設定"}
                    from web.lan_listener import get_lan_ip
                    lan_ip = get_lan_ip()
                    return {"success": True, "lan_port": lan_port, "lan_ip": lan_ip}
                else:
                    # Disable 順序：先 persist false，再 stop()。
                    # 原因：middleware lan_access_gate 讀 load_config().get("server_mode")，
                    # persist false 後 gate 立即阻擋新 LAN 連線（defense-in-depth），
                    # 即使 stop() 尚未完成也已安全。若 persist 失敗 → config 仍 true，
                    # listener 仍跑，兩者一致（不需 rollback）。
                    try:
                        mutate_config(lambda cfg: cfg.setdefault("general", {}).update({"server_mode": False}))
                    except Exception as e:                    # noqa: BLE001
                        logger.error("server_mode disable persist 失敗: %s", e)
                        return {"success": False, "error": "無法儲存伺服器模式設定"}
                    lan_listener.stop()
                    return {"success": True, "lan_port": None}

        # locale 驗證在 mutate 前（保留既有順序：驗證 → 寫入 → translate reset）
        if field == "locale" and request.value not in ("zh-TW", "zh-CN", "ja", "en"):
            logger.warning("嘗試設定不支援的語系: %s", request.value)
            return {"success": False, "error": "不支援的語系"}

        def _mut(cfg):
            cfg.setdefault("general", {})[field] = request.value
        mutate_config(_mut)

        if field == "locale":
            _reset_translate_service()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新設定欄位失敗: %s", e)
        return {"success": False, "error": "更新設定欄位失敗"}


@router.get("/config/general/lan-port")
def get_lan_port() -> dict:
    """取得 LAN listener 目前使用的 port + LAN IP（server mode 啟用中回值，否則 null）

    lan_ip 獨立於 listener 狀態：IP 可偵測→回真值，IP 不可偵測→回 null。
    搭配前端 `?? null` 清除邏輯：listener 停止但 IP 可偵測 → lanIp 保留、lanPort
    null → 顯示「listener_down」；IP 真的無法偵測 → lanIp null → 顯示「no_lan_ip」。
    """
    from web.lan_listener import lan_listener, get_lan_ip
    running = lan_listener.is_running
    return {
        "lan_port": lan_listener.lan_port if running else None,
        "lan_ip": get_lan_ip(),  # 獨立於 running：null 僅在 IP 真的無法偵測時
    }


class SwitchExternalManagerRequest(BaseModel):
    # 值域必須與 core.config.ScraperConfig.external_manager 完全一致（四值）。
    # 用 Literal-typed model（不收裸 str）：mutator 直接把 body 值寫進 raw dict
    # （不經 AppConfig model_validate），若收裸 str 非法值會靜默落盤。FastAPI 對
    # 非法 Literal 值自動回 422（gotchas-backend「Literal 守不到純 str 入口」72d）。
    external_manager: Literal["off", "jellyfin", "emby", "kodi"]


@router.post("/config/switch-external-manager")
def switch_external_manager(request: SwitchExternalManagerRequest) -> dict:
    """切換全域 external_manager，並破壞性重設離線（唯讀）來源（spec §90b(iv) 真理來源）。

    server-side 原子完成：枚舉離線來源的 DB 卡 → delete_by_paths 刪除 + 縮圖失效 →
    mutate_config 原子移除離線 config 條目 + 設新 external_manager。零檔案系統刪除。

    ⚠️ 破壞性、不可逆：永久刪除離線來源的 DB video row（連同 user_tags）。DB 刪除與
    config 寫入無分散式交易，刻意採「先 DB 刪、後 config 落盤」的可自癒失敗序（非假
    rollback）——若 config 落盤失敗，卡已刪、離線來源仍在 config，重觸發時 delete_by_paths
    對已缺席 path no-op、重試 mutate_config 收斂成功。

    註：保持同步 def —— body 走 DB + config 檔案 I/O，依 async-offload 守衛須在
    Starlette threadpool 執行，不可改 async def 卡 event loop。
    """
    # Finding 2 + PR #93 P1/P2 雙向互斥 + switch 序列化 guard：try_begin_switch 原子地
    #   (a) generate 在飛 → 'generate_in_progress'（原 forward guard，前端顯示「產生進行中」）；
    #   (b) 另一個 switch 已持窗口 → 'switch_in_progress'（PR #93 P2：否則第二個 switch 也進、
    #       第一個 end_switch() 會在第二個窗口中把 _switch_active 清掉 → generate 趁隙補回卡）；
    #   (c) 整份設定儲存持窗口 → 'config_save_in_progress'（PR #93 P2-e：否則 switch 的 purge
    #       與該儲存的 mutate_config 交錯 → 舊快照存檔把剛 purge 的離線來源條目寫回）；
    #   (d) 否則回 None、佔住 _switch_active 整個 purge 窗口 → 期間新 generate 掛號被
    #       try_mark_generate_active 拒絕、新整份儲存被 try_begin_config_save 拒絕，杜絕反向 race。
    #       成功佔住後必 end_switch()（finally 保證）。
    reason = try_begin_switch()
    if reason is not None:
        _switch_refuse_msg = {
            "generate_in_progress": "產生進行中，請稍後再切換模式。",
            "config_save_in_progress": "設定儲存中，請稍後再切換模式。",
        }
        return {
            "success": False,
            "reason": reason,
            "error": _switch_refuse_msg.get(reason, "另一個切換正在進行中，請稍後再試。"),
        }
    try:
        return _switch_external_manager_locked(request)
    finally:
        end_switch()


def _switch_external_manager_locked(request: SwitchExternalManagerRequest) -> dict:
    """switch_external_manager 的 purge 主體（已持 _switch_active 窗口，見呼叫端）。"""
    # Step 1：讀 config 枚舉 offline_sources（唯讀，config 鎖外）
    gallery = load_config().get("gallery", {})
    mappings = gallery.get("path_mappings", {})
    offline_sources = [s for s in iter_gallery_sources(gallery) if s.readonly and s.path]

    # _canonical_source_prefix 對「髒來源路徑」會拋 ValueError（共用 readonly_source 的同名
    # helper，杜絕重複實作漂移 + PR #93 P2-f：file:/// URI 型來源也套 path_mappings 對齊 DB
    # 命名空間，否則 purge miss 該唯讀卡）。破壞性端點絕不可因單一髒路徑 500 卡死使用者切換 →
    # 髒來源 skip（無法比對其卡 → 保守不刪）。同時前綴預算一次，免 deleted_paths 每片重算。
    def _safe_prefixes(sources) -> list:
        out = []
        for s in sources:
            try:
                out.append(_canonical_source_prefix(s.path, mappings))
            except ValueError:
                continue
        return out

    offline_prefixes = _safe_prefixes(offline_sources)
    # 可寫（非唯讀）來源前綴：巢狀/重疊時由可寫來源「主張」其卡，從刪除集扣除。
    # spec §90b(iv)-1 保證「可寫來源與其 DB 卡不受影響」；可寫夾若巢狀在唯讀夾之下
    # （如唯讀 D:/media + 可寫 D:/media/local），可寫卡同落唯讀前綴，若不扣除會被誤刪
    # （連同 user_tags 永久流失）。破壞性操作保守偏向「不刪」。
    writable_prefixes = _safe_prefixes(
        [s for s in iter_gallery_sources(gallery) if s.path and not s.readonly]
    )

    # Step 2：枚舉待刪 DB 卡（無 `not in current_paths` gate —— 無條件清該離線來源全部卡）
    db_path = get_db_path()
    init_db(db_path)
    repo = VideoRepository(db_path)
    # 最具體來源勝（PR #93 Codex P2-b）：與 showcase/scraper 的 is_readonly_source 判定
    # 共用同一個 is_path_readonly，不再內聯抄「任一可寫壓任一唯讀」壞規則——否則可寫父
    # 底下的唯讀子夾卡會被誤豁免不刪、config 條目卻被移除 → 切模式後留殭屍唯讀卡。
    # v.path 為 DB canonical file:/// URI，前綴集已 coerce，直接比對（比照原內聯）。
    deleted_paths = [
        v.path
        for v in repo.get_all()
        if is_path_readonly(v.path, offline_prefixes, writable_prefixes)
    ]

    # Step 3：DB 刪除（單 DELETE IN + commit，原子；空 list 回 0 安全）+ 縮圖失效
    deleted_cards = repo.delete_by_paths(deleted_paths)
    for p in deleted_paths:
        try:
            thumbnail_cache.invalidate(p)
        except Exception:  # noqa: BLE001 — best-effort：縮圖失效失敗不阻斷主流程
            logger.exception("thumbnail_cache.invalidate failed (non-fatal): %s", p)

    # Step 4：mutate_config 原子改 config（移除離線條目 + 設 external_manager）
    # 先 DB 後 config：若此步拋錯 → 卡已刪、離線來源仍在 config → 回 success:False
    # （可自癒殘留，重觸發收斂）。不照抄 server_mode 的 rollback（DB 刪除不可逆）。
    def _mutator(cfg: dict) -> None:
        gal = cfg.setdefault("gallery", {})
        dirs = gal.get("directories", []) or []
        # 保留非 readonly 條目：dict 看 readonly 旗標；bare str 永遠非 readonly（保留）
        gal["directories"] = [
            d for d in dirs
            if not (isinstance(d, dict) and d.get("readonly") is True)
        ]
        cfg.setdefault("scraper", {})["external_manager"] = request.external_manager

    try:
        mutate_config(_mutator)
    except Exception as e:  # noqa: BLE001
        logger.error("switch_external_manager config 落盤失敗（卡已刪、離線仍在 config，可自癒）: %s", e)
        return {"success": False, "error": "無法儲存媒體伺服器模式設定"}

    # Step 6：回傳（Step 5 = 零檔案系統刪除，全程未 rmtree/unlink/os.remove）
    return {
        "success": True,
        "removed_sources": len(offline_sources),
        "deleted_cards": deleted_cards,
        "external_manager": request.external_manager,
    }


def _collect_strm_targets(repo, path_mappings: dict) -> list:
    """枚舉「已產出且夾內有既有 .strm」的片，回 [(strm_path: Path, source_fs_path: str)]。

    dry_run 與實際改寫共用此函式 → 「哪些片有 strm」的判定完全一致，保證
    count（dry_run）== rewritten（實際，除非個別片 best-effort 寫失敗）。

    - filter `output_dir` 非空（''＝未產出的骨架 row，不入枚舉）。
    - 用 glob 定位既有 .strm（非 _build_old_base 重建，Codex P1）：`_resolve_movie_dir`
      保證一夾一片，`<output_dir>/*.strm` 至多命中一個 → 用磁碟實際檔名的 stem，對
      config 漂移（同次改 filename_format）免疫；無既有 strm → skip 不新建。
    """
    targets = []
    for v in repo.get_all():
        if not v.output_dir:
            continue
        # per-row 容錯：單列壞 output_dir（uri_to_fs_path/glob 拋錯）只 skip 該列，
        # 不害整批 rewrite 中止（比照 _write_strm 的 per-movie best-effort 契約）。
        try:
            # uri-no-reverse: already paired with reverse_path_mapping on next line
            movie_dir_fs = uri_to_fs_path(v.output_dir)
            # 與 _resolve_movie_dir（core/readonly_producer.py）寫檔當下用同一套 targeted
            # reverse-map：WSL+UNC mapped 輸出根下，output_dir 存的是映射端 URI，需反解回
            # 本機實際掛載路徑才 glob 得到磁碟上真正的 .strm（否則恆定位映射端、count 永 0，
            # 改映射後既有 strm 永不改寫）。無映射/非 wsl → 退回 uri_to_fs_path 直解不變。
            if CURRENT_ENV == 'wsl' and path_mappings:
                movie_dir_fs = reverse_path_mapping(movie_dir_fs, path_mappings) or movie_dir_fs
            strm = next(Path(movie_dir_fs).glob('*.strm'), None)
        except Exception as e:  # noqa: BLE001 — best-effort：壞列 skip 不阻斷整批
            logger.warning("rewrite_strm 略過壞 output_dir 列（%r）: %s", v.output_dir, e)
            continue
        if strm is None:
            continue
        # source path 也要走同一套 reverse-map（PR #93 二審 P2）：v.path 在 WSL+gallery
        # path_mappings 下同樣存映射端 URI，但 _write_strm 的 strm_path_mappings（播放端重寫）
        # 本機前綴 = 原始掃描路徑。若只 uri_to_fs_path 得映射端 //NAS/... 會對不上 strm 規則
        # → 改寫內容 ≠ 初次生成內容（掉了播放端映射）。反解回原掃描路徑，令改寫 == 生成。
        # uri-no-reverse: already paired with reverse_path_mapping on next line
        source_fs_path = uri_to_fs_path(v.path)
        if CURRENT_ENV == 'wsl' and path_mappings:
            source_fs_path = reverse_path_mapping(source_fs_path, path_mappings) or source_fs_path
        targets.append((strm, source_fs_path))
    return targets


@router.post("/config/rewrite-strm")
def rewrite_strm(dry_run: bool = False) -> dict:
    """就地改寫使用者媒體庫既有 .strm（依當前 strm_path_mappings 重套播放端路徑）。

    spec §90a.3/§90a.4 驗收 5（CD-90a-7）：改路徑規則 → 既有全部 .strm 立即同步新映射
    （消除 stale-strm bug）。**只覆寫一行純文字**，不刪檔、不動 nfo/封面、不改 DB path、
    不重刮。

    - `dry_run=true`：只枚舉+glob 計數（供前端 heads-up N），零檔案寫入 → `{success, count}`。
    - `dry_run=false`（預設）：實際 `_write_strm` 覆寫 → `{success, rewritten}`。
    - off 模式自守（external_manager == 'off'）：直接回 0，不 enumerate/glob/寫檔
      （off 風味產出片本就無 .strm）。

    同步 def（DB + 檔案 I/O 走 threadpool，比照 switch_external_manager）。`_write_strm`
    的 config 實參＝scraper 區塊（它同層讀 strm_path_mappings），不可傳 full config。
    """
    key = "count" if dry_run else "rewritten"
    # PR #93 五審三次 P2：掃描/產生進行中拒絕改寫。producer 正用 generate 起始的舊 config
    # 快照續產出，此時 rewrite 與其併行 → 兩者對同一片可能各寫一次、且 rewrite 修不到 generate
    # 之後才產出的片 → stale。與 update_config 的映射 gate 成對（存檔擋掉即不會觸發自動改寫，
    # 此處再擋獨立/直接呼叫，防禦縱深）。dry_run 也擋，讓前端 heads-up 階段就明確拒絕。
    if is_generate_in_progress():
        return {"success": False, "reason": "generate_in_progress",
                "error": "掃描／產生進行中，請完成後再改寫 .strm。"}
    try:
        cfg = load_config()
        scraper_cfg = cfg.get('scraper', {})
        # off-mode 自守（防禦縱深；主 gate 在前端）
        if scraper_cfg.get('external_manager', 'off') == 'off':
            return {"success": True, key: 0}

        db_path = get_db_path()
        init_db(db_path)
        repo = VideoRepository(db_path)
        # gallery.path_mappings（WSL↔本機 FS 映射；≠ scraper.strm_path_mappings 播放端重寫）
        # 供 _collect_strm_targets 反解 mapped output_dir 回本機路徑再 glob。
        path_mappings = cfg.get('gallery', {}).get('path_mappings', {})
        targets = _collect_strm_targets(repo, path_mappings)

        if dry_run:
            return {"success": True, "count": len(targets)}

        rewritten = 0
        for strm, source_fs_path in targets:
            # str(strm)[:-5] 去 '.strm' → base_stem；用磁碟實際檔名（Codex P1 免疫）
            if _write_strm(str(strm)[:-5], source_fs_path, scraper_cfg):
                rewritten += 1
        return {"success": True, "rewritten": rewritten}
    except Exception as e:  # noqa: BLE001 — 端點層例外收斂為 success:False（比照 config.py 慣例）
        logger.error("rewrite_strm 失敗: %s", e)
        return {"success": False, "error": "改寫 strm 失敗"}


@router.get("/version")
async def get_version() -> dict:
    """取得版本資訊"""
    from core.version import VERSION_INFO
    return {"success": True, **VERSION_INFO}


@router.get("/config/format-variables")
async def get_format_variables() -> dict:
    """取得可用的格式變數

    每個變數帶 ``folder_ok`` 情境旗標（CD-95a-6/8）：``{suffix}`` 為檔名限定
    （版本標記屬影片名稱，不在資料夾層級再分版本），其餘變數 folder/filename 兩情境皆可用。
    前端命名區以此端點為變數集 + 情境的單一真理來源（SSOT）；label 仍走 i18n
    ``settings.var.*``（本端點不承擔多語）。
    """
    return {
        "variables": [
            {"name": "{num}", "description": "番號", "example": "SONE-205", "folder_ok": True},
            {"name": "{title}", "description": "標題", "example": "新人出道...", "folder_ok": True},
            {"name": "{actor}", "description": "演員（第一位）", "example": "三上悠亜", "folder_ok": True},
            {"name": "{actors}", "description": "所有演員", "example": "三上悠亜, 明日花", "folder_ok": True},
            {"name": "{maker}", "description": "片商", "example": "S1", "folder_ok": True},
            {"name": "{date}", "description": "發行日期", "example": "2024-01-15", "folder_ok": True},
            {"name": "{year}", "description": "年份", "example": "2024", "folder_ok": True},
            {"name": "{month}", "description": "月份（2位）", "example": "01", "folder_ok": True},
            {"name": "{day}", "description": "日（2位）", "example": "15", "folder_ok": True},
            {"name": "{suffix}", "description": "版本標記（自動偵測）", "example": "-4k", "folder_ok": False},
        ]
    }


@router.get("/ollama/models")
async def get_ollama_models(url: str) -> dict:
    """取得 Ollama 可用模型列表"""
    try:
        # 確保 URL 格式正確
        url = url.rstrip('/')
        api_url = f"{url}/api/tags"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()

            models = [m['name'] for m in data.get('models', [])]
            return {"success": True, "models": models}

    except httpx.TimeoutException:
        return {"success": False, "error": "連線逾時"}
    except httpx.ConnectError:
        return {"success": False, "error": "無法連線到 Ollama"}
    except Exception as e:
        logger.error("取得 Ollama 模型列表失敗: %s", e)
        return {"success": False, "error": "取得模型列表失敗"}


class OllamaTestRequest(BaseModel):
    url: str
    model: str


@router.post("/ollama/test")
async def test_ollama_model(request: OllamaTestRequest) -> dict:
    """測試 Ollama 模型是否能正常回應"""
    try:
        url = request.url.rstrip('/')

        config = await asyncio.to_thread(load_config)
        locale = config.get("general", {}).get("locale", "zh-TW")
        lang_config = LANGUAGE_PROMPTS.get(locale, LANGUAGE_PROMPTS["zh-TW"])
        lang_name = lang_config["name"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/chat",
                json={
                    "model": request.model,
                    "messages": [
                        {"role": "user", "content": f"將以下日文翻譯成{lang_name}，只輸出翻譯結果：新人女優デビュー"}
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": 500,  # think mode 需要足夠 token（翻譯本身 ~20 tok，其餘供推理）
                        "temperature": 0.3
                    }
                }
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get("message", {}).get("content", "").strip()
            if result:
                return {"success": True, "result": f"回應：{result}"}
            else:
                return {"success": False, "error": "模型無回應"}

    except httpx.TimeoutException:
        return {"success": False, "error": "連線逾時"}
    except httpx.ConnectError:
        return {"success": False, "error": "無法連線到 Ollama"}
    except Exception as e:
        logger.error("測試 Ollama 模型失敗: %s", e)
        return {"success": False, "error": "測試模型失敗"}


class ProxyTestRequest(BaseModel):
    proxy_url: str


@router.post("/proxy/test")
def test_proxy(request: ProxyTestRequest) -> dict:
    """測試 Proxy 連線（透過 DMM GraphQL endpoint 驗證）"""
    import requests

    is_direct = request.proxy_url.strip().lower() == 'direct'
    if is_direct:
        proxies = {'http': None, 'https': None}
        success_message = "直連測試成功（DMM 可達）"
        non_jp_message = "直連可達，但 DMM 回傳 403（非日本 IP，建議使用 Proxy）"
    else:
        proxies = {'http': request.proxy_url, 'https': request.proxy_url}
        success_message = "Proxy 連線成功（DMM 可達）"
        non_jp_message = "Proxy 連線成功，但 DMM 回傳 403（可能非日本 IP）"

    try:
        resp = requests.post(
            "https://api.video.dmm.co.jp/graphql",
            json={"query": "{ __typename }"},
            headers={"Content-Type": "application/json"},
            proxies=proxies,
            timeout=10
        )
        if resp.status_code == 200:
            return {"success": True, "reason": "ok", "message": success_message}
        elif resp.status_code == 403:
            return {"success": False, "reason": "non_jp", "message": non_jp_message}
        else:
            return {"success": False, "reason": "unexpected_status", "message": f"DMM 回傳異常狀態碼: {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 連線逾時"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 無法連線到目標主機"}
    except Exception:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 請檢查輸入格式"}
