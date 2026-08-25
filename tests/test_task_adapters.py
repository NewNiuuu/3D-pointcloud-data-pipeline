"""Canonical Task Record 与三类 adapter 的测试。

重点验证两件事：

1. **格式与 3D-GRPO 实际读取的字段对齐** —— 依据是读 `grpo/dataset.py` 的
   实测，不是猜测；
2. **泄漏防护不可绕过** —— 用故意构造的泄漏样本验证每一路 adapter 都会被拦下。
"""

from __future__ import annotations

import copy

import pytest

jsonschema = pytest.importorskip("jsonschema")

from core.errors import ErrorCode  # noqa: E402
from core.metadata import validate_against_schema  # noqa: E402
from task_adapters import (  # noqa: E402
    ADAPTER_REGISTRY,
    AdapterError,
    LeakageError,
    Multimodal3DAdapter,
    PointcloudNativeAdapter,
    Qwen2DMetadataAdapter,
    get_adapter,
    scan_for_leakage,
)


@pytest.fixture
def record():
    return {
        "schema_version": "0.1.0",
        "sample_id": "task_sample_0001",
        "task_spec_id": "3d_vqa.metric.minimum_distance@0.1.0",
        "scene_id": "uavscenes_AMtown01_0000",
        "metadata_snapshot_id": "meta_3f1a9c2b",
        "split_group_id": "AMtown",
        "capability_tags": ["metric_geometry"],
        "low_altitude_tags": ["nadir_view", "weak_depth_cue"],
        "supervision_level": "deterministic_derived",
        "inputs": {
            "pointcloud_ref": "scene.ply",
            "visual_inputs": ["f0012.jpg", "f0015.jpg"],
            "camera_refs": ["<pose_007>"],
            "observer_pose_id": "<pose_007>",
            "visible_metadata": {
                "observer": {"position": [0.0, 0.0, 30.0]},
                "entities": [{"object_id": "<obj_001>", "category": "building"}],
            },
            "visible_metadata_fields": ["observer.position", "entities.object_id"],
            "question": "Which structure is closest to the UAV?",
        },
        "hidden_target": {"target_type": "minimum_distance",
                          "object_id": "<obj_042>", "distance_m": 18.37},
        "target_geometry": {"anchor_kind": "object_obb", "entity_ids": ["<obj_042>"]},
        "evidence": {"used_entities": ["<obj_042>"],
                     "used_fields": ["observer.position"],
                     "derivation_program": "point_to_polyline_distance"},
        "checker": {"name": "check_minimum_distance_answer",
                    "version": "0.1.0", "tolerance_m": 0.1},
        "adapters": ["qwen_2d_metadata", "pointcloud_native", "multimodal_3d"],
        "provenance": {"created_at": "2026-08-25T00:00:00Z",
                       "code_version": "0.1.0", "task_spec_version": "0.1.0"},
    }


@pytest.fixture
def mcq_record(record):
    r = copy.deepcopy(record)
    r["task_spec_id"] = "3d_grounding.object@0.1.0"
    r["inputs"]["question"] = "Which structure is the referred one?"
    r["inputs"]["choices"] = [
        {"key": "A", "text": "the northern rooftop"},
        {"key": "B", "text": "the southern rooftop"},
        {"key": "C", "text": "the central courtyard"},
    ]
    r["hidden_target"] = {"target_type": "grounding", "answer": "the southern rooftop"}
    r["evidence"]["used_entities"] = []
    return r


