"""确定性 Checker：把模型输出与隐藏 target 比对判分。

契约来源：CLAUDE_CODE_PROJECT_SPEC.md §19（Task Sample Contract 的 ``checker``
字段）、§23.7（task-sample-auditor）、§43.3（可验证性）。

## 为什么 checker 先于题目存在

一道题如果没有确定性 checker，就无法判断模型答对与否，也就不该被生成
（SPEC §27 G3 硬失败：``MISSING_CHECKER``）。因此实现顺序是
**几何函数 → checker → Task Spec**，而不是先写题再想怎么判。

## 三条纪律

1. **checker 独立重算 target，不信任样本里存的 target**。若样本存的 target
   与重算结果不一致，说明上游几何或样本已损坏 —— 这是硬失败
   （``DERIVED_FIELD_NOT_RECOMPUTABLE`` / ``CHECKER_DISAGREEMENT``），
   不是把答案改成模型说的那个。
2. **容差显式且随 checker 版本冻结**。改容差等于改判分标准，必须提版本。
3. **checker 不做语义宽容**。"差不多对"由人工复核或 LLM judge 处理，
   checker 只给确定性判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from core.errors import ErrorCode
from geometry.primitives import (
    GeometryError,
    minimum_point_to_polyline_distance,
    observer_relative_direction,
)

__all__ = [
    "CheckResult",
    "CheckerError",
    "check_minimum_distance_answer",
    "check_object_grounding_answer",
    "check_observer_relative_direction_answer",
    "check_cross_view_correspondence_answer",
    "CHECKER_REGISTRY",
    "get_checker",
]


class CheckerError(RuntimeError):
    """checker 无法执行（输入缺字段、几何退化等）。

    与"判定不通过"不同：不通过是正常结果，无法执行是上游出了问题。
    """


@dataclass(frozen=True)
class CheckResult:
    """checker 判定结果。"""

    passed: bool
    checker: str
    version: str
    detail: str = ""
    recomputed_target: Any = None
    error_codes: tuple[ErrorCode, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)

    def __bool__(self) -> bool:  # pragma: no cover - 便于 if result: 写法
        return self.passed


def _require(mapping: Mapping[str, Any], key: str, who: str) -> Any:
    if key not in mapping:
        raise CheckerError(f"{who} 缺少必需字段 {key!r}")
    return mapping[key]


# --------------------------------------------------------------- metric VQA

def check_minimum_distance_answer(
    answer: Mapping[str, Any],
    evidence: Mapping[str, Any],
    tolerance_m: float = 0.10,
) -> CheckResult:
    """校验"哪个实体离观察者最近、距离多少"。

    对应 Task Spec ``3d_vqa.metric.minimum_distance``，推导程序
    :func:`geometry.primitives.minimum_point_to_polyline_distance`。

    ``evidence`` 必须含 ``observer_position`` 与 ``polylines``（实体ID -> 折线），
    checker 据此**独立重算** target，不读样本里存的答案。

    判定：实体 ID 必须精确相等；距离必须落在 ``tolerance_m`` 内。
    两者缺一即不通过 —— 距离对但指错实体不算对，反之亦然。
    """
    version = "0.1.0"
    name = "check_minimum_distance_answer"

    observer = np.asarray(_require(evidence, "observer_position", "evidence"),
                          dtype=np.float64)
    polylines = _require(evidence, "polylines", "evidence")
    if not polylines:
        raise CheckerError("evidence.polylines 为空，无法重算 target")

    try:
        true_id, true_distance, segment = minimum_point_to_polyline_distance(
            observer, polylines)
    except GeometryError as exc:
        raise CheckerError(f"几何退化，无法重算 target：{exc}") from exc

    # 歧义检测：次近实体若也落在容差内，该题无唯一答案
    distances = sorted(
        minimum_point_to_polyline_distance(observer, {k: v})[1]
        for k, v in polylines.items()
    )
    if len(distances) > 1 and abs(distances[1] - distances[0]) <= tolerance_m:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail=(f"最近与次近距离相差 {distances[1] - distances[0]:.4f} m，"
                    f"不超过容差 {tolerance_m} m，该题无唯一答案"),
            recomputed_target={"object_id": true_id, "distance_m": true_distance},
            error_codes=(ErrorCode.NON_UNIQUE_ANSWER,),
        )

    answer_id = answer.get("object_id")
    answer_distance = answer.get("distance_m")

    if answer_id != true_id:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail=f"实体 ID 不符：答 {answer_id!r}，真值 {true_id!r}",
            recomputed_target={"object_id": true_id, "distance_m": true_distance},
            error_codes=(ErrorCode.CHECKER_DISAGREEMENT,),
        )

    if answer_distance is None:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail="答案缺少 distance_m",
            recomputed_target={"object_id": true_id, "distance_m": true_distance},
            error_codes=(ErrorCode.INVALID_UNIT,),
        )

    try:
        error = abs(float(answer_distance) - true_distance)
    except (TypeError, ValueError):
        return CheckResult(
            passed=False, checker=name, version=version,
            detail=f"distance_m 非数值：{answer_distance!r}",
            recomputed_target={"object_id": true_id, "distance_m": true_distance},
            error_codes=(ErrorCode.INVALID_UNIT,),
        )

    passed = error <= tolerance_m
    return CheckResult(
        passed=passed, checker=name, version=version,
        detail=("通过" if passed
                else f"距离误差 {error:.4f} m 超过容差 {tolerance_m} m"),
        recomputed_target={"object_id": true_id, "distance_m": true_distance,
                           "segment_index": segment},
        error_codes=() if passed else (ErrorCode.CHECKER_DISAGREEMENT,),
        metrics={"absolute_error_m": error, "true_distance_m": true_distance},
    )


# --------------------------------------------------------------- 3D Grounding

def check_object_grounding_answer(
    answer: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> CheckResult:
    """校验对象级 3D Grounding。

    ``evidence`` 必须含 ``target_object_id`` 与 ``candidate_ids``。

    三条判定：

    1. 答案 ID 必须在候选集内 —— 引用不存在的实体是硬失败
       （``NONEXISTENT_ENTITY_REFERENCE``），比答错更严重，说明模型在编造。
    2. 若 evidence 标注了 ``ambiguous_ids``（多个同等有效答案），模型必须
       返回歧义标记而非硬猜（SPEC §26.1）。
    3. 否则 ID 精确相等才算通过。
    """
    version = "0.1.0"
    name = "check_object_grounding_answer"

    target_id = _require(evidence, "target_object_id", "evidence")
    candidates = list(_require(evidence, "candidate_ids", "evidence"))
    if target_id not in candidates:
        raise CheckerError(
            f"target {target_id!r} 不在候选集内，evidence 自相矛盾")

    ambiguous = set(evidence.get("ambiguous_ids") or ())
    answered_ambiguous = bool(answer.get("ambiguous"))
    answer_id = answer.get("object_id")

    if ambiguous:
        passed = answered_ambiguous
        return CheckResult(
            passed=passed, checker=name, version=version,
            detail=("正确识别为歧义" if passed
                    else f"存在 {len(ambiguous)} 个同等候选，应返回歧义而非单一答案"),
            recomputed_target={"ambiguous_ids": sorted(ambiguous)},
            error_codes=() if passed else (ErrorCode.AMBIGUITY_UNMARKED,),
        )

    if answered_ambiguous:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail="答案唯一，但模型返回了歧义标记",
            recomputed_target={"object_id": target_id},
            error_codes=(ErrorCode.CHECKER_DISAGREEMENT,),
        )

    if answer_id not in candidates:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail=f"引用了候选集外的实体 {answer_id!r}",
            recomputed_target={"object_id": target_id},
            error_codes=(ErrorCode.NONEXISTENT_ENTITY_REFERENCE,),
        )

    passed = answer_id == target_id
    return CheckResult(
        passed=passed, checker=name, version=version,
        detail="通过" if passed else f"答 {answer_id!r}，真值 {target_id!r}",
        recomputed_target={"object_id": target_id},
        error_codes=() if passed else (ErrorCode.CHECKER_DISAGREEMENT,),
    )


# --------------------------------------------------------------- situated VQA

def check_observer_relative_direction_answer(
    answer: Mapping[str, Any],
    evidence: Mapping[str, Any],
    lateral_deadzone_deg: float = 10.0,
) -> CheckResult:
    """校验观察者相对方位（前/后 + 左/右）。

    ``evidence`` 需含 ``target_position``、``observer_position``、
    ``observer_forward``，可选 ``up``。

    落在死区内（正前方 ±``lateral_deadzone_deg``）的样本**判为不合格**而非
    放宽判定：这类样本的左右答案会因位姿微小误差翻转，不具备稳定真值。
    """
    version = "0.1.0"
    name = "check_observer_relative_direction_answer"

    try:
        truth = observer_relative_direction(
            _require(evidence, "target_position", "evidence"),
            _require(evidence, "observer_position", "evidence"),
            _require(evidence, "observer_forward", "evidence"),
            up=evidence.get("up", (0.0, 0.0, 1.0)),
            lateral_deadzone_deg=lateral_deadzone_deg,
        )
    except GeometryError as exc:
        raise CheckerError(f"几何退化，无法重算 target：{exc}") from exc

    if truth["lateral"] == "ambiguous":
        return CheckResult(
            passed=False, checker=name, version=version,
            detail=(f"目标横向角 {truth['lateral_angle_deg']:.2f}° 落在死区 "
                    f"±{lateral_deadzone_deg}° 内，左右无稳定真值，该样本不合格"),
            recomputed_target=truth,
            error_codes=(ErrorCode.NON_UNIQUE_ANSWER,),
        )

    mismatches = [
        f"{axis}: 答 {answer.get(axis)!r} != 真值 {truth[axis]!r}"
        for axis in ("longitudinal", "lateral")
        if answer.get(axis) != truth[axis]
    ]
    passed = not mismatches
    return CheckResult(
        passed=passed, checker=name, version=version,
        detail="通过" if passed else "；".join(mismatches),
        recomputed_target=truth,
        error_codes=() if passed else (ErrorCode.CHECKER_DISAGREEMENT,),
        metrics={"lateral_angle_deg": float(truth["lateral_angle_deg"]),
                 "distance_m": float(truth["distance_m"])},
    )


# --------------------------------------------------------------- Cross-view

def check_cross_view_correspondence_answer(
    answer: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> CheckResult:
    """校验跨视角对应：两个视角中的 2D 实例是否同一 3D 实体。

    ``evidence`` 需含 ``same_entity``（布尔真值）。

    额外要求模型给出的 ``confidence``（若有）落在 ``[0,1]`` —— 越界说明输出
    schema 未被遵守，属 G4 硬失败而非答错。
    """
    version = "0.1.0"
    name = "check_cross_view_correspondence_answer"

    truth = bool(_require(evidence, "same_entity", "evidence"))
    if "same_entity" not in answer:
        return CheckResult(
            passed=False, checker=name, version=version,
            detail="答案缺少 same_entity",
            recomputed_target={"same_entity": truth},
            error_codes=(ErrorCode.SCHEMA_UNREPAIRABLE,),
        )

    confidence = answer.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return CheckResult(
                passed=False, checker=name, version=version,
                detail=f"confidence 非数值：{answer.get('confidence')!r}",
                recomputed_target={"same_entity": truth},
                error_codes=(ErrorCode.SCHEMA_UNREPAIRABLE,),
            )
        if not 0.0 <= confidence <= 1.0:
            return CheckResult(
                passed=False, checker=name, version=version,
                detail=f"confidence {confidence} 越界，应在 [0,1]",
                recomputed_target={"same_entity": truth},
                error_codes=(ErrorCode.SCHEMA_UNREPAIRABLE,),
            )

    passed = bool(answer["same_entity"]) == truth
    return CheckResult(
        passed=passed, checker=name, version=version,
        detail="通过" if passed else f"答 {answer['same_entity']}，真值 {truth}",
        recomputed_target={"same_entity": truth},
        error_codes=() if passed else (ErrorCode.CHECKER_DISAGREEMENT,),
    )


#: Task Spec 的 ``checker`` 字段按名索引到此表。
CHECKER_REGISTRY = {
    "check_minimum_distance_answer": check_minimum_distance_answer,
    "check_object_grounding_answer": check_object_grounding_answer,
    "check_observer_relative_direction_answer":
        check_observer_relative_direction_answer,
    "check_cross_view_correspondence_answer":
        check_cross_view_correspondence_answer,
}


def get_checker(name: str):
    """按名取 checker。未注册的名字必须报错而非静默跳过校验。"""
    if name not in CHECKER_REGISTRY:
        raise CheckerError(
            f"未注册的 checker {name!r}；已注册：{sorted(CHECKER_REGISTRY)}")
    return CHECKER_REGISTRY[name]
