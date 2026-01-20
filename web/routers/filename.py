"""
檔名解析 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List

from core.scrapers.utils import extract_number, check_subtitle

router = APIRouter(prefix="/api", tags=["filename"])


# ============ Pydantic 模型 ============

class ParseFilenameRequest(BaseModel):
    """批次檔名解析請求"""
    filenames: List[str] = Field(..., description="檔案名稱列表")


class ParsedFile(BaseModel):
    """單個檔案解析結果"""
    filename: str
    number: Optional[str] = None
    has_subtitle: bool = False


class ParseFilenameResponse(BaseModel):
    """批次檔名解析響應"""
    results: List[ParsedFile]
    total: int
    parsed: int


# ============ API 端點 ============

@router.post("/parse-filename", response_model=ParseFilenameResponse)
async def parse_filename(request: ParseFilenameRequest) -> ParseFilenameResponse:
    """
    批次解析檔名，提取番號和字幕資訊

    Args:
        request: 包含檔名列表的請求

    Returns:
        ParseFilenameResponse: 解析結果

    Example:
        POST /api/parse-filename
        {"filenames": ["SONE-205.mp4", "[中文字幕] ABC-123.mkv"]}

        Response:
        {
            "results": [
                {"filename": "SONE-205.mp4", "number": "SONE-205", "has_subtitle": false},
                {"filename": "[中文字幕] ABC-123.mkv", "number": "ABC-123", "has_subtitle": true}
            ],
            "total": 2,
            "parsed": 2
        }
    """
    results = []
    parsed_count = 0

    for filename in request.filenames:
        number = extract_number(filename)
        has_subtitle = check_subtitle(filename)

        results.append(ParsedFile(
            filename=filename,
            number=number,
            has_subtitle=has_subtitle
        ))

        if number:
            parsed_count += 1

    return ParseFilenameResponse(
        results=results,
        total=len(request.filenames),
        parsed=parsed_count
    )
