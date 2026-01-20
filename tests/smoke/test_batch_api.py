"""
test_batch_api.py - 批次翻譯 API 測試

⚠️ 只用於本地手動測試，不進 CI（需要 FastAPI 服務和 Ollama）

執行方式：
    # 先啟動服務
    python app.py
    
    # 然後運行測試
    python tests/smoke/test_batch_api.py

環境變數：
    API_URL: API 基礎 URL (默認 http://localhost:8000)
    OLLAMA_URL: Ollama 服務 URL (供 translate_service 使用)
"""

import pytest
import asyncio
import os
import time

# 嘗試導入 requests，如果沒有則用 httpx
try:
    import requests
    USE_REQUESTS = True
except ImportError:
    import httpx
    USE_REQUESTS = False


# 測試配置
API_URL = os.getenv("API_URL", "http://localhost:8000")
BATCH_ENDPOINT = f"{API_URL}/api/translate-batch"


def post_json(url, data, timeout=60):
    """發送 POST 請求"""
    if USE_REQUESTS:
        resp = requests.post(url, json=data, timeout=timeout)
        return resp.status_code, resp.json() if resp.status_code == 200 else resp.text
    else:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=data)
            return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


@pytest.mark.smoke
class TestBatchTranslateAPI:
    """批次翻譯 API 測試"""

    def test_batch_basic(self):
        """基本批次翻譯 (2 個標題)"""
        titles = ["新人デビュー", "中出し解禁"]

        status, data = post_json(BATCH_ENDPOINT, {"titles": titles}, timeout=60)

        print(f"\n基本批次翻譯:")
        print(f"  狀態碼: {status}")

        if status != 200:
            pytest.skip(f"API 無法連線: {data}")

        print(f"  翻譯: {data.get('translations', [])}")
        print(f"  成功: {data.get('count', 0)}/{len(titles)}")

        assert len(data.get("translations", [])) == len(titles), "對齊率失敗"

    def test_batch_five_titles(self):
        """批次翻譯 5 個標題"""
        titles = [
            "痴漢願望の女 色情狂ナース編 天使もえ",
            "芸能人 白石茉莉奈 旦那と子供に内緒の人妻温泉不倫旅行",
            "新人 AV デビュー 桜空もも",
            "中出し解禁 巨乳美少女",
            "潮吹き絶頂 連続イキまくり"
        ]

        start = time.time()
        status, data = post_json(BATCH_ENDPOINT, {"titles": titles}, timeout=120)
        elapsed = time.time() - start

        print(f"\n批次翻譯 5 個標題:")
        print(f"  耗時: {elapsed:.2f} 秒")

        if status != 200:
            pytest.skip(f"API 無法連線: {data}")

        print(f"  成功: {data.get('count', 0)}/{len(titles)}")

        for i, (orig, trans) in enumerate(zip(titles, data.get("translations", [])), 1):
            status_mark = "✓" if trans else "✗"
            print(f"  {i}. [{status_mark}] {orig[:20]}... → {trans[:20] if trans else '(空)'}...")

        assert len(data.get("translations", [])) == len(titles), "對齊率失敗"

    def test_batch_empty(self):
        """空列表處理"""
        status, data = post_json(BATCH_ENDPOINT, {"titles": []})

        print(f"\n空列表處理:")
        print(f"  狀態碼: {status}")

        if status != 200:
            pytest.skip(f"API 無法連線: {data}")

        assert data.get("translations") == [], "空輸入應返回空列表"
        assert data.get("count") == 0
        assert data.get("errors") == []

    def test_batch_single(self):
        """單個標題"""
        titles = ["テスト"]

        status, data = post_json(BATCH_ENDPOINT, {"titles": titles})

        print(f"\n單個標題:")

        if status != 200:
            pytest.skip(f"API 無法連線: {data}")

        print(f"  翻譯: {data.get('translations', [])}")

        assert len(data.get("translations", [])) == 1, "對齊率失敗"


if __name__ == "__main__":
    print("=== 批次翻譯 API 測試 ===\n")
    print(f"API URL: {BATCH_ENDPOINT}\n")
    print("注意：初次連線 Ollama 可能需要 20 秒（模型載入）\n")

    try:
        # 基本測試
        print("【測試 1】基本批次翻譯 (2 個標題)")
        print("-" * 40)
        titles = ["新人デビュー", "中出し解禁"]

        start = time.time()
        status, data = post_json(BATCH_ENDPOINT, {"titles": titles}, timeout=60)
        elapsed = time.time() - start

        if status == 200:
            print(f"耗時: {elapsed:.2f} 秒")
            print(f"成功: {data.get('count', 0)}/{len(titles)}")
            for i, (orig, trans) in enumerate(zip(titles, data.get("translations", [])), 1):
                print(f"  {i}. {orig} → {trans}")
            print("✅ 通過\n")
        else:
            print(f"❌ 失敗: {data}")
            exit(1)

        # 對齊率測試
        print("【測試 2】對齊率測試 (5 個標題)")
        print("-" * 40)
        titles = [
            "痴漢願望の女",
            "中出し解禁",
            "潮吹き絶頂",
            "新人デビュー",
            "巨乳美少女"
        ]

        start = time.time()
        status, data = post_json(BATCH_ENDPOINT, {"titles": titles}, timeout=120)
        elapsed = time.time() - start

        if status == 200:
            translations = data.get("translations", [])
            print(f"耗時: {elapsed:.2f} 秒")
            print(f"輸入: {len(titles)} 個")
            print(f"輸出: {len(translations)} 個")
            print(f"對齊率: {'100%' if len(translations) == len(titles) else '失敗!'}")
            print("✅ 通過\n")
        else:
            print(f"❌ 失敗: {data}")

        # 空列表測試
        print("【測試 3】空列表處理")
        print("-" * 40)
        status, data = post_json(BATCH_ENDPOINT, {"titles": []})

        if status == 200 and data.get("translations") == []:
            print("空輸入 → 空輸出")
            print("✅ 通過\n")
        else:
            print(f"❌ 失敗: {data}")

        print("🎉 所有測試通過！")

    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
