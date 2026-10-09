"""core/auto_organize.py — 自動整理一輪的純同步本體（spec-144 T3 / plan CD-144-4..7）。

run_one_round() 全同步：列檔 → .nfo／記憶／番號過濾 → smart_search → 翻譯判斷
→ organize_file → 四類統計。不含排程、不含鎖——中止與宣告只透過 should_abort /
on_file_start 兩個 Callable 參數，本模組對它們的實作一無所知（T4a 的事）。
core 層，禁止 import 任何 web.* 符號（BE-LINT-01）。
"""
import asyncio
import os
from typing import Callable, Optional

from core.database import organize_failures
from core.db_inflow import try_inflow_upsert
from core.favorite_scan import detect_nfo, list_favorite_video_files, resolve_favorite_folder
from core.logger import get_logger
from core.organizer import extract_chinese_title, organize_file
from core.path_utils import coerce_to_file_uri
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.scraper import smart_search, search_jav, is_number_format
from core.scrapers.utils import extract_number, has_japanese
from core.source_settings import is_uncensored_mode_effective
from core.translate_service import create_translate_service
from core.wishlist_reconcile import reconcile_wishlist

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 失敗記憶是 best-effort（Codex PR#181 五審 P1 ／ 六審 P3）
#
# 它只是「省得重問 8 個來源」的快取，**不該有權殺掉整輪**：DB 一鎖住（背景掃描正在寫）
# 這些呼叫就拋例外 ⇒ 整輪當場結束、一部片都沒整理，排程還要再等 12 小時。
# 手動清單那一邊已經是 best-effort（web/routers/search.py::_filter_files_sync），
# 自動不該比手動嚴格——「與手動同一份判斷」是這支 branch 自己的原則。
# 查不到就當作沒有記憶：頂多多問一次 8 個來源，而那正是沒有這個快取時的行為。
# ---------------------------------------------------------------------------

def _memory_says_skip(upper_number: str, dup_key: str) -> Optional[bool]:
    """查失敗記憶。回 True/False＝查得到；回 **None**＝查不到（呼叫端本輪起不再查）。"""
    try:
        return bool(
            organize_failures.should_skip('not_found', upper_number)
            or organize_failures.should_skip('duplicate', dup_key)
        )
    except Exception:
        logger.warning(
            "[auto_organize] 讀取失敗記憶失敗，本輪不再查詢記憶（照常整理，"
            "查無結果／重複的片這一輪會被重新問一次）", exc_info=True,
        )
        return None


def _remember_failure(reason: str, key: str, number: str, **kwargs) -> bool:
    """記一筆失敗記憶；成功回 True。記不起來頂多下一輪再問一次，不值得把整輪賠進去。"""
    try:
        organize_failures.record_failure(reason, key, number, **kwargs)
        return True
    except Exception:
        logger.warning(
            "[auto_organize] 記錄「%s」失敗（%s），本輪繼續", reason, number, exc_info=True,
        )
        return False


