"""test_focal_detector.py - core/focal/{pigo,detector}.py 單元測試

測試範圍（TASK-98a-T1 DoD 1-3, 5-smoke）：
- port oracle：sample.jpg 跑 detect_faces，對拍釘定座標（bit-exact 回歸鎖）
- 選點：合成多框驗 0.05 分群 + Scale*Q 加權平均 + 無臉回 None
        + 2D 質心 x/y 分量與原單軸 _cluster_and_select 一致（CD-98a-4 契約）
- crop_image_position：橫圖/直圖裁切、bounds clamp、ratio 出界回原圖
- detect_focal smoke：對 sample.jpg 真跑一次（cascade 缺檔會 RED）
"""
from pathlib import Path

import pytest
from PIL import Image

from core.focal import crop_image_position, detect_focal
from types import SimpleNamespace

from core.focal.detector import (
    _cluster_and_select,
    _cluster_and_select_2d,
    _dominant_axis_by_ratio,
    detect_faces,
    format_focal,
    parse_focal,
    select_focal_from_boxes,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "focal" / "sample.jpg"
_NO_FACE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos" / "no_face_detected.jpg"


# ============ port oracle ============


class TestPortOracle:
    """sample.jpg (288x488, 去識別中央臉肖像) 跑 detect_faces 對拍釘定座標。

    fixture 是一張裁掉來源浮水印/名稱的臉肖像，供 port oracle 用。參考座標由
    core/focal 本身對此 sample.jpg 跑單角度 detect_faces 產出並釘住：
    axis=Y（int(488*0.6667)=325 > 288 → 主軸 Y），strongest-group 1D pos
    ~= 0.4569（Y），2D centroid ~= (0.4734, 0.4569)。任何 pigo.py 算術的
    mutation 都會移動這個值 —— 這正是 oracle 要抓的。

    已知盲點（coarse oracle）：位置＝群內權重的加權平均比值，對「所有權重
    乘同一常數」這種 uniform-scalar 係數 bug 天然不敏感（分子分母同倍抵消）。
    真實 pigo 回歸多為結構性（bit-shift/表索引/threshold 錯）→ 先讓 detect_faces
    count 掉到 0（found=False）就被 test_detect_faces_finds_detections 抓死，
    輪不到數值容忍。若未來報「count 變了但位置 oracle 仍綠」，記得這個盲點。
    """


    def test_strongest_group_lands_in_pinned_face_region(self):
        img = Image.open(_FIXTURE)
        faces = detect_faces(img)
        w, h = img.size
        axis = _dominant_axis_by_ratio(w, h, 2.0 / 3.0)
        assert axis == 1  # Y dominant for this portrait + ratio

        pos, found = _cluster_and_select(w, h, faces, axis)
        assert found is True
        # Pinned reference (tight tolerance; a pigo arithmetic regression moves it).
        assert pos == pytest.approx(0.4569, abs=0.01)

        centroid = _cluster_and_select_2d(w, h, faces, axis)
        assert centroid is not None
        x_ratio, y_ratio = centroid
        # axis==1 -> 2D y-component equals the 1D dominant pos (CD-98a-4 contract).
        assert y_ratio == pytest.approx(pos, abs=1e-9)
        assert y_ratio == pytest.approx(0.4569, abs=0.01)
        assert x_ratio == pytest.approx(0.4734, abs=0.01)


# ============ selection (_cluster_and_select / _cluster_and_select_2d) ============


class TestClusterAndSelect:
    """合成 (row, col, scale, q) 驗證分群 / 加權平均 / None 行為。"""

    def test_no_faces_returns_not_found(self):
        pos, found = _cluster_and_select(100, 100, [], axis=0)
        assert found is False
        assert pos == 0.0


    def test_two_close_faces_cluster_and_weighted_average(self):
        # axis=0 (x=col/width). Two detections within 0.05 of each other
        # must merge into one group; weighted average of their x positions.
        width = height = 100
        # col=40 -> x=0.40, col=44 -> x=0.44 (diff 0.04 <= 0.05 tolerance)
        faces = [
            (10, 40, 10, 1.0),   # weight = 10
            (10, 44, 10, 3.0),   # weight = 30
        ]
        pos, found = _cluster_and_select(width, height, faces, axis=0)
        assert found is True
        expected = (0.40 * 10 + 0.44 * 30) / (10 + 30)
        assert pos == pytest.approx(expected)

    def test_far_apart_faces_form_separate_groups_strongest_wins(self):
        width = height = 100
        # Group A: single weak face at x=0.1
        # Group B: single strong face at x=0.9 (far beyond 0.05 tolerance)
        faces = [
            (10, 10, 5, 1.0),    # weight = 5, x = 0.10
            (10, 90, 50, 10.0),  # weight = 500, x = 0.90
        ]
        pos, found = _cluster_and_select(width, height, faces, axis=0)
        assert found is True
        assert pos == pytest.approx(0.9)


# ============ select_focal_from_boxes (187a-T2) ============


def _boxes_to_pigo_faces(boxes, work_w, work_h):
    """box (x,y,w,h,score) → _cluster_and_select_2d 的 (row, col, scale, q)。"""
    faces = []
    for b in boxes:
        faces.append((
            (b.y + b.h / 2) * work_h,
            (b.x + b.w / 2) * work_w,
            b.w * work_w,
            b.score,
        ))
    return faces


class TestSelectFocalFromBoxes:
    """187a-T2：端點 box 選臉須與 pigo 風格 _cluster_and_select_2d 等價。"""

    def test_select_focal_from_boxes_matches_pigo_cluster(self):
        # 大臉低分 vs 小臉高分、兩群分兩側：scale 參與加權時大臉勝；scale=1.0 mutation 則小臉勝。
        boxes_x = [
            SimpleNamespace(x=0.05, y=0.40, w=0.40, h=0.30, score=0.3),
            SimpleNamespace(x=0.80, y=0.40, w=0.05, h=0.10, score=1.0),
        ]
        work_w, work_h, ratio_x = 100, 100, 0.71
        assert _dominant_axis_by_ratio(work_w, work_h, ratio_x) == 0
        expected_x = _cluster_and_select_2d(
            work_w, work_h, _boxes_to_pigo_faces(boxes_x, work_w, work_h), axis=0,
        )
        assert select_focal_from_boxes(boxes_x, work_w, work_h, ratio_x) == expected_x

        boxes_y = [
            SimpleNamespace(x=0.40, y=0.05, w=0.40, h=0.40, score=0.3),
            SimpleNamespace(x=0.40, y=0.80, w=0.05, h=0.05, score=1.0),
        ]
        work_w_y, work_h_y, ratio_y = 100, 200, 0.71
        assert _dominant_axis_by_ratio(work_w_y, work_h_y, ratio_y) == 1
        expected_y = _cluster_and_select_2d(
            work_w_y, work_h_y, _boxes_to_pigo_faces(boxes_y, work_w_y, work_h_y), axis=1,
        )
        assert select_focal_from_boxes(boxes_y, work_w_y, work_h_y, ratio_y) == expected_y

        # 單臉與空 boxes
        single = [SimpleNamespace(x=0.2, y=0.3, w=0.1, h=0.1, score=0.9)]
        expected_single = _cluster_and_select_2d(
            work_w, work_h, _boxes_to_pigo_faces(single, work_w, work_h), axis=0,
        )
        assert select_focal_from_boxes(single, work_w, work_h, ratio_x) == expected_single
        assert select_focal_from_boxes([], work_w, work_h, ratio_x) is None

    def test_select_focal_from_boxes_clamps_out_of_bounds_center(self):
        """端點框超出圖緣時臉心須夾回，否則 format_focal 寫出 >1 座標、parse 判無效。"""
        boxes = [SimpleNamespace(x=0.9, y=0.5, w=0.4, h=0.2, score=0.9)]
        work_w, work_h, ratio = 100, 100, 0.71
        result = select_focal_from_boxes(boxes, work_w, work_h, ratio)
        assert result is not None
        x_ratio, y_ratio = result
        assert 0.0 <= x_ratio <= 1.0
        assert 0.0 <= y_ratio <= 1.0
        assert parse_focal(format_focal(result)) is not None


# ============ crop_image_position ============


class TestCropImagePosition:
    def test_landscape_crop_ratio_071(self):
        img = Image.new("RGB", (1000, 600))
        out = crop_image_position(img, 0.71, 0.5)
        w, h = out.size
        assert h == 600
        assert w == int(600 * 0.71)


    def test_crop_bounds_clamp_no_padding(self):
        img = Image.new("RGB", (200, 100))
        # pos near the right edge should clamp the crop box to stay in bounds
        out = crop_image_position(img, 0.71, 1.0)
        w, h = out.size
        assert w <= 200
        assert h <= 100


# ============ detect_focal (product entry point) ============


class TestDetectFocal:


    def test_detect_focal_no_face_real_photo_returns_none(self):
        """TASK-102c-T1 方案 A：pigo 真跑對確定無臉的真圖必須回 None（Layer 1 回歸）。

        「organizer 收到 None 後有沒有正確 fallback」是 Layer 2 職責，已在
        test_organizer.py::TestCropToPosterByteForByteRegression::test_no_face_real_photo_branch3
        用 mock 驗證 wiring；本測試只驗 pigo 本身「真的能正確判定無臉」。
        """
        result = detect_focal(str(_NO_FACE_FIXTURE), 2.0 / 3.0, 650)
        assert result is None


# ============ serde (CD-98a-3: "x,y" 4-decimal canonical string) ============


class TestFocalSerde:
    def test_round_trip(self):
        focal = (0.6231, 0.4177)
        assert parse_focal(format_focal(focal)) == pytest.approx(focal)


    def test_parse_garbage_is_none(self):
        assert parse_focal('garbage') is None


