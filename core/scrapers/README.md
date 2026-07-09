# core/scrapers — 來源爬蟲文件

> **適用狀態：post-spec-85（v0.11.0）**  
> 描述清理後的穩定行為。不包含已移除的死碼（javbus variant 探查、SCRAPER_CLASSES 等）。

---

## 1. 來源能力矩陣

### 1.1 有碼來源（CENSORED_SOURCES）

| 來源 ID | 顯示名 | exact 番號 | keyword-fuzzy | prefix 範圍 | 需 proxy | 桌面限定 CF | 封面浮水印 | 備註 |
|---------|--------|-----------|---------------|------------|---------|------------|-----------|------|
| `dmm` | DMM | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | GraphQL API；需日本 IP（VPN/proxy）；數位 PPV 新片優先；封面高畫質 |
| `javbus` | JavBus | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | 直打 detail URL；封面無浮水印但**僅右半裁切**；搜尋端點 `/search/` 已 404（站方改版，variant 探查已移除，見 §2） |
| `jav321` | Jav321 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | keyword 搜尋恆回空，故不入 FUZZY_SEARCH_SOURCES |
| `javdb` | JavDB | ✅ | ❌ | ❌ | ❌ | ⚠️ | ✅ | 重複 keyword 呼叫觸發 Cloudflare ban，故不入 FUZZY_SEARCH_SOURCES；封面有浮水印 |
| `javlibrary` | JavLibrary | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | **manual_only**：不進 SOURCE_ORDER fan-out；exact-only（CD-70b）；需 CfTransport（桌面版限定）；封面 hotlink DMM CDN（`pl.jpg`，同 dmm 無浮水印）；手動版本切換：**eager 全抓、新片優先、三手動入口（lightbox/search/switch-source）多版本皆出切換器**（spec-86 done，含 T7 switch-source follow-on） |

### 1.2 無碼來源（UNCENSORED_SOURCES）

| 來源 ID | 顯示名 | exact 番號 | keyword-fuzzy | prefix 範圍 | 需 proxy | 桌面限定 CF | 封面浮水印 | 備註 |
|---------|--------|-----------|---------------|------------|---------|------------|-----------|------|
| `d2pass` | D2Pass | ✅ | ❌ | ❌ | ❌ | ❌ | [需確認] | 無碼；日期格式番號（caribbeancom / 1pondo 等） |
| `heyzo` | HEYZO | ✅ | ❌ | ❌ | ❌ | ❌ | [需確認] | 無碼；HEYZO-XXXX 格式 |
| `fc2` | FC2 | ✅ | ❌ | ❌ | ❌ | ❌ | [需確認] | 無碼；javten.com 鏡像；**無發行日**（`date=""` 硬定） |
| `avsox` | AVSOX | ✅ | ❌ | ❌ | ❌ | ❌ | [需確認] | 無碼；模糊鏈永不呼叫（`search_by_keyword` 刻意不接線） |

### 1.3 常數定義位置

```
core/scrapers/utils.py
  CENSORED_SOURCES    = ['dmm', 'javbus', 'jav321', 'javdb']  (+ javlibrary append)
  UNCENSORED_SOURCES  = ['d2pass', 'heyzo', 'fc2', 'avsox']
  SOURCE_ORDER        = CENSORED_SOURCES + UNCENSORED_SOURCES  # 8 elem，不含 javlibrary
  PROXY_SOURCES       = {'dmm'}
  FUZZY_SEARCH_SOURCES = ['javbus', 'dmm']
```

> `javlibrary` 在 `SOURCE_ORDER` 建立後才 `append` 進 `CENSORED_SOURCES`，確保不污染 fan-out 排序（CD-70b-10）。

### 1.4 評分 / 簡介覆蓋（NFO-only，spec-93）

各來源網站有提供才抓，寫進 `Video.rating`（parse 一律正規化 0–5，NFO writer ×2→Jellyfin 0–10）/ `Video.summary`。**NFO-only**：經 `_summary`/`_rating` internal carrier 只流向 NFO `<plot>`/`<rating>`（給 Jellyfin/Emby/Kodi 顯示），API 回前端前一律 strip、不進 DB、不進 OpenAver UI、不翻譯（US7 契約）。

