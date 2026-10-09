"""Live smoke canary — per-source health check (TASK-73b-T3; d2pass split per site in 155c-T2).

Wires the T1 pure decision-core (`classify_one` / `quorum_verdict`) and the T2
evergreen number list (`CANARY_NUMBERS`) into a live smoke suite: one
`test_{source}_canary` per source, each running the real `search()` over its
numbers, adding a reachability probe for Group A, and turning the quorum verdict
into pytest pass / skip / fail.

ZERO production scraper changes. The deterministic judgement logic is covered by
`tests/unit/test_source_canary_logic.py` (runs in CI, no network). This file is
the live shell only — it must NOT be collected by the standard PR command
(`--ignore=tests/smoke -m "not smoke and not e2e"`).

verdict mapping:
  green -> pass (source alive)
  skip  -> pytest.skip (unreachable / known-dead / proxy not configured)
  red   -> pytest.fail (200-but-empty parse, or returned wrong/empty Video)
"""
import pytest

from tests.smoke._canary_core import classify_one, quorum_verdict, GROUP_A, numbers_match
from core.scrapers.errors import SourceBlocked, SourceUnreachable
from tests.smoke._canary_numbers import CANARY_NUMBERS, D2PASS_ACTRESS_CANARY
from tests.smoke._probe import _probe_reachable
from core.scrapers import (
    JavBusScraper,
    JAV321Scraper,
    HEYZOScraper,
    D2PassScraper,
    FC2OfficialScraper,
    JavDBScraper,
    AVSOXScraper,
    DMMScraper,
)

pytestmark = pytest.mark.smoke


def _run_canary(source: str, scraper, note: str = "", method: str = "search") -> None:
    """Run the canary for one source: loop numbers -> classify -> quorum -> verdict.

    quorum needs every number's result before deciding, so this is a per-source
    loop (NOT pytest.parametrize).

    `note` (optional) prepends a source-specific hint to the skip/fail reason so a
    human reading `pytest -r s` can tell an *expected* skip (avsox known-dead,
    javdb CF-ban) from an incidental one — without touching the pure T1 core.

    `method` is the scraper method name to call (string + getattr on purpose:
    a typo surfaces as AttributeError instead of a silent wrong lambda).
    """
    results = []
    first_pass_video = None
    # `getattr` 故意留在迴圈外、也故意不在 try 裡：`method` 打錯字要當場 AttributeError
    # （＝測試自己壞了，該 ERROR），不可以被下面那個 broad except 收成「來源紅了」。
    call = getattr(scraper, method)
    for number in CANARY_NUMBERS[source]:
        try:
            video = call(number)
        except TimeoutError as e:
            # Feed the exception instance (not None) so classify_one row 1 -> skip.
            results.append(classify_one(e, None, number, source))
            continue
        except (SourceUnreachable, SourceBlocked) as e:
            if source == "dmm" and isinstance(e, SourceBlocked):
                # DMM 站方拒絕＝非日本線路（地區限制），不是站壞了：DMM 探針任何 HTTP
                # 回應都算可達，走下面的 video=None 會被判成 row-4 fail（紅燈誤報）。
                print(f"[canary] dmm/{number} 被站方拒絕（非日本線路）: {e} → skip")
                results.append("skip")
                continue
            # Transport-level failure (CF ban / cannot connect). Until 0.15.1 these
            # were swallowed into `None` inside javdb's `_get_html`; typed exceptions
            # (TASK-132a-T2) made them escape `search()` and blow straight past the
            # `except TimeoutError` above, turning the *expected* javdb CF-ban skip
            # into a hard ERROR. Collapsing to `video = None` restores the pre-0.15.1
            # input shape EXACTLY — including the Group A probe below, so a Group A
            # source keeps its row-4 (reachable but empty -> fail) verdict rather
            # than being silently downgraded to skip.
            #
            # NOTE for 132b: this restores the *input*, it does NOT hand out the
            # "all skip = normal" exemption — that comes from Group B membership in
            # `_canary_core.GROUP_B`. The new API canary must NOT join Group B
            # (spec-132 F5: it never touches CF, so all-skip means it is really dead).
            video = None
        except Exception as e:
            # 映射／解析炸掉（欄位型別變了、信封形狀變了、pydantic 驗證失敗…）。
            # 這正是這顆燈存在的理由，卻是唯一會**繞過** classify/quorum 的路徑：
            # 不接的話它是 pytest ERROR ⇒ ① 判決不再來自 classify_one，
            # ② 迴圈當場中止，後面幾個番號一個都沒驗到（Codex PR review P2）。
            #
            # 🔴 **刻意記成 "fail" 而不是塞 `video = None`**：塞 None 的話
            # Group B 會走 classify_one row 6 → skip，而 Group B 的「全 skip 視為正常」
            # 豁免會把**真正的 parser 回歸**吃掉，變成靜靜的綠燈（spec-132 B8 禁止的正是
            # 這種放寬）。記 "fail" 對兩個 group 都是「這個番號壞了」，語意一致。
            #
            # quorum 仍然 pass-wins：一個番號的資料形狀特殊 → 其餘健康 → 綠（正確，
            # 資料介面是活的）；整批都炸 → 紅（正確，形狀真的變了）。
            print(f"[canary] {source}/{number} 映射失敗: {type(e).__name__}: {e}")
            results.append("fail")
            continue
        probe = _probe_reachable(source, number, scraper) if source in GROUP_A else None
        outcome = classify_one(video, probe, number, source)
        if outcome == "pass" and first_pass_video is None:
            first_pass_video = video
        results.append(outcome)

    verdict, reason = quorum_verdict(results)
    if verdict == "green":
        return first_pass_video
    hint = f"{note} — " if note else ""
    if verdict == "skip":
        pytest.skip(f"{source}: {hint}{reason}")
    pytest.fail(f"{source}: {hint}{reason}")


