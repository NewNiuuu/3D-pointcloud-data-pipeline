"""L0/L1/L2 Metadata Schema 与跨层校验的测试。

结构分两部分：

1. **合法 fixture 必须通过** —— 保证 schema 不是紧到没法用；
2. **每个不变量都用故意构造的坏数据验证会被拦下** ——
   一个从不失败的校验器等于没有校验。

fixture 刻意做成**最小合法样例**，同时也是 schema 的可执行文档：
新人想知道「一份合法的 L1 长什么样」，读这里比读 schema 快。
"""

from __future__ import annotations

import copy
import json

import pytest

jsonschema = pytest.importorskip("jsonschema")

from core.errors import ErrorCode  # noqa: E402
from core.metadata import (  # noqa: E402
    MetadataError,
    SCHEMA_VERSION,
    derive_metric_eligibility,
    load_schema,
    validate_against_schema,
    validate_snapshot_consistency,
)

SHA = "a" * 64


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def l0():
    return {
        "schema_version": SCHEMA_VERSION,
        "scene_id": "uavscenes_AMtown01_0000",
        "coordinate_frame": "uavscenes_world_metric",
        "unit": "meter",
        "scale": {
            "status": "metric",
            "source": "rtk_gps",
            "depth_type": "externally_anchored",
            "domain_calibrated": False,
            "anchor_provenance_verified": True,
            "camera_baseline_m": 3.7,
            "alignment_residual_m": 0.14,
        },
        "cameras": [{
            "frame_id": "f0001",
            "K": [[1469.5, 0, 1174.0], [0, 1469.5, 1049.9], [0, 0, 1]],
            "T_world_from_camera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "coordinate_convention": "x_right_y_down_z_forward",
            "pose_source": "native",
            "nadir_angle_deg": 87.6,
        }],
        "depth": [{
            "artifact_id": "dep_001",
            "producer": {"name": "VGGT-Omega", "version": "1b_512"},
            "role": "primary",
            "depth_uri": "depth/f0001.npy",
            "confidence_uri": "depth_conf/f0001.npy",
            "depth_type": "relative",
            "frame_ids": ["f0001"],
        }],
        "invalid_geometry": {
            "reason_masks": {
                "water": {"uri": "masks/water.npy",
                          "producer": {"name": "OneFormer", "version": "ade20k"}}
            }
        },
        "provenance": {
            "created_at": "2026-08-25T00:00:00Z",
            "code_version": "0.1.0",
            "source_scene_manifest": "scene_manifest.json",
        },
    }


@pytest.fixture
def l1():
    return {
        "schema_version": SCHEMA_VERSION,
        "scene_id": "uavscenes_AMtown01_0000",
        "objects": [{
            "object_id": "<obj_001>",
            "category": "building",
            "geometry": {"centroid": [10.0, 5.0, 2.0]},
            "visibility": {"visible_frames": ["f0001"]},
            "confidence": {"semantic": 0.9, "geometry": 0.8, "mask": 0.85},
            "provenance": {"source_frames": ["f0001"],
                           "producers": ["grounding_dino_base"],
                           "supervision_level": "filtered_pseudo"},
        }],
        "surfaces": [{
            "surface_id": "<region_001>",
            "surface_type": "ground",
            "plane": {"normal": [0, 0, 1], "offset_m": 0.0, "fit_method": "ransac"},
            "slope_deg": 3.2,
            "roughness_m": 0.08,
            "extent": {"area_m2": 120.0, "largest_inscribed_circle_m": 6.0},
            "quality": {"geometry": 0.92, "semantic": 0.88},
            "provenance": {"source_frames": ["f0001"],
                           "producers": ["plane_fit"],
                           "supervision_level": "deterministic_derived"},
        }],
        "regions": [{
            "region_id": "<region_009>",
            "purpose": "depth_reliability",
            "point_support": {"point_count": 5000},
            "provenance": {"source_frames": ["f0001"],
                           "producers": ["lidar_vision_residual"],
                           "supervision_level": "deterministic_derived"},
        }],
        "provenance": {"created_at": "2026-08-25T00:00:00Z",
                       "code_version": "0.1.0",
                       "l0_geometry_ref": "geometry_manifest.json"},
    }


@pytest.fixture
def l2():
    return {
        "schema_version": SCHEMA_VERSION,
        "scene_id": "uavscenes_AMtown01_0000",
        "relations": [{
            "relation_id": "rel_001",
            "relation_type": "height_difference_m",
            "subject_id": "<obj_001>",
            "object_id": "<region_001>",
            "value": 12.5,
            "unit": "meter",
            "derivation": {"program": "height_difference",
                           "inputs": ["objects.<obj_001>.geometry.centroid",
                                      "surfaces.<region_001>.plane.offset_m"]},
        }],
        "provenance": {"created_at": "2026-08-25T00:00:00Z",
                       "code_version": "0.1.0",
                       "l1_entities_ref": "entities.json"},
    }


