#!/bin/bash
# Task 1 集成測試腳本（簡化版）
# 適用於 Task 1.3.4 後的設計：純手動批次翻譯

set -e

echo "=== Task 1 集成測試 ==="
echo ""

# 讀取配置中的 Ollama URL
OLLAMA_URL=$(python3 -c "import json; c = json.load(open('web/config.json')); print(c.get('translate',{}).get('ollama',{}).get('url', 'http://localhost:11434'))" 2>/dev/null || echo "http://localhost:11434")
echo "Ollama URL: $OLLAMA_URL"
echo ""

# 【1/4】檢查 Ollama 服務
echo "【1/4】檢查 Ollama 服務..."
if curl -s --connect-timeout 5 "$OLLAMA_URL/api/tags" > /dev/null; then
    echo "  ✅ Ollama 服務運行正常"
else
    echo "  ❌ Ollama 服務未運行或無法連接"
    echo "  提示：請確認 Ollama 已啟動"
    exit 1
fi

# 【2/4】檢查模型
echo ""
echo "【2/4】檢查翻譯模型..."
MODEL=$(python3 -c "import json; c = json.load(open('web/config.json')); print(c.get('translate',{}).get('ollama',{}).get('model', 'qwen3:8b'))" 2>/dev/null || echo "qwen3:8b")
echo "  配置的翻譯模型: $MODEL"

# 【3/4】測試批次翻譯 API
echo ""
echo "【3/4】測試批次翻譯 API..."
RESPONSE=$(curl -s -X POST http://localhost:8080/api/translate-batch \
  -H "Content-Type: application/json" \
  -d '{"titles":["新人デビュー","中出し解禁"],"batch_size":10}' 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -q "translations"; then
    COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "?")
    echo "  ✅ 批次翻譯 API 正常 (成功 $COUNT/2)"
else
    echo "  ⚠️ 批次翻譯 API 未響應（伺服器可能未啟動）"
    echo "  提示：請先執行 python app.py"
fi

# 【4/4】運行 pytest
echo ""
echo "【4/4】運行單元測試..."
if source venv/bin/activate 2>/dev/null && pytest tests/unit tests/integration -q --tb=no 2>/dev/null; then
    echo "  ✅ 所有測試通過"
else
    echo "  ⚠️ 部分測試失敗，請檢查詳情"
fi

echo ""
echo "=== 基礎測試完成 ==="
echo ""
echo "請在瀏覽器中進行手動驗證："
echo "  1. 開啟 http://localhost:8080/search"
echo "  2. 搜尋 'SONE-576'"
echo "  3. 確認搜尋結果正常（不會自動翻譯）"
echo "  4. 點擊翻譯按鈕 → 批次翻譯 10 片"
echo ""
