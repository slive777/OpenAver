"""
test_translate_live.py - 翻譯服務 Smoke 測試

⚠️ 只用於本地手動測試，不進 CI（需要 Ollama 服務）

執行方式：
    pytest tests/smoke/test_translate_live.py -v -m smoke

前提條件：
- Ollama 服務運行中
- 配置的翻譯模型已安裝

配置優先順序：
1. 用戶配置 (~/.config/openaver/config.json)
2. 環境變數 OLLAMA_URL / OLLAMA_MODEL
3. 預設值 localhost:11434 / qwen3:8b
"""

import pytest
import asyncio
import os
import json
from pathlib import Path
from core.translate_service import create_translate_service


def load_test_config():
    """載入測試配置，優先使用用戶配置"""
    # 嘗試從專案目錄讀取配置
    config_paths = [
        Path(__file__).parent.parent.parent / "web" / "config.json",  # 專案內
        Path.home() / ".config" / "openaver" / "config.json",  # 用戶目錄
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                translate_config = user_config.get("translate", {})
                ollama_config = translate_config.get("ollama", {})

                # 直接讀取 ollama 配置（不管 provider 設什麼）
                if ollama_config:
                    return {
                        "provider": "ollama",
                        "ollama": {
                            "url": ollama_config.get("url", os.getenv("OLLAMA_URL", "http://localhost:11434")),
                            "model": ollama_config.get("model", os.getenv("OLLAMA_MODEL", "qwen3:8b"))
                        }
                    }
            except Exception:
                continue  # 讀取失敗，嘗試下一個

    # 預設配置（可通過環境變數覆蓋）
    return {
        "provider": "ollama",
        "ollama": {
            "url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL", "qwen3:8b")
        }
    }


TEST_CONFIG = load_test_config()


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
            pytest.skip("Ollama 無法連線（Windows 請開啟 Ollama 應用程式）")

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
            pytest.skip("Ollama 無法連線（Windows 請開啟 Ollama 應用程式）")

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
            pytest.skip("Ollama 無法連線（Windows 請開啟 Ollama 應用程式）")

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
                pytest.skip(f"Batch={n} Ollama 無法連線（Windows 請開啟 Ollama）")

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