# ========== Group A (probe-backed) ==========

def test_javbus_canary():
    _run_canary("javbus", JavBusScraper())


def test_jav321_canary():
    _run_canary("jav321", JAV321Scraper())


def test_heyzo_canary():
    _run_canary("heyzo", HEYZOScraper())


def _classify_d2pass_one(video, probe_reachable, expected_number, expected_actress) -> str:
    """單筆 d2pass 判定（CD-155c-9）：video 非 None 時番號／標題／封面／預期女優四項全過
    才是 "pass"，任一不過即 "fail"；video 為 None 時比照 Group A 既有語意用 probe 分
    "fail"（可達卻空）／"skip"（不可達）。自成一體，不呼叫 classify_one 本體（CD-155c-6）。
    """
    if video is not None:
        actress_names = {a.name for a in video.actresses}
        if not numbers_match(video.number, expected_number, "d2pass"):
            return "fail"
        if not video.title:
            return "fail"
        if not video.cover_url:
            return "fail"
        if expected_actress not in actress_names:
            return "fail"
        return "pass"
    return "fail" if probe_reachable else "skip"


def _probe_d2pass_site(site: str, number: str, scraper) -> bool:
    """d2pass 三站專用 reachability probe（CD-155c-8）：caribbeancom 打 HTML 詳情頁（JSON
    API 已死，見 CD-155c-1），200 視為可達；1pondo/10musume JSON API 仍活，沿用
    scraper._fetch_json。CONTRACT（比照 _probe.py 檔頭）：永不拋出，任何例外一律回 False。
    """
    try:
        movie_id = scraper.normalize_number(number)
        if site == "caribbeancom":
            url = scraper.SITE_DETAIL_URL[site].format(id=movie_id)
            resp = scraper._session.get(url, timeout=10)
            return resp.status_code == 200
        return scraper._fetch_json(site, movie_id) is not None
    except Exception as e:
        print(f"[canary] d2pass/{site}/{number} probe 例外: {type(e).__name__}: {e}")
        return False


def _run_d2pass_canary(site: str) -> None:
    """D2Pass 單站 canary：迴圈 D2PASS_ACTRESS_CANARY[site] -> 判定 -> quorum -> pytest 結果。

    自成一體（CD-155c-6），不共用 `_run_canary`／`_probe_reachable`；例外處理逐段照抄
    `_run_canary`（TimeoutError -> skip；SourceUnreachable/SourceBlocked -> video=None 走
    probe；其他 Exception -> 記 "fail" 並 continue，避免迴圈中止漏驗後面的番號）。
    """
    scraper = D2PassScraper()
    results = []
    for number, expected_actress in D2PASS_ACTRESS_CANARY[site]:
        try:
            video = scraper.search(number)
        except TimeoutError:
            results.append("skip")
            continue
        except (SourceUnreachable, SourceBlocked):
            video = None
        except Exception as e:
            print(f"[canary] d2pass/{site}/{number} 映射失敗: {type(e).__name__}: {e}")
            results.append("fail")
            continue
        probe = _probe_d2pass_site(site, number, scraper) if video is None else None
        results.append(_classify_d2pass_one(video, probe, number, expected_actress))

    verdict, reason = quorum_verdict(results)
    if verdict == "green":
        return
    if verdict == "skip":
        pytest.skip(f"d2pass/{site}: {reason}")
    pytest.fail(f"d2pass/{site}: {reason}")


