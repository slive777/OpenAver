"""
gfriends CDN 查表模組
透過片商映射 + jsDelivr CDN HEAD request 定位女優圖片
不下載 Filetree.json，不 clone repo，零額外儲存
"""

from typing import Optional
import requests

CDN_BASE = "https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/Content"
FALLBACK_FOLDER = "9-AVDBS"

# maker_mapping.json 的 maker name → gfriends Content/ 資料夾
# 由 cross-reference 產生：gfriends 50 folders × maker_mapping 168 unique makers
# 多個 maker name 可指向同一 folder（別名/子品牌）
MAKER_TO_GFRIENDS = {
    # ── 7 系列（大廠） ──
    "S1": "7-S1",
    "S1 NO.1 STYLE": "7-S1",
    "Moodyz": "7-Moodyz",
    "MOODYZ": "7-Moodyz",
    "MOODYZ Best": "7-Moodyz",
    "MOODYZ DIVA": "7-Moodyz",
    "Madonna": "7-Madonna",
    "マドンナ(Madonna)": "7-Madonna",
    # ── 8 系列 ──
    "IdeaPocket": "8-Ideapocket",
    "IDEA POCKET": "8-Ideapocket",
    "Honnaka": "8-Honnaka",
    "kira*kira": "8-KiraKira",
    # ── 1-6 系列 ──
    "FALENO": "1-FALENO",
    "DAHLIA": "2-Dahlia",
    "MUTEKI": "3-MUTEKI",
    "kawaii*": "4-Kawaii",
    "Kawaii": "4-Kawaii",
    "E-Body": "5-Ebody",
    "PREMIUM": "5-Premium",
    "Chijo Heaven": "5-痴女天堂",
    # ── v 系列 ──
    "Attackers": "v-Attackers",
    "Prestige": "v-Prestige",
    "桃太郎映像出版": "v-桃太郎",
    # ── w 系列 ──
    "Oppai": "w-OPPAI",
    "Emmusume Lab": "w-えむっ娘ラボ",
    # ── x 系列 ──
    "Das!": "x-DAS",
    "KMP": "x-KMP",
    "SCOOP（KMP）": "x-KMP",
    "KMPVR-彩-": "x-KMP",
    "Wanz Factory": "x-WANZ",
    "溜池ゴロー": "x-溜池ゴロー",
    # ── 無獨立 folder → 聚合來源 ──
    "SOD": "9-AVDBS",
    "SOD Create": "9-AVDBS",
}
# 未映射的 gfriends folders（不在 maker_mapping.json 中）：
#   0-Hand-Storage, 1-Diaz, 2-Juicy-Honey, 2-Nanairo, 3-Allpro, 3-Arrows,
#   3-Lovepop, 6-Capsule, 6-Mines, 6-Tpowers, 7-未満, 8-Bambi, 8-Cmore,
#   8-Digigra, 8-GRAPHIS, 8-Warashi, 9-Eightman, 9-Javrave, v-Fitch,
#   x-BeFree, y-AVDC, y-Attractive, y-Minnano, y-无垢,
#   z-DMM(步), z-DMM(骑), z-Derekhsu, z-ラグジュTV
# → 這些由 FALLBACK_FOLDER = "9-AVDBS" 兜底


def _check_gfriends_url(folder: str, name: str) -> Optional[str]:
    """
    對 CDN/{folder}/{name}.jpg 發 HEAD request（timeout=3s）

    Args:
        folder: gfriends Content/ 下的資料夾名稱（e.g. "7-S1"）
        name: 女優名稱（e.g. "桜空もも"）

    Returns:
        命中的 URL，或 None
    """
    try:
        url = f"{CDN_BASE}/{folder}/{name}.jpg"
        resp = requests.head(url, timeout=3)
        if resp.status_code == 200:
            return url

        # 嘗試 AI-Fix 版本
        ai_fix_url = f"{CDN_BASE}/{folder}/AI-Fix-{name}.jpg"
        resp2 = requests.head(ai_fix_url, timeout=3)
        if resp2.status_code == 200:
            return ai_fix_url

        return None
    except Exception:
        return None


def lookup_gfriends(name: str, makers: list = None) -> Optional[str]:
    """
    依片商優先順序查詢 gfriends 女優圖片

    Args:
        name: 女優名稱（日文）
        makers: [Top1片商, Top2片商, ...] 從搜尋結果統計

    嘗試順序：Top1 folder → Top2 folder → 9-AVDBS fallback
    每步為一個 HEAD request (~42ms)

    Returns:
        命中的 CDN URL，或 None
    """
    folders_to_try = []
    for maker in (makers or []):
        folder = MAKER_TO_GFRIENDS.get(maker)
        if folder and folder not in folders_to_try:
            folders_to_try.append(folder)

    # Fallback: 聚合來源
    if FALLBACK_FOLDER not in folders_to_try:
        folders_to_try.append(FALLBACK_FOLDER)

    for folder in folders_to_try:
        url = _check_gfriends_url(folder, name)
        if url:
            return url
    return None
