"""
測試片商 (Maker) 提取功能

目的：找出為什麼搜尋結果沒有片商資訊
"""

import sys
sys.path.insert(0, '/home/peace/JavHelper')

from core.scraper import scrape_javbus, scrape_jav321, search_jav


def test_individual_scrapers():
    """測試各個來源的 maker 回傳"""
    number = 'SONE-103'

    print(f"=== 測試番號: {number} ===\n")

    # 測試 JavBus
    print("【JavBus】")
    jb = scrape_javbus(number)
    if jb:
        print(f"  maker: {jb.get('maker', '(無)')}")
        print(f"  所有 keys: {list(jb.keys())}")
        # 印出完整資料檢查
        for k, v in jb.items():
            if k not in ['stars', 'tags']:
                print(f"  {k}: {v}")
    else:
        print("  (無結果)")

    print()

    # 測試 Jav321
    print("【Jav321】")
    j321 = scrape_jav321(number)
    if j321:
        print(f"  maker: {j321.get('maker', '(無)')}")
        print(f"  所有 keys: {list(j321.keys())}")
    else:
        print("  (無結果)")

    print()

    # 測試整合後的結果
    print("【search_jav 整合結果】")
    result = search_jav(number)
    if result:
        print(f"  number: {result.get('number')}")
        print(f"  title: {result.get('title')[:50]}...")
        print(f"  maker: {result.get('maker', '(無)')}")
        print(f"  actors: {result.get('actors')}")
        print(f"  source: {result.get('source')}")
    else:
        print("  (無結果)")


def test_multiple_numbers():
    """測試多個番號的 maker"""
    numbers = ['SONE-103', 'IPZZ-031', 'MIDV-001', 'STARS-800']

    print("\n=== 批次測試 maker ===\n")
    print(f"{'番號':<12} {'Maker':<20} {'來源':<10}")
    print("-" * 45)

    for num in numbers:
        result = search_jav(num)
        if result:
            maker = result.get('maker', '-')
            source = result.get('source', '-')
            print(f"{num:<12} {maker:<20} {source:<10}")
        else:
            print(f"{num:<12} {'(無結果)':<20}")


if __name__ == '__main__':
    test_individual_scrapers()
    test_multiple_numbers()
