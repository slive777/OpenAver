# 測試樣本資料

Phase 16 Task 2: 爬蟲測試用樣本番號

> ⚠️ **DMM 測試注意**：DMM API 需要日本 IP，必須開啟 VPN（如 Surfshark 日本節點）才能連線。
> 不開 VPN 時 DMM 網路測試會失敗，這是正常的。離線測試（番號解析、前綴轉換）不需要 VPN。

## 使用方式

```python
from tests.sample import (
    CENSORED_SAMPLES,
    UNCENSORED_SAMPLES,
    FC2_SAMPLES,
    DMM_CONTENT_ID_SAMPLES,
    get_sample_by_source,
)

# 取得特定來源的測試番號
javbus_samples = get_sample_by_source("javbus")
fc2_samples = get_sample_by_source("fc2")
```

## 樣本分類

### 有碼番號 (CENSORED_SAMPLES)

| 番號 | 片商 | 女優 | 支援來源 |
|------|------|------|----------|
| SONE-205 | S1 | 未歩なな | javbus, jav321, javdb, dmm |
| SSNI-001 | S1 | 三上悠亞 | javbus, jav321, javdb |
| MIDV-018 | Moodyz | 高橋しょう子 | javbus, jav321, javdb |
| STARS-804 | SOD | 永野いち夏 | javbus, jav321, javdb, dmm |
| ABW-001 | Prestige | 河北彩花 | javbus, jav321, javdb |

### 無碼番號 (UNCENSORED_SAMPLES)

| 番號 | 來源 | 支援爬蟲 |
|------|------|----------|
| 051119-917 | caribbeancom | avsox |
| 010120-001 | 1pondo | avsox |

### FC2 番號 (FC2_SAMPLES)

| 番號 | 賣家 | 支援爬蟲 |
|------|------|----------|
| FC2-PPV-1723984 | プライベートマスク | fc2 |

### DMM Content ID 轉換 (DMM_CONTENT_ID_SAMPLES)

| 番號 | DMM Content ID | 說明 |
|------|----------------|------|
| SONE-205 | sone00205 | 無前綴 |
| STARS-804 | 1stars00804 | "1" 前綴 |
| ABW-001 | 118abw00001 | "118" 前綴 |

## 新增樣本

新增測試番號時請確保：

1. 該番號確實存在於目標資料庫
2. 記錄預期的來源 (`expected_sources`)
3. 記錄關鍵資訊（女優、片商、日期等）
4. 如果是 DMM 樣本，記錄 `dmm_content_id`
