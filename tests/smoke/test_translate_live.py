"""
test_translate_live.py - 翻譯服務 Smoke 測試

⚠️ 只用於本地手動測試，不進 CI（需要 Ollama 服務）

執行方式：
    pytest tests/smoke/test_translate_live.py -v -m smoke

前提條件：
- Ollama 服務運行中
- qwen3:8b 模型已安裝
- translategemma:12b 模型已安裝（批次翻譯）
"""

import pytest
import asyncio
import os
from core.translate_service import create_translate_service


# 測試配置（可通過環境變量覆蓋）
# export OLLAMA_URL=http://172.18.128.1:11434
TEST_CONFIG = {
    "provider": "ollama",
    "ollama": {
        "url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
        "model": "qwen3:8b",
        "batch_model": "translategemma:12b"
    }
}


@pytest.mark.smoke
class TestTranslateSingleLive:
    """單片翻譯連通測試"""

    @pytest.mark.asyncio
    async def test_translate_single_basic(self):
        """基本單片翻譯"""
        service = create_translate_service(TEST_CONFIG)

        title = "新人 AV デビュー 桜空もも"
        result = await service.translate_single(title)

        print(f"\n原文: {title}")
        print(f"譯文: {result}")

        if not result:
            pytest.skip("Ollama 無法連線或翻譯失敗")

        assert len(result) > 0, "翻譯結果不應為空"
        assert len(result) <= 100, "翻譯結果過長"

    @pytest.mark.asyncio
    async def test_translate_single_complex(self):
        """複雜標題翻譯"""
        service = create_translate_service(TEST_CONFIG)

        title = "痴漢願望の女 色情狂ナース編 天使もえ"
        result = await service.translate_single(title)

        print(f"\n原文: {title}")
        print(f"譯文: {result}")

        if not result:
            pytest.skip("Ollama 無法連線或翻譯失敗")

        assert len(result) > 0


@pytest.mark.smoke
class TestTranslateBatchLive:
    """批次翻譯連通測試"""

    @pytest.mark.asyncio
    async def test_translate_batch_alignment(self):
        """批次翻譯對齊率測試"""
        service = create_translate_service(TEST_CONFIG)

        titles = [
            "中出し解禁 巨乳美少女",
            "潮吹き絶頂 連続イキまくり",
            "新人 AV デビュー 桜空もも",
            "芸能人 白石茉莉奈 人妻温泉不倫旅行",
            "痴漢願望の女 色情狂ナース編"
        ]

        results = await service.translate_batch(titles)

        print(f"\n批次翻譯結果 ({len(titles)} 個):")
        for i, (orig, trans) in enumerate(zip(titles, results), 1):
            print(f"{i}. {orig}")
            print(f"   → {trans}")

        # 關鍵：驗證對齊率
        assert len(results) == len(titles), f"對齊失敗: 輸入 {len(titles)}, 輸出 {len(results)}"

        # 驗證翻譯質量
        non_empty = sum(1 for r in results if r)
        print(f"\n成功翻譯: {non_empty}/{len(titles)}")

        if non_empty == 0:
            pytest.skip("Ollama 無法連線或翻譯失敗")

        assert non_empty >= len(titles) * 0.8, "翻譯成功率低於 80%"

    @pytest.mark.asyncio
    async def test_translate_batch_various_sizes(self):
        """不同批次大小測試"""
        service = create_translate_service(TEST_CONFIG)

        for n in [1, 3, 5, 10]:
            titles = [f"テスト標題 {i+1}" for i in range(n)]
            results = await service.translate_batch(titles)

            print(f"\nBatch size {n}: 輸入 {len(titles)}, 輸出 {len(results)}")

            if not any(results):
                pytest.skip(f"Batch={n} Ollama 無法連線")

            assert len(results) == n, f"Batch={n} 對齊失敗"

    @pytest.mark.asyncio
    async def test_translate_batch_empty(self):
        """空列表處理"""
        service = create_translate_service(TEST_CONFIG)

        results = await service.translate_batch([])

        assert results == [], "空輸入應返回空列表"


if __name__ == "__main__":
    # 快速測試（不需要 pytest）
    print("=== 翻譯服務連通測試 ===\n")

    async def quick_test():
        try:
            service = create_translate_service(TEST_CONFIG)

            # 單片測試
            print("【單片翻譯】")
            result = await service.translate_single("新人 AV デビュー 桜空もも")
            print(f"結果: {result}\n")

            # 批次測試
            print("【批次翻譯】")
            titles = ["中出し解禁", "潮吹き絶頂", "巨乳美少女"]
            results = await service.translate_batch(titles)
            for t, r in zip(titles, results):
                print(f"{t} → {r}")

            print("\n✅ 測試完成")

        except Exception as e:
            print(f"❌ 測試失敗: {e}")

    asyncio.run(quick_test())