@pytest.fixture
def snapshot():
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": "meta_3f1a9c2b",
        "scene_id": "uavscenes_AMtown01_0000",
        "dataset_id": "uavscenes",
        "split_group_id": "AMtown",
        "layers": {
            "l0_geometry":  {"uri": "geometry_manifest.json", "schema_version": SCHEMA_VERSION, "content_sha256": SHA},
            "l1_entities":  {"uri": "entities.json",          "schema_version": SCHEMA_VERSION, "content_sha256": SHA},
            "l2_relations": {"uri": "relations.json",         "schema_version": SCHEMA_VERSION, "content_sha256": SHA},
            "l3_capability": None,
        },
        "capabilities": {
            "scale_status": "metric",
            "depth_type": "externally_anchored",
            "metric_task_eligible": True,
            "available_entity_types": ["object", "surface", "region"],
            "camera_baseline_m": 3.7,
            "parallax_ratio": 0.30,      # 尺度无关的基线充分性（>= 0.05 即合格）
            "nadir_angle_median_deg": 87.6,
            "reasons": [],
        },
        "gate": {"gate_id": "G2", "status": "pass"},
        "provenance": {"created_at": "2026-08-25T00:00:00Z",
                       "code_version": "0.1.0",
                       "schema_versions": {"l0_geometry": SCHEMA_VERSION}},
    }


PROGRAMS = {"height_difference", "point_to_polyline_distance", "observer_relative_direction"}


# ------------------------------------------------------------------ schema 本身

class TestSchemasLoad:
    @pytest.mark.parametrize("name", ["l0_geometry", "l1_entities", "l2_relations", "metadata_snapshot"])
    def test_schema_is_valid_json_schema(self, name):
        s = load_schema(name)
        jsonschema.Draft202012Validator.check_schema(s)

    def test_unknown_schema_raises(self):
        with pytest.raises(MetadataError, match="未知 schema"):
            load_schema("nope")

    @pytest.mark.parametrize("name", ["l0_geometry", "l1_entities", "l2_relations", "metadata_snapshot"])
    def test_additional_properties_forbidden_at_root(self, name):
        """根层禁止未知字段 —— 打错字的字段名必须报错而非被静默忽略。"""
        assert load_schema(name).get("additionalProperties") is False


class TestValidFixturesPass:
    def test_l0(self, l0):
        validate_against_schema(l0, "l0_geometry")

    def test_l1(self, l1):
        validate_against_schema(l1, "l1_entities")

    def test_l2(self, l2):
        validate_against_schema(l2, "l2_relations")

    def test_snapshot(self, snapshot):
        validate_against_schema(snapshot, "metadata_snapshot")

    def test_consistency_clean(self, snapshot, l0, l1, l2):
        assert validate_snapshot_consistency(
            snapshot, l0, l1, l2, known_programs=PROGRAMS) == []


# ------------------------------------------------------------------ schema 层拦截

class TestSchemaRejects:
    def test_rejects_unknown_field(self, l0):
        bad = dict(l0, typoed_field=1)
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l0_geometry")

    def test_rejects_bad_unit(self, l0):
        bad = dict(l0, unit="feet")
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l0_geometry")

    def test_rejects_bad_depth_type(self, l0):
        bad = copy.deepcopy(l0); bad["scale"]["depth_type"] = "sort_of_metric"
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l0_geometry")

    def test_rejects_malformed_entity_id(self, l1):
        bad = copy.deepcopy(l1); bad["objects"][0]["object_id"] = "obj_1"
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l1_entities")

    def test_relation_requires_derivation(self, l2):
        """没有 derivation 就无法验证可重算（§23.4）。"""
        bad = copy.deepcopy(l2); del bad["relations"][0]["derivation"]
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l2_relations")

    def test_derivation_requires_inputs(self, l2):
        bad = copy.deepcopy(l2); bad["relations"][0]["derivation"]["inputs"] = []
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l2_relations")

    def test_snapshot_requires_explicit_l3_key(self, snapshot):
        """l3 缺失必须写显式 null —— 遗漏与『确认没有』是两回事。"""
        bad = copy.deepcopy(snapshot); del bad["layers"]["l3_capability"]
        validate_against_schema(bad, "metadata_snapshot")  # 允许省略
        bad2 = copy.deepcopy(snapshot); bad2["layers"]["l3_capability"] = None
        validate_against_schema(bad2, "metadata_snapshot")  # null 也合法

    def test_snapshot_requires_content_hash(self, snapshot):
        bad = copy.deepcopy(snapshot); del bad["layers"]["l0_geometry"]["content_sha256"]
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "metadata_snapshot")

    def test_surface_requires_plane_and_extent(self, l1):
        bad = copy.deepcopy(l1); del bad["surfaces"][0]["plane"]
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l1_entities")

    def test_slope_range_enforced(self, l1):
        bad = copy.deepcopy(l1); bad["surfaces"][0]["slope_deg"] = 120.0
        with pytest.raises(MetadataError):
            validate_against_schema(bad, "l1_entities")


