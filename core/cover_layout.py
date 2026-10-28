"""cover_layout.py — 封面正典位置解析的單一真理來源（feature/112，CD-112-1）。

依賴 `os`（`os.path` 純字串運算 + `os.path.exists`）＋ `core.logger` ＋
`core.config.STEM_IMAGE_MODES`。
**為什麼有 logger**（T1 卡當時判「不需要」，pre-merge Stage 1 gemini P3-1 推翻）：
本模組原本全是無失敗路徑的純函式，照 `core/enrich_contract.py` 的先例不設 logger；
但 `same_target_verdict` 加入之後模組**有了吞例外的分支**（fail-closed 的 `except OSError`），
那正是 `core/path_utils.py` 之所以有 logger 的同一個判準。吞了不記＝靜默吞噬。
**T3（112b）起 import `core.config.STEM_IMAGE_MODES`**（此前 T1 stub 階段不 import，
理由見下方——`resolve_cover_target` 現在是三步規則本體，第③步要用它做正向白名單判斷，
不再是 unused import）。**不 import** `core.path_utils`。

為什麼用 `os.path` 純字串運算、**不違反** CLAUDE.md 的 `path_utils` 規則：
CLAUDE.md 的路徑處理禁止清單針對的是**跨 Zone 的路徑格式轉換**——手動 strip/建構
`file:///` URI、`replace('/', '\\')` 做分隔符轉換、手動 `startswith('file:///')`
判斷、自建 shadow 路徑轉換 helper。本模組三個函式（`cover_base_stem` /
`cover_candidates` / `resolve_cover_target`）做的是**同一個 Zone 內（Zone 1，已由
呼叫端正規化過的後端 FS 原生路徑）、字串尾端的檔名語意運算**：剝副檔名、剝
`-poster` / `-fanart` 後綴、換副檔名——不跨 Zone、不碰路徑分隔符、不處理
`file://` URI，因此不落在 `path_utils.py` 的管轄範圍內。既有先例一致：
`web/routers/scanner.py::_cover_base_stem`（本模組 `cover_base_stem` 的升格前身，
CD-112-9）本來就在 `path_utils.py` 之外用 `os.path.splitext` + 字串切片；
`core/database/migrate.py`、`core/enricher.py`、`core/organizer.py`、
`core/enrich_contract.py` 等處的 `Path(...).with_suffix('.jpg')` 也都是同一類
「檔名尾端語意運算」，同樣不在 `path_utils.py` 裡。`path_utils.py` 自身的定位是
「支援 Windows 本地 / WSL 網路路徑 / Unix 路徑」的**跨環境格式轉換**，不是
「副檔名／後綴管理」，兩者職責不重疊。

**單一真理來源（CD-112-1）**：本模組是封面正典位置推導邏輯的唯一實作。任何需要
「從封面路徑還原片級 stem」「列出 stem 級候選」「決定本次封面寫到哪」
「算 NFO 圖片旗標」的呼叫點，一律呼叫這裡的公開函式，**不得各自重新推導一份**
（重新推導會製造鏡像漂移，正是 feature/105／111 已經踩過、CD-112-9 意圖根除的
那一類 bug 的成因）。

**PR1（112a）的範圍**：**五個公開函式**（`cover_base_stem` /
`cover_candidates` / `resolve_cover_target` / `nfo_image_flag` /
`same_target_verdict`）全部落地，但當時 **`resolve_cover_target` 是 stub**——本體
無條件回傳同名候選，不檢查磁碟、不檢查 `external_manager`。

**T3（PR2，feature/112b）已把 stub 換成三步規則本體**：① 同名候選存在 → 沿用
② fanart 候選存在 → 沿用 ③ 皆無 → `external_manager in STEM_IMAGE_MODES` ? fanart
候選 : 同名候選（正向白名單，非法值 fail-closed 落到同名）。

六個產出端推導點**已在本 PR 的 T2b 全部換成呼叫 `resolve_cover_target`**（純代換：
stub 恆回同名 `.jpg`，逐字等價）；`scanner.py` 的 `_cover_base_stem` 已在 T2c 刪除
並改 import 本模組的 `cover_base_stem`。
> ⚠️ 本段在 T1 當下寫的是「四個公開函式／零呼叫端改動」——那是 T1 那一個 commit
> 的事實，但同一支 PR 的 T2b/T2c 之後就不再成立。pre-merge Stage 2 review 抓到這份
> 過期敘述（單一真理來源的模組不該對自己的現況說謊），已更正。

**`same_target_verdict` 的交棒清單（CD-112-8 說「所有」，此處是窮舉，勿再只列 3 處）**

⚠️ **清單的判準是「寫入 stem 級衍生圖位置的每一個寫入點」，不是「以 cover 為來源的
寫入點」。** T3 當初的稽核用 `grep "copy2(cover, *)" / "crop_to_poster(cover, *)"` 做，
因此只數到 **7 處**，而 curator sidecar 的兩處 `copy2(sidecar, dst)` 寫的是**同樣那兩個
目的檔**、來源不同——結構上對那個 grep 隱形，直到 Codex PR#125 round-2 P1 才浮出來
（2026-08-05）。凡是新增「往 `<stem>-poster.jpg` / `<stem>-fanart.jpg` / 正典封面位置
寫入」的程式碼，**不論來源是誰**，都必須進這張表；`tests/unit/test_cover_write_site_inventory.py`
是這張表的機械對帳（新增任何寫入點都會轉紅，逼人回來看這一段）。

| 位置 | 動作 | 狀態 |
|---|---|---|
| ① `core/organizer.py:608` | `copy2` cover → fanart | ✅ PR1 已保護（preflight ＋ `SameFileError` backstop）|
| ② `core/organizer.py:624` | `crop_to_poster` cover → poster | ✅ PR1 已保護（只有 preflight）|
| ③ `core/enricher.py:300` | `copy2` cover → fanart | ✅ T3 已保護（preflight ＋ `SameFileError` backstop）|
| ④ `core/enricher.py:316` | `crop_to_poster` cover → poster | ✅ T3 已保護（只有 preflight）|
| ⑤ `core/readonly_assets.py::_write_media_images` | `copy2` cover → fanart | ✅ T3 已保護（preflight ＋ `SameFileError` backstop）|
| ⑥ `core/readonly_assets.py::_write_media_images` | `crop_to_poster` cover → poster | ✅ T3 已保護（只有 preflight）|
| ⑦ `core/organizer.py::organize_file` 的**第三份內聯實作** | 已改為呼叫 `generate_jellyfin_images` | ✅ T3 已消滅（不再是獨立實作，同檔保護 100% 繼承自 ①②）|
| ⑧ `core/readonly_assets.py::_write_cover_copy` | `copyfile` 來源封面 → 正典封面位置 | ✅ pre-merge red-team 補（2338c62d）＋ round-1 P2 加 `exists(dst)`（a552f674）＋ round-3 P1 加 collision policy：**`dst` 已存在一律不覆寫**|

**collision policy（Codex PR#125 round-3 P1，2026-08-05）**：同檔判斷擋得住「src 與 dst
是同一個檔」，擋不住「src 與 dst 是**兩個不同的 curator 原檔**」。collocated 佈局
（輸出根落回來源目錄）下，來源同時有 `{stem}.jpg` 與 `{stem}-fanart.jpg` 時，
`find_cover_image` L1 挑同名 → CD-112-7 把 `-fanart` 升格為複製**來源**，而
`resolve_cover_target` 第①步看到同名檔已存在 → 把它當**目標**，兩邊各對一半、
互相覆寫。修法分兩層：
- **⑧ 層**：`dst` 已存在就沿用、零寫入（與第①②步的「沿用」語意同源；`('copy', …)`
  全庫只有 ingest 一個生產者，齒輪重刮走 `('download', …)` 不經過這裡）。
- **來源層**：`resolve_ingest_plan` 的第三元素改為**宣告所有存在的 sidecar**
  （`'fanart'` 不再恆 `None`）——原本那個 `None` 的前提是「`cover_fs` 會等於 fanart
  路徑」，在上述佈局下為假。
| ⑨ `core/readonly_assets.py::_copy_curator_sidecar` | `copy2` curator **sidecar** → fanart | ✅ round-2 P1 已保護（preflight ＋ `SameFileError` backstop；兩個 slot 共用同一個 choke point）|
| ⑩ 同上 | `copy2` curator **sidecar** → poster | ✅ 同 ⑨（不再各自 `copy2`）|
| ⑫ `core/organizer.py::_acquire_cover` | `copyfile` 上傳暫存封面 → 正典封面位置 | ✅ 豁免（183-T5a）：來源恆為資料根 `tmp/cover-upload/<token>.jpg`（伺服器 resolve 出的路徑），目標在媒體庫，結構上不可能同檔，不加 preflight |

（`core/organizer.py:506` 的 `copy2` 在 `crop_to_poster` **內部**——「已是直向、無需
裁切」的葉節點分支，它的保護 100% 繼承自呼叫端 ②④⑥ 的 preflight，不是獨立寫入點。）

`generate_jellyfin_images` 的呼叫端因此從 2 處變 3 處：`web/routers/scanner.py`
（既有）、`core/readonly_assets.py::_write_media_images`（既有）、
`core/organizer.py::organize_file`（T3 新增，見下方）。
"""

