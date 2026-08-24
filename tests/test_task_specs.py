"""Task Spec 校验测试。

除了验证 4 个真实 Spec 合规，还**故意构造违规 Spec** 来证明检查确实会拦下
它们 —— 一个从不失败的校验器等于没有校验。
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from checkers import CHECKER_REGISTRY
from core.task_spec import TaskSpecError, load_all_task_specs, load_task_spec

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "task_specs"


@pytest.fixture(scope="module")
def specs():
    return load_all_task_specs(SPEC_DIR)


class TestRealSpecs:
    def test_all_specs_load(self, specs):
        assert len(specs) == 4, [s.task_id for s in specs]

    def test_covers_the_three_confirmed_task_families(self, specs):
        """2026-08-24 用户确认的首批任务范围。"""
        families = {s.raw["task_family"] for s in specs}
        assert families == {"3d_grounding", "3d_vqa", "cross_view_correspondence"}

    def test_ids_are_unique(self, specs):
        ids = [s.qualified_id for s in specs]
        assert len(set(ids)) == len(ids)

    def test_every_checker_is_registered(self, specs):
        for spec in specs:
            assert spec.checker in CHECKER_REGISTRY

    def test_every_output_schema_exists(self, specs):
        for spec in specs:
            assert (ROOT / spec.raw["output_schema"]).exists()

    def test_no_hidden_field_is_visible(self, specs):
        """铁律 6 的机器可判定形式。"""
        for spec in specs:
            assert not set(spec.visible_fields) & set(spec.hidden_fields), spec.task_id

    def test_metric_specs_require_metric_scenes(self, specs):
        """铁律 8：带米制容差的任务必须要求 metric 场景。"""
        for spec in specs:
            if spec.numeric_tolerance_m is not None:
                assert spec.requires_metric, spec.task_id

    def test_every_target_maps_to_a_3d_anchor(self, specs):
        """SPEC §41：每个 target 必须落到具体 3D 锚点。"""
        for spec in specs:
            anchor = spec.raw["target_anchor"]
            assert anchor["kind"]
            assert anchor["maps_to"], spec.task_id

    def test_pointcloud_native_adapter_is_declared(self, specs):
        """3D-GRPO 是明确消费方，pointcloud_native 不得缺席。"""
        for spec in specs:
            assert "pointcloud_native" in spec.raw["adapters"], spec.task_id

    def test_supervision_is_deterministic_not_language_generated(self, specs):
        """首批全是 program-first，真值由几何程序产生，不能是语言生成。"""
        for spec in specs:
            assert spec.raw["generation_mode"] == "program_first"
            assert spec.raw["supervision_level"] == "deterministic_derived"

    def test_each_spec_justifies_3d_necessity(self, specs):
        for spec in specs:
            necessity = spec.raw["three_d_necessity"]
            assert necessity["rationale"].strip()
            assert necessity["conditions"]

    def test_leakage_rules_ban_the_obvious_shortcut_fields(self, specs):
        """每个 Spec 都必须显式禁掉自己的"答案字段"。"""
        for spec in specs:
            forbidden = set(spec.raw["leakage_rules"]["forbidden_input_fields"])
            assert forbidden, spec.task_id
            # 隐藏字段应当被同时列入禁用清单，形成双重保险
            assert set(spec.hidden_fields) & forbidden, spec.task_id


class TestValidationActuallyBites:
    """故意构造违规 Spec，证明校验器不是摆设。"""

    @pytest.fixture
    def base(self):
        return yaml.safe_load(
            (SPEC_DIR / "vqa" / "metric_minimum_distance_v1.yaml")
            .read_text(encoding="utf-8"))

    def _write(self, tmp_path: Path, spec: dict) -> Path:
        target = tmp_path / "task_specs" / "vqa"
        target.mkdir(parents=True, exist_ok=True)
        path = target / "bad.yaml"
        path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        # schemas 需可解析，做一个符号链接式的复制
        (tmp_path / "schemas" / "answers").mkdir(parents=True, exist_ok=True)
        (tmp_path / "schemas" / "answers" /
         "vqa_metric_distance_answer.schema.json").write_text("{}", encoding="utf-8")
        return path

    def test_rejects_hidden_field_in_visible_inputs(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["metadata_input_fields"].append("derived.minimum_distance")
        with pytest.raises(TaskSpecError, match="目标泄漏"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_forbidden_field_in_visible_inputs(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["metadata_input_fields"].append("entities.distance_to_observer")
        with pytest.raises(TaskSpecError, match="目标泄漏"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_parent_path_leakage(self, base, tmp_path):
        """可见字段是隐藏字段的父路径 —— 等于暴露整棵子树。"""
        spec = copy.deepcopy(base)
        spec["metadata_input_fields"].append("derived")
        with pytest.raises(TaskSpecError, match="父路径"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_metric_tolerance_on_nonmetric_scene(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["required_scene_capabilities"]["scale_status"] = "relative"
        with pytest.raises(TaskSpecError, match="必须要求 metric 场景"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_unregistered_checker(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["checker"] = "check_something_nonexistent"
        with pytest.raises(TaskSpecError, match="未注册"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_empty_hidden_targets(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["hidden_target_fields"] = []
        with pytest.raises(TaskSpecError, match="没有隐藏目标"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_unjustified_3d_necessity(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["three_d_necessity"]["rationale"] = "   "
        with pytest.raises(TaskSpecError, match="3D 必要性必须论证"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_low_altitude_claim_without_signals(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["low_altitude_specificity"]["signals"] = []
        with pytest.raises(TaskSpecError, match="低空信号"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_missing_target_anchor(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["target_anchor"] = {}
        with pytest.raises(TaskSpecError, match="target_anchor.kind"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_missing_required_field(self, base, tmp_path):
        spec = copy.deepcopy(base)
        del spec["derivation_program"]
        with pytest.raises(TaskSpecError, match="缺少必需字段"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_bad_generation_mode(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["generation_mode"] = "vibes"
        with pytest.raises(TaskSpecError, match="generation_mode 非法"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)

    def test_rejects_nonexistent_output_schema(self, base, tmp_path):
        spec = copy.deepcopy(base)
        spec["output_schema"] = "schemas/answers/not_there.schema.json"
        with pytest.raises(TaskSpecError, match="output_schema 不存在"):
            load_task_spec(self._write(tmp_path, spec), root=tmp_path)
