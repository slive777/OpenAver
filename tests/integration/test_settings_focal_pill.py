"""tests/integration/test_settings_focal_pill.py — F3/F4 settings 頁人臉自動對焦狀態列
（feature/152c TASK-9，CD-152c-19）。

`client` fixture 與 config 隔離（`_isolate_config` autouse）都來自
`tests/integration/conftest.py`；每個測試在該隔離設定檔上用
`core_config.mutate_config` 覆寫 `focal_device`，不直接用 `save_config`
整份取代（會漏掉 AppConfig 其他欄位，讓 /settings 渲染其他區塊時噴錯）。
"""
from __future__ import annotations

from core import config as core_config
from core.version import VERSION


def _seed_focal_device(*, disabled: bool, judged_at_version: str, consecutive_timeout_count: int = 2) -> None:
    def _mutator(cfg: dict) -> None:
        cfg["focal_device"] = {
            "disabled": disabled,
            "consecutive_timeout_count": consecutive_timeout_count,
            "judged_at_version": judged_at_version,
        }
    core_config.mutate_config(_mutator)


def _extract_focal_input_tag(html: str) -> str:
    """抓出人臉自動對焦那顆 <input> 的完整開始標籤（不含其他 toggle）。

    不能用文案定位：文案定位會被「前面任何含相同字串的元素或註解」搶走，reviewer 實測可假綠。
    改以 data-focal-auto-pill 錨點屬性定位：
    html.index("data-focal-auto-pill") 找到屬性位置 →
    html.rindex("<input", 0, idx) 往回找標籤開頭 →
    html.index(">", input_start) 找標籤結尾。
    """
    idx = html.index("data-focal-auto-pill")
    input_start = html.rindex("<input", 0, idx)
    input_end = html.index(">", input_start)
    return html[input_start:input_end + 1]


class TestSettingsFocalAutoPill:
    def test_version_mismatch_lazy_reset_renders_enabled(self, client):
        """F3 核心驗收（CD-152c-19）：舊版本判定的 disabled=True，執行版本已不同
        → /settings 渲染出「啟用」。若前端／模板改成直接讀 config.focal_device.disabled，
        這條會紅（那正是它存在的理由）。
        """
        assert "0.16.3" != VERSION, "測試前提：judged_at_version 需與目前 VERSION 不同"
        _seed_focal_device(disabled=True, judged_at_version="0.16.3")

        resp = client.get("/settings")
        assert resp.status_code == 200
        html = resp.text
        input_tag = _extract_focal_input_tag(html)

        # [lint-guard: pytest-justified] checkbox 狀態是跨層契約：後端 focal_device 狀態
        # ⇒ 渲染出 checked／未 checked。模板檔的靜態字面同時含兩種可能，static_guard_lint
        # 分不出「哪一種後端狀態會渲染出哪一種」——? 浮層文案已改狀態無關單一文案，
        # 改由 scripts/static_guard_lint.mjs 的 required-string 守接線。
        assert "checked" in input_tag, f"版本已變更，預期渲染成啟用（checked），實際標籤：{input_tag}"

    def test_matching_version_disabled_renders_unchecked(self, client):
        """disabled=True 且 judged_at_version == 目前 VERSION → 維持停用（未勾選）。"""
        _seed_focal_device(disabled=True, judged_at_version=VERSION)

        resp = client.get("/settings")
        assert resp.status_code == 200
        html = resp.text
        input_tag = _extract_focal_input_tag(html)

        # [lint-guard: pytest-justified] checkbox 狀態是跨層契約：後端 focal_device 狀態
        # ⇒ 渲染出 checked／未 checked。模板檔的靜態字面同時含兩種可能，static_guard_lint
        # 分不出「哪一種後端狀態會渲染出哪一種」——? 浮層文案已改狀態無關單一文案，
        # 改由 scripts/static_guard_lint.mjs 的 required-string 守接線。
        assert "checked" not in input_tag, f"版本相同、仍停用，不應 checked，實際標籤：{input_tag}"

    def test_faces_enabled_user_disabled_renders_unchecked(self, client):
        """187a-T2 pill 接線：外部 faces 開啟時仍只反映本機 local_disabled_in。

        T2 時 is_disabled_in 與 local_disabled_in 行為相同，本測試此時不可證偽
        app.py 改讀取端；T3 後由主 session 驗。
        """
        _seed_focal_device(disabled=True, judged_at_version=VERSION)

        def _mutator(cfg: dict) -> None:
            cfg["focal_device"]["set_by_user"] = True
            cfg.setdefault("ai_services", {})["faces"] = {
                "enabled": True,
                "url": "http://x",
                "api_key": "",
                "model": "",
            }

        core_config.mutate_config(_mutator)

        resp = client.get("/settings")
        assert resp.status_code == 200
        input_tag = _extract_focal_input_tag(resp.text)

        # [lint-guard: pytest-justified] checkbox 狀態是跨層契約：後端 focal_device 狀態
        # ⇒ 渲染出 checked／未 checked。模板檔的靜態字面同時含兩種可能，static_guard_lint
        # 分不出「哪一種後端狀態會渲染出哪一種」——? 浮層文案已改狀態無關單一文案，
        # 改由 scripts/static_guard_lint.mjs 的 required-string 守接線。
        assert "checked" not in input_tag, f"使用者停用時不應 checked，實際標籤：{input_tag}"