import os

from core.config import STEM_IMAGE_MODES
from core.logger import get_logger

logger = get_logger(__name__)

COVER_EXT = '.jpg'


def cover_base_stem(cover_fs: str) -> str:
    """從封面路徑還原「片級 stem」：剝掉副檔名，再剝掉 -poster / -fanart 後綴。

    <dir>/ABC-123-fanart.jpg → <dir>/ABC-123

    升格自 web/routers/scanner.py::_cover_base_stem（CD-112-9），行為**逐字等價**
    ——包含它的既有限制，本函式不修正、不擴充：
    - `os.path.splitext` 只剝**最後一個**副檔名（中段的 `.` 不受影響，例如
      `ABC-123.vol1.jpg` → `ABC-123.vol1`）。
    - 用 `str.endswith` + 切片剝一次後綴，**大小寫敏感**（`-FANART` 不會被剝）。
    - 只剝一次（`break`）：先剝掉尾端 `-fanart`，即使剝完後仍以 `-poster` 結尾
      也不會連著剝掉第二層。
    - 純尾碼比對，**不消歧義**：`my-fanart.jpg` 這種本來就以 `-fanart` 結尾的
      原生檔名，一樣會被剝成 `my`——這是既有的結構性二義性（CD-112-9 是純升格，
      不是這裡順手修掉）。

    回傳形狀：`str`，與輸入同一個路徑格式（不做任何 Zone 轉換）。
    """
    stem = os.path.splitext(cover_fs)[0]
    for suffix in ('-poster', '-fanart'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    return stem


def cover_candidates(base_stem: str) -> tuple[str, str]:
    """(同名, fanart) 兩個 stem 級候選，順序即優先序（CD-112-3）。

    純字串串接，零 I/O——不呼叫 `os.path.exists`，呼叫端自行決定要不要檢查磁碟。
    """
    return (base_stem + COVER_EXT, base_stem + '-fanart' + COVER_EXT)


def resolve_cover_target(base_stem: str, external_manager: str) -> str:
    """本次封面應該寫到哪 / 記帳該指哪（spec §2.1.1）。

    三步規則（CD-112-3／CD-112-3b，T3 落地）：
    ① `<base_stem>.jpg`（同名候選）已存在 → 沿用
    ② `<base_stem>-fanart.jpg`（fanart 候選）已存在 → 沿用
    ③ 皆無 → 依 flavour 新建：`external_manager in STEM_IMAGE_MODES` ? fanart 候選 : 同名候選

    ①→② 的順序必須與 `find_cover_image` 的 L1 > L1.5 同序（CD-112-3），兩者都用
    `cover_candidates` 的回傳順序，不自行重排。

    ③ 用**正向白名單**（`BE-CONFIG-03`）：`external_manager` 在這條路徑上是純
    `str`，不經 Pydantic `Literal` 驗證。非法值／大小寫不符／`None` 一律
    fail-closed 落到「同名」（＝改動前行為），**不得寫成 `!= 'off'`**。
    """
    same, fanart = cover_candidates(base_stem)
    if os.path.exists(same):
        return same
    if os.path.exists(fanart):
        return fanart
    return fanart if external_manager in STEM_IMAGE_MODES else same


def nfo_image_flag(base_stem: str, suffix: str, wrote_this_run: bool) -> bool:
    """餵給 generate_nfo 的 has_poster / has_fanart（CD-112-16）。

    = wrote_this_run or os.path.exists(base_stem + suffix + COVER_EXT)

    Why 磁碟真相而非「本次寫了什麼」：唯讀路徑的 NFO 是無條件重寫，preserve
    命中時「本次沒產圖」，若照實傳 False，`generate_nfo` 會把圖片標籤退回指向
    同名 `.jpg`——那個檔在新佈局可能不存在。

    ⚠️ 只准餵 generate_nfo，不得回灌 _clean_stale_singletons：後者必須維持
    「本次真的產了新檔才刪舊檔」這個既有語意，否則會把還在服役的正典封面
    當成過期檔案刪掉。
    """
    return wrote_this_run or os.path.exists(base_stem + suffix + COVER_EXT)


def same_target_verdict(src: str, dst: str) -> tuple[bool, bool]:
    """判斷 src / dst 是否指向磁碟上同一份檔案，回傳 `(is_same, certain)` 雙訊號。

    Stage 2 review P1（feature/112a pre-merge，2026-08-04，推翻前身 `is_same_target`
    的單一布林設計）：**「要不要寫」與「能不能宣稱成功」是兩件事，不能共用同一個
    布林**。舊版 `is_same_target` 對未知 `OSError` fail-closed 回 `True`，呼叫端
    （`generate_jellyfin_images`）看到 `True` 就同時做兩件事——跳過寫入**且**把
    `result['poster']` / `result['fanart']` 設成 `True`。跳過寫入是對的（安全側，
    見下方 fail-closed 理由不變）；但宣稱成功是假的——目的檔案實際上完全沒有被
    建立。這個假成功會沿著呼叫鏈往下傳導、造成兩個具體後果：
    1. `core/readonly_assets.py` 唯讀路徑把 `result['poster']`/`result['fanart']`
       轉成 `generate_nfo(has_poster=..., has_fanart=...)` 的旗標——NFO 因此寫出
       指向**不存在**檔案的 image tag（懸空引用，正是 CD-112-16／AC7 要消滅的
       那一類）。
    2. `_clean_stale_singletons` 在標題漂移時，看到「本次已產圖」就刪掉磁碟上
       舊的 `-poster.jpg`/`-fanart.jpg`，而新檔案實際沒有被寫出——形成一個洞，
       違反該函式 docstring 的明文承諾：「A transient download/generation
       failure this run keeps the matching old file on disk rather than
       leaving a hole」。

    因此把單一布林拆成 `(is_same, certain)`：
    - `is_same`：呼叫端要不要跳過寫入（safety 訊號，決定「動不動作」）。
    - `certain`：這個 `is_same` 判斷有多確定，只有 `certain=True` 時呼叫端才
      可以把 `is_same` 直接當「成功」回報（honesty 訊號，決定「敢不敢宣稱」）。

    五格真值表（唯一權威，呼叫端不得自創其他組合）：

    | 情境 | `(is_same, certain)` | 呼叫端行為 |
    |---|---|---|
    | `src == dst` | `(True, True)` | 不寫、宣稱成功 |
    | `samefile` 回 `True`（hardlink/symlink 別名）| `(True, True)` | 不寫、宣稱成功 |
    | `samefile` 回 `False` | `(False, True)` | 照常寫 |
    | `FileNotFoundError` | `(False, True)` | 照常寫（沒有可被覆寫的同一檔）|
    | 其他 `OSError`（未知）| `(True, False)` | **不寫**（安全不變）、**不得宣稱成功** |

    只有最後一格的 `certain` 是 `False`；其餘四格都「確定」——包括 `is_same=True`
    的前兩格，因為它們的「同一檔」判斷有實證依據（字串相等或 `samefile` 明確
    回答），不確定的只有「未知 `OSError` 底下 dst 究竟長什麼樣」這一件事。

    呼叫端（不附行號，行號會過期）：`organizer.py`、`enricher.py`、
    `readonly_assets.py`，是 CD-112-8「路徑相等或 `os.path.samefile`」原文的單一
    真理來源實作（CD-112-1）。外部庫工具（MDCX/Javinizer 等）常把
    `<stem>-poster.jpg` 建成 `<stem>.jpg` 的 hardlink 或 symlink——此時字串不等
    但兩個路徑是同一個 inode，若不攔下，`crop_to_poster` 會**就地覆寫使用者的
    封面原檔**（實測 800×538 → 379×538，md5 改變），直接違反 prd.md 技術決策
    #6 承重牆「衍生產物不回寫原檔」。

    **fail-closed，但只對「未知」錯誤**：`os.path.samefile` 在權限被拒、或部分
    網路磁碟／Windows 共用資源上會拋 `OSError` 子類（實測 `PermissionError`
    可重現：對父目錄 `chmod 0o000` 後 `os.path.samefile` 直接拋出，不是回傳
    False）。這類**未知**例外拋出時 `is_same` 回 `True`（呼叫端因此跳過寫入）
    ——兩個方向的後果不對稱：誤判「不同檔」而照常寫入，最壞情況是**就地毀損
    使用者原檔（不可逆）**；跳過寫入，最壞情況只是**少產一張衍生圖（可由齒輪
    重刮／掃描頁批次補齊救回）**。不確定時一律選代價小的那邊——但這條路徑
    現在同時回 `certain=False`，呼叫端不再能把「代價小的那邊」誤報成「成功」。

    **`FileNotFoundError` 是唯一的例外，獨立分流、不落入上面的 fail-closed**：
    `dst` 通常是尚未產生的衍生檔（`-poster.jpg` / `-fanart.jpg`），這是最常見
    的情況，`samefile` 對不存在的路徑（`src` 或 `dst` 任一邊）一律拋
    `FileNotFoundError`——這是「沒有可被覆寫的同一檔」，不是「不確定」，回傳
    `(False, True)` 讓正常產圖流程繼續。**這個分流本身就是本函式修過一次的
    TOCTOU 洞**：舊版先呼叫 `os.path.exists(dst)` 判斷要不要進 `samefile`，但
    `exists()` 回傳與 `samefile()` 執行之間存在檔案可被外部程序刪除的窗口——
    `exists()` 剛好回 `True`，`dst` 隨即被刪，`samefile` 才拋出
    `FileNotFoundError`，卻被舊版的 `except OSError` 一併吞成「同一檔」，讓
    呼叫端誤報「已產圖」而目的檔實際不存在，等於重新製造 NFO 懸空引用（Codex
    PR review 第二輪 P1，2026-08-04）。現在的寫法**不再先 `exists()` 探測**，
    直接呼叫 `samefile`，`FileNotFoundError` 由專屬的 `except` 分支承接、與其他
    `OSError` 分開判——沒有「探測」與「使用」分成兩步的時間窗，這條 race 在
    結構上不存在了。**broken symlink**（`os.path.lexists` 為 True 但目標不
    存在）在這裡的行為與「檔案不存在」一致：`samefile` 對 broken symlink 會
    follow 到不存在的目標並拋 `FileNotFoundError`，同樣走「視為不同檔、照常
    寫入」這條路——這是安全的，因為 broken symlink 底下沒有真正的檔案內容
    可以被誤判成 `src` 的別名。

    `st_ino` 在 Windows／FAT32／部分網路磁碟上可能不可靠（不支援 file id 的
    檔案系統上恆為 0），導致把兩個實際不同的檔案誤判成「同一檔」。但這個
    誤判方向一樣落在 fail-closed 那一側（結果等同上面的 fail-closed 例外
    路徑）——後果只是少產一張衍生圖，可接受，不是資料毀損。

    ⚠️ **刻意接受的殘留邊界**：未知 `OSError`（權限被拒、網路磁碟逾時等）時
    `is_same=True, certain=False`，呼叫端跳過寫入且不得宣稱成功——但此時 `dst`
    是否真的存在、內容是否真的與 `src` 相同，**都無法確定**，函式本身也不知道。
    呼叫端因此老實回報「未產圖」，使用者需要手動重新整理／批次補齊來救回這一張。
    這不是被解決的問題，是相對於「誤判不同檔、就地毀損原檔」這個不可逆後果，
    刻意選擇的較輕代價。要徹底排除，需要呼叫端在跳過寫入後另外驗證 `dst` 確實
    存在且內容正確，本函式的職責只到「同檔判斷」為止，不做這件事。**但
    fail-closed 這一路必須留下日誌**（pre-merge Stage 1 gemini P3-1）：改動前
    這類硬性 I/O 錯誤（不合法路徑、`NotADirectoryError`、WinError 123…）會在
    `copy2` 階段炸出、被呼叫端的 `except Exception` 記成「複製失敗」；改為
    preflight 之後它們被本函式攔下，若不記錄就是**靜默吞噬**（雖然不再回報
    假成功，但沒有日誌線索照樣難查）。

    ⚠️ **`src == dst` 這條捷徑不驗存在性**（Stage 1 gemini P2，具名 residual）：
    兩個路徑字面相同時它們**定義上就是同一個目標**，但該檔可能根本不存在
    （例如呼叫端檢查存在性之後、真正動作之前被外部程序刪除）。此時呼叫端會
    回報「已產圖」而檔案不在。今天的唯一後果是 scanner 批次少吐一行警告
    （`generate_jellyfin_images_stream` 只拿它決定要不要 warn）；唯讀路徑
    pre-T3 的 `cover_fs` 與 `fanart_path` 字串永不相等，到不了這條分支。
    **刻意不在此加存在性檢查**：權限錯誤時 `os.path.exists` 會回 False，
    把一個正確的 True 翻成 False → 在 T3 的新佈局下讓 NFO tag 退回 fallback
    → 反而製造懸空引用。**T3 讓唯讀正典變成 `-fanart.jpg` 之後（字串相等成為
    常態路徑），這一條必須重新評估。**
    """
    if src == dst:
        return True, True
    try:
        return os.path.samefile(src, dst), True
    except FileNotFoundError:
        return False, True
    except OSError as e:
        # fail-closed：不寫入，但 certain=False——不得讓呼叫端把這格宣稱成功。
        # 必須記錄——這條路徑會把「目標路徑根本不可寫」這類硬錯誤變成靜默的
        # 「未產圖」，不記就查不到。
        logger.warning(
            "same_target_verdict 無法判定同檔，fail-closed 跳過寫入且不宣稱成功 "
            "(src=%s, dst=%s): %s", src, dst, e
        )
        return True, False
