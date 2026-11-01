"""test_showcase_grouping.py — GET /api/showcase/videos / /api/showcase/video 的
分組序列化行為（TASK-122-T2）。

AC-4（單檔片逐位元組不變，機械驗證）：讀回 `tests/fixtures/showcase/multipart_t2_baseline.json`
—— 這份 fixture 是**動手改 core/multipart_group.py／showcase.py 之前**、用現行未改動的
`_serialize_video()` 對一個「全部單檔片」合成 DB 跑 `GET /api/showcase/videos` 產生的
（見 TASK-122-T2 directive 步驟 1，硬性禁止用 git 指令回復工作區取得改動前輸出）。
本檔用**完全相同的合成 DB 資料**（逐欄位對照 fixture 生成腳本）重打一次同一支端點，
逐筆逐鍵比對：除新增的 `part_tokens` 鍵外，其餘 22 個既有 key 值必須完全相等。

AC-18：`_serialize_group()` 輸出的 `path` 必為 `group.members[0]`（part-1）的 path。
"""
import json
from pathlib import Path

import pytest

from core.database import Video
from core.path_utils import to_file_uri
from core.multipart_group import VideoGroup
from web.routers.showcase import _serialize_group


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "showcase" / "multipart_t2_baseline.json"

# 與 AC-4 baseline 產生腳本逐欄位相同的合成資料——4 筆全單檔片，涵蓋有封面／無封面／
# 有 sample_images／無 duration 等既有欄位邊界組合。**不得改動這份資料**，否則 AC-4
# 逐鍵比對會失去意義（比的就是「同輸入、改動前後輸出相同」）。
def _baseline_videos() -> list[Video]:
    return [
        Video(
            path=to_file_uri("/home/user/media/SONE-205.mp4"),
            number="SONE-205",
            title="Test Video 1",
            original_title="テストビデオ1",
            actresses=["坂道みる", "深田えいみ"],
            maker="S1 NO.1 STYLE",
            director="Some Director",
            series="Some Series",
            label="SONE",
            release_date="2024-01-15",
            tags=["単体作品", "ハイビジョン", "独占配信"],
            user_tags=["★5"],
            duration=120,
            size_bytes=3145728000,
            cover_path=to_file_uri("/home/user/media/SONE-205/poster.jpg"),
            sample_images=[to_file_uri("/home/user/media/SONE-205/s1.jpg")],
            mtime=1705276800.0,
            auto_focal="0.5,0.5",
            crop_mode="auto",
        ),
        Video(
            path=to_file_uri("/home/user/media/ABW-001.mp4"),
            number="ABW-001",
            title="Test Video 2 - No Cover No Duration",
            original_title="",
            actresses=["新ありな"],
            maker="Prestige",
            release_date="2024-02-01",
            tags=["スレンダー"],
            duration=None,
            size_bytes=2147483648,
            cover_path="",
            mtime=1706745600.0,
        ),
        Video(
            path=to_file_uri("/home/user/media/FC2-001.mp4"),
            number="FC2-PPV-001",
            title="Test Video 3 - Zero size None fields",
            original_title="",
            actresses=[],
            maker="",
            release_date="",
            tags=[],
            duration=None,
            size_bytes=0,
            cover_path="",
            mtime=0.0,
        ),
        Video(
            path=to_file_uri("/home/user/media/sub/MIRD-151.mp4"),
            number="MIRD-151",
            title="Test Video 4 - subfolder with sample images",
            original_title="",
            actresses=["女優D"],
            maker="MakerD",
            release_date="2023-05-05",
            tags=["tagD"],
            duration=90,
            size_bytes=1000000,
            cover_path=to_file_uri("/home/user/media/sub/MIRD-151/poster.jpg"),
            sample_images=[
                to_file_uri("/home/user/media/sub/MIRD-151/s1.jpg"),
                to_file_uri("/home/user/media/sub/MIRD-151/s2.jpg"),
            ],
            mtime=1683273600.0,
        ),
    ]


@pytest.fixture
def baseline_showcase_config():
    return {
        "gallery": {
            "directories": ["/home/user/media"],
            "path_mappings": {},
            "min_size_mb": 0,
            "thumbnail_width": 400,
        },
        "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"},
        "thumbnail_cache_enabled": False,
    }


