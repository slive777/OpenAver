# 安全政策 (Security Policy)

## 支援版本

目前支援安全更新的版本：

| 版本 | 支援狀態 |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## 報告漏洞

如果您發現安全漏洞，請**不要**在公開的 GitHub Issues 中報告。

### 報告方式

1. **Email**：請發送郵件至專案維護者（透過 GitHub profile 取得聯絡方式）
2. **GitHub Private Vulnerability Reporting**：使用 [GitHub 的私人漏洞報告功能](https://github.com/slive777/OpenAver/security/advisories/new)

### 報告內容

請在報告中包含以下資訊：

- 漏洞類型（例如：XSS、SQL Injection、路徑遍歷等）
- 受影響的檔案路徑或功能
- 重現步驟
- 潛在影響評估
- 建議的修復方式（如果有）

### 回應時間

- **確認收到**：48 小時內
- **初步評估**：7 天內
- **修復時程**：依嚴重程度而定
  - 嚴重 (Critical)：盡快修復
  - 高 (High)：14 天內
  - 中 (Medium)：30 天內
  - 低 (Low)：下一個版本

### 安全更新

安全修復將會：
1. 在 CHANGELOG.md 中註明（不揭露具體細節）
2. 透過 GitHub Release 發布
3. 在修復發布後才公開漏洞詳情

## 安全最佳實踐

使用 OpenAver 時，建議：

1. **保持更新**：使用最新版本
2. **本地執行**：OpenAver 設計為本地工具，請勿暴露在公共網路
3. **防火牆**：如果在網路環境執行，確保適當的防火牆設定
4. **Ollama API**：如果使用 AI 翻譯功能，確保 Ollama 服務僅供本地存取

## 已知安全考量

- OpenAver 是本地應用程式，預設綁定 `127.0.0.1:8000`
- 圖片代理功能會向外部網站發送請求
- 設定檔儲存在本地 `config.json`，請勿上傳至公開環境

---

感謝您幫助我們保持 OpenAver 的安全！
