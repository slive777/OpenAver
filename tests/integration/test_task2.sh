#!/bin/bash
# Task 2 集成測試腳本
# 測試 Gemini 翻譯功能

set -e

echo "=== Task 2 Gemini 集成測試 ==="
echo ""

# 檢查並清理 8000 端口
echo "【0/4】檢查測試端口..."
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    PID=$(lsof -t -i:8000)
    echo "  ⚠️ 端口 8000 被占用 (PID: $PID)"
else
    echo "  ✅ 端口 8000 可用"
fi
echo ""

# 讀取配置
PROVIDER=$(python3 -c "import json; c = json.load(open('web/config.json')); print(c.get('translate',{}).get('provider', 'ollama'))" 2>/dev/null || echo "ollama")
echo "當前 Provider: $PROVIDER"
echo ""

# 測試 1：Gemini 測試端點
echo "【1/4】測試 Gemini 測試端點..."

if [ "$PROVIDER" = "gemini" ]; then
    API_KEY=$(python3 -c "import json; c = json.load(open('web/config.json')); print(c.get('translate',{}).get('gemini',{}).get('api_key', ''))" 2>/dev/null || echo "")

    if [ -n "$API_KEY" ]; then
        RESPONSE=$(curl -s -X POST http://localhost:8000/api/gemini/test \
          -H "Content-Type: application/json" \
          -d "{\"api_key\":\"$API_KEY\"}" 2>/dev/null || echo "")

        if echo "$RESPONSE" | grep -q "\"success\":true"; then
            MODEL_COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('count', 0))" 2>/dev/null || echo "0")
            echo "  ✅ Gemini API 測試成功，找到 $MODEL_COUNT 個模型"
        else
            echo "  ⚠️ Gemini API 測試失敗（伺服器可能未啟動）"
        fi
    else
        echo "  ⚠️ 未配置 Gemini API Key"
    fi
else
    echo "  ⏭️  跳過（當前使用 Ollama）"
fi

# 測試 2：批次翻譯 API
echo ""
echo "【2/4】測試批次翻譯 API..."

RESPONSE=$(curl -s -X POST http://localhost:8000/api/translate-batch \
  -H "Content-Type: application/json" \
  -d '{"titles":["新人デビュー","中出し解禁"]}' 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -q "translations"; then
    COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "?")
    echo "  ✅ 批次翻譯 API 正常 (成功 $COUNT/2)"
else
    echo "  ⚠️ 批次翻譯 API 未響應（伺服器可能未啟動）"
    echo "  提示：請先執行 uvicorn web.app:app --host 0.0.0.0 --port 8000"
fi

# 測試 3：配置驗證
echo ""
echo "【3/4】驗證配置結構..."

HAS_GEMINI=$(python3 -c "import json; c = json.load(open('web/config.json')); print('gemini' in c.get('translate', {}))" 2>/dev/null || echo "False")
HAS_OLLAMA=$(python3 -c "import json; c = json.load(open('web/config.json')); print('ollama' in c.get('translate', {}))" 2>/dev/null || echo "False")

if [ "$HAS_GEMINI" = "True" ]; then
    echo "  ✅ 配置包含 Gemini 字段"
else
    echo "  ❌ 配置缺少 Gemini 字段"
fi

if [ "$HAS_OLLAMA" = "True" ]; then
    echo "  ✅ 配置包含 Ollama 字段"
else
    echo "  ❌ 配置缺少 Ollama 字段"
fi

# 測試 4：運行單元測試
echo ""
echo "【4/4】運行單元測試..."

if source venv/bin/activate 2>/dev/null && pytest tests/unit tests/integration -q --tb=no 2>/dev/null; then
    echo "  ✅ 所有測試通過"
else
    echo "  ⚠️ 部分測試失敗，請檢查詳情"
fi

echo ""
echo "=== 自動化測試完成 ==="
echo ""
echo "請繼續手動測試："
echo "  1. 開啟 Settings → 切換到 Gemini"
echo "  2. 測試 API Key → 選擇模型"
echo "  3. 搜尋 'SONE-576' → 點擊翻譯"
echo "  4. 驗證翻譯速度和質量"
echo ""
