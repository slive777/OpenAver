"""8 源健康金絲雀 — 常青番號清單（TASK-73b-T2 live sweep 產物）.

每個番號為對應 scraper ``search()`` 的 **INPUT 形式**（非 ``.number`` 輸出形式；
輸入/輸出格式差由 ``_canary_core.numbers_match`` 橋接，見 73b-T1）。

Sweep 查證日期：2026-06-17（全源 live 實打；dmm 經 gluetun proxy
``192.168.1.177:8888`` 走生產 ``DMMScraper`` 路徑）。番號會隨站方資料汰換，
T3 的 quorum 設計容忍個別下架（≥1 pass 即綠）。

排除 ``javlibrary``（CF 真人驗證 + 桌面專屬，無法自動化；spec §US1 Non-Goal）。
"""

CANARY_NUMBERS: dict[str, list[str]] = {
    # 有碼 echo-input（.number = normalize_number(input)）
    "javbus": ["SONE-205", "SONE-103", "JUR-688", "SNOS-143", "N0762", "N2046"],
    # N0762/N2046 = Tokyo Hot 單字母無碼（73a 修好），live 證實 javbus 收錄且修復有效
    "jav321": ["MIDV-018", "SONE-103", "N0762", "STARS-804"],
    "javdb": ["SSNI-001", "SONE-103"],  # 刻意放少（查多觸發 CF ban，接受全 skip 為正常）

    # dmm — 經 proxy 實打；.number 取自 DMM API（非 echo-input），故須挑「回的番號 == 查的番號」者。
    # 排除 SSNI-001：proxy 實打回 SSNI-192（dmm content-id 前綴學習映射到別片）→ 會被 classify_one
    # row 3 正確判 fail，但非金絲雀本意，故不放進常青清單。
    "dmm": ["SONE-205", "MIDV-018", "MIDV-139", "SONE-103", "SSIS-500"],

    # 無碼
    "d2pass": ["010120-001", "031515-828", "120415_201", "010122_001"],
    # 分隔符語義顯著（- = caribbean / _ = 1pondo），逐字比；混放兩站覆蓋 site-order 偵測
    "heyzo": ["HEYZO-0783", "HEYZO-1000", "HEYZO-1500", "HEYZO-2000", "HEYZO-2300"],
    "fc2": ["FC2-PPV-1723984", "FC2-PPV-2200414", "FC2-PPV-2781063", "FC2-PPV-2865434"],
    # fc2 INPUT 用 FC2-PPV- 形式（scraper 接受）；輸出 .number=FC2-{id}（無 PPV），numbers_match 橋接

    "avsox": ["051119-917"],  # known-dead until US5（站方轉 SPA + 403）；T3 預期 all-skip
}
