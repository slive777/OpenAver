"""core.database.actress_library — 庫內女優聚合（spec-117 子模組，TASK-117-T1）。

【Opus 裁決 ①】分組／聚合的單一所有者。這是**第三個**模組同時 import `.actress`
與 `.alias`——先例：`core.database.migrate` 同形狀 import `.video`（見該檔）。
`actress.py` 與 `alias.py` 之間仍然零依賴，這個模組才是組合點。分組是領域邏輯
（「誰跟誰是同一人、算幾片」），不是 HTTP 關注點，所以不放 router 層。
"""
import time
from typing import List

from .actress import ActressRepository
from .alias import AliasRepository
from core.recent_rules import FavStat, effective_score, video_weight


def get_library_actresses() -> List[dict]:
    """依 alias group 聚合庫內全部女優，回傳每筆 { primary_name, names[], video_count,
    is_favorite }。

    規則（§1.1 定死 + Opus 裁決 ②）：
      - pairs = ActressRepository().get_video_actress_pairs()——一次查詢拿到全部
        (rowid, actress_name) 配對。
      - name → (primary_name, names[]) 由 AliasRepository().get_all() 建一次 lookup dict
        （primary_name 與每個 alias 都指向同一組 (primary_name, [primary_name]+aliases)）；
        lookup miss 時 group_key = name 本身，names = [name]。
      - video_count = 該 group 的 set(rowid) 長度（Python 側 DISTINCT，CD-117-2）。
      - is_favorite：`favorite_names = {a.name for a in ActressRepository().get_all()}`
        建一次集合，判定 `any(n in favorite_names for n in names)`——讀 `actresses` 表同一欄，
        不查 alias 表是否存在該 group（迴圈內不得逐一呼叫 exists()，Opus 裁決 ②）。

        Codex PR review P2（已查證屬實）：早期版本只判 `primary_name in favorite_names`。
        `AliasRepository.add()`（手動建組，走 `/api/actress-aliases` 別名管理 UI）允許
        使用者自己打任意 primary_name，不要求它是已收藏女優——「A 是使用者手打的 group
        primary（未收藏）、B 是已收藏女優的正式名、B 被使用者手動加成 A 的 alias」是
        UI 上點幾下就能做到的合法資料形狀，不是邊界攻擊。只查 primary 會讓這整組漏判
        成未收藏。

      - **顯示用 primary_name**（AC-3.1「顯示已收藏女優的正式名」）：只在 group 自己的
        primary 不在 favorite_names、但某個 alias 成員在時才需要換名——否則維持
        `record.primary_name`。換的話，`names_list`（= `[primary_name] + aliases`，
        既有儲存順序）裡**第一個**命中 `favorite_names` 的名字就是顯示用名字；這個順序
        天然優先選 group 自己的 primary（它若已收藏，第一個命中的就是它自己，不換），
        只有它未收藏、其他成員命中時才會換成該成員。不引入額外排序規則，多個成員同時
        已收藏的情況下也是確定性的（永遠是 names_list 裡最先出現的那個）。
        `resolve()` 雙向解析（primary 或 alias 命中都回整組），所以換掉顯示名不影響
        CD-117-2 的 parity 口徑：`count_videos_for_actress_names(resolve(顯示名))` 與
        `resolve(record.primary_name)` 是同一個 group、同一個結果。
      - 排序 = video_count desc, primary_name asc（AC-2.2 穩定次序）；排序欄位讀的就是
        上面「顯示用 primary_name」，所以換名後同片數的相鄰兩組排序會跟著顯示名走——
        這是預期結果（畫面上看到的字母序才是使用者真正在意的次序），不是回歸。

    排除 0 片（AC-2.7）天然成立：group 只可能由 pairs（有片子的名字）建立，不
    outer join 收藏表。

    整支函式全程只開 3 次連線（pairs 一次、alias get_all() 一次、favorites get_all()
    一次），與 group 數無關——迴圈內是純 Python 記憶體分組，不開任何 DB 連線。
    """
    pairs = ActressRepository().get_video_actress_pairs()

    # name -> (primary_name, names_list)；names_list 對同一 group 內每個名字共用同一物件
    lookup: dict = {}
    for record in AliasRepository().get_all():
        names_list = [record.primary_name] + list(record.aliases)
        for n in names_list:
            lookup[n] = (record.primary_name, names_list)

    favorite_names = {a.name for a in ActressRepository().get_all()}

    groups: dict = {}  # primary_name -> {"names": list, "rowids": set}
    for rowid, name in pairs:
        primary_name, names_list = lookup.get(name, (name, [name]))
        group = groups.get(primary_name)
        if group is None:
            group = {"names": names_list, "rowids": set()}
            groups[primary_name] = group
        group["rowids"].add(rowid)

    result = []
    for primary_name, group in groups.items():
        names_list = group["names"]
        # 顯示用 primary_name：names_list 順序中第一個命中 favorite_names 的名字；
        # 沒有命中則維持 group 自己的 primary_name（見上方 docstring／AC-3.1）。
        display_name = next(
            (n for n in names_list if n in favorite_names), primary_name
        )
        result.append(
            {
                "primary_name": display_name,
                "names": names_list,
                "video_count": len(group["rowids"]),
                "is_favorite": any(n in favorite_names for n in names_list),
            }
        )
    result.sort(key=lambda g: (-g["video_count"], g["primary_name"]))
    return result


def _alias_name_sets(alias_repo) -> dict:
    """name -> 該名字所屬 group 的全部名字（與 _alias_base.resolve 同序：primary 優先於 alias）。"""
    records = alias_repo.get_all()
    lookup: dict = {}
    for record in records:  # 先填 alias
        group = {record.primary_name} | set(record.aliases)
        for alias in record.aliases:
            lookup[alias] = group
    for record in records:  # primary 後填、覆蓋 alias
        lookup[record.primary_name] = {record.primary_name} | set(record.aliases)
    return lookup


def get_favorite_actress_stats(now=None, *, actress_repo=None, alias_repo=None) -> dict:
    """一次掃描算出每位收藏女優的 FavStat(name, video_count, score)（CD-184-3 ②）。

    - video_count 與 count_videos_for_actress_names(resolve(name)) 同口徑（rowid 去重）。
    - score = sum(video_weight) 後套 effective_score；每請求現算、不快取。
    - 全函式只開 3 次連線（pairs、alias get_all、favorites get_all）。
    """
    if now is None:
        now = time.time()
    actress_repo = actress_repo or ActressRepository()
    alias_repo = alias_repo or AliasRepository()
    pairs = actress_repo.get_video_actress_mtime_pairs()
    lookup = _alias_name_sets(alias_repo)
    favorites = [a.name for a in actress_repo.get_all()]

    rowid_mtime: dict = {}
    rowids_by_name: dict = {}
    for rowid, name, mtime in pairs:
        rowid_mtime[rowid] = mtime
        rowids_by_name.setdefault(name, set()).add(rowid)

    stats: dict = {}
    for fav in favorites:
        all_rowids: list = []
        for n in lookup.get(fav, {fav}):
            all_rowids.extend(rowids_by_name.get(n, ()))
        distinct = set(all_rowids)  # 同片掛多個名字只算一次
        raw = sum(video_weight(rowid_mtime[r], now) for r in distinct)
        stats[fav] = FavStat(fav, len(distinct), effective_score(raw))
    return stats
