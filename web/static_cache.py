"""
NoCacheStaticFiles — StaticFiles subclass that injects Cache-Control: no-cache.

目的：根治 heuristic caching。Starlette 原生 StaticFiles 只送 ETag + Last-Modified；
瀏覽器對「有 Last-Modified 但無 Cache-Control」套用 heuristic freshness（約 (now − Last-Modified) × 10%），
在 freshness 窗口內不重驗 → 重新部署後同檔名仍吃舊 JS/CSS，直到窗口過期或使用者 hard-reload。

`no-cache` 不是「不快取」；意為「可存快取，但每次必須帶 If-None-Match / If-Modified-Since 重驗」。
Starlette 已產 ETag + Last-Modified → 未變回 304（空 body），有變才回 200 新版，免 hard-reload。

機制說明（post-construction mutation）：
  super().file_response(...) 回傳 200 FileResponse 或 304 NotModifiedResponse。
  對 200 路徑：直接是 FileResponse 物件，headers dict 可寫。
  對 304 路徑：是 NotModifiedResponse 物件，其 __init__ 在「建構時」已完成白名單過濾，
  建構後的 headers dict 仍可直接寫入（Python MutableHeaders 不設防）。
  我們在 super().file_response() 回傳後才 mutate，__init__ 早已執行完畢，
  白名單不再介入——header 直接寫入即生效。
  因此 200（FileResponse）與 304（NotModifiedResponse）兩條路均會帶 Cache-Control: no-cache。
"""
from fastapi.staticfiles import StaticFiles


class NoCacheStaticFiles(StaticFiles):
    """對 /static 的所有回應加 Cache-Control: no-cache。

    override file_response（同步方法，200 和 304 都經此）。
    在 super().file_response() 回傳後做 post-construction headers mutation，
    兩條回應路徑（200 FileResponse / 304 NotModifiedResponse）均有效。
    """

    def file_response(self, *args, **kwargs):
        # super 回傳 200 FileResponse 或 304 NotModifiedResponse；
        # 兩者在 __init__ 執行後 headers dict 仍可直接寫入（post-construction mutation）。
        # 注意：NotModifiedResponse.__init__ 的白名單過濾在「建構時」已完成；
        # 我們在建構後才 mutate，故白名單不介入——header 直接寫入即生效。
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
