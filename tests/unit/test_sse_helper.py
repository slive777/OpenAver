"""_sse_event 格式契約測試"""
import json

from web.routers.scanner import _sse_event


class TestSseEventFormat:
    """_sse_event() 格式契約測試"""

    def test_ascii_dict(self):
        """純 ASCII dict 應輸出標準 SSE 格式"""
        result = _sse_event({"type": "test", "message": "hello"})
        assert result == 'data: {"type": "test", "message": "hello"}\n\n'

    def test_chinese_dict(self):
        """含中文 dict 應保留 Unicode（ensure_ascii=False）"""
        result = _sse_event({"type": "log", "message": "含中文 UTF-8"})
        assert result == 'data: {"type": "log", "message": "含中文 UTF-8"}\n\n'
        # 確保中文沒有被 escape 成 \uXXXX
        assert "\\u" not in result

    def test_empty_dict(self):
        """空 dict 應輸出合法的 SSE message"""
        result = _sse_event({})
        assert result == "data: {}\n\n"

    def test_return_type_is_str(self):
        """回傳值必須是 str"""
        result = _sse_event({"type": "done"})
        assert isinstance(result, str)

    def test_ends_with_double_newline(self):
        """SSE message 必須以 \\n\\n 結尾"""
        result = _sse_event({"type": "progress", "current": 1, "total": 10})
        assert result.endswith("\n\n")

    def test_starts_with_data_prefix(self):
        """SSE message 必須以 'data: ' 開頭"""
        result = _sse_event({"type": "error", "message": "something failed"})
        assert result.startswith("data: ")

    def test_json_body_is_valid(self):
        """data: 後面的 JSON 必須可被 json.loads 解析"""
        data = {"type": "done", "count": 42}
        result = _sse_event(data)
        # 剝除 "data: " 前綴和尾端 \n\n
        json_str = result[len("data: "):].rstrip("\n")
        parsed = json.loads(json_str)
        assert parsed == data