def run_one_round(
    config: dict,
    should_abort: Optional[Callable[[], bool]] = None,
    on_file_start: Optional[Callable[[str], None]] = None,
) -> dict:
    """跑一輪自動整理，回傳統計 dict（schema 見 plan T3 步驟 8，唯一定義）。"""
    added = []
    cover_missing = []
    failed = []
    skipped_has_nfo = 0
    skipped_memory_hit = 0
    skipped_duplicate = []
    newly_recorded = 0
    memory_ok = True   # 失敗記憶掛掉之後本輪不再查（整輪只記一行 log，1965 個檔不能記 1965 行）
    aborted_after = None

    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})  # 整輪只取一次（DoD-7）

    folder = resolve_favorite_folder(config)
    if not folder:
        return {"folder_not_configured": True}

    # 唯讀 guard：對「最愛資料夾」本身判一次，不逐檔判（CD-144-7）
    ro_prefixes = readonly_source_prefixes(gallery_config, path_mappings)
    wr_prefixes = writable_source_prefixes(gallery_config, path_mappings)
    if is_path_readonly(coerce_to_file_uri(folder, path_mappings), ro_prefixes, wr_prefixes):
        return {"readonly": True}

    files = list_favorite_video_files(folder, config)
    # 列不到目錄就**這一輪什麼都不動**（Codex PR #181 二審 P0）。
    # 政策跟 list_favorite_video_files 那邊是一對：
    #   單一檔案問不到 → 跳過那個檔（還有 N-1 部可以做）
    #   整個資料夾問不到 → 一部都不做（我們不知道哪些片已經刮好了）
    # 沿用既有的 folder_unreachable 哨兵——scheduler 已經有這個分支與通知文案
    # （`notif.auto_organize_folder_unreachable`「定時整理：無法存取最愛資料夾」），
    # 不新增機制、不新增 i18n。`folder` 由 scheduler 的 setdefault 補上。
    try:
        nfo_map = detect_nfo(files, strict=True)
    except OSError:
        logger.warning(
            "[auto_organize] 偵測 NFO 時列不到最愛資料夾，本輪不處理任何檔案：%s",
            folder, exc_info=True,
        )
        return {"folder_unreachable": True}

    uncensored_mode = is_uncensored_mode_effective(config)  # 整輪只算一次（DoD-7 慣例）
    scraper_config = config.get('scraper', {})
    translate_config = config.get('translate', {})
    translate_enabled = translate_config.get('enabled', False)
    # locale 一定要傳（Codex PR #181 P1）：`create_translate_service` 的 target_language
    # 預設是 "zh-TW"，少傳這一個參數 ⇒ **不論使用者把介面語言設成什麼，一律翻成繁中**，
    # 而這裡的翻譯結果會蓋掉標題、進**檔名／資料夾名／NFO <title>**（core/organizer.py:1092、
    # :1211、:1336），是無人值守的批次寫入。手動那條路（web/routers/translate.py:65-68）
    # 本來就有傳，只有這條新路徑漏了。
    # 對日文使用者尤其致命：三個 provider 的 translate_single 都有
    # `if self.target_language == "ja": return title` 這條**專門保護日文使用者的短路**，
    # 但服務永遠是用 "zh-TW" 建出來的 ⇒ 那條短路從來打不到，日文標題全被翻成繁中。
    #
    # 建構本身也要保護（Codex PR #181 第二條）：provider=gemini 而 API key 是空字串時
    # `GeminiTranslateService.__init__` 直接拋 ValueError（設定頁存得出這個狀態——
    # 沒有跨欄位驗證，「切到 Gemini、還沒貼 key 就存檔」是很平常的順序）。
    # 這一行在 per-file try/except 之外 ⇒ 整輪 0 部片被處理，使用者只看到一則
    # 「定時整理失敗，請查閱日誌」，看不出是翻譯設定沒配好。
    # 翻譯是**加分項不是前提**，建不起來就降級成「這一輪不翻譯」，繼續整理（與 DoD-8
    # 「翻譯失敗不擋、不計 failed」同一個政策）。
    translate_service = None
    if translate_enabled:
        locale = config.get('general', {}).get('locale', 'zh-TW')
        try:
            translate_service = create_translate_service(translate_config, locale)
        except Exception:
            logger.warning(
                "[auto_organize] 翻譯服務建不起來（provider 未配好？），本輪不翻譯照常整理",
                exc_info=True,
            )
            translate_service = None

    completed = 0
    for path in files:
        # ① should_abort → ② extract_number → ③ on_file_start，順序不可顛倒（DoD-5）
        if should_abort is not None and should_abort():
            aborted_after = completed
            break

        filename = os.path.basename(path)
        # 番號一律從 basename 取：與 web/routers/search.py::_filter_files_sync 同源（CD-144-8 要求兩邊算出同一個鍵），等價性由 tests/unit/test_number_extraction_key_parity.py 守
        number = extract_number(filename)
        if not number:
            continue  # 無番號跳過，不計數，不呼叫 on_file_start

        if on_file_start is not None:
            on_file_start(number)

        if nfo_map.get(path, False):
            skipped_has_nfo += 1
            completed += 1
            continue

        upper_number = number.upper()
        dup_key = organize_failures.duplicate_key(path, path_mappings)  # 純函式，不碰 DB
        if memory_ok:
            hit = _memory_says_skip(upper_number, dup_key)
            memory_ok = hit is not None      # None＝DB 掛了，本輪起不再問
            if hit:
                skipped_memory_hit += 1  # 記憶命中不算事件（DoD-9）
                completed += 1
                continue

        if is_number_format(number) or uncensored_mode:
            results = smart_search(number, uncensored_mode=uncensored_mode)  # CD-144-4：逐字同手動批次
        else:
            _r = search_jav(number)
            results = [_r] if _r else []
        if not results:
            if _remember_failure('not_found', upper_number, number):
                newly_recorded += 1
            failed.append(number)
            completed += 1
            continue

        metadata = dict(results[0])  # CD-144-5：原樣，不加不減（不覆蓋 number）

        chinese_title = extract_chinese_title(filename, number, metadata.get('actors'))
        if not chinese_title and translate_service is not None and has_japanese(metadata.get('title', '')):
            try:
                translated = asyncio.run(translate_service.translate_single(metadata['title']))
            except Exception:
                # 不擋、不計 failed（DoD-8），但要留痕（Codex PR #181 二審 P3）：
                # 無人值守跑完只會回報「成功」，沒有這一行就查不出為什麼標題沒翻。
                logger.warning(
                    "[auto_organize] 翻譯失敗，%s 沿用原標題", number, exc_info=True,
                )
                translated = ""
            if translated:
                metadata['translated_title'] = translated

        organize_result = organize_file(path, metadata, scraper_config)

        if organize_result.get('duplicate'):
            target = organize_result.get('duplicate_target', '')
            if _remember_failure('duplicate', dup_key, number, duplicate_target=target):
                newly_recorded += 1
            skipped_duplicate.append({"number": number, "target": target})
        elif organize_result.get('success'):
            try:
                organize_failures.clear_on_success(number)
            except Exception:
                logger.warning(
                    "[auto_organize] 清除失敗記憶失敗（%s），整理已完成、本輪繼續", number, exc_info=True,
                )
            # in-flow upsert：與手動整理（web/routers/scraper.py:276）同一個動作。
            # 少了這一行，自動整理成功的片**不會進 DB**——瀏覽頁看不到它、
            # 迴圈結束那次 reconcile_wishlist() 也查不到它（對帳走
            # VideoRepository.get_by_numbers），spec §F5「自動入庫的片同輪從書籤消失」
            # 因此永遠不成立。try_inflow_upsert 自帶 try/except、回字串不拋，
            # 不在 Scanner 追蹤夾內時靜默回 "not_linked"。
            target_file = organize_result.get('new_filename')
            if target_file:
                try_inflow_upsert(target_file, old_file_path=path)
            if organize_result.get('cover_path'):
                added.append(number)
            else:
                cover_missing.append(number)
        else:
            failed.append(number)

        completed += 1

    # 迴圈結束（含被中止的情況）跑一次。**必須包 try**：這一步在整輪的最後，
    # 片已經全部搬完改完名了。它拋例外（掃描正在寫、DB 鎖住）會讓整輪冒到排程的
    # except，發一則「定時整理失敗」——而那一輪其實全部成功，摘要根本沒發出去 ⇒
    # 使用者不知道那幾十部已經被搬走改名，而且它們現在都有 NFO 了、下一輪一律跳過，
    # 這筆帳永遠補不回來。通知是這個功能唯一的帳本（spec §F5），不能誤報。
    # 形狀照 web/routers/scanner.py:739-743（另外三個呼叫點都是這樣包的）。
    wishlist_reconcile_failed = False
    try:
        wishlist_removed = reconcile_wishlist()
    except Exception:
        logger.exception("[auto_organize] wishlist 對帳失敗（本輪收尾）；整理結果不受影響")
        wishlist_removed = []
        wishlist_reconcile_failed = True

    return {
        "added": added,
        "cover_missing": cover_missing,
        "failed": failed,
        "skipped": {
            "has_nfo": skipped_has_nfo,
            "memory_hit": skipped_memory_hit,
            "duplicate": skipped_duplicate,
        },
        "newly_recorded": newly_recorded,
        "wishlist_removed": wishlist_removed,
        "wishlist_reconcile_failed": wishlist_reconcile_failed,
        "aborted_after": aborted_after,
    }