def test_d2pass_1pondo_canary():
    _run_d2pass_canary("1pondo")


def test_d2pass_caribbeancom_canary():
    _run_d2pass_canary("caribbeancom")


def test_d2pass_10musume_canary():
    _run_d2pass_canary("10musume")


def test_avsox_canary():
    # Group A (probe-backed): _ensure_session() probe distinguishes site-down (skip)
    # from 200-but-empty-parse (fail). avsox revived via JSON API (US5).
    _run_canary("avsox", AVSOXScraper(), note="avsox revived (JSON API)")


# ========== Group B (quorum-only, no probe) ==========

def test_fc2_canary():
    _run_canary("fc2", FC2OfficialScraper())


def test_javdb_canary():
    # javdb needs curl_cffi (CF bypass). Numbers are deliberately few -> all-skip
    # must not fail (Group B quorum: None probe -> row 6 skip).
    # Hits search_via_html only — the API path has its own canary (Group A).
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        pytest.skip("curl_cffi not installed")
    _run_canary(
        "javdb",
        JavDBScraper(),
        note="javdb all-skip likely CF-banned",
        method="search_via_html",
    )


def test_javdb_api_canary():
    # Group A: never touches Cloudflare, so all-skip means the API path is dead.
    # 拿回**真的通過 quorum 的那一部**——不可以再自己抓 `[0]`：第一個番號被下架、
    # 但後面某個過了的時候，quorum 是綠（pass-wins），重抓 `[0]` 卻會回 None ⇒
    # 整支 skip ⇒ 底下的解碼驗證被靜默跳過，而那時明明有一張可用的封面
    # （Codex PR review P3）。順帶少發一次活站請求。
    video = _run_canary("javdb-api", JavDBScraper(), method="search_via_api")

    # 判綠之後才做：抓一張封面 → 走 production 的 host→codec 對應解碼 → 驗魔數。
    # 「解碼規則／host 對應壞了」在 runtime 沒有偵測器（CD-132b-7 說明了為什麼不在
    # 搜尋時驗），這顆燈就是那個偵測器。沒有它，使用者會是第一個發現的人。
    from urllib.parse import urlparse

    import requests

    from core.image_codec import decode_image_payload, looks_like_image

    if video is None or not video.cover_url:
        # 判綠必定代表至少一個 "pass"，而 "pass" 的定義就含 cover_url ⇒ 這條走不到。
        # 留著是防呆：哪天 `_run_canary` 的回傳約定改了，這裡要 skip 不要 AttributeError。
        pytest.skip("javdb-api: 拿不到封面網址（上面的 quorum 已經判過了）")
    host = urlparse(video.cover_url).hostname or ""
    try:
        resp = requests.get(video.cover_url, timeout=20)
    except requests.exceptions.RequestException as e:
        # 連不到圖床是**站方／網路**問題，不是「我們的解碼規則壞了」。
        # 不 try/except 的話這裡會變成 pytest ERROR，人工讀報表時分不出是哪一種（review P3）。
        pytest.skip(f"javdb-api: 連不到圖床（{type(e).__name__}）——非解碼問題")
    if resp.status_code != 200:
        # `requests.get()` 對 4xx/5xx **不會拋例外**，所以上面那個 except 接不到它。
        # 不擋的話 403/429/503 的錯誤頁 body 會被拿去解碼、魔數過不了，
        # 然後報成「解碼規則失效」——一次圖床抽風就是一顆假紅（Codex PR review round-3 P3）。
        # 這一格與上面那個 except 是同一個判斷：圖床拿不到東西 ＝ 站方問題 ＝ skip。
        pytest.skip(f"javdb-api: 圖床回 {resp.status_code}——非解碼問題")
    raw = resp.content
    payload = decode_image_payload(host, raw)
    if not looks_like_image(payload):
        pytest.fail(
            f"javdb-api: 封面解不開（host={host}, raw={len(raw)}B, payload={len(payload)}B）"
            " — host→codec 對應或解碼規則可能失效"
        )


# ========== dmm (4-way) ==========

def test_dmm_canary():
    scraper = DMMScraper()
    _run_canary("dmm", scraper)
