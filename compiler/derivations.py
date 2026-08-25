"""推导程序：从 metadata 确定性地算出隐藏 target。

契约来源：SPEC §20.1（program-first 的编译顺序）、铁律 7（可确定计算的值
必须由程序产生）。

每个程序的签名统一为：

```
(context) -> (hidden_target, evidence_extra, ambiguity)
```

- ``hidden_target``：隐藏答案，**绝不进入可见 metadata**；
- ``evidence_extra``：``used_entities`` 与 ``derivation_inputs``，供审计与重算；
- ``ambiguity``：歧义标记。**答案不唯一时必须标出**（SPEC §43.3），
  不得让模型硬猜 —— 那样产生的题没有稳定真值。

程序**只调用** :mod:`geometry` 中的纯函数，不自己实现几何计算 ——
保证 checker 能用同一套函数独立重算。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from geometry import (
    GeometryError,
    minimum_point_to_polyline_distance,
    observer_relative_direction,
)

__all__ = ["DERIVATION_PROGRAMS", "get_derivation_program"]


def _entity_position(ent: dict[str, Any]) -> list[float] | None:
    geo = ent.get("geometry") or {}
    c = geo.get("centroid")
    return list(c) if c else None


def minimum_distance_program(ctx: dict[str, Any]) -> tuple:
    """``3d_vqa.metric.minimum_distance`` 的推导。

    把每个候选实体的几何折算为可供距离计算的折线：
    有 centerline 用之，否则用质心退化为单点段（两端相同的段会被
    :func:`point_to_polyline_distance` 跳过，故用质心构造一条极短段）。
    """
    l1 = ctx["l1"]
    observer = _observer_position(ctx)
    if observer is None:
        raise GeometryError("缺少观察者位置，无法计算距离")

    polylines: dict[str, Any] = {}
    for ent in l1.get("objects") or []:
        eid = ent.get("object_id")
        geo = ent.get("geometry") or {}
        line = geo.get("centerline")
        if line and len(line) >= 2:
            polylines[eid] = line
        else:
            pos = _entity_position(ent)
            if pos:
                # 质心退化：构造一条 1mm 段，使点-折线距离等于点-点距离
                polylines[eid] = [pos, [pos[0] + 1e-3, pos[1], pos[2]]]
    if len(polylines) < 2:
        raise GeometryError(f"候选实体不足 2 个（实得 {len(polylines)}）")

    entity_id, distance, segment = minimum_point_to_polyline_distance(observer, polylines)

    # 歧义：次近实体落在容差内则答案不唯一
    tolerance = float((ctx["spec"].raw.get("quality_requirements") or {})
                      .get("numeric_tolerance_m", 0.1))
    others = sorted(
        minimum_point_to_polyline_distance(observer, {k: v})[1]
        for k, v in polylines.items())
    ambiguous = len(others) > 1 and abs(others[1] - others[0]) <= tolerance

    return (
        {"target_type": "minimum_distance", "object_id": entity_id,
         "distance_m": round(float(distance), 4), "nearest_segment_index": int(segment)},
        {"used_entities": sorted(polylines),
         "derivation_inputs": {"observer_position": list(observer),
                               "candidate_count": len(polylines)}},
        {"is_ambiguous": bool(ambiguous),
         "reason": "次近实体落在数值容差内" if ambiguous else None},
    )


def observer_relative_direction_program(ctx: dict[str, Any]) -> tuple:
    """``3d_vqa.situated.observer_relative_direction`` 的推导。

    死区内的样本标为歧义 —— 该处左右会因位姿微小误差翻转，没有稳定真值。
    """
    l1 = ctx["l1"]
    observer = _observer_position(ctx)
    forward = _observer_forward(ctx)
    if observer is None or forward is None:
        raise GeometryError("缺少观察者位置或朝向")

    objects = [e for e in (l1.get("objects") or []) if _entity_position(e)]
    if not objects:
        raise GeometryError("没有可用的目标实体")
    target_ent = objects[0]
    deadzone = float((ctx["spec"].raw.get("quality_requirements") or {})
                     .get("lateral_deadzone_deg", 10.0))

    result = observer_relative_direction(
        _entity_position(target_ent), observer, forward,
        lateral_deadzone_deg=deadzone)
    ambiguous = result["lateral"] == "ambiguous"

    return (
        {"target_type": "observer_relative_direction",
         "object_id": target_ent.get("object_id"),
         "longitudinal": result["longitudinal"], "lateral": result["lateral"],
         "lateral_angle_deg": round(float(result["lateral_angle_deg"]), 4)},
        {"used_entities": [target_ent.get("object_id")],
         "derivation_inputs": {"observer_position": list(observer),
                               "observer_forward": list(forward),
                               "lateral_deadzone_deg": deadzone}},
        {"is_ambiguous": ambiguous,
         "reason": f"横向角落在 ±{deadzone}° 死区内" if ambiguous else None},
    )


def select_referent_program(ctx: dict[str, Any]) -> tuple:
    """``3d_grounding.object`` 的推导：按空间谓词选出被指代实体。

    首版谓词是「距观察者最远」—— 选它是因为**外观无法区分远近**：
    近垂直下视下同类地物尺度相近，必须用三维位置才能判定。
    """
    l1 = ctx["l1"]
    observer = _observer_position(ctx)
    if observer is None:
        raise GeometryError("缺少观察者位置")

    cands = [(e.get("object_id"), _entity_position(e))
             for e in (l1.get("objects") or []) if _entity_position(e)]
    if len(cands) < 3:
        raise GeometryError(f"候选实体不足 3 个（实得 {len(cands)}）")

    o = np.asarray(observer, dtype=float)
    ranked = sorted(((eid, float(np.linalg.norm(np.asarray(p) - o)))
                     for eid, p in cands), key=lambda x: -x[1])
    target_id, far = ranked[0]

    # 与次远的差距过小则不可分辨。**判据必须是相对的** ——
    # 本任务是序数判定，可在 relative 尺度的场景上运行（DESIGN §40.5 机制 2），
    # 那里「米」没有定义。2026-08-25 修正：原为写死的 `< 1.0`（米），
    # 在 VGGT 相对尺度下（中位景深≈1）会把**几乎所有样本判成歧义**，实测确认。
    # 现按最远距离的比例判定，任何尺度下含义一致。
    rel_margin = float((ctx["spec"].raw.get("quality_requirements") or {})
                       .get("ordinal_margin_ratio", 0.05))
    ambiguous = (len(ranked) > 1
                 and abs(far - ranked[1][1]) < rel_margin * max(far, 1e-9))

    return (
        {"target_type": "grounding", "object_id": target_id},
        {"used_entities": [eid for eid, _ in cands],
         "derivation_inputs": {"observer_position": list(observer),
                               "predicate": "farthest_from_observer"}},
        {"is_ambiguous": ambiguous,
         "reason": (f"最远与次远的差距不足最远距离的 {rel_margin:.0%}"
                    if ambiguous else None),
         "equivalent_answers": [target_id, ranked[1][0]] if ambiguous else []},
    )


def link_observations_program(ctx: dict[str, Any]) -> tuple:
    """``cross_view_correspondence.object`` 的推导：读关联图的判定结果。

    **不自己做关联** —— 关联是 L2-S3 融合阶段的产物。本程序只把已收敛的
    链接转成 target；未收敛（``same_entity`` 为 null）的链接**不产生样本**，
    因为它既不是正样本也不是负样本。
    """
    links = [l for l in (ctx["l2"].get("cross_view_links") or [])
             if l.get("same_entity") is not None]
    if not links:
        raise GeometryError("没有已收敛的跨视角链接")
    link = links[0]
    return (
        {"target_type": "cross_view_correspondence",
         "same_entity": bool(link["same_entity"]),
         "link_id": link.get("link_id")},
        {"used_entities": [link.get("entity_id")] if link.get("entity_id") else [],
         "derivation_inputs": {"probability": link.get("probability"),
                               "evidence": link.get("evidence")}},
        {"is_ambiguous": False},
    )


def _observer_position(ctx: dict[str, Any]) -> list[float] | None:
    for cam in (ctx["l1"].get("cameras") or []) + (ctx["l2"].get("cameras") or []):
        if cam.get("pose_id") == ctx.get("observer_pose_id"):
            return list(cam.get("position")) if cam.get("position") else None
    return None


def _observer_forward(ctx: dict[str, Any]) -> list[float] | None:
    for cam in (ctx["l1"].get("cameras") or []) + (ctx["l2"].get("cameras") or []):
        if cam.get("pose_id") == ctx.get("observer_pose_id"):
            return list(cam.get("forward")) if cam.get("forward") else None
    return None


#: Task Spec 的 `derivation_program` 字段按名索引到此表。
DERIVATION_PROGRAMS = {
    "minimum_point_to_polyline_distance": minimum_distance_program,
    "observer_relative_direction": observer_relative_direction_program,
    "select_referent_by_spatial_predicate": select_referent_program,
    "link_observations_via_lifted_point_support": link_observations_program,
}


def get_derivation_program(name: str):
    """按名取推导程序。未注册的名字必须报错，不得静默跳过。"""
    if name not in DERIVATION_PROGRAMS:
        raise KeyError(
            f"未注册的推导程序 {name!r}；已注册：{sorted(DERIVATION_PROGRAMS)}")
    return DERIVATION_PROGRAMS[name]
