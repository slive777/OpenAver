"""自訂來源的封閉錯誤型別與 reason 常數。"""

LOAD_REASONS = frozenset({
    "yaml_syntax",
    "duplicate_key",
    "alias",
    "unsafe_tag",
    "too_large",
    "unknown_key",
    "bad_id",
    "reserved_id",
    "id_filename_mismatch",
    "bad_pattern",
    "bad_template",
    "bad_selector",
    "missing_negative_assert",
    "fetch_cf_unsupported",
    "unknown_fetch",
    "unknown_transform",
})

SCRAPE_ERROR_REASONS = frozenset({
    "http_status",
    "blocked_target",
    "network",
    "timeout",
    "too_large",
    "redirect_limit",
    "parse_empty",
    "transport_unavailable",
})


class LoadError(Exception):
    """YAML 載入／驗證失敗。不帶 YAML 原文。"""

    def __init__(self, reason, message="", field_path=""):
        self.reason = reason
        self.field_path = field_path
        self.message = message
        super().__init__(reason, field_path, message)

    def __str__(self):
        return f"[{self.reason}] {self.field_path}: {self.message}"


class BlockedTarget(Exception):
    """請求目標被安全規則擋下。"""

    def __init__(self, reason, message=""):
        self.reason = reason
        self.message = message
        super().__init__(reason, message)

    def __str__(self):
        return f"[{self.reason}] {self.message}"
