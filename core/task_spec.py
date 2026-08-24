"""Task Spec 加载与校验。

契约来源：CLAUDE_CODE_PROJECT_SPEC.md §24（Declarative Task Spec）、
§43（Task Design Invariants）、铁律 5/6/8。

Task Spec 是一道题的"配方"。本模块负责在**编译任何样本之前**就把不合规的
Spec 挡下来 —— 这些检查是 G3 门禁的静态部分：

1. **目标泄漏**（铁律 6 / ``TARGET_LEAKAGE``）：``hidden_target_fields`` 与
   ``leakage_rules.forbidden_input_fields`` 中的字段，**不得**出现在
   ``metadata_input_fields`` 里。这是可静态判定的，不必等到运行时。
2. **checker 存在**（``MISSING_CHECKER``）：``checker`` 必须已注册。
   引用一个不存在的 checker 等于这道题没人判分。
3. **尺度资格**（铁律 8 / ``METRIC_TASK_ON_NONMETRIC_SCENE``）：声明了米制
   数值容差的任务，必须同时要求 ``scale_status: metric``。
4. **3D 必要性与低空特性必须显式论证**（SPEC §43.1/§43.2）：不能只打标签，
   要写清理由；空理由视为未论证。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

from checkers import CHECKER_REGISTRY

__all__ = ["TaskSpec", "TaskSpecError", "load_task_spec", "load_all_task_specs"]

_REQUIRED_TOP_LEVEL = (
    "task_id", "version", "task_family", "generation_mode",
    "three_d_necessity", "required_scene_capabilities", "visual_input_policy",
    "metadata_input_fields", "hidden_target_fields", "derivation_program",
    "checker", "output_schema", "leakage_rules", "eligibility",
    "quality_requirements", "supervision_level", "target_anchor",
)

_GENERATION_MODES = {"program_first", "hybrid", "model_first_constrained"}

_SUPERVISION_LEVELS = {
    "strong", "deterministic_derived", "filtered_pseudo", "weak",
    "language_generated",
}


class TaskSpecError(ValueError):
    """Task Spec 不合规。"""


@dataclass(frozen=True)
class TaskSpec:
    """已通过静态校验的 Task Spec。"""

    raw: dict[str, Any]
    path: Path

    @property
    def task_id(self) -> str:
        return self.raw["task_id"]

    @property
    def version(self) -> str:
        return self.raw["version"]

    @property
    def qualified_id(self) -> str:
        return f"{self.task_id}@{self.version}"

    @property
    def checker(self) -> str:
        return self.raw["checker"]

    @property
    def visible_fields(self) -> list[str]:
        return list(self.raw["metadata_input_fields"])

    @property
    def hidden_fields(self) -> list[str]:
        return list(self.raw["hidden_target_fields"])

    @property
    def requires_metric(self) -> bool:
        caps = self.raw["required_scene_capabilities"]
        return caps.get("scale_status") == "metric"

    @property
    def numeric_tolerance_m(self) -> float | None:
        return self.raw["quality_requirements"].get("numeric_tolerance_m")


def _fail(path: Path, message: str) -> None:
    raise TaskSpecError(f"{path.name}: {message}")


def _check_leakage(spec: dict[str, Any], path: Path) -> None:
    """铁律 6：可见输入不得包含隐藏 target 或其等价派生字段。"""
    visible = set(spec["metadata_input_fields"])
    hidden = set(spec["hidden_target_fields"])
    forbidden = set(spec["leakage_rules"].get("forbidden_input_fields") or ())

    overlap = visible & hidden
    if overlap:
        _fail(path, f"目标泄漏：hidden_target_fields 出现在可见输入中 {sorted(overlap)}")

    banned = visible & forbidden
    if banned:
        _fail(path, f"目标泄漏：forbidden_input_fields 出现在可见输入中 {sorted(banned)}")

    # 前缀泄漏：可见字段是隐藏字段的父路径时，等于把整棵子树暴露出去
    for vis in visible:
        for hid in hidden:
            if hid.startswith(vis + "."):
                _fail(path,
                      f"目标泄漏：可见字段 {vis!r} 是隐藏字段 {hid!r} 的父路径，"
                      "会连同隐藏子字段一起暴露")

    if not hidden:
        _fail(path, "hidden_target_fields 为空 —— 没有隐藏目标的任务无从判分")


def _check_scale_discipline(spec: dict[str, Any], path: Path) -> None:
    """铁律 8：绝对米制目标只能出在 metric 场景上。"""
    tolerance = spec["quality_requirements"].get("numeric_tolerance_m")
    scale_status = spec["required_scene_capabilities"].get("scale_status")
    if tolerance is not None and scale_status != "metric":
        _fail(path,
              f"声明了米制容差 {tolerance} 但 required_scene_capabilities."
              f"scale_status={scale_status!r}；绝对米制任务必须要求 metric 场景")


def _check_checker(spec: dict[str, Any], path: Path) -> None:
    name = spec["checker"]
    if name not in CHECKER_REGISTRY:
        _fail(path, f"checker {name!r} 未注册；已注册 {sorted(CHECKER_REGISTRY)}")


def _check_justifications(spec: dict[str, Any], path: Path) -> None:
    """SPEC §43.1/§43.2：3D 必要性与低空特性必须写明理由，不能只打标签。"""
    necessity = spec.get("three_d_necessity") or {}
    if not str(necessity.get("rationale", "")).strip():
        _fail(path, "three_d_necessity.rationale 为空 —— 3D 必要性必须论证")
    if not necessity.get("conditions"):
        _fail(path, "three_d_necessity.conditions 为空 —— 需指明满足 SPEC §43.1 的哪些条件")

    low_alt = spec.get("low_altitude_specificity")
    if low_alt is not None:
        if not str(low_alt.get("rationale", "")).strip():
            _fail(path, "声明了低空特性但 rationale 为空（SPEC §43.2）")
        if not low_alt.get("signals"):
            _fail(path, "声明了低空特性但未列出所用的低空信号（SPEC §43.2）")


def _check_enums_and_paths(spec: dict[str, Any], path: Path, root: Path) -> None:
    if spec["generation_mode"] not in _GENERATION_MODES:
        _fail(path, f"generation_mode 非法：{spec['generation_mode']!r}")
    if spec["supervision_level"] not in _SUPERVISION_LEVELS:
        _fail(path, f"supervision_level 非法：{spec['supervision_level']!r}")

    schema_path = root / spec["output_schema"]
    if not schema_path.exists():
        _fail(path, f"output_schema 不存在：{spec['output_schema']}")

    anchor = spec.get("target_anchor") or {}
    if not anchor.get("kind"):
        _fail(path, "target_anchor.kind 缺失 —— 每个 target 必须映射到具体 3D 锚点"
                    "（SPEC §41）")


def load_task_spec(path: str | Path, root: Path | None = None) -> TaskSpec:
    """加载并校验单个 Task Spec。不合规直接抛错，不返回半成品。"""
    spec_path = Path(path)
    root = Path(root) if root else spec_path.resolve().parents[2]

    try:
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TaskSpecError(f"{spec_path.name}: YAML 解析失败：{exc}") from exc

    if not isinstance(raw, dict):
        _fail(spec_path, "顶层必须是映射")

    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        _fail(spec_path, f"缺少必需字段：{missing}")

    _check_enums_and_paths(raw, spec_path, root)
    _check_checker(raw, spec_path)
    _check_leakage(raw, spec_path)
    _check_scale_discipline(raw, spec_path)
    _check_justifications(raw, spec_path)

    return TaskSpec(raw=raw, path=spec_path)


def load_all_task_specs(task_specs_dir: str | Path) -> list[TaskSpec]:
    """加载目录下全部 Task Spec，并检查 ``task_id@version`` 唯一。"""
    directory = Path(task_specs_dir)
    root = directory.parent
    specs = [load_task_spec(p, root=root)
             for p in sorted(directory.rglob("*.yaml"))]

    seen: dict[str, Path] = {}
    for spec in specs:
        if spec.qualified_id in seen:
            raise TaskSpecError(
                f"task_id 重复：{spec.qualified_id} 同时出现在 "
                f"{seen[spec.qualified_id].name} 与 {spec.path.name}")
        seen[spec.qualified_id] = spec.path
    return specs