@pytest.fixture
def baseline_client(make_client, temp_db, baseline_showcase_config, make_populated_db):
    make_populated_db(_baseline_videos())
    return make_client(
        ["core.database.connection.get_db_path", "web.routers.showcase.get_db_path", "web.routers.showcase.load_config"],
        mock_db_path=temp_db,
        config_override=baseline_showcase_config,
    )


class TestAC4BaselineFixtureComparison:
    """AC-4：單檔片序列化逐位元組不變的機械驗證。"""


    def test_every_video_key_except_part_tokens_matches_baseline_exactly(self, baseline_client):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            baseline = json.load(f)

        response = baseline_client.get("/api/showcase/videos")
        data = response.json()
        actual_videos = data["videos"]
        expected_videos = baseline["videos"]

        assert len(actual_videos) == len(expected_videos)

        # 以 path 對齊（兩邊皆用同一份合成資料，path 具唯一性可當比對鍵）
        actual_by_path = {v["path"]: v for v in actual_videos}
        expected_by_path = {v["path"]: v for v in expected_videos}
        assert set(actual_by_path.keys()) == set(expected_by_path.keys())

        for path, expected_v in expected_by_path.items():
            actual_v = actual_by_path[path]
            # part_tokens 是本 task 新增的鍵，baseline 裡不存在——單獨斷言，不進逐鍵迴圈
            assert "part_tokens" not in expected_v
            assert actual_v.get("part_tokens") == [], (
                f"單檔片 {path} 的 part_tokens 必為 []，實際 {actual_v.get('part_tokens')}"
            )
            for key, expected_value in expected_v.items():
                assert key in actual_v, f"缺少既有 key: {key}（path={path}）"
                assert actual_v[key] == expected_value, (
                    f"key={key} 值不符（path={path}）: "
                    f"expected={expected_value!r} actual={actual_v[key]!r}"
                )
            # 反向確認沒有意外多出的既有 key
            # 排除的鍵都是「後續 branch 全域新增、有自己的測試」的鍵，各自單獨斷言過：
            #   part_tokens —— 本 task（122）新增
            #   user_rating —— spec-123 精選新增（TASK-123-T2 的 _serialize_video 無條件輸出，
            #                   未精選為 0；該欄位的行為由 tests/integration/test_api_showcase.py
            #                   的 TestShowcaseUserRatingField 三支守著，不歸本 baseline 管）
            #   needs_translate —— 172 新增，無條件輸出
            #   has_plot —— 187b CD-187b-1.3 新增，無條件輸出 bool（NULL→false；FE-ALPINE-06）
            assert actual_v.get("user_rating") == 0, (
                f"單檔片 {path} 的 user_rating 在 baseline fixture 情境下必為 0，"
                f"實際 {actual_v.get('user_rating')}"
            )
            assert "needs_translate" in actual_v, f"單檔片 {path} 缺 needs_translate 欄位（172 新增，無條件輸出）"
            assert "has_plot" in actual_v, f"單檔片 {path} 缺 has_plot 欄位（187b 新增，無條件輸出）"
            assert type(actual_v["has_plot"]) is bool, (
                f"單檔片 {path} 的 has_plot 必須是 bool，實際 {actual_v['has_plot']!r}"
            )
            assert actual_v["has_plot"] is False, (
                f"單檔片 {path} 的 has_plot 在 baseline fixture 情境下必為 false，"
                f"實際 {actual_v['has_plot']!r}"
            )
            extra_keys = (
                set(actual_v.keys()) - set(expected_v.keys())
                - {"part_tokens", "user_rating", "needs_translate", "has_plot"}
            )
            assert not extra_keys, f"多出非預期 key: {extra_keys}（path={path}）"


# ── AC-18：合併卡 path 必為 part-1 ───────────────────────────────────────