| 來源 | 評分 | 簡介 | 取得方式（皆同請求免費，除註記） |
|------|------|------|----------------------------------|
| `dmm` | ✅ | ✅ | 簡介＝主 `DETAIL_QUERY` 的 `description`；評分＝**獨立 root probe** `reviewSummary(contentId:){average}`（三態 cache、禁擴 `DETAIL_QUERY`、失敗降級不影響主 metadata）|
| `jav321` | ✅ | ✅ | 同頁文字 `平均評価: N.N`（0–5，勿 ÷10）+ 描述 div |
| `fc2` | ✅ | ✅ | JSON-LD `aggregateRating`（支援 `@graph`）+ `div.col.des` 簡介 |
| `heyzo` | ✅ | ✅ | 同一 JSON-LD `aggregateRating` + `description` |
| `d2pass`（1pondo/10musume）| ✅ | ✅ | 同一 phpauto JSON `AvgRating`（`<=5` guard）+ `Desc` |
| `d2pass`（caribbeancom）| ✅ | ✅ | **JSON API 已死→HTML fallback**：moviepage `itemprop=description` + `meta-rating` 星數 rune-count（0–5）|
| `javdb` | ✅ | ❌ | `.panel-block` 文字 `評分: N.N分`（站上無簡介）|
| `javbus` / `avsox` | ❌ | ❌ | 站上無此兩格 → 不做 |

---

## 2. 番號重複（collision）行為

### 2.1 各來源預設給哪部

| 情境 | 行為 |
|------|------|
| JavBus 裸 URL（`/SONE-001`）| 命中舊版（第一個上架的版本） |
| DMM GraphQL | 命中數位版（通常為最新版） |
| JavLibrary 搜尋列表 | 可能回傳多筆版本（見 §2.2） |

### 2.2 版本切換現況

- **JavBus variant 探查（spec-85 已移除）**：舊版透過 `/search/` 端點枚舉同番號多版本 ID，但該端點於 2025 年站方改版後已 404。依賴此機制的 `get_all_variant_ids` / `search_by_variant_id` 及前端版本切換 UI 已在 **spec-85 全棧原子清除**。
- **JavLibrary 手動版本切換（spec-86 done）**：同番號多版本的使用者手動切換，基於 JavLibrary 搜尋列表（非 JavBus 搜尋）。開窗時 eager 全抓所有候選的完整 detail、新片優先排序（發行日 desc，預設游標停在最新）。**三個手動入口遇多版本皆出現封面 `‹ ›` 切換器**讓使用者選版本，採用語意各異：lightbox 寫入選定版本 NFO/封面（保留不可逆警告）、search 採用選定版本進結果列、switch-source 以選定版本就地替換當前結果卡。**switch-source 單版本維持靜默直接替換**（最小驚訝；多版本才開切換器，spec-86 D7 follow-on 已於 T7 實作，反轉原 Non-Goal）。不進批次匯入、不揭露 AI agent（detail_url 為內部路由細節，AC9）。

---

## 3. 搜尋路由架構

`smart_search(query, ...)` 的四條分派路徑（`core/scraper.py`）：

### 3.1 四模式分派

| 模式 | 觸發條件 | 實際呼叫 | 引擎選擇原則 |
|------|----------|---------|-------------|
| **exact** | `is_number_format(query)` — 完整番號（SONE-205） | `search_jav_single_source(query, sid)` × enabled sources | 依 `get_enabled_source_ids()` 優先序串接直打，命中即回（early-return），不等其他來源 |
| **partial** | `is_partial_number(query)` — 縮略番號（MIDV-01） | `search_partial()` → JavBus 固定 | 能力約束：只有 JavBus 能做番號前綴枚舉；非技術債，不動 |
| **prefix** | `is_prefix_only(query)` — 純前綴（MIDV） | `search_prefix()` → JavBus `get_ids_from_search(type=1)` | 同上，JavBus 固定；fallback 依序試 actress → keyword |
| **actress/keyword** | 其餘 | `_fuzzy_search_chain()` → FUZZY_SEARCH_SOURCES | Active-Row 順序選引擎，always-on（見 §3.2） |

### 3.2 Fuzzy Chain Always-On（CD-65-4）

`FUZZY_SEARCH_SOURCES = ['javbus', 'dmm']` 是**能力白名單**，不跟隨 enabled 開關：

- 使用 `get_all_source_ids_ordered()`（含停用來源），而非 `get_enabled_source_ids()`。
- 理由：metatube 等其他來源不具模糊能力；javbus / dmm 是「模糊引擎」角色，與主來源開關正交。
- 排除 jav321（keyword 恆回空）、javdb（重複呼叫觸發 CF ban）。

### 3.3 Exact 模式設計決策（spec-85 確立）

**採用「依優先序串接直打、命中即回（cascade early-return）」，捨棄 wait-all fan-out。**

| 方案 | 延遲（POC 實測） | 問題 |
|------|----------------|------|
| 串接直打（採用） | ~1–2.3s（命中首位或次位） | 單來源結果，不做多來源 merge |
| wait-all fan-out | 10–24s | 被最慢來源拖死；POC 確認不可行 |

cascade 行為：
- `enabled_sids = get_enabled_source_ids(availability_map)` — 尊重使用者拖曳順序
- 逐一呼叫 `search_jav_single_source(query, sid)`，命中（非空）即 `return [res]`
- 全部 miss → 回 `[]`（不 fallback 到 fan-out）
- `mode=exact` 不帶 `&source=`（UI 觸發不到此路徑）維持原 wait-all 語意，作為 API 逃生口

