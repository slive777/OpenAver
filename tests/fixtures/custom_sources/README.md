# Custom source fixtures

## 這批檔案是什麼

「自訂來源」解譯器（`core/custom_source/`）的測試輸入：真實站台回應的子集，共 11 份，
涵蓋單頁 og 標籤、兩步（搜尋頁 → 詳情頁）、模糊搜尋、純文字頁與查無結果頁。
內容原樣複製、不改動；檔名已匿名化，改以頁面形狀命名，不出現真站名。

## 為什麼這裡可以收真站 HTML

`tests/fixtures/scrapers/README.md` 的政策是「不再收真站 HTML」，因為那類測試斷言的是
**parser 解析出哪些欄位**，站方改版時本地真檔還是舊結構、測試照樣全綠，是假綠。

本目錄不同：被測對象是**解譯器行為**（selector 語法、步驟串接、空結果處理、錯誤分類），
不是站方結構。斷言不碰站方內容（不比對標題、番號、圖址等站方資料）。

- 守的是解譯器行為，不是站方結構。
- 站方改版時本目錄不需要更新；舊檔照樣能驗解譯器。
- 檔案是真實回應的子集（不是合成 HTML），才不會抹平空佔位與 null。

## 行尾

部分檔案含 CRLF，原樣保留，由 `.gitattributes`（`tests/fixtures/**/*.html -whitespace`）
與 git 在 commit 時正規化；細節見 `tests/fixtures/scrapers/README.md` 的「行尾／eol 說明」。
`.gitignore` 預設忽略 `*.html`，本目錄靠 negation 規則進版控，禁止 `git add -f`。
