#!/usr/bin/env python3
"""
Task 2.8 測試腳本：Gemini Safety Settings 驗證

測試內容：
1. 使用 BLOCK_NONE 翻譯高風險 AV 標題
2. 驗證 finishReason 錯誤處理
3. 批次翻譯成功率測試
"""

import asyncio
import json
from pathlib import Path
from core.translate_service import create_translate_service


# 高風險測試標題（Task 2.8 中提到的）
HIGH_RISK_TITLES = [
    "中出し解禁 白石茉莉奈",
    "完全主観 密着セックス",
    "射精させられた全裸の2次会",
    "生中出し 解禁",
    "イキまくり絶頂",
    "3本番スペシャル",
    "初体験4本番",
    "新人デビュー 天使もえ",
    "絶頂覚醒 痙攣セックス",
    "本番解禁 美少女デビュー"
]


def load_config():
    """載入 Gemini API 配置"""
    config_path = Path.home() / ".config" / "openaver" / "config.json"

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        print("\n請先在 Settings 中配置 Gemini API Key")
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    translate_config = config.get("translate", {})

    if translate_config.get("provider") != "gemini":
        print("⚠️ 當前 Provider 不是 Gemini")
        print(f"   當前: {translate_config.get('provider')}")
        print("\n請在 Settings 中切換到 Gemini")
        return None

    gemini_config = translate_config.get("gemini", {})
    api_key = gemini_config.get("api_key", "")

    if not api_key:
        print("❌ Gemini API Key 未配置")
        return None

    print(f"✅ 配置已載入")
    print(f"   Provider: gemini")
    print(f"   Model: {gemini_config.get('model', 'gemini-flash-lite-latest')}")
    print(f"   API Key: {api_key[:20]}...")
    print()

    return translate_config


async def run_single_translation(service, title):
    """測試單個標題翻譯（輔助函數，非 pytest test）"""
    print(f"原文: {title}")
    result = await service.translate_single(title)

    if result:
        print(f"✅ 翻譯: {result}")
        return True
    else:
        print(f"❌ 翻譯失敗")
        return False


async def run_batch_translation(service, titles):
    """測試批次翻譯（輔助函數，非 pytest test）"""
    print(f"\n批次翻譯 {len(titles)} 個標題...")
    print("=" * 60)

    results = await service.translate_batch(titles)

    success_count = sum(1 for r in results if r)
    success_rate = (success_count / len(titles)) * 100

    print(f"\n結果：")
    for i, (original, translated) in enumerate(zip(titles, results), 1):
        status = "✅" if translated else "❌"
        print(f"{status} {i}. {original}")
        if translated:
            print(f"      → {translated}")

    print(f"\n成功率: {success_count}/{len(titles)} ({success_rate:.1f}%)")

    return success_rate


async def main():
    print("=" * 60)
    print("Task 2.8 Gemini Safety Settings 測試")
    print("=" * 60)
    print()

    # 載入配置
    config = load_config()
    if not config:
        return

    # 創建翻譯服務
    try:
        service = create_translate_service(config)
    except Exception as e:
        print(f"❌ 創建翻譯服務失敗: {e}")
        return

    # 測試 1: 單個高風險標題
    print("📋 測試 1: 單個高風險標題")
    print("=" * 60)
    test_title = HIGH_RISK_TITLES[0]
    success = await run_single_translation(service, test_title)
    print()

    # 測試 2: 批次翻譯 5 個高風險標題
    print("📋 測試 2: 批次翻譯 5 個高風險標題")
    print("=" * 60)
    batch_5 = HIGH_RISK_TITLES[:5]
    rate_5 = await run_batch_translation(service, batch_5)
    print()

    # 測試 3: 批次翻譯全部 10 個高風險標題
    print("📋 測試 3: 批次翻譯全部 10 個高風險標題")
    print("=" * 60)
    rate_10 = await run_batch_translation(service, HIGH_RISK_TITLES)
    print()

    # 總結
    print("=" * 60)
    print("📊 測試總結")
    print("=" * 60)
    print(f"單個翻譯: {'✅ 通過' if success else '❌ 失敗'}")
    print(f"批次 5 片: {rate_5:.1f}% 成功率")
    print(f"批次 10 片: {rate_10:.1f}% 成功率")
    print()

    if rate_10 >= 98:
        print("🎉 Task 2.8 目標達成！成功率 ≥ 98%")
    elif rate_10 >= 90:
        print("✅ 成功率良好，但仍有優化空間")
    else:
        print("⚠️ 成功率較低，建議檢查：")
        print("   1. safetySettings 是否正確添加")
        print("   2. API Key 是否有效")
        print("   3. 模型是否為 gemini-flash-lite-latest")

    print()
    print("💡 提示：")
    print("   - 修改前預期成功率: ~90-95%")
    print("   - 修改後預期成功率: ~98-99%")
    print("   - 使用 BLOCK_NONE 應該大幅提升通過率")
    print()


if __name__ == "__main__":
    asyncio.run(main())