---

## 4. 介面契約

### 4.1 BaseScraper（`core/scrapers/base.py`）

```
class BaseScraper(ABC):
    # 必須實作（abstract）
    def _get_source_name(self) -> str:           # 回傳來源 ID（如 'javbus'）
    def search(self, number: str) -> Optional[Video]:   # 精確番號搜尋
    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:  # 關鍵字搜尋
    
    # 預設實作
    def validate_number(self, number: str) -> bool      # 正規式格式驗證
    def normalize_number(self, number: str) -> str      # 委派 normalize_number_impl()
```

`search()` 約定：
- 回傳 `Video` 物件（命中）或 `None`（找不到）
- 格式錯誤拋 `ValueError`；網路超時拋 `TimeoutError`
- 不應 raise 其他未預期例外（caller 依 exception boundary 決定 fallback）

### 4.2 normalize_number（`core/scrapers/utils.py:normalize_number_impl`）

post-spec-85（T1c 解耦後）：standalone 函式，不再實例化 `JavBusScraper`。

功能：大寫化、補連字號（`sone103` → `SONE-103`）、去除 `-UC`/`-UNCEN`/`-LEAKED` 後綴、strip 空白。

呼叫路徑：
- `core/scraper.py:normalize_number()` — module-level 公開 API，委派 `normalize_number_impl()`
- `BaseScraper.normalize_number()` — instance method，同樣委派；`D2PassScraper` override 處理日期格式特例

### 4.3 Video model（`core/scrapers/models.py`）

| 欄位 | 類型 | 說明 |
|------|------|------|
| `number` | str | 番號（SONE-205） |
| `title` | str | 影片標題 |
| `actresses` | list[Actress] | 女優列表 |
| `date` | str | 發行日期（YYYY-MM-DD）；FC2 恆為空 |
| `maker` | str | 片商 |
| `cover_url` | str | 封面 URL |
| `tags` | list[str] | 類別標籤 |
| `source` | str | 資料來源 ID |
| `detail_url` | str | 詳情頁 URL |
| `director` | str | 導演 |
| `duration` | Optional[int] | 片長（分鐘） |
| `label` | str | 發行商/レーベル |
| `series` | str | 系列 |
| `sample_images` | list[str] | 劇照 URL 列表 |
| `rating` | Optional[float] | 評分 |
| `votes` | Optional[int] | 投票數 |
| `summary` | str | 簡介（僅供 NFO，不進 `to_legacy_dict`） |

---

## 5. 封面優先序

封面欄位（`cover_url` / `sample_images`）依 **user_order（使用者在「掃描來源」頁的拖曳順序）** 解析，取第一個非空來源，兩欄各自獨立（`core/source_merger.py`）。

**不存在硬編碼封面優先序**：來源排序完全由 user_order 決定，無寫死的 cover priority 常數。

浮水印特性影響推薦排序：

| 來源 | 封面特性 | 推薦排序建議 |
|------|----------|------------|
| JavBus | 無浮水印，但右半裁切 | 排前（若可接受裁切）|
| DMM | 無浮水印，全框高畫質 | 排前（需 proxy） |
| Jav321 | 無浮水印，全框 | 排前 |
| JavDB | **有浮水印** | 排後（避免封面帶水印） |

> 用戶若將 JavDB 排前，封面將帶浮水印。推薦：JavBus / DMM / Jav321 排於 JavDB 之前。

---

## 6. 陷阱速查

完整陷阱列表見 [`feature/AI_COLLABORATION/gotchas-backend.md`](../../feature/AI_COLLABORATION/gotchas-backend.md)，以下為最高頻觸發點一覽：

| 陷阱 | 一句話 |
|------|--------|
| Mock patch target | 測試 patch 要指**使用端** `core.scraper.*`，不是定義端 `core.scrapers.javbus.*`；否則 mock 不生效、測試打真網路 |
| DMM proxy gate | `search_jav_single_source(q, 'dmm')` 無 `proxy_url` 時 DMM 回 `None`，cascade 繼續試下一個來源（預期行為） |
| JavBus 搜尋端點已死 | `/search/{keyword}` 回 404；exact 走 detail URL（正常）；partial/prefix 走 `get_ids_from_search`（正常）；**不可**再實作任何依賴 `/search/` 的功能 |
| javlibrary manual_only | `get_enabled_source_ids()` 自動排除 manual_only 來源，javlibrary 不進 cascade head；只能由進階搜尋顯式指定 |
| fuzzy always-on | 停用 javbus/dmm 只影響 exact cascade；模糊路徑仍會呼叫它們（設計如此，CD-65-4） |
| FC2 無發行日 | FC2 scraper 硬定 `date=""`，不可視為 bug |
| 路徑處理 | `file:///` URI 轉換一律用 `core/path_utils.py`，禁止手動 strip/建構 |
