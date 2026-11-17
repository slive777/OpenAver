from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from core.logger import get_logger
from core.nfo_field_edit import apply_edit, read_edit_view
from core.user_tags_write import hold_nfo_write
from web.routers.showcase_files import _resolve_scope  # noqa: PLC2701 — 沿用 200b 的同一個 scope 判定，不另寫第二份

logger = get_logger(__name__)
router = APIRouter(prefix="/api/showcase", tags=["showcase"])
_PAYLOAD_KEYS = ("value", "add", "remove")


class EditFieldRequest(BaseModel):
    path: str
    field: str
    value: Any = None
    add: Any = None
    remove: Any = None


def _fail(code):
    return {"success": False, "error": code}


def _scope(path):
    ctx, error = _resolve_scope(path)
    if error is not None:
        return None, _fail("not_found")
    return ctx, None


def _payload(req):
    data = req.model_dump(exclude_unset=True)
    return {key: data[key] for key in _PAYLOAD_KEYS if key in data}


@router.get("/video/edit-data")
def get_edit_data(path: str):
    try:
        ctx, error = _scope(path)
        if error is not None:
            return error
        return read_edit_view(ctx.repo, ctx.row, ctx.config, ctx.path_mappings)
    except ValueError:
        return _fail("invalid_path")
    except Exception:
        logger.error("[edit-data] 讀取失敗", exc_info=True)
        return _fail("nfo_unreadable")


@router.post("/video/edit-field")
def edit_field(req: EditFieldRequest):
    try:
        ctx, error = _scope(req.path)
        if error is not None:
            return error
        with hold_nfo_write():
            row = ctx.repo.get_by_path(req.path)
            if row is None:
                return _fail("not_found")
            return apply_edit(ctx.repo, row, req.field, _payload(req), ctx.config, ctx.path_mappings)
    except ValueError:
        return _fail("invalid_path")
    except Exception:
        logger.error("[edit-field] 寫入失敗", exc_info=True)
        return _fail("nfo_write_failed")
