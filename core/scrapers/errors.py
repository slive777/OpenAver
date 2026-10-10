"""爬蟲例外型別"""


class SourceUnreachable(RuntimeError):
    """連不上這個來源（連線被拒 / 逾時 / DNS 失敗 / 被牆）。
    User-visible meaning: 「javdb 目前連不上」——使用者的下一步是檢查網路 / 代理。
    """


class SourceBlocked(RuntimeError):
    """連得上，但對方擋住我們（403 / 429 / 503 / CF 挑戰頁）。
    User-visible meaning: 「javdb 暫時不可用」——使用者的下一步是等我們修 / 稍後再試。
    """


class SourceParseEmpty(RuntimeError):
    """連得上、也拿到頁面，但抽不出任何欄位（站方多半改版了）。
    User-visible meaning: 「這個自訂來源抽不到資料」——使用者的下一步是回設定頁重跑驗收。
    """
