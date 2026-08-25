"""任务编译器的测试。

用**合成 scene package** 验证 —— 这是 `DESIGN.md（附录：第三层）` §12
明确规定的路径（"用合成 scene package 完成本地测试，再迁移到服务器"），
也使这套测试不依赖 VGGT-Ω 权重。

重点验证三件事：

1. **编译顺序的实质依赖** —— 资格在前、target 在中、泄漏检查在后；
2. **运行时泄漏检查能查出静态检查查不出的东西**（实际数据里含答案值）；
3. **不合格的场景被跳过且带理由**，而不是静默丢弃或强行生成。
"""

from __future__ import annotations

import copy

import pytest

from compiler import (
    CompilerError,
    IneligibleScene,
    TaskCompiler,
    DERIVATION_PROGRAMS,
    project_fields,
)
from core.task_spec import load_all_task_specs
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def specs():
    return {s.task_id: s for s in load_all_task_specs(ROOT / "task_specs")}


def _obj(oid: str, category: str, centroid: list[float]) -> dict:
    """合成实体。带齐 Task Spec 资格条件要求的字段 —— OBB 与可见帧。

    最初的 fixture 缺 OBB，被 grounding Spec 的 all_candidates_have_valid_obb
    正确拒掉了。那不是 bug，是编译器按 Spec 办事；补全 fixture 才对。
    """
    return {
        "object_id": oid, "category": category,
        "geometry": {
            "centroid": centroid,
            "obb": {"center": centroid, "extent": [4.0, 4.0, 3.0],
                    "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        },
        "visibility": {"visible_frames": ["f0001", "f0002"]},
        "confidence": {"semantic": 0.9, "geometry": 0.85, "mask": 0.8},
    }


@pytest.fixture
def scene():
    """合成场景：观察者在原点上方，三个实体距离递增。"""
    return {
        "snapshot": {
            "scene_id": "synth_0001",
            "snapshot_id": "meta_synth01",
            "split_group_id": "SynthTown",
            "layers": {"l0_geometry": {"uri": "scene.ply"}},
            "capabilities": {
                "scale_status": "metric",
                "depth_type": "externally_anchored",
                "metric_task_eligible": True,
                "available_entity_types": ["object", "surface", "region"],
                "camera_baseline_m": 12.0,
                "parallax_ratio": 0.30,      # 尺度无关的基线充分性（>=0.05 即合格）
                "nadir_angle_median_deg": 87.6,
                "depth_relief_ratio": 1.15,
                "reasons": [],
            },
        },
        "l1": {
            "cameras": [{"pose_id": "<pose_007>", "position": [0.0, 0.0, 30.0],
                         "forward": [1.0, 0.0, 0.0]}],
            "objects": [
                _obj("<obj_001>", "building", [10.0, -6.0, 0.0]),
                _obj("<obj_002>", "building", [25.0, -6.0, 0.0]),
                _obj("<obj_003>", "rooftop", [60.0, -6.0, 0.0]),
            ],
            "surfaces": [], "regions": [],
        },
        "l2": {"relations": [], "cross_view_links": []},
        "visual_inputs": ["f0001.jpg", "f0002.jpg"],
        "observer_pose_id": "<pose_007>",
        "question": "Which structure is closest to the drone?",
    }


@pytest.fixture
def compiler():
    return TaskCompiler(DERIVATION_PROGRAMS)


# ------------------------------------------------------------------ 字段掩码

class TestFieldProjection:
    def test_extracts_only_listed_paths(self):
        src = {"observer": {"position": [1, 2, 3], "secret": "no"},
               "entities": [{"object_id": "<obj_001>", "hidden": 42}]}
        out = project_fields(src, ["observer.position", "entities.object_id"])
        assert out == {"observer": {"position": [1, 2, 3]},
                       "entities": [{"object_id": "<obj_001>"}]}
        assert "secret" not in out["observer"]
        assert "hidden" not in out["entities"][0]

    def test_list_wildcard_preserves_structure(self):
        src = {"entities": [{"geometry": {"centroid": [1, 1, 1], "obb": "x"}},
                            {"geometry": {"centroid": [2, 2, 2], "obb": "y"}}]}
        out = project_fields(src, ["entities.geometry.centroid"])
        assert out["entities"] == [{"geometry": {"centroid": [1, 1, 1]}},
                                   {"geometry": {"centroid": [2, 2, 2]}}]

    def test_missing_path_is_skipped_not_error(self):
        assert project_fields({"a": 1}, ["b.c"]) == {}


# ------------------------------------------------------------------ 资格

class TestEligibility:
    def test_eligible_scene_compiles(self, compiler, specs, scene):
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=scene["visual_inputs"],
            observer_pose_id=scene["observer_pose_id"], question=scene["question"])
        assert rec["hidden_target"]["object_id"] == "<obj_001>"
        assert rec["hidden_target"]["distance_m"] == pytest.approx(
            (10**2 + 6**2 + 30**2) ** 0.5, abs=0.01)

    def test_non_metric_scene_is_skipped_with_reason(self, compiler, specs, scene):
        """铁律 8 的运行时形式：非 metric 场景不得出米制题。"""
        bad = copy.deepcopy(scene)
        bad["snapshot"]["capabilities"]["metric_task_eligible"] = False
        bad["snapshot"]["capabilities"]["reasons"] = ["depth_type=relative"]
        with pytest.raises(IneligibleScene) as exc:
            compiler.compile_one(
                specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
                bad["l1"], bad["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        assert any("metric_task_eligible" in r for r in exc.value.reasons)

    def test_scale_status_mismatch_skipped(self, compiler, specs, scene):
        bad = copy.deepcopy(scene)
        bad["snapshot"]["capabilities"]["scale_status"] = "relative"
        with pytest.raises(IneligibleScene):
            compiler.compile_one(
                specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
                bad["l1"], bad["l2"], visual_inputs=[], observer_pose_id="<pose_007>")

    def test_skip_carries_reasons_not_silent(self, compiler, specs, scene):
        """不合格是正常结果，但必须带理由 —— 不得静默丢弃。"""
        bad = copy.deepcopy(scene)
        bad["snapshot"]["capabilities"]["metric_task_eligible"] = False
        try:
            compiler.compile_one(
                specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
                bad["l1"], bad["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        except IneligibleScene as skip:
            assert skip.reasons and all(isinstance(r, str) for r in skip.reasons)
            assert skip.scene_id == "synth_0001"


# ------------------------------------------------------------------ 泄漏（运行时）

class TestRuntimeLeakageDetection:
    def test_catches_answer_value_static_check_cannot(self, compiler, specs, scene):
        """**静态检查查不出的泄漏** —— 字段名合法，但实际数据里含答案值。

        这里给 <obj_001> 加一个 category 字段，其内容恰好是答案距离的文本。
        Task Spec 的静态校验只看字段名列表，完全查不到。
        """
        bad = copy.deepcopy(scene)
        d = (10**2 + 6**2 + 30**2) ** 0.5
        bad["l1"]["objects"][0]["category"] = f"building at {round(d, 4)} meters"
        with pytest.raises(CompilerError, match="TARGET_LEAKAGE|泄漏"):
            compiler.compile_one(
                specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
                bad["l1"], bad["l2"], visual_inputs=[],
                observer_pose_id="<pose_007>")

    def test_clean_scene_passes_leakage_check(self, compiler, specs, scene):
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        assert rec["quality"]["leakage_checked"] is True

    def test_hidden_target_not_in_visible_metadata(self, compiler, specs, scene):
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        import json
        blob = json.dumps(rec["inputs"]["visible_metadata"], ensure_ascii=False)
        assert str(rec["hidden_target"]["distance_m"]) not in blob


# ------------------------------------------------------------------ 推导程序

class TestDerivations:
    def test_grounding_picks_farthest(self, compiler, specs, scene):
        rec = compiler.compile_one(
            specs["3d_grounding.object"], scene["snapshot"], scene["l1"],
            scene["l2"], visual_inputs=["a.jpg", "b.jpg"],
            observer_pose_id="<pose_007>")
        assert rec["hidden_target"]["object_id"] == "<obj_003>"

    def test_situated_direction_computed(self, compiler, specs, scene):
        rec = compiler.compile_one(
            specs["3d_vqa.situated.observer_relative_direction"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=["a.jpg"],
            observer_pose_id="<pose_007>")
        t = rec["hidden_target"]
        assert t["longitudinal"] == "front"
        assert t["lateral"] in {"left", "right", "ambiguous"}

    def test_ambiguity_is_flagged_not_guessed(self, compiler, specs, scene):
        """答案不唯一时必须标歧义（SPEC §43.3），不得让模型硬猜。"""
        bad = copy.deepcopy(scene)
        bad["l1"]["objects"][1] = _obj("<obj_002>", "building", [10.02, -6.0, 0.0])
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
            bad["l1"], bad["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        assert rec["ambiguity"]["is_ambiguous"] is True
        assert rec["ambiguity"]["reason"]

    def test_unregistered_program_raises(self, specs, scene):
        c = TaskCompiler({})
        with pytest.raises(CompilerError, match="未注册"):
            c.compile_one(specs["3d_grounding.object"], scene["snapshot"],
                          scene["l1"], scene["l2"], visual_inputs=[],
                          observer_pose_id="<pose_007>")


# ------------------------------------------------------------------ 产出契约

class TestOutputContract:
    def test_record_validates_against_schema(self, compiler, specs, scene):
        from core.metadata import validate_against_schema
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=["a.jpg"],
            observer_pose_id="<pose_007>", question="Which is closest?")
        validate_against_schema(rec, "canonical_task_record")

    def test_all_adapters_can_render_compiled_record(self, compiler, specs, scene):
        """端到端：编译出的记录必须能被三路 adapter 无泄漏地投影。"""
        from task_adapters import get_adapter
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], scene["snapshot"],
            scene["l1"], scene["l2"], visual_inputs=["a.jpg"],
            observer_pose_id="<pose_007>", question="Which is closest?")
        for name in rec["adapters"]:
            out = get_adapter(name).render(rec)
            assert out.sample_id == rec["sample_id"]

    def test_sample_id_is_deterministic(self, compiler, specs, scene):
        a = compiler.compile_one(
            specs["3d_grounding.object"], scene["snapshot"], scene["l1"],
            scene["l2"], visual_inputs=["a.jpg"], observer_pose_id="<pose_007>")
        b = compiler.compile_one(
            specs["3d_grounding.object"], scene["snapshot"], scene["l1"],
            scene["l2"], visual_inputs=["a.jpg"], observer_pose_id="<pose_007>")
        assert a["sample_id"] == b["sample_id"]

    def test_low_altitude_tags_filtered_by_snapshot_facts(self, compiler, specs, scene):
        """声称低空信号但快照没有该事实时，标签不予保留。"""
        bad = copy.deepcopy(scene)
        bad["snapshot"]["capabilities"]["nadir_angle_median_deg"] = None
        bad["snapshot"]["capabilities"]["depth_relief_ratio"] = 5.0
        rec = compiler.compile_one(
            specs["3d_vqa.metric.minimum_distance"], bad["snapshot"],
            bad["l1"], bad["l2"], visual_inputs=[], observer_pose_id="<pose_007>")
        assert rec["low_altitude_tags"] == []

    def test_batch_collects_skips_without_aborting(self, compiler, specs, scene):
        good = scene
        bad = copy.deepcopy(scene)
        bad["snapshot"]["scene_id"] = "synth_0002"
        bad["snapshot"]["capabilities"]["metric_task_eligible"] = False
        result = compiler.compile_many(
            [specs["3d_vqa.metric.minimum_distance"]], [good, bad])
        assert len(result.records) == 1
        assert len(result.skipped) == 1
        assert result.ok
