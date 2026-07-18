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
from core.focal.detector import (
    _cluster_and_select,
    _cluster_and_select_2d,
    _dominant_axis_by_ratio,
    detect_faces,
    format_focal,
    parse_focal,
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

    def test_detect_faces_finds_detections(self):
        img = Image.open(_FIXTURE)
        faces = detect_faces(img)
        assert len(faces) > 0, "sample.jpg must yield at least one raw detection"

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

    def test_no_faces_2d_returns_none(self):
        assert _cluster_and_select_2d(100, 100, [], axis=0) is None

    def test_single_face_weighted_average_is_its_own_position(self):
        # row=50, col=80, scale=20, q=2.0 -> width=100 -> x=0.8
        faces = [(50, 80, 20, 2.0)]
        pos, found = _cluster_and_select(100, 100, faces, axis=0)
        assert found is True
        assert pos == pytest.approx(0.8)

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

    def test_cluster_tolerance_boundary_just_outside_does_not_merge(self):
        width = height = 100
        # diff = 0.06 > 0.05 tolerance -> must NOT merge; strongest single wins
        faces = [
            (10, 40, 10, 1.0),   # x=0.40, weight=10
            (10, 46, 10, 1.0),   # x=0.46, weight=10 (equal weight tie -> first found kept as group)
        ]
        pos, found = _cluster_and_select(width, height, faces, axis=0)
        assert found is True
        # Each is its own group of weight 10; group order among ties is
        # stable-sort, so the first-seen group (x=0.40) wins the tie.
        assert pos == pytest.approx(0.40)

    def test_degenerate_zero_weight_group_returns_not_found(self):
        # scale=0 or q=0 -> weight=0 -> total_w <= 0 branch
        faces = [(10, 10, 0, 5.0)]
        pos, found = _cluster_and_select(100, 100, faces, axis=0)
        assert found is False
        assert pos == 0.0

    def test_degenerate_zero_weight_group_2d_returns_none(self):
        faces = [(10, 10, 0, 5.0)]
        assert _cluster_and_select_2d(100, 100, faces, axis=0) is None

    def test_2d_x_matches_1d_when_axis_is_x(self):
        """CD-98a-4 契約：axis==0 時 2D x 分量必須 == 原單軸值。"""
        width, height = 200, 150
        faces = [
            (30, 40, 10, 1.5),
            (35, 44, 12, 2.5),
            (100, 150, 30, 5.0),
        ]
        axis = 0
        pos_1d, found = _cluster_and_select(width, height, faces, axis)
        assert found is True
        centroid = _cluster_and_select_2d(width, height, faces, axis)
        assert centroid is not None
        x_ratio, _y_ratio = centroid
        assert x_ratio == pytest.approx(pos_1d)

    def test_2d_y_matches_1d_when_axis_is_y(self):
        """CD-98a-4 契約：axis==1 時 2D y 分量必須 == 原單軸值。"""
        width, height = 150, 200
        faces = [
            (30, 40, 10, 1.5),
            (34, 45, 12, 2.5),
            (150, 100, 30, 5.0),
        ]
        axis = 1
        pos_1d, found = _cluster_and_select(width, height, faces, axis)
        assert found is True
        centroid = _cluster_and_select_2d(width, height, faces, axis)
        assert centroid is not None
        _x_ratio, y_ratio = centroid
        assert y_ratio == pytest.approx(pos_1d)

    def test_2d_also_averages_the_other_axis(self):
        """2D 版本除了主軸值外，另一軸也要是同群的加權平均（不是 0 或任意值）。"""
        width, height = 100, 100
        faces = [
            (20, 40, 10, 1.0),   # x=0.40 row=20 -> y=0.20, weight=10
            (60, 44, 10, 3.0),   # x=0.44 row=60 -> y=0.60, weight=30
        ]
        axis = 0
        centroid = _cluster_and_select_2d(width, height, faces, axis)
        assert centroid is not None
        x_ratio, y_ratio = centroid
        expected_y = (0.20 * 10 + 0.60 * 30) / (10 + 30)
        assert y_ratio == pytest.approx(expected_y)


# ============ crop_image_position ============


class TestCropImagePosition:
    def test_landscape_crop_ratio_071(self):
        img = Image.new("RGB", (1000, 600))
        out = crop_image_position(img, 0.71, 0.5)
        w, h = out.size
        assert h == 600
        assert w == int(600 * 0.71)

    def test_portrait_crop_ratio_3_4(self):
        img = Image.new("RGB", (600, 1000))
        ratio = 3.0 / 4.0
        out = crop_image_position(img, ratio, 0.5)
        w, h = out.size
        # w = int(height*ratio) = int(1000*0.75) = 750 >= width(600)
        # -> falls into the h-branch: h = int(width/ratio)
        assert w == 600
        assert h == int(600 / ratio)

    def test_crop_bounds_clamp_no_padding(self):
        img = Image.new("RGB", (200, 100))
        # pos near the right edge should clamp the crop box to stay in bounds
        out = crop_image_position(img, 0.71, 1.0)
        w, h = out.size
        assert w <= 200
        assert h <= 100

    def test_ratio_out_of_range_returns_original(self):
        img = Image.new("RGB", (200, 100))
        out = crop_image_position(img, 1e-3, 0.5)  # < 1e-2
        assert out is img
        out2 = crop_image_position(img, 1e3, 0.5)  # > 1e2
        assert out2 is img


# ============ detect_focal (product entry point) ============


class TestDetectFocal:
    def test_detect_focal_smoke_returns_xy_in_unit_square(self):
        result = detect_focal(str(_FIXTURE), 2.0 / 3.0, 650)
        assert result is not None
        x, y = result
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0

    def test_detect_focal_returns_none_on_missing_file(self):
        result = detect_focal("/nonexistent/path/does-not-exist.jpg", 2.0 / 3.0, 650)
        assert result is None

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

    def test_format_none_is_empty_string(self):
        assert format_focal(None) == ''

    def test_format_produces_four_decimals(self):
        assert format_focal((0.5, 0.333333)) == "0.5000,0.3333"

    def test_parse_empty_string_is_none(self):
        assert parse_focal('') is None

    def test_parse_none_is_none(self):
        assert parse_focal(None) is None

    def test_parse_garbage_is_none(self):
        assert parse_focal('garbage') is None

    def test_parse_wrong_part_count_is_none(self):
        assert parse_focal('1,2,3') is None
        assert parse_focal('1') is None

    def test_parse_non_float_parts_is_none(self):
        assert parse_focal('a,b') is None

    def test_parse_non_finite_is_none(self):
        # nan/inf are "valid" floats to float() but must degrade to unset
        # (right-crop) rather than leak into crop math / CSS object-position.
        assert parse_focal('nan,nan') is None
        assert parse_focal('inf,0.5') is None
        assert parse_focal('1e400,1') is None      # 1e400 -> inf
        assert parse_focal('0.5,-inf') is None

    def test_parse_out_of_range_is_none(self):
        # focal is a ratio in [0,1]x[0,1]; hand-corrupted DB values outside
        # that range must degrade to unset (right-crop fallback) rather than
        # leak into crop math / CSS object-position (98b/98c).
        assert parse_focal('1.2,-0.1') is None
        assert parse_focal('1.2,0.5') is None
        assert parse_focal('0.5,-0.1') is None
        assert parse_focal('-0.0001,0.5') is None

    def test_parse_boundary_values_are_accepted(self):
        # inclusive bounds: 0.0 and 1.0 are valid ratios.
        assert parse_focal('0.0,0.0') == (0.0, 0.0)
        assert parse_focal('1.0,1.0') == (1.0, 1.0)
