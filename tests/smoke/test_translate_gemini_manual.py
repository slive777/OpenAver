#!/usr/bin/env python3
"""
手动测试翻译功能（无需启动服务器）
"""
import asyncio
import json
from core.translate_service import create_translate_service

async def test_translation():
    print("=" * 60)
    print("Task 1.3.1 配置迁移验证")
    print("=" * 60)

    # 读取配置
    with open('web/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    translate_config = config.get('translate', {})

    print("\n📋 配置检查：")
    print(f"  enabled: {translate_config.get('enabled')}")
    print(f"  provider: {translate_config.get('provider')}")
    print(f"  auto_progressive: {translate_config.get('auto_progressive')}")
    print(f"  progressive_first: {translate_config.get('progressive_first')}")
    print(f"  progressive_range: {translate_config.get('progressive_range')}")
    print(f"  batch_size: {translate_config.get('batch_size')}")

    ollama_config = translate_config.get('ollama', {})
    print(f"\n🔧 Ollama 配置（嵌套结构）：")
    print(f"  url: {ollama_config.get('url')}")
    print(f"  model: {ollama_config.get('model')}")

    # 检查旧字段
    if 'ollama_url' in translate_config or 'ollama_model' in translate_config:
        print(f"\n⚠️ 发现旧字段（应该被删除）：")
        if 'ollama_url' in translate_config:
            print(f"  ollama_url: {translate_config.get('ollama_url')}")
        if 'ollama_model' in translate_config:
            print(f"  ollama_model: {translate_config.get('ollama_model')}")
    else:
        print(f"\n✅ 旧字段已清理")

    # 测试翻译服务
    print(f"\n" + "=" * 60)
    print("翻译功能测试")
    print("=" * 60)

    try:
        service = create_translate_service(translate_config)
        print(f"✅ 翻译服务创建成功")
        print(f"   URL: {service.ollama_url}")
        print(f"   Model: {service.model}")

        # 测试单片翻译
        print(f"\n🧪 测试 1：单片翻译")
        test_title = "新人 AV デビュー 桜空もも"
        print(f"   原文: {test_title}")
        result = await service.translate_single(test_title)
        if result:
            print(f"   译文: {result}")
            print(f"   ✅ 单片翻译成功")
        else:
            print(f"   ❌ 翻译失败（可能 Ollama 未连接）")

        # 测试批次翻译
        print(f"\n🧪 测试 2：批次翻译（3 个标题）")
        test_titles = [
            "痴漢願望の女 色情狂ナース編",
            "新人 NO.1 STYLE デビュー",
            "巨乳女教師の誘惑"
        ]
        results = await service.translate_batch(test_titles)

        if results and len(results) == len(test_titles):
            print(f"   ✅ 批次翻译成功")
            for i, (orig, trans) in enumerate(zip(test_titles, results), 1):
                print(f"   {i}. {orig}")
                print(f"      → {trans}")
        else:
            print(f"   ❌ 批次翻译失败")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_translation())
