"""
test_fix_numbers.py — Unit tests for fix-numbers logic:
  - _get_fixed_number helper
  - preview rule filtering (empty rules / rules subset)
  - apply re-validation
  - invalid rule names → 400

All tests are pure Python — no FS, no DB, no network.
"""

import pytest


# ── U1: preview 規則過濾 — 空 rules 套用全部 ─────────────────────────────────

class TestPreviewRulesEmpty:
    """U1: rules=[] 時套用全部 4 條規則，4 種 corrupted number 都被比中"""

    def test_empty_rules_applies_all_four_rules(self):
        from web.routers.collection import CORRUPTION_RULES, _is_corrupted_number, _get_fixed_number
        import re

        # 各 corruption 類型一筆
        rows = [
            {"id": 1, "number": "7IPZ-154",   "path": "file:///a/1.mp4"},
            {"id": 2, "number": "TKIPZ-154",  "path": "file:///a/2.mp4"},
            {"id": 3, "number": "K9IPZ-154",  "path": "file:///a/3.mp4"},
            {"id": 4, "number": "R-IPZ-154",  "path": "file:///a/4.mp4"},
            {"id": 5, "number": "IPZ-154",    "path": "file:///a/5.mp4"},  # 正常，不應出現
        ]

        rules_to_apply = CORRUPTION_RULES  # empty rules → all rules
        affected = []
        for row in rows:
            number = row["number"]
            upper = number.upper()
            for rule in rules_to_apply:
                m = re.match(rule["pattern"], upper)
                if m:
                    new_number = m.group(rule["fix_group"])
                    affected.append({
                        "id":         row["id"],
                        "old_number": number,
                        "new_number": new_number,
                        "rule":       rule["name"],
                        "path":       row["path"],
                    })
                    break  # 取第一條符合的

        assert len(affected) == 4
        rule_names = {item["rule"] for item in affected}
        assert rule_names == {"digit_prefix", "TK_prefix", "K9_prefix", "R_prefix"}

        # 正常番號不出現
        ids = {item["id"] for item in affected}
        assert 5 not in ids


# ── U2: preview 規則過濾 — 指定 rules 子集 ───────────────────────────────────

class TestPreviewRulesSubset:
    """U2: rules=["digit_prefix"] 時只比中 digit_prefix 的番號"""

    def test_subset_rules_only_matches_specified_rule(self):
        from web.routers.collection import CORRUPTION_RULES
        import re

        rows = [
            {"id": 1, "number": "7IPZ-154",   "path": "file:///a/1.mp4"},
            {"id": 2, "number": "TKIPZ-154",  "path": "file:///a/2.mp4"},
            {"id": 3, "number": "K9IPZ-154",  "path": "file:///a/3.mp4"},
            {"id": 4, "number": "R-IPZ-154",  "path": "file:///a/4.mp4"},
        ]

        requested_names = ["digit_prefix"]
        rules_to_apply = [r for r in CORRUPTION_RULES if r["name"] in requested_names]

        affected = []
        for row in rows:
            number = row["number"]
            upper = number.upper()
            for rule in rules_to_apply:
                m = re.match(rule["pattern"], upper)
                if m:
                    affected.append({
                        "id":         row["id"],
                        "old_number": number,
                        "new_number": m.group(rule["fix_group"]),
                        "rule":       rule["name"],
                        "path":       row["path"],
                    })
                    break

        assert len(affected) == 1
        assert affected[0]["id"] == 1
        assert affected[0]["rule"] == "digit_prefix"
        assert affected[0]["new_number"] == "IPZ-154"


# ── U3: fix_group 提取正確性 ──────────────────────────────────────────────────

class TestGetFixedNumber:
    """U3: _get_fixed_number 對各種 corrupted number 回傳正確的修正番號"""

    def setup_method(self):
        from web.routers.collection import _get_fixed_number
        self._get_fixed_number = _get_fixed_number

    def test_digit_prefix(self):
        """7IPZ-154 → digit_prefix fix_group=2 → IPZ-154"""
        result = self._get_fixed_number("7IPZ-154")
        assert result == "IPZ-154"

    def test_tk_prefix(self):
        """TKIPZ-154 → TK_prefix fix_group=1 → IPZ-154"""
        result = self._get_fixed_number("TKIPZ-154")
        assert result == "IPZ-154"

    def test_k9_prefix(self):
        """K9IPZ-154 → K9_prefix fix_group=1 → IPZ-154"""
        result = self._get_fixed_number("K9IPZ-154")
        assert result == "IPZ-154"

    def test_r_prefix(self):
        """R-IPZ-154 → R_prefix fix_group=1 → IPZ-154"""
        result = self._get_fixed_number("R-IPZ-154")
        assert result == "IPZ-154"

    def test_normal_number_returns_none(self):
        """正常番號 IPZ-154 → None（不 match 任何規則）"""
        result = self._get_fixed_number("IPZ-154")
        assert result is None

    def test_none_input_returns_none(self):
        """None → None（None-safe）"""
        result = self._get_fixed_number(None)
        assert result is None


# ── U4: apply 重新驗證 — 番號已修正則跳過 ────────────────────────────────────

class TestApplyRevalidation:
    """U4: apply 前重新驗證，已修正番號（不符合 CORRUPTION_RULES）應跳過"""

    def test_already_fixed_number_is_skipped(self):
        from web.routers.collection import _is_corrupted_number, _get_fixed_number

        # 模擬 apply 時從 DB 讀出的番號已是正常番號
        current_number = "IPZ-154"

        # 重新驗證：不符合任何規則 → 應跳過
        assert _is_corrupted_number(current_number) is False
        assert _get_fixed_number(current_number) is None

    def test_still_corrupted_number_is_updated(self):
        from web.routers.collection import _is_corrupted_number, _get_fixed_number

        # 模擬番號仍然 corrupted
        current_number = "7IPZ-154"

        assert _is_corrupted_number(current_number) is True
        new_number = _get_fixed_number(current_number)
        assert new_number == "IPZ-154"


# ── U5: rules 含無效名稱 → 400 ───────────────────────────────────────────────

class TestInvalidRuleNames:
    """U5: rules 含不在 CORRUPTION_RULES 中的名稱應觸發 HTTP 400"""

    def setup_method(self):
        from fastapi.testclient import TestClient
        from web.app import app
        self.client = TestClient(app)

    def test_invalid_rule_name_returns_400(self):
        """rules=["digit_prefix", "evil_rule"] → HTTP 400"""
        resp = self.client.post(
            "/api/collection/fix-numbers/preview",
            json={"rules": ["digit_prefix", "evil_rule"]},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "evil_rule" in str(data)

    def test_completely_invalid_rules_returns_400(self):
        """rules=["bad_rule"] → HTTP 400"""
        resp = self.client.post(
            "/api/collection/fix-numbers/preview",
            json={"rules": ["bad_rule"]},
        )
        assert resp.status_code == 400
