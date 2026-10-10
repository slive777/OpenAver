"""
web/routers/custom_sources.py — TASK-165-T5
============================================
自訂來源 HTTP 路由：六個端點，只做 HTTP 轉換，業務全在 core.custom_source.service。
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.custom_source import service
from core.custom_source.schema import ID_RE
from core.custom_source.service import ServiceError

router = APIRouter(prefix="/api", tags=["custom_sources"])

MAX_BODY_BYTES = 256 * 1024
UPLOAD_NEXT = "請呼叫驗收；通過後請使用者到設定頁打開"
_ERROR_TEXT = {
    "data_root_not_ready": "資料根尚未就緒，請先完成資料根設定",
    "verify_busy": "另一個來源正在驗收，請稍後再試",
    "not_loaded": "找不到這個自訂來源",
    "load_failed": "這個自訂來源的檔案載入失敗",
    "changed_during_verify": "驗收期間這個來源被更動，結果已丟棄，請重新驗收",
    "not_passed": "這個來源尚未通過驗收，不能啟用",
}


class EnabledRequest(BaseModel):
    enabled: bool


class ApplicableRequest(BaseModel):
    number: str


def _limit_body(request: Request):
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="檔案超過 256 KiB，請縮小後重傳")


def _fail(error: ServiceError):
    content = error.payload()
    content["error"] = error.extra.get("message") or _ERROR_TEXT.get(error.code, error.code)
    return JSONResponse(
        status_code=error.http_status,
        content=content,
    )


def _bad_id(source_id: str):
    if ID_RE.fullmatch(source_id) is None:
        return _fail(ServiceError("not_loaded", 404))
    return None


@router.post("/custom-sources", dependencies=[Depends(_limit_body)])
def upload_source(body: bytes = Body(...)):
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _fail(ServiceError("yaml_syntax", 400, field_path="", line=None, message="檔案不是有效的 UTF-8"))
    try:
        result = service.upload(text)
    except ServiceError as exc:
        return _fail(exc)
    return {"success": True, **result, "next": UPLOAD_NEXT}


@router.post("/custom-sources/applicable")
def applicable_sources(body: ApplicableRequest):
    return {"success": True, "applicable": service.applicable(body.number)}


@router.get("/custom-sources")
def list_sources():
    return {"success": True, "sources": service.list_sources()}


@router.post("/custom-sources/{source_id}/verify")
def verify_source(source_id: str):
    if (rejected := _bad_id(source_id)) is not None:
        return rejected
    try:
        return {"success": True, **service.verify(source_id)}
    except ServiceError as exc:
        return _fail(exc)


@router.delete("/custom-sources/{source_id}")
def remove_source(source_id: str):
    if (rejected := _bad_id(source_id)) is not None:
        return rejected
    try:
        return {"success": True, **service.remove(source_id)}
    except ServiceError as exc:
        return _fail(exc)


# enabled 端點僅供設定頁，不進 capabilities（D-165-2）
@router.post("/custom-sources/{source_id}/enabled")
def set_source_enabled(source_id: str, body: EnabledRequest):
    if (rejected := _bad_id(source_id)) is not None:
        return rejected
    try:
        return {"success": True, **service.set_enabled(source_id, body.enabled)}
    except ServiceError as exc:
        return _fail(exc)