# ------------------------------------------------------------------ 跨层不变量

class TestCrossLayerInvariants:
    def _codes(self, *args, **kw):
        return {i.code for i in validate_snapshot_consistency(*args, **kw)}

    def test_broken_reference_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l2); bad["relations"][0]["subject_id"] = "<obj_999>"
        assert ErrorCode.BROKEN_ID_REFERENCE in self._codes(
            snapshot, l0, l1, bad, known_programs=PROGRAMS)

    def test_duplicate_entity_id_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l1)
        bad["regions"][0]["region_id"] = "<region_001>"   # 与 surface 撞号
        assert ErrorCode.DUPLICATE_ENTITY_ID in self._codes(
            snapshot, l0, bad, l2, known_programs=PROGRAMS)

    def test_metric_eligibility_must_be_rederivable(self, snapshot, l0, l1, l2):
        """铁律 8/9：不能手工把资格放宽。"""
        bad = copy.deepcopy(l0)
        bad["scale"]["anchor_provenance_verified"] = False   # 资格应变 false
        assert ErrorCode.SCALE_CLAIM_INCONSISTENT in self._codes(
            snapshot, bad, l1, l2, known_programs=PROGRAMS)

    def test_relative_depth_can_never_be_metric_eligible(self, snapshot, l0, l1, l2):
        bad_snap = copy.deepcopy(snapshot)
        bad_snap["capabilities"]["depth_type"] = "relative"
        bad_l0 = copy.deepcopy(l0); bad_l0["scale"]["depth_type"] = "relative"
        assert ErrorCode.SCALE_CLAIM_INCONSISTENT in self._codes(
            bad_snap, bad_l0, l1, l2, known_programs=PROGRAMS)

    def test_unregistered_program_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l2)
        bad["relations"][0]["derivation"]["program"] = "magic_guess"
        assert ErrorCode.DERIVED_FIELD_NOT_RECOMPUTABLE in self._codes(
            snapshot, l0, l1, bad, known_programs=PROGRAMS)

    def test_collapsed_reason_masks_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l0)
        bad["invalid_geometry"] = {"combined_uri": "masks/all_invalid.npy"}
        assert ErrorCode.REASON_MASKS_COLLAPSED in self._codes(
            snapshot, bad, l1, l2, known_programs=PROGRAMS)

    def test_collapsed_confidence_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l1)
        bad["objects"][0]["confidence"] = {"semantic": 0.9}
        assert ErrorCode.CONFIDENCE_COMPONENTS_COLLAPSED in self._codes(
            snapshot, l0, bad, l2, known_programs=PROGRAMS)

    def test_non_vggt_primary_rejected(self, snapshot, l0, l1, l2):
        """铁律 1/4：点云主路径 MUST 是 VGGT-Ω。"""
        bad = copy.deepcopy(l0)
        bad["depth"][0]["producer"]["name"] = "Depth-Anything-3"
        assert ErrorCode.CONFLICTING_SCALE_CLAIM in self._codes(
            snapshot, bad, l1, l2, known_programs=PROGRAMS)

    def test_multiple_primaries_rejected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(l0)
        second = copy.deepcopy(bad["depth"][0]); second["artifact_id"] = "dep_002"
        bad["depth"].append(second)
        assert ErrorCode.CONFLICTING_SCALE_CLAIM in self._codes(
            snapshot, bad, l1, l2, known_programs=PROGRAMS)

    def test_missing_content_hash_detected(self, snapshot, l0, l1, l2):
        bad = copy.deepcopy(snapshot)
        bad["layers"]["l1_entities"]["content_sha256"] = "   "
        assert ErrorCode.MISSING_PROVENANCE in self._codes(
            bad, l0, l1, l2, known_programs=PROGRAMS)


class TestMetricEligibilityRule:
    @pytest.mark.parametrize("dt", ["relative", "affine_invariant", "pseudo"])
    def test_non_metric_never_eligible(self, dt):
        assert not derive_metric_eligibility(
            dt, domain_calibrated=True, anchor_provenance_verified=True)

    def test_metric_needs_domain_calibration(self):
        assert not derive_metric_eligibility(
            "metric", domain_calibrated=False, anchor_provenance_verified=True)
        assert derive_metric_eligibility(
            "metric", domain_calibrated=True, anchor_provenance_verified=False)

    def test_anchored_needs_verified_provenance(self):
        assert not derive_metric_eligibility(
            "externally_anchored", domain_calibrated=True, anchor_provenance_verified=False)
        assert derive_metric_eligibility(
            "externally_anchored", domain_calibrated=False, anchor_provenance_verified=True)
