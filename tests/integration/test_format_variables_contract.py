"""契約守衛：GET /api/config/format-variables ⊆ organizer.format_string 消費。

鎖住「端點暴露的每個 {name} 都被 core.organizer.format_string 真正取代（非留字面）」
與 folder_ok 情境旗標契約（CD-95a-10〔3〕 / CD-95a-6/8，plan-95a T2）。

信號可靠性：sanitize_filename 的非法字元清單不含 `{` `}`（organizer.py:31-37），
故未被消費的 token 會保留大括號留在輸出；被消費的 token 不留大括號。以此為
mutation-靈敏的消費信號——端點若加 organizer 不認得的 token（如 {studio}），
format_string 會原樣回傳含大括號的字面 → 本測 RED。
"""
from core.organizer import format_string

# 讓所有欄位有值：確保「被消費」與「空字串殘留」不混淆
SAMPLE = {
    "number": "SONE-205",
    "title": "新人出道",
    "actors": ["三上悠亜", "明日花"],
    "maker": "S1",
    "date": "2024-01-15",
    "suffix": "-4k",
}


def _variables(client):
    resp = client.get("/api/config/format-variables")
    assert resp.status_code == 200
    return resp.json()["variables"]


def test_every_endpoint_token_consumed_by_organizer(client):
    """端點每個 {name} 都被 format_string 取代（輸出不殘留大括號）。"""
    for var in _variables(client):
        name = var["name"]
        out = format_string(name, SAMPLE, use_fallback=True)
        assert "{" not in out and "}" not in out, (
            f"{name} 未被 organizer.format_string 消費（殘留大括號：{out!r}）"
        )
        assert out != name, f"{name} 原樣留字面：{out!r}"


def test_folder_ok_flag_contract(client):
    """每項含 folder_ok；{suffix}=False（檔名限定），其餘為 True，恰 10 變數。"""
    variables = _variables(client)
    assert len(variables) == 10, f"預期 10 個變數，實得 {len(variables)}"
    for var in variables:
        assert "folder_ok" in var, f"{var['name']} 缺 folder_ok 旗標"
        assert isinstance(var["folder_ok"], bool)
    by_name = {v["name"]: v["folder_ok"] for v in variables}
    assert by_name["{suffix}"] is False, "{suffix} 應為檔名限定 folder_ok=False"
    for name, ok in by_name.items():
        if name != "{suffix}":
            assert ok is True, f"{name} 應 folder_ok=True，實得 {ok}"
