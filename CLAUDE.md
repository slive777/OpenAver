# OpenAver - Claude 專案規則

## 專案資訊

詳見 [`feature/prd.md`](feature/prd.md)

**當前狀態**：查看 `feature/<分支名>/plan.md`

---

## 開發環境

### 執行測試
**一律使用 venv：**
```bash
# 一般開發（排除 smoke）
source venv/bin/activate && pytest tests/ -v --ignore=tests/smoke -m "not smoke"

# Milestone（全部測試）
source venv/bin/activate && pytest tests/ -v
```

### Smoke Test 說明
Smoke tests 會連線外部服務，測試時：
- **API 服務**：自動管理（有則用，無則啟動，測試後關閉）
- **Ollama**：需手動啟動（Windows 開啟 Ollama 應用程式）
- **Gemini**：需設定 API key

若外部服務無法連線，測試會 **skip**（不是失敗），並顯示原因。

---

## Milestone Commit

當用戶要求 "commit milestone" 時，依序執行：

1. **測試** - `source venv/bin/activate && pytest tests/ -v`，全部通過才繼續
2. **敏感資訊檢查** - 搜尋以下 patterns（排除 venv/、.git/、archives/）：
   - `password`, `api_key`, `apikey`, `secret`, `token`
   - `\.env` 檔案內容
   - `credentials`, `private_key`
   - 硬編碼的 IP 地址或網址（非公開 API）
3. **更新 CHANGELOG.md** - Keep a Changelog 格式，新增版本區塊
4. **更新 feature/prd.md** - 發展歷程表格新增 Phase
5. **檢查文檔** - 詢問用戶 README.md、core/README.md 是否需要更新
6. **顯示 commit message** - 格式：`milestone: Phase XX - 描述`
7. **等待確認** - 用戶確認後才執行 commit

**主動提議時機**：合併 feature branch 到 main 後，提議「要進行 milestone commit 嗎？」

---

## 程式碼規範

### 路徑處理
**路徑問題一律用 `core/path_utils.py`**

- `normalize_path()` - 轉換為當前環境路徑
- `to_file_uri()` - 轉換為 `file:///` URI 格式
- `to_windows_path()` / `to_wsl_path()` - 跨平台轉換

不要在其他模組自行實作路徑轉換邏輯。

### Tailwind CSS 編譯
修改 `web/static/css/input.css` 後**必須**重新編譯 `tailwind.css`，並一起 commit：
```bash
npx @tailwindcss/cli -i web/static/css/input.css -o web/static/css/tailwind.css
```
`tailwind.css` 是 generated file，若與 `input.css` 不同步會導致 theme 失效（例如 light mode 元件消失）。

---

## Release 發布

當用戶要求發布新版本時，依序執行：

1. **更新版本號** - 修改 `core/version.py` 的 `__version__`
2. **Commit** - 格式：`🚀 release: vX.Y.Z - 簡短描述`
3. **建立 Tag** - `git tag vX.Y.Z`
4. **Push** - `git push && git push --tags`
5. **等待 GitHub Actions** - 自動打包 Windows + macOS 並上傳到 Release

⚠️ **注意**：不要本地打包！GitHub Actions 打包的 ZIP 才能用 Windows 內建解壓縮不報錯。

---

## Commit 風格

```
feat(X.Y): 功能描述
fix(X.Y): 修復描述
refactor(X.Y): 重構描述
docs: 文檔更新
chore: 雜項
🎯 milestone: Phase XX - 階段描述
🚀 release: vX.Y.Z - 版本描述
```

## CHANGELOG 格式

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
#### 🎯 功能分類標題
- 具體功能描述

### Changed
- 變更描述

### Fixed
- 修復描述
```