class TestSchema:
    def test_valid_record_passes(self, record):
        validate_against_schema(record, "canonical_task_record")

    def test_task_spec_id_must_carry_version(self, record):
        bad = copy.deepcopy(record); bad["task_spec_id"] = "3d_vqa.metric.minimum_distance"
        with pytest.raises(Exception):
            validate_against_schema(bad, "canonical_task_record")

    def test_target_geometry_required(self, record):
        """SPEC §41：只有字符串 ID 不算锚点，点云模型无从消费。"""
        bad = copy.deepcopy(record); del bad["target_geometry"]
        with pytest.raises(Exception):
            validate_against_schema(bad, "canonical_task_record")

    def test_checker_required(self, record):
        bad = copy.deepcopy(record); del bad["checker"]
        with pytest.raises(Exception):
            validate_against_schema(bad, "canonical_task_record")

    def test_removed_capability_tags_rejected(self, record):
        """2026-08-25 移除的能力标签不得再出现。"""
        for tag in ("thin_structure", "occupancy_navigation", "flight_safety", "active_perception"):
            bad = copy.deepcopy(record); bad["capability_tags"] = [tag]
            with pytest.raises(Exception):
                validate_against_schema(bad, "canonical_task_record")

    def test_removed_anchor_kinds_rejected(self, record):
        for kind in ("centerline", "trajectory", "route"):
            bad = copy.deepcopy(record); bad["target_geometry"]["anchor_kind"] = kind
            with pytest.raises(Exception):
                validate_against_schema(bad, "canonical_task_record")


class TestPointcloudNativeShareGPT:
    """产出须为规范 ShareGPT 格式；字段对齐依据是实测 3D-GRPO/grpo/dataset.py。"""

    def test_is_sharegpt_conformant(self, record):
        """ShareGPT：conversations 列表，每轮有 from / value 两个键。"""
        out = PointcloudNativeAdapter().render(record)
        convs = out.payload["conversations"]
        assert [c["from"] for c in convs] == ["human", "gpt"]
        for c in convs:
            assert set(c) == {"from", "value"}
            assert isinstance(c["value"], str) and c["value"]
        assert out.verification["sharegpt_conformant"] is True

    def test_emits_pointcloud_field(self, record):
        p = PointcloudNativeAdapter().render(record).payload
        assert isinstance(p["point_clouds"], list)

    def test_point_cloud_placeholder_present(self, record):
        """dataset.py 会把 <point_cloud> 替换成 point-token 三连。"""
        out = PointcloudNativeAdapter().render(record)
        assert "<point_cloud>" in out.payload["conversations"][0]["value"]

    def test_only_first_pointcloud_is_read_so_emit_one(self, record):
        out = PointcloudNativeAdapter().render(record)
        assert len(out.payload["point_clouds"]) == 1

    def test_freeform_carries_deterministic_judging_info(self, record):
        """自由作答须带足判分信息，供训练侧按数据类型实现 reward。"""
        out = PointcloudNativeAdapter().render(record)
        assert out.verification["answer_mode"] == "free_form"
        assert out.verification["mcq_renderable"] is False
        assert out.verification["sharegpt_conformant"] is True
        assert "reward_note" in out.verification

    def test_mcq_is_compatible_with_current_reward(self, mcq_record):
        out = PointcloudNativeAdapter().render(mcq_record)
        assert out.verification["answer_mode"] == "multiple_choice"
        assert out.verification["mcq_renderable"] is True
        assert out.payload["conversations"][1]["value"] == "B"

    def test_mcq_without_matching_target_is_rejected(self, mcq_record):
        """选项里没有正确答案 = 无解题，必须拒绝而非静默产出。"""
        bad = copy.deepcopy(mcq_record)
        bad["hidden_target"]["answer"] = "something not in the choices"
        with pytest.raises(AdapterError, match="无解题"):
            PointcloudNativeAdapter().render(bad)

    def test_missing_pointcloud_rejected(self, record):
        bad = copy.deepcopy(record); bad["inputs"]["pointcloud_ref"] = None
        with pytest.raises(AdapterError, match="pointcloud_ref"):
            PointcloudNativeAdapter().render(bad)