class TestAC18RepresentativePathIsPart1:
    def test_serialize_group_path_equals_members_first_path(self):
        part1 = Video(
            path=to_file_uri("/media/ABC-123-cd1.mp4"),
            number="ABC-123",
            title="Part 1 title",
            size_bytes=100,
        )
        part2 = Video(
            path=to_file_uri("/media/ABC-123-cd2.mp4"),
            number="ABC-123",
            title="Part 2 title (should not leak into base)",
            size_bytes=200,
        )
        group = VideoGroup(members=[part1, part2], part_tokens=["cd1", "cd2"])

        result = _serialize_group(group, path_mappings={}, enabled=False)

        assert result["path"] == part1.path
        assert result["path"] == group.members[0].path
        # 其餘欄位（含 title）逐字取 part-1，不做欄位級 merge（CD-122-4）
        assert result["title"] == "Part 1 title"
        # size 是覆寫的加總欄位，唯一例外
        assert result["size"] == 300
        assert result["part_tokens"] == ["cd1", "cd2"]


# ── AC-12（TASK-123-T7）：精選寫入層 ＋ 序列化層串成一條完整證據鏈 ───────────────────
#
# tests/integration/test_user_rating_api.py 的 TestScenario4MultipartRepresentative
# 已經驗過「寫入層」：送 -cd2 路徑，DB 裡實際被寫入 user_rating 的是代表段（-cd1）
# 那一列。這裡驗的是「序列化層」：精選之後，group_rows()/_serialize_group()（本 branch
# 完全未動這段既有邏輯）吐出來的 showcase 列表仍然只有一張合併卡，且那張卡的
# `user_rating` 正確反映代表段的值——不會因為 user_rating 只寫在 cd1 而讓前端
# 「只看精選」漏篩或重複算成兩張卡。
#
# 端到端走真實 TestClient：先打 POST /api/user-rating（真正的寫入路徑），
# 再打 GET /api/showcase/videos（真正的序列化路徑），兩者共用同一個 tmp DB。

class TestAC12PickThenSerializeStaysOneCard:
    def _make_group_db(self, make_populated_db):
        """同資料夾、同 stem、各帶 part token 的兩列 -> group_rows() 判定成組。"""
        part1 = Video(
            path=to_file_uri("/home/user/media/GRP-001-cd1.mp4"),
            number="GRP-001",
            title="Group Part 1",
            size_bytes=100,
        )
        part2 = Video(
            path=to_file_uri("/home/user/media/GRP-001-cd2.mp4"),
            number="GRP-001",
            title="Group Part 2",
            size_bytes=200,
        )
        return make_populated_db([part1, part2]), part1.path, part2.path

    @pytest.fixture
    def group_showcase_config(self):
        return {
            "gallery": {
                "directories": ["/home/user/media"],
                "path_mappings": {},
                "min_size_mb": 0,
                "thumbnail_width": 400,
            },
            "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
            "database": {"path": ":memory:"},
            "translate": {"provider": "ollama", "ollama_model": "llama3"},
            "thumbnail_cache_enabled": False,
        }

    def _make_group_client(self, make_client, db_path, group_showcase_config):
        """showcase／collection 兩個 router 共用同一個 tmp DB ＋ 同一份 config
        （AC-12 需要真正打 POST /api/user-rating 寫入、再打 GET /api/showcase/videos
        讀回，兩個端點分屬不同 router 檔案，各自的 get_db_path/load_config 要一起 mock）。
        """
        return make_client(
            [
                "web.routers.showcase.get_db_path",
                "web.routers.showcase.load_config",
                "web.routers.collection.get_db_path",
                "web.routers.collection.load_config",
            ],
            mock_db_path=db_path,
            config_override=group_showcase_config,
        )


    def test_pick_part2_resolves_to_representative_then_only_one_card_with_rating(
        self, make_populated_db, make_client, group_showcase_config
    ):
        """精選 cd2（非代表段，經 resolve_group() 落到 cd1）→ 序列化整組同樣只有
        1 筆、user_rating == 1——驗證 resolve_group() 代表段解析在序列化層的另一面。"""
        db_path, _part1_path, part2_path = self._make_group_db(make_populated_db)
        client = self._make_group_client(make_client, db_path, group_showcase_config)

        resp = client.post("/api/user-rating", json={"file_path": part2_path, "picked": True})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        listing = client.get("/api/showcase/videos")
        assert listing.status_code == 200
        data = listing.json()
        assert data["total"] == 1, "分集片精選後序列化層必須仍只吐一張合併卡"
        card = data["videos"][0]
        assert card["user_rating"] == 1
        assert card["part_tokens"] == ["cd1", "cd2"]
