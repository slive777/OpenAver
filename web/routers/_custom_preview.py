"""自訂來源重刮預覽／確認共用：五結果映射與失敗分類（同一份，不得兩份）。"""
from core.scraper import (
    access_error_info, fetch_custom_by_detail_url, internal_nfo_carriers,
    search_custom_versions,
)
from core.scrapers.errors import (
    CustomSourceRefused, SourceBlocked, SourceParseEmpty, SourceUnreachable,
)
from web.routers._custom_gate import REASON_TEXT, refusal_for # noqa: PLC2701 — 卡片指定的 web 內部底線模組（165-T7b），同 router 層共用 gate 句表，尚未升格為公開名


def classify_custom_failure(exc: Exception, source: str) -> dict:
    """抓取例外 → 結構化失敗 dict；其餘 RuntimeError 併入「連不到」。"""
    if isinstance(exc, CustomSourceRefused):
        return {"success": False, "custom_error": "refused", "custom_reason": exc.reason, "source": source}
    if isinstance(exc, SourceParseEmpty):
        return {"success": False, "custom_error": "parse_empty", "source": source}
    if isinstance(exc, SourceBlocked):
        return {"success": False, "access_error": "refused", "source": source}
    return {"success": False, "access_error": "unreachable", "source": source}


def parse_empty_text(source: str) -> str:
    name = access_error_info(SourceUnreachable(), source)["message"].removesuffix(" 連不到，請檢查網路或代理設定")
    return f"{name} 抓不到資料，站方可能改版了，請到設定頁重跑驗收"


def failure_text(exc: Exception, source: str) -> str:
    if isinstance(exc, CustomSourceRefused):
        return REASON_TEXT.get(exc.reason, REASON_TEXT["not_loaded"])
    if isinstance(exc, SourceParseEmpty):
        return parse_empty_text(source)
    return access_error_info(exc if isinstance(exc, SourceBlocked) else SourceUnreachable(), source)["message"]


def preview_custom(source: str, number: str) -> dict:
    refused = refusal_for(source, number)
    if refused:
        return {"success": False, "custom_error": "refused", "custom_reason": refused[0], "error": refused[1]}
    from core.custom_source.service import call_bounded  # lazy：AC-165-8
    try:
        versions = call_bounded(lambda: search_custom_versions(source, number))
    except RuntimeError as exc:
        return classify_custom_failure(exc, source)
    if not versions:
        return {"success": False, "custom_error": "not_found", "source": source}
    if len(versions) == 1:
        return {"success": True, **versions[0]}
    return {"success": True, "candidates": versions}


def custom_candidate_data(source: str, detail_url: str, number: str):
    """確認用預抓：回 (scraper_data, error_response)，不 raise（形狀同 javlib 版）。"""
    from core.custom_source.service import call_bounded  # lazy：AC-165-8
    try:
        video = call_bounded(lambda: fetch_custom_by_detail_url(source, detail_url, number))
    except RuntimeError as exc:
        return None, {**classify_custom_failure(exc, source), "error": failure_text(exc, source)}
    if video is None:
        return None, {"success": False, "error": "自訂來源無法取得指定版本資料"}
    data = video.to_legacy_dict()
    data.update(internal_nfo_carriers(video))
    return data, None