class TestQwenAdapterRespectsIronRule3:
    def test_pointcloud_is_withheld(self, record):
        """铁律 3：Qwen 不读点云 —— 即使记录里有也必须丢弃。"""
        out = Qwen2DMetadataAdapter().render(record)
        assert "pointcloud_ref" not in out.payload
        assert out.verification["pointcloud_withheld"] is True

    def test_requires_visual_inputs(self, record):
        bad = copy.deepcopy(record); bad["inputs"]["visual_inputs"] = []
        with pytest.raises(AdapterError, match="visual_inputs"):
            Qwen2DMetadataAdapter().render(bad)

    def test_carries_metadata_context(self, record):
        out = Qwen2DMetadataAdapter().render(record)
        assert out.payload["metadata_context"]["observer"]["position"] == [0.0, 0.0, 30.0]


class TestLeakageGuardCannotBeBypassed:
    """泄漏防护是基类强制的，三路 adapter 都绕不过。"""

    @pytest.mark.parametrize("adapter_name", ["pointcloud_native", "qwen_2d_metadata", "multimodal_3d"])
    def test_answer_id_in_question_is_caught(self, record, adapter_name):
        bad = copy.deepcopy(record)
        bad["inputs"]["question"] = "Is <obj_042> the closest structure?"
        with pytest.raises(LeakageError) as exc:
            get_adapter(adapter_name).render(bad)
        assert exc.value.code is ErrorCode.TARGET_LEAKAGE

    @pytest.mark.parametrize("adapter_name", ["qwen_2d_metadata", "multimodal_3d"])
    def test_answer_value_in_metadata_is_caught(self, record, adapter_name):
        bad = copy.deepcopy(record)
        bad["inputs"]["visible_metadata"]["derived"] = {"minimum_distance": 18.37}
        with pytest.raises(LeakageError):
            get_adapter(adapter_name).render(bad)

    @pytest.mark.parametrize("adapter_name", ["qwen_2d_metadata", "multimodal_3d"])
    def test_target_entity_in_metadata_is_caught(self, record, adapter_name):
        bad = copy.deepcopy(record)
        bad["inputs"]["visible_metadata"]["entities"].append({"object_id": "<obj_042>"})
        with pytest.raises(LeakageError):
            get_adapter(adapter_name).render(bad)

    def test_clean_record_passes_all_adapters(self, record):
        for name in record["adapters"]:
            get_adapter(name).render(record)

    def test_verification_is_separated_from_payload(self, record):
        """判分信息与模型可见载荷分开存放，下游不可能顺手喂给模型。"""
        out = Multimodal3DAdapter().render(record)
        assert out.verification["hidden_target"]["distance_m"] == 18.37
        assert scan_for_leakage(out.payload, record["hidden_target"], record["evidence"]) == []

    def test_short_strings_do_not_false_positive(self):
        """'left' 这类短串本就可能合法出现，不应误判为泄漏。"""
        assert scan_for_leakage({"question": "Is it on the left?"},
                                {"lateral": "left"}) == []


class TestRegistry:
    def test_all_three_registered(self):
        assert set(ADAPTER_REGISTRY) == {
            "qwen_2d_metadata", "pointcloud_native", "multimodal_3d"}

    def test_unknown_adapter_raises(self):
        with pytest.raises(AdapterError, match="未注册"):
            get_adapter("telepathy")

    def test_undeclared_adapter_refuses(self, record):
        bad = copy.deepcopy(record); bad["adapters"] = ["qwen_2d_metadata"]
        with pytest.raises(AdapterError, match="未声明支持"):
            PointcloudNativeAdapter().render(bad)


class TestMcqQuestionStillScanned:
    """MCQ 的选项必然含答案（故豁免），但**问题文本**不得指明哪个对。"""

    def test_question_revealing_answer_is_caught(self, mcq_record):
        import copy
        bad = copy.deepcopy(mcq_record)
        bad["inputs"]["question"] = "Is it the southern rooftop, which is the answer?"
        with pytest.raises(LeakageError, match="问题文本泄漏"):
            PointcloudNativeAdapter().render(bad)

    def test_clean_mcq_question_passes(self, mcq_record):
        out = PointcloudNativeAdapter().render(mcq_record)
        assert out.payload["conversations"][1]["value"] == "B"
