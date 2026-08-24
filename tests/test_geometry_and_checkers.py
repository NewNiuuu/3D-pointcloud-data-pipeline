"""几何函数与 checker 的测试。

重点不在"函数能跑"，而在**退化情形是否被正确拒绝**。一个在退化输入上
返回貌似合理数值的几何函数，会静默污染整个数据集 —— 这比抛异常危险得多。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from checkers import (
    CheckerError,
    check_cross_view_correspondence_answer,
    check_minimum_distance_answer,
    check_object_grounding_answer,
    check_observer_relative_direction_answer,
    get_checker,
)
from core.errors import ErrorCode
from geometry import (
    GeometryError,
    axis_aligned_bounding_box,
    azimuth_elevation,
    camera_center_from_pose,
    camera_forward_from_pose,
    centroid,
    height_difference,
    minimum_point_to_polyline_distance,
    observer_relative_direction,
    oriented_bounding_box,
    point_in_frustum,
    point_to_polyline_distance,
    point_to_segment_distance,
    project_points,
    visible_ratio,
    world_to_camera,
)

IDENTITY = np.eye(4)


# --------------------------------------------------------------- 距离

class TestPointToSegment:
    def test_perpendicular_foot_inside_segment(self):
        d = point_to_segment_distance([0, 5, 0], [-10, 0, 0], [10, 0, 0])
        assert d == pytest.approx(5.0)

    def test_projection_outside_uses_endpoint(self):
        """投影落在线段外时必须取端点距离，不能用无限直线。

        用直线会低估距离 —— 电线净空一类问题上，低估等于把危险判成安全。
        """
        d = point_to_segment_distance([20, 5, 0], [-10, 0, 0], [10, 0, 0])
        assert d == pytest.approx(math.hypot(10, 5))

    def test_degenerate_segment_raises(self):
        with pytest.raises(GeometryError, match="退化为一点"):
            point_to_segment_distance([0, 0, 0], [1, 1, 1], [1, 1, 1])

    def test_nan_input_raises(self):
        with pytest.raises(GeometryError, match="NaN"):
            point_to_segment_distance([0, float("nan"), 0], [0, 0, 0], [1, 0, 0])


class TestPointToPolyline:
    def test_returns_nearest_segment_index(self):
        line = [[0, 0, 0], [10, 0, 0], [10, 10, 0]]
        d, idx = point_to_polyline_distance([10, 5, 0], line)
        assert d == pytest.approx(0.0)
        assert idx == 1

    def test_duplicate_vertices_are_skipped_not_fatal(self):
        line = [[0, 0, 0], [0, 0, 0], [10, 0, 0]]
        d, _ = point_to_polyline_distance([5, 3, 0], line)
        assert d == pytest.approx(3.0)

    def test_all_vertices_identical_raises(self):
        with pytest.raises(GeometryError, match="顶点重合"):
            point_to_polyline_distance([1, 1, 1], [[0, 0, 0], [0, 0, 0]])

    def test_single_vertex_raises(self):
        with pytest.raises(GeometryError, match="至少需 2 个顶点"):
            point_to_polyline_distance([1, 1, 1], [[0, 0, 0]])


class TestMinimumOverPolylines:
    def test_picks_nearest_entity(self):
        lines = {
            "<wire_004>": [[0, 3, 0], [10, 3, 0]],
            "<wire_007>": [[0, 9, 0], [10, 9, 0]],
        }
        entity, distance, _ = minimum_point_to_polyline_distance([5, 0, 0], lines)
        assert entity == "<wire_004>"
        assert distance == pytest.approx(3.0)

    def test_empty_candidates_raises(self):
        with pytest.raises(GeometryError, match="为空"):
            minimum_point_to_polyline_distance([0, 0, 0], {})


# --------------------------------------------------------------- 相机

class TestCameraPose:
    def test_center_is_translation_column(self):
        T = np.eye(4)
        T[:3, 3] = [1.0, 2.0, 3.0]
        assert camera_center_from_pose(T) == pytest.approx([1.0, 2.0, 3.0])

    def test_rejects_non_orthonormal_rotation(self):
        T = np.eye(4)
        T[0, 0] = 2.0
        with pytest.raises(GeometryError, match="非正交"):
            camera_center_from_pose(T)

    def test_rejects_bad_bottom_row(self):
        T = np.eye(4)
        T[3] = [1.0, 0.0, 0.0, 1.0]
        with pytest.raises(GeometryError, match=r"\[0,0,0,1\]"):
            camera_center_from_pose(T)

    def test_forward_conventions_are_opposite(self):
        cv = camera_forward_from_pose(IDENTITY, "x_right_y_down_z_forward")
        gl = camera_forward_from_pose(IDENTITY, "x_right_y_up_z_backward")
        assert cv == pytest.approx([0, 0, 1])
        assert gl == pytest.approx([0, 0, -1])

    def test_unknown_convention_raises(self):
        """约定写错会让所有前后左右整体翻转，必须显式拒绝而非默认。"""
        with pytest.raises(GeometryError, match="未知相机约定"):
            camera_forward_from_pose(IDENTITY, "whatever")

    def test_world_to_camera_inverts_translation(self):
        T = np.eye(4)
        T[:3, 3] = [5.0, 0.0, 0.0]
        out = world_to_camera([[5.0, 0.0, 0.0]], T)
        assert out[0] == pytest.approx([0.0, 0.0, 0.0])


class TestProjection:
    K = np.array([[100.0, 0.0, 50.0], [0.0, 100.0, 40.0], [0.0, 0.0, 1.0]])

    def test_principal_point_maps_to_center(self):
        uv, depth = project_points([[0.0, 0.0, 10.0]], IDENTITY, self.K)
        assert uv[0] == pytest.approx([50.0, 40.0])
        assert depth[0] == pytest.approx(10.0)

    def test_frustum_excludes_points_behind_camera(self):
        pts = [[0.0, 0.0, 10.0], [0.0, 0.0, -10.0]]
        inside = point_in_frustum(pts, IDENTITY, self.K, (80, 100))
        assert inside.tolist() == [True, False]

    def test_frustum_excludes_out_of_image(self):
        pts = [[0.0, 0.0, 10.0], [100.0, 0.0, 10.0]]
        inside = point_in_frustum(pts, IDENTITY, self.K, (80, 100))
        assert inside.tolist() == [True, False]

    def test_visible_ratio_is_fraction(self):
        pts = [[0.0, 0.0, 10.0], [0.0, 0.0, -10.0]]
        assert visible_ratio(pts, IDENTITY, self.K, (80, 100)) == pytest.approx(0.5)


# --------------------------------------------------------------- 观察者相对关系

class TestObserverRelative:
    origin = [0.0, 0.0, 0.0]
    forward = [1.0, 0.0, 0.0]        # 朝 +X
    # up=+Z 时 right = forward × up = (1,0,0)×(0,0,1) = (0,-1,0)，即 -Y 为右

    def test_front_and_behind(self):
        front = observer_relative_direction([10, -5, 0], self.origin, self.forward)
        behind = observer_relative_direction([-10, -5, 0], self.origin, self.forward)
        assert front["longitudinal"] == "front"
        assert behind["longitudinal"] == "behind"

    def test_left_right_follows_right_hand_rule(self):
        right = observer_relative_direction([5, -5, 0], self.origin, self.forward)
        left = observer_relative_direction([5, 5, 0], self.origin, self.forward)
        assert right["lateral"] == "right"
        assert left["lateral"] == "left"

    def test_deadzone_returns_ambiguous_not_a_guess(self):
        """紧贴中线时左右会因位姿微小误差翻转，必须显式标歧义。"""
        result = observer_relative_direction(
            [100.0, 1.0, 0.0], self.origin, self.forward, lateral_deadzone_deg=10.0)
        assert result["lateral"] == "ambiguous"
        assert abs(result["lateral_angle_deg"]) < 10.0

    def test_target_at_observer_raises(self):
        with pytest.raises(GeometryError, match="重合"):
            observer_relative_direction(self.origin, self.origin, self.forward)

    def test_forward_parallel_to_up_raises(self):
        with pytest.raises(GeometryError, match="平行"):
            observer_relative_direction([1, 1, 1], self.origin, [0.0, 0.0, 1.0])

    def test_azimuth_zero_straight_ahead(self):
        az, el = azimuth_elevation([10, 0, 0], self.origin, self.forward)
        assert az == pytest.approx(0.0, abs=1e-9)
        assert el == pytest.approx(0.0, abs=1e-9)

    def test_elevation_positive_when_above(self):
        _, el = azimuth_elevation([10, 0, 10], self.origin, self.forward)
        assert el == pytest.approx(45.0)

    def test_height_difference_signed(self):
        assert height_difference([0, 0, 5], [0, 0, 2]) == pytest.approx(3.0)
        assert height_difference([0, 0, 2], [0, 0, 5]) == pytest.approx(-3.0)


# --------------------------------------------------------------- 实体几何

class TestEntityGeometry:
    def test_centroid_and_aabb(self):
        pts = [[0, 0, 0], [2, 4, 6]]
        assert centroid(pts) == pytest.approx([1, 2, 3])
        lo, hi = axis_aligned_bounding_box(pts)
        assert lo == pytest.approx([0, 0, 0])
        assert hi == pytest.approx([2, 4, 6])

    def test_obb_recovers_axis_aligned_box(self):
        pts = np.array([[x, y, z] for x in (-2, 2) for y in (-1, 1) for z in (-0.5, 0.5)])
        obb = oriented_bounding_box(pts)
        assert obb["center"] == pytest.approx([0, 0, 0], abs=1e-9)
        assert sorted(obb["extent"]) == pytest.approx([1.0, 2.0, 4.0])

    def test_obb_recovers_rotated_box(self):
        pts = np.array([[x, y, z] for x in (-2, 2) for y in (-1, 1) for z in (-0.5, 0.5)])
        angle = np.pi / 6
        R = np.array([[np.cos(angle), -np.sin(angle), 0],
                      [np.sin(angle), np.cos(angle), 0],
                      [0, 0, 1]])
        obb = oriented_bounding_box(pts @ R.T)
        assert sorted(obb["extent"]) == pytest.approx([1.0, 2.0, 4.0], abs=1e-9)

    def test_obb_rejects_too_few_points(self):
        with pytest.raises(GeometryError, match="至少需 3 个点"):
            oriented_bounding_box([[0, 0, 0], [1, 1, 1]])

    def test_obb_rejects_coincident_points(self):
        with pytest.raises(GeometryError, match="退化为单点"):
            oriented_bounding_box([[1, 1, 1]] * 5)

    def test_empty_points_raise(self):
        with pytest.raises(GeometryError, match="为空"):
            centroid(np.zeros((0, 3)))


# --------------------------------------------------------------- Checker

class TestMinimumDistanceChecker:
    evidence = {
        "observer_position": [5.0, 0.0, 0.0],
        "polylines": {
            "<wire_004>": [[0, 3, 0], [10, 3, 0]],
            "<wire_007>": [[0, 9, 0], [10, 9, 0]],
        },
    }

    def test_correct_answer_passes(self):
        r = check_minimum_distance_answer(
            {"object_id": "<wire_004>", "distance_m": 3.02}, self.evidence)
        assert r.passed
        assert r.metrics["true_distance_m"] == pytest.approx(3.0)

    def test_distance_beyond_tolerance_fails(self):
        r = check_minimum_distance_answer(
            {"object_id": "<wire_004>", "distance_m": 3.5}, self.evidence)
        assert not r.passed
        assert ErrorCode.CHECKER_DISAGREEMENT in r.error_codes

    def test_right_distance_wrong_entity_fails(self):
        """指错实体不因数值接近而通过。"""
        r = check_minimum_distance_answer(
            {"object_id": "<wire_007>", "distance_m": 3.0}, self.evidence)
        assert not r.passed

    def test_checker_recomputes_and_ignores_stored_target(self):
        """checker 独立重算，不采信样本里存的 target。"""
        r = check_minimum_distance_answer(
            {"object_id": "<wire_004>", "distance_m": 3.0}, self.evidence)
        assert r.recomputed_target["distance_m"] == pytest.approx(3.0)

    def test_near_tie_is_flagged_non_unique(self):
        evidence = {
            "observer_position": [5.0, 0.0, 0.0],
            "polylines": {
                "<wire_004>": [[0, 3.00, 0], [10, 3.00, 0]],
                "<wire_007>": [[0, 3.05, 0], [10, 3.05, 0]],
            },
        }
        r = check_minimum_distance_answer(
            {"object_id": "<wire_004>", "distance_m": 3.0}, evidence)
        assert not r.passed
        assert ErrorCode.NON_UNIQUE_ANSWER in r.error_codes

    def test_missing_evidence_raises_not_fails(self):
        """evidence 缺字段是上游损坏，应抛错而非判为答错。"""
        with pytest.raises(CheckerError, match="缺少必需字段"):
            check_minimum_distance_answer({"object_id": "x"}, {})

    def test_non_numeric_distance_is_unit_error(self):
        r = check_minimum_distance_answer(
            {"object_id": "<wire_004>", "distance_m": "三米"}, self.evidence)
        assert not r.passed
        assert ErrorCode.INVALID_UNIT in r.error_codes


class TestGroundingChecker:
    evidence = {
        "target_object_id": "<obj_003>",
        "candidate_ids": ["<obj_001>", "<obj_003>", "<obj_007>"],
    }

    def test_correct_id_passes(self):
        assert check_object_grounding_answer({"object_id": "<obj_003>"},
                                             self.evidence).passed

    def test_wrong_id_fails(self):
        assert not check_object_grounding_answer({"object_id": "<obj_001>"},
                                                 self.evidence).passed

    def test_hallucinated_id_is_distinct_error(self):
        """编造实体比答错更严重，错误码必须区分。"""
        r = check_object_grounding_answer({"object_id": "<obj_999>"}, self.evidence)
        assert not r.passed
        assert ErrorCode.NONEXISTENT_ENTITY_REFERENCE in r.error_codes

    def test_ambiguous_case_requires_ambiguous_answer(self):
        evidence = dict(self.evidence, ambiguous_ids=["<obj_003>", "<obj_007>"])
        assert check_object_grounding_answer({"ambiguous": True}, evidence).passed
        bad = check_object_grounding_answer({"object_id": "<obj_003>"}, evidence)
        assert not bad.passed
        assert ErrorCode.AMBIGUITY_UNMARKED in bad.error_codes

    def test_unnecessary_ambiguity_claim_fails(self):
        assert not check_object_grounding_answer({"ambiguous": True},
                                                 self.evidence).passed

    def test_self_inconsistent_evidence_raises(self):
        with pytest.raises(CheckerError, match="自相矛盾"):
            check_object_grounding_answer(
                {"object_id": "<obj_001>"},
                {"target_object_id": "<obj_099>", "candidate_ids": ["<obj_001>"]})


class TestDirectionChecker:
    evidence = {
        "target_position": [5.0, -5.0, 0.0],
        "observer_position": [0.0, 0.0, 0.0],
        "observer_forward": [1.0, 0.0, 0.0],
    }

    def test_correct_direction_passes(self):
        r = check_observer_relative_direction_answer(
            {"longitudinal": "front", "lateral": "right"}, self.evidence)
        assert r.passed

    def test_wrong_lateral_fails(self):
        r = check_observer_relative_direction_answer(
            {"longitudinal": "front", "lateral": "left"}, self.evidence)
        assert not r.passed

    def test_deadzone_sample_is_rejected_as_non_unique(self):
        evidence = dict(self.evidence, target_position=[100.0, 1.0, 0.0])
        r = check_observer_relative_direction_answer(
            {"longitudinal": "front", "lateral": "right"}, evidence)
        assert not r.passed
        assert ErrorCode.NON_UNIQUE_ANSWER in r.error_codes


class TestCrossViewChecker:
    def test_correct_passes(self):
        assert check_cross_view_correspondence_answer(
            {"same_entity": True}, {"same_entity": True}).passed

    def test_wrong_fails(self):
        assert not check_cross_view_correspondence_answer(
            {"same_entity": False}, {"same_entity": True}).passed

    def test_missing_field_is_schema_error(self):
        r = check_cross_view_correspondence_answer({}, {"same_entity": True})
        assert ErrorCode.SCHEMA_UNREPAIRABLE in r.error_codes

    def test_out_of_range_confidence_is_schema_error(self):
        r = check_cross_view_correspondence_answer(
            {"same_entity": True, "confidence": 1.5}, {"same_entity": True})
        assert not r.passed
        assert ErrorCode.SCHEMA_UNREPAIRABLE in r.error_codes


class TestRegistry:
    def test_all_checkers_registered(self):
        from checkers import CHECKER_REGISTRY
        assert len(CHECKER_REGISTRY) == 4
        for name in CHECKER_REGISTRY:
            assert get_checker(name) is CHECKER_REGISTRY[name]

    def test_unknown_checker_raises_not_silently_skips(self):
        """未注册的 checker 必须报错 —— 静默跳过等于没有校验。"""
        with pytest.raises(CheckerError, match="未注册"):
            get_checker("check_nothing")
