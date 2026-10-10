# Custom source fixtures

這裡只放「自訂來源」設定檔（`*.yaml`）樣本，是合理設定檔形狀的範例，schema、registry、解譯器測試共用。

頁面不存在這裡：解譯器測試用的 HTML 是測試內嵌的極小合成頁，集中在
`tests/unit/_custom_source_pages.py`，每頁只含該 yaml 的 selector 會碰到的元素，網域一律 `*.example`。

## 為什麼不收真站 HTML

站能不能抓得下來是使用者（與使用者自己的 AI）寫設定時的責任，不是我們的測試能保證的；
存真站頁面對我們的程式碼零資訊。解譯器行為（selector、兩步串接、查無結果、錯誤分類、
請求預算、去重、番號邊界比對）幾行合成 HTML 就驗得出來。
