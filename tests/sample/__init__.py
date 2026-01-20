"""測試樣本資料

Phase 16 Task 2: 爬蟲測試用樣本番號

包含：
- 有碼番號（主流片商）
- 無碼番號（Carib/1Pondo）
- FC2 番號
- 特殊格式番號
"""

# ========== 有碼番號（Censored）==========

# 主流片商測試番號（確認存在於各資料庫）
CENSORED_SAMPLES = {
    # S1 系列
    "SONE-205": {
        "maker": "S1",
        "actress": "未歩なな",
        "date": "2024",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },
    "SSNI-001": {
        "maker": "S1",
        "actress": "三上悠亞",
        "date": "2018",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },
    "SSIS-001": {
        "maker": "S1",
        "actress": "安齋らら",
        "date": "2020",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },

    # Moodyz 系列
    "MIDV-018": {
        "maker": "Moodyz",
        "actress": "高橋しょう子",
        "date": "2021",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },
    "MIDE-001": {
        "maker": "Moodyz",
        "actress": "高橋しょう子",
        "date": "2013",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },

    # IdeaPocket 系列
    "IPX-001": {
        "maker": "IdeaPocket",
        "actress": "桃乃木かな",
        "date": "2017",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },
    "IPZZ-001": {
        "maker": "IdeaPocket",
        "actress": "桃乃木かな",
        "date": "2022",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },

    # SOD STAR 系列
    "STARS-804": {
        "maker": "SOD",
        "actress": "永野いち夏",
        "date": "2023",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },

    # Prestige 系列
    "ABW-001": {
        "maker": "Prestige",
        "actress": "河北彩花",
        "date": "2020",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },

    # Madonna 系列
    "JUQ-001": {
        "maker": "Madonna",
        "actress": "",
        "date": "2022",
        "expected_sources": ["javbus", "jav321", "javdb"],
    },
}

# ========== 無碼番號（Uncensored）==========

# Carib/1Pondo 等無碼片商
UNCENSORED_SAMPLES = {
    "051119-917": {
        "title": "結婚直前で心が揺らいだ新婦の情事",
        "actress": "@YOU",
        "source": "caribbeancom",
        "expected_sources": ["avsox"],
    },
    "010120-001": {
        "title": "一本道",
        "source": "1pondo",
        "expected_sources": ["avsox"],
    },
    "011923-001": {
        "title": "",
        "source": "1pondo",
        "expected_sources": ["avsox"],
    },
}

# ========== FC2 番號 ==========

FC2_SAMPLES = {
    "FC2-PPV-1723984": {
        "title": "透け透け体操服にローライズブルマーでハミ尻",
        "seller": "プライベートマスク",
        "expected_sources": ["fc2"],
    },
    "FC2-PPV-3061583": {
        "title": "",  # 可能找不到
        "seller": "",
        "expected_sources": ["fc2"],
    },
}

# ========== 特殊格式番號 ==========

# 用於測試番號正規化
NUMBER_FORMAT_SAMPLES = {
    # 各種 SONE-205 格式
    "sone205": "SONE-205",
    "SONE-205": "SONE-205",
    "SONE205": "SONE-205",
    "sone-205": "SONE-205",
    "  SONE-205  ": "SONE-205",

    # FC2 格式
    "FC2-PPV-1723984": "1723984",  # FC2 正規化後
    "FC2PPV-1723984": "1723984",
    "FC2-1723984": "1723984",
    "fc2ppv1723984": "1723984",
}

# ========== 不存在的番號（用於測試錯誤處理）==========

INVALID_SAMPLES = [
    "INVALID-99999",
    "XXXX-000",
    "TEST-12345678",
    "NOTEXIST-001",
]

# ========== 輔助函數 ==========

def get_all_censored_numbers() -> list[str]:
    """取得所有有碼測試番號"""
    return list(CENSORED_SAMPLES.keys())


def get_all_uncensored_numbers() -> list[str]:
    """取得所有無碼測試番號"""
    return list(UNCENSORED_SAMPLES.keys())


def get_all_fc2_numbers() -> list[str]:
    """取得所有 FC2 測試番號"""
    return list(FC2_SAMPLES.keys())


def get_sample_by_source(source: str) -> list[str]:
    """依來源取得測試番號"""
    result = []

    for num, info in CENSORED_SAMPLES.items():
        if source in info.get("expected_sources", []):
            result.append(num)

    for num, info in UNCENSORED_SAMPLES.items():
        if source in info.get("expected_sources", []):
            result.append(num)

    for num, info in FC2_SAMPLES.items():
        if source in info.get("expected_sources", []):
            result.append(num)

    return result
