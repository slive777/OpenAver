"""metatube → Video mapper（spec §5.2）"""
import re
from urllib.parse import quote, urlencode, urlparse

from core.logger import get_logger
from core.scrapers.models import Actress, Video

logger = get_logger(__name__)

# FC2 系 provider 名稱集合
_FC2_PROVIDERS = {"FC2", "fc2hub", "FC2PPVDB"}

# FC2 雜訊 marker regex（全 ASCII，無 \uXXXX 需求）
_FC2_NOISE_RE = re.compile(
    r"(<script|function\(|\{\{|[A-Za-z0-9+/]{40,}={0,2})"
)


def _build_proxy_image_url(base_url: str, provider: str, number: str, image_url: str) -> str:
    """metatube 圖片代理端點 URL（泛化建構器，形狀同 CD-113c-4／12／13）。

    metatube 伺服器的 `/v1/images/primary/{provider}/{number}?url=<image>&ratio=0&quality=100`
    是**通用伺服器端圖片代理**：`?url=` 存在時伺服器會用該 provider 的 Fetcher
    在境外取回**任何**圖片 URL（封面、劇照 preview_images、thumb…）並原圖回傳
    （`ratio=0`＝不裁切，`quality=100`＝原品質；實測 200 回真實 JPEG 原尺寸）。
    本地 OpenAver 不直連被牆的源站 CDN——所有從 metatube 刮到的圖片走同一條路
    取回（來源一致性，feature/metatube-image-proxy）。

    base_url 或 image_url 任一空 → ''（沒有可代理的東西）。
    provider／number 若含 `quote(safe="")` 需要轉義的字元（非 ASCII／保留字）
    → ''，不組出一個上線會被 T3a `_SAFE_PATH_SEGMENT` 擋下的 URL——讓呼叫端
    的 fallback 自然接手，而不是讓使用者看到一張穩定 403 的圖。T3a 的允許字元集
    與 `quote()` 的預設 safe 集合定義相同（RFC 3986 unreserved），故「轉義前後
    是否相等」是判斷「會不會被 T3a 擋下」的精確 predicate，不是近似值
    （Opus 審核裁決 4）。
    """
    if not base_url or not image_url:
        return ""

    # ---- Codex PR review P1（2026-08-07）：base_url 的 userinfo 不得外流 ----
    # `validate_metatube_url()` 只看 scheme／hostname／port，**從不檢查 userinfo**，
    # 所以 `https://user:pass@host` 是通得過設定的（實測確認）。而本欄位會經
    # `to_legacy_dict()` 進 `/api/search` 的 JSON 回應、再被前端當成
    # `/api/proxy-image?url=...` 的值真的送出去——帳密會出現在瀏覽器網址列、
    # devtools、瀏覽紀錄。base_url 帶 userinfo 的唯一合理現實情境是「metatube
    # 前面擋了一層做 Basic Auth 的反向代理」（metatube 自己只認 Bearer，
    # `client.py` 與 sdk 的 `route/auth.go` 都是；而 `requests` 會把 URL userinfo
    # 自動轉成 `Authorization: Basic` header）。
    #
    # 因此**不在這裡靜默剝掉帳密**：那會讓「預覽打不通」變成難以診斷的失敗。
    # 一律回 ''，讓既有 fallback 接手。真正的連線路徑（`MetatubeHttpClient`）
    # 拿到的仍是完整 base_url，Basic Auth 不受影響。
    #
    # query／fragment 一起擋是**同一個 guard 順手修掉的功能 bug**：下面是字串
    # 內插，`http://h:9/?x=1` 會組出 `http://h:9/?x=1/v1/images/...`——路徑掉進
    # 原本的 query 裡，URL 從一開始就是壞的（實測）。
    parsed_base = urlparse(base_url)
    if parsed_base.username or parsed_base.password:
        logger.debug(
            "proxy URL 略過：metatube base_url 帶 userinfo（host=%s）",
            parsed_base.hostname,
        )
        return ""
    if parsed_base.query or parsed_base.fragment:
        logger.debug(
            "proxy URL 略過：metatube base_url 帶 query/fragment（host=%s）",
            parsed_base.hostname,
        )
        return ""

    provider_enc = quote(provider, safe="")
    number_enc = quote(number, safe="")
    if provider_enc != provider or number_enc != number:
        return ""
    query = urlencode({"url": image_url, "ratio": 0, "quality": 100})
    return f"{base_url.rstrip('/')}/v1/images/primary/{provider_enc}/{number_enc}?{query}"


def _build_preview_cover_url(base_url: str, provider: str, number: str, cover_url: str) -> str:
    """metatube 預覽端點 URL（封面特化 wrapper，CD-113c-4／12／13）。

    cover_url 空時回 ''（沒有可預覽的東西），讓前端 `preview_cover_url || cover`
    的 fallback 接手。建構與防護邏輯全在 `_build_proxy_image_url`（形狀相同），
    這裡只負責綁定語義上的「預覽封面」參數位置。
    """
    return _build_proxy_image_url(base_url, provider, number, cover_url)


def map_movie_info(info: dict, base_url: str = "") -> Video:
    """metatube MovieInfo dict → OpenAver Video（spec §5.2 完整映射）

    全程 info.get() 容缺：search 精簡結果欠缺欄位時不 raise。
    base_url：這次呼叫實際打的 metatube 伺服器（見 core/scraper.py 的
    _MetatubeShim），用來出生時就綁定 preview_cover_url（CD-113c-4／12／13）。
    """
    provider = info.get("provider", "")
    number = info.get("number", "")

    logger.debug("map_movie_info provider=%s number=%s", provider, number)

    # actors：過濾空字串，避免 Actress min_length=1 ValidationError
    raw_actors = info.get("actors") or []
    actresses = [Actress(name=n) for n in raw_actors if n]

    # release_date：可能是 None（JSON null）或 RFC3339 "YYYY-MM-DDT00:00:00Z"
    raw_date = info.get("release_date") or ""
    date = raw_date.split("T")[0]

    # runtime 0 → None（無值不顯示，CD-63a-9 plan 拍板）
    runtime = info.get("runtime") or None

    # score 0.0 → None（無評分不顯示，spec §5.2）
    score = info.get("score") or None

    # summary 清理
    summary = clean_metatube_summary(provider, info.get("summary") or "")

    cover_url = info.get("cover_url", "")
    preview_cover_url = _build_preview_cover_url(base_url, provider, number, cover_url)

    # 來源一致性：從 metatube 刮到的影片，封面也應走 metatube 取回，避免本地
    # 直連被牆的源站圖片 URL 超時。preview_cover_url 是 metatube 伺服器的
    # `/v1/images/primary/...` 代理端點；base_url 帶 userinfo/query 等無法組出
    # 代理 URL 時 _build_preview_cover_url 返回 ''，此時回退原始 cover_url，
    # 行為與修改前一致。
    effective_cover_url = preview_cover_url or cover_url

    # 來源一致性（續，feature/metatube-image-proxy）：劇照 preview_images →
    # sample_images 同樣逐張改寫成 metatube 代理端點 URL，取回路徑與封面一致。
    # 逐張獨立降級：某張組不出代理 URL（base_url 異常／provider 需轉義）時
    # 該張回退原始 URL，不影響其他張。
    raw_samples = info.get("preview_images") or []
    sample_images = [
        _build_proxy_image_url(base_url, provider, number, u) or u for u in raw_samples
    ]

    return Video(
        number=number,
        title=info.get("title", ""),
        maker=info.get("maker", ""),
        director=info.get("director", ""),
        label=info.get("label", ""),
        series=info.get("series", ""),
        actresses=actresses,
        date=date,
        cover_url=effective_cover_url,
        preview_cover_url=preview_cover_url,
        tags=info.get("genres") or [],
        detail_url=info.get("homepage", ""),
        duration=runtime,
        sample_images=sample_images,
        rating=score,
        summary=summary,
        source=f"metatube:{provider}",
        # thumb_url / big_thumb_url / preview_video_url / preview_video_hls_url 不吸（defer，spec §6）；
        # actors 只映射名字（Actress model 無頭像欄位、nfo 只寫名字）——演員圖不在本改動範圍
    )


def clean_metatube_summary(provider: str, raw: str) -> str:
    """清理 metatube summary 文字

    FC2 系（FC2 / fc2hub / FC2PPVDB）：
      - 截斷至首個雜訊 marker 前（<script、function(、{{、base64 ≥40 chars）
      - strip + 限長 500

    其他 provider：
      - strip + 限長 500

    空字串輸入 → ''
    """
    if not raw:
        return ""

    if provider in _FC2_PROVIDERS:
        m = _FC2_NOISE_RE.search(raw)
        text = raw[: m.start()] if m else raw
    else:
        text = raw

    # strip 前後空白 + 限長 500（Python str slice 是 codepoint-safe，CJK 正確）
    return text.strip()[:500]
