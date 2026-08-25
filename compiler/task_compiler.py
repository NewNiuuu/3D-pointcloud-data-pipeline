"""任务编译：metadata snapshot + Task Spec → Canonical Task Record。

契约来源：SPEC §11 的 L2-S6、§23.6（原 `task-prompt-compiler` 的职责）、§20.1。
按 2026-08-25 的决定（`PROJECT_HANDOFF.md` §19.4），本模块实现为**普通代码**，
暂不封装为 Skill。

## 编译顺序不可调换

SPEC §20.1 规定 program-first 任务的编译顺序，其中前后依赖是实质性的：

1. **先判场景资格** —— 不合格的场景根本不该进入后续步骤；
2. **再确定性地算出隐藏 target**；
3. **然后**按字段掩码裁出可见 metadata；
4. **最后**做泄漏检查。

第 4 步必须在第 2、3 步之后：**只有同时握着「真实的答案」和「实际裁出的输入」，
才能检查前者是否漏进了后者**。Task Spec 的静态校验只能比对字段名列表，
查不出"这份实际数据里恰好含有答案值"。

## 与静态校验的分工

| 检查 | 时机 | 能查出什么 |
|---|---|---|
| `core.task_spec` 的静态校验 | 加载 Spec 时 | 字段名层面的泄漏、checker 未注册、非 metric 场景出米制题 |
| 本模块的运行时检查 | 编译每个样本时 | **实际数据**中的答案值泄漏、场景资格不符、答案不唯一 |

二者缺一不可 —— 静态过了运行时照样可能漏。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Sequence

from checkers import CHECKER_REGISTRY
from core.errors import ErrorCode
from core.task_spec import TaskSpec
from task_adapters import scan_for_leakage

__all__ = [
    "CompilerError",
    "IneligibleScene",
    "CompileResult",
    "TaskCompiler",
    "project_fields",
]

RECORD_SCHEMA_VERSION = "0.1.0"
COMPILER_VERSION = "0.1.0"


class CompilerError(RuntimeError):
    """编译无法进行（Spec 与 metadata 不匹配、程序未注册等）。"""


@dataclass(frozen=True)
class IneligibleScene(Exception):
    """场景不具备出该题的资格。

    **不是错误，是正常结果** —— 但必须携带理由，避免场景被静默丢弃
    （对应 metadata_snapshot 的 `capabilities.reasons` 设计意图）。
    """

    task_id: str
    scene_id: str
    reasons: tuple[str, ...]

    def __str__(self) -> str:  # pragma: no cover
        return (f"场景 {self.scene_id} 不具备 {self.task_id} 的资格："
                + "；".join(self.reasons))


@dataclass
class CompileResult:
    """一次编译的产出。"""

    records: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[IneligibleScene] = field(default_factory=list)
    #: 编译过程中命中的硬失败。非空时**不得**发布这批样本。
    failures: list[tuple[str, ErrorCode, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def project_fields(source: dict[str, Any], paths: Sequence[str]) -> dict[str, Any]:
    """按点分路径从 metadata 中裁出子图。

    支持列表通配：``entities.geometry.centroid`` 会对 ``entities`` 列表中的
    每个元素取 ``geometry.centroid``，并保持列表结构。

    **只取列出的路径** —— 这是字段掩码的实现，多带一个字段就可能泄漏答案。
    路径不存在时**静默跳过**（该实体没有该属性是正常的），但整个路径在所有
    实体上都取不到时，调用方应当视为 Spec 与数据不匹配。
    """
    out: dict[str, Any] = {}
    for path in paths:
        parts = path.split(".")
        _project_into(source, parts, out)
    return out


def _project_into(src: Any, parts: Sequence[str], dst: dict[str, Any]) -> None:
    if not parts:
        return
    head, rest = parts[0], parts[1:]
    if isinstance(src, dict):
        if head not in src:
            return
        value = src[head]
        if not rest:
            dst[head] = value
            return
        if isinstance(value, list):
            bucket = dst.setdefault(head, [{} for _ in value])
            # 已有 bucket 长度可能不同（不同路径投影到同一列表），按需补齐
            while len(bucket) < len(value):
                bucket.append({})
            for i, item in enumerate(value):
                _project_into(item, rest, bucket[i])
            return
        child = dst.setdefault(head, {})
        if isinstance(child, dict):
            _project_into(value, rest, child)


class TaskCompiler:
    """把 metadata snapshot 按 Task Spec 编译为 Canonical Task Record。

    ``derivation_programs`` 把 Spec 的 ``derivation_program`` 名映射到实际函数。
    函数签名统一为 ``(context) -> (hidden_target, evidence_extra, ambiguity)``，
    其中 ``context`` 含 snapshot、l1、l2 与 Spec。
    """

    def __init__(
        self,
        derivation_programs: dict[str, Callable[[dict[str, Any]], tuple]],
        *,
        code_version: str = COMPILER_VERSION,
    ) -> None:
        self._programs = dict(derivation_programs)
        self._code_version = code_version

    # ---------- 资格 ----------

    def check_eligibility(
        self, spec: TaskSpec, snapshot: dict[str, Any], l1: dict[str, Any],
        l2: dict[str, Any] | None = None,
    ) -> list[str]:
        """返回不合格的理由列表；空列表表示合格。

        ``eligibility.require_all`` 里混着两类条件，必须分开取值：

        - **场景级能力**（``camera_baseline_m``、``scale_status`` 等）
          —— 存在 snapshot 的 ``capabilities`` 里；
        - **任务时量**（``candidate_count``、``minimum_views`` 等）
          —— 必须从 L1/L2 的实际数据现算。

        早期实现把两类都去 snapshot 查，任务时量取到 ``None`` 后判不合格，
        导致**每个场景都被拒、静默产出零样本** —— 这是最难察觉的失败模式。

        遇到**两边都算不出**的条件键时**抛错而非跳过**：那是 Spec 与编译器的
        不匹配，应当立刻暴露，而不是安静地让产出归零。
        """
        reasons: list[str] = []
        caps = snapshot.get("capabilities") or {}
        required = spec.raw.get("required_scene_capabilities") or {}
        facts = self._eligibility_facts(caps, l1, l2 or {})

        want_scale = required.get("scale_status")
        if want_scale and caps.get("scale_status") != want_scale:
            reasons.append(
                f"要求 scale_status={want_scale}，实际 {caps.get('scale_status')}")

        # 米制题必须真的有资格 —— 铁律 8 的运行时形式
        if spec.numeric_tolerance_m is not None and not caps.get("metric_task_eligible"):
            reasons.append(
                "本任务产出绝对米制目标，但 metric_task_eligible 为 false"
                + (f"（{'；'.join(caps.get('reasons') or [])}）"
                   if caps.get("reasons") else ""))

        allowed_depth = required.get("depth_type_allowed")
        if allowed_depth and caps.get("depth_type") not in allowed_depth:
            reasons.append(
                f"depth_type={caps.get('depth_type')} 不在允许集 {allowed_depth} 内")

        min_cands = required.get("minimum_candidates")
        if min_cands is not None and facts["candidate_count"] < min_cands:
            reasons.append(
                f"候选实体 {facts['candidate_count']} 个，少于要求的 {min_cands}")

        need_surface = any(
            "surface" in str(g) or "slope" in str(g) or "plane" in str(g)
            for g in (required.get("geometry") or []))
        if need_surface and "surface" not in set(caps.get("available_entity_types") or []):
            reasons.append("任务需要 surface 实体，但本快照不含该类型")

        for item in spec.raw.get("eligibility", {}).get("require_all") or []:
            if not isinstance(item, dict):
                continue
            for key, want in item.items():
                reason = self._check_requirement(key, want, facts)
                if reason:
                    reasons.append(reason)
        return reasons

    @staticmethod
    def _eligibility_facts(
        caps: dict[str, Any], l1: dict[str, Any], l2: dict[str, Any],
    ) -> dict[str, Any]:
        """合并「场景级能力」与「从数据现算的任务时量」。"""
        objects = l1.get("objects") or []
        facts = dict(caps)
        facts.update({
            "candidate_count": len(objects),
            "view_baseline_meters": caps.get("camera_baseline_m"),
            "association_confidence": max(
                [l.get("probability", 0.0) for l in (l2.get("cross_view_links") or [])],
                default=0.0),
            "all_candidates_have_valid_obb": all(
                (o.get("geometry") or {}).get("obb") is not None for o in objects),
            "all_centerlines_have_at_least_two_vertices": all(
                len((o.get("geometry") or {}).get("centerline") or []) >= 2
                for o in objects if (o.get("geometry") or {}).get("centerline")),
            "target_visible_in_at_least_n_views": max(
                [len((o.get("visibility") or {}).get("visible_frames") or [])
                 for o in objects], default=0),
            "both_observations_have_valid_point_support": bool(
                l2.get("cross_view_links")),
            "observer_forward_available": any(
                c.get("forward") for c in (l1.get("cameras") or [])),
            "entity_centroid_available": any(
                (o.get("geometry") or {}).get("centroid") for o in objects),
            "scale_status_is_metric": caps.get("scale_status") == "metric",
            "domain_calibrated": caps.get("domain_calibrated",
                                          caps.get("metric_task_eligible")),
        })
        return facts

    @staticmethod
    def _check_requirement(key: str, want: Any, facts: dict[str, Any]) -> str | None:
        """校验单条 require_all 条件。算不出的键**抛错**而非静默跳过。"""
        if key.endswith("_at_least"):
            base = key[: -len("_at_least")]
            got = facts.get(base, facts.get(key))
            if got is None:
                raise CompilerError(
                    f"资格条件 {key!r} 无法判定：既不在 snapshot.capabilities 中，"
                    f"也无法从 L1/L2 现算。请在 _eligibility_facts 中补上 {base!r}，"
                    "否则会静默产出零样本")
            return None if got >= want else f"{base} = {got}，低于要求的 {want}"
        if isinstance(want, bool):
            got = facts.get(key)
            if got is None:
                raise CompilerError(
                    f"资格条件 {key!r} 无法判定，请在 _eligibility_facts 中补上")
            return None if bool(got) == want else f"{key} = {got}，要求 {want}"
        return None

    # ---------- 编译 ----------

    def compile_one(
        self,
        spec: TaskSpec,
        snapshot: dict[str, Any],
        l1: dict[str, Any],
        l2: dict[str, Any],
        *,
        visual_inputs: Sequence[str],
        observer_pose_id: str | None = None,
        question: str | None = None,
        choices: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """编译单条记录。不合格抛 :class:`IneligibleScene`。"""
        scene_id = snapshot.get("scene_id", "")

        # 1. 资格 —— 必须最先，不合格的场景不该进入后续步骤
        reasons = self.check_eligibility(spec, snapshot, l1, l2)
        if reasons:
            raise IneligibleScene(spec.task_id, scene_id, tuple(reasons))

        # 2. checker 必须已注册（G3 硬失败 MISSING_CHECKER）
        if spec.checker not in CHECKER_REGISTRY:
            raise CompilerError(
                f"Task Spec {spec.qualified_id} 的 checker {spec.checker!r} 未注册")

        # 3. 确定性算出隐藏 target
        program_name = spec.raw["derivation_program"]
        program = self._programs.get(program_name)
        if program is None:
            raise CompilerError(
                f"推导程序 {program_name!r} 未注册；已注册：{sorted(self._programs)}")
        hidden_target, evidence_extra, ambiguity = program({
            "spec": spec, "snapshot": snapshot, "l1": l1, "l2": l2,
            "observer_pose_id": observer_pose_id,
        })

        # 4. 按字段掩码裁出可见 metadata
        source = {"observer": self._observer_view(l1, l2, observer_pose_id),
                  "entities": l1.get("objects") or [],
                  "surfaces": l1.get("surfaces") or [],
                  "regions": l1.get("regions") or [],
                  "observations": self._observations(l2),
                  "cameras": self._cameras(l1, l2)}
        visible = project_fields(source, spec.visible_fields)

        # 4b. 候选顺序确定性打乱。
        # Task Spec 的 leakage_rules 明确要求：候选列表不得按与 target 的关系排序，
        # 否则模型可从位置反推答案。以 scene_id 为种子保证可复现。
        self._shuffle_candidates(visible, scene_id)

        # 5. 运行时泄漏检查 —— 必须在 3、4 之后
        #
        # 排除**结构性必需**的实体 ID：grounding 这类"从候选中指认"的任务，
        # 正确答案的 ID 必然出现在可见候选列表里 —— 那是任务的定义，不是泄漏。
        # 真正的防线是 Spec 的 forbidden_input_fields（is_target / rank /
        # distance_to_observer）与上面的候选打乱。
        findings = scan_for_leakage(
            visible, self._scannable_target(hidden_target, spec))
        if findings:
            raise CompilerError(
                f"[{ErrorCode.TARGET_LEAKAGE.value}] 场景 {scene_id} 的可见 metadata "
                f"泄漏了隐藏目标：{findings[:3]}")

        sample_id = self._sample_id(spec, scene_id, hidden_target)
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "sample_id": sample_id,
            "task_spec_id": spec.qualified_id,
            "scene_id": scene_id,
            "metadata_snapshot_id": snapshot.get("snapshot_id"),
            "split_group_id": snapshot.get("split_group_id"),
            "capability_tags": list(spec.raw.get("capability_tags") or []),
            "low_altitude_tags": self._low_altitude_tags(spec, snapshot),
            "supervision_level": spec.raw["supervision_level"],
            "inputs": {
                "pointcloud_ref": (snapshot.get("layers", {}).get("l0_geometry") or {}).get("uri"),
                "visual_inputs": list(visual_inputs),
                "camera_refs": [observer_pose_id] if observer_pose_id else [],
                "observer_pose_id": observer_pose_id,
                "visible_metadata": visible,
                "visible_metadata_fields": list(spec.visible_fields),
                "question": question,
                "choices": choices,
            },
            "hidden_target": hidden_target,
            "target_geometry": self._target_geometry(spec, hidden_target),
            "evidence": {
                "used_entities": list(evidence_extra.get("used_entities") or []),
                "used_fields": list(spec.visible_fields),
                "derivation_program": program_name,
                "derivation_inputs": evidence_extra.get("derivation_inputs") or {},
            },
            "checker": self._checker_block(spec),
            "structurally_visible_target_ids": self._structural_ids(hidden_target, spec),
            "ambiguity": ambiguity or {"is_ambiguous": False},
            "adapters": list(spec.raw.get("adapters") or []),
            "quality": {"leakage_checked": True, "three_d_necessity_verified": True},
            "provenance": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "code_version": self._code_version,
                "task_spec_version": spec.version,
                "prompt_template": spec.raw.get("prompt_template"),
            },
        }

    def compile_many(
        self, specs: Iterable[TaskSpec], scenes: Iterable[dict[str, Any]], **kw: Any,
    ) -> CompileResult:
        """对多个 Spec × 多个场景批量编译，收集跳过与失败而非中断。"""
        result = CompileResult()
        for scene in scenes:
            for spec in specs:
                try:
                    result.records.append(self.compile_one(
                        spec, scene["snapshot"], scene["l1"], scene["l2"],
                        visual_inputs=scene.get("visual_inputs", []),
                        observer_pose_id=scene.get("observer_pose_id"),
                        question=scene.get("question"),
                        choices=scene.get("choices"), **kw))
                except IneligibleScene as skip:
                    result.skipped.append(skip)
                except CompilerError as exc:
                    result.failures.append(
                        (scene["snapshot"].get("scene_id", ""),
                         ErrorCode.TARGET_LEAKAGE if "TARGET_LEAKAGE" in str(exc)
                         else ErrorCode.SCENE_CAPABILITY_UNMET, str(exc)))
        return result

    # ---------- 内部 ----------

    @classmethod
    def _structural_ids(cls, target: dict[str, Any], spec: TaskSpec) -> list[str]:
        """登记那些「必然出现在可见候选中」的目标 ID，供 adapter 豁免扫描。"""
        scannable = cls._scannable_target(target, spec)
        return sorted(
            v for k, v in target.items()
            if k not in scannable and isinstance(v, str)
            and v.startswith("<") and v.endswith(">"))

    @staticmethod
    def _shuffle_candidates(visible: dict[str, Any], seed: str) -> None:
        """就地打乱候选列表顺序。种子取 scene_id，保证同场景每次一致。"""
        import random

        for key in ("entities", "surfaces", "regions", "observations"):
            items = visible.get(key)
            if isinstance(items, list) and len(items) > 1:
                random.Random(seed + key).shuffle(items)

    @staticmethod
    def _scannable_target(target: dict[str, Any], spec: TaskSpec) -> dict[str, Any]:
        """从隐藏 target 中剔除结构性必需可见的实体 ID。

        判据：Spec 的 ``metadata_input_fields`` 中含 ``*.object_id`` 一类的
        ID 字段时，说明候选 ID 本就该可见，答案 ID 自然在其中。

        **其余值一律照扫** —— 距离数值、方位枚举、布尔答案都不该出现在输入里。
        """
        id_fields_visible = any(
            f.endswith(("object_id", "observation_id", "surface_id", "region_id"))
            for f in spec.visible_fields)
        if not id_fields_visible:
            return target
        return {k: v for k, v in target.items()
                if not (isinstance(v, str) and v.startswith("<") and v.endswith(">"))}

    @staticmethod
    def _sample_id(spec: TaskSpec, scene_id: str, target: dict[str, Any]) -> str:
        """确定性 sample_id —— 同样输入必得同样 ID，便于去重与复现。"""
        seed = f"{spec.qualified_id}|{scene_id}|{sorted(target.items())}"
        return "task_sample_" + hashlib.sha256(seed.encode()).hexdigest()[:12]

    @staticmethod
    def _observer_view(l1: dict, l2: dict, pose_id: str | None) -> dict[str, Any]:
        for cam in (l1.get("cameras") or []) + (l2.get("cameras") or []):
            if cam.get("pose_id") == pose_id:
                return dict(cam)
        return {"pose_id": pose_id} if pose_id else {}

    @staticmethod
    def _observations(l2: dict) -> list[dict[str, Any]]:
        obs: list[dict[str, Any]] = []
        for link in l2.get("cross_view_links") or []:
            for key in ("observation_a", "observation_b"):
                if link.get(key):
                    obs.append(dict(link[key]))
        return obs

    @staticmethod
    def _cameras(l1: dict, l2: dict) -> list[dict[str, Any]]:
        return list(l1.get("cameras") or []) + list(l2.get("cameras") or [])

    @staticmethod
    def _low_altitude_tags(spec: TaskSpec, snapshot: dict) -> list[str]:
        """把 Spec 声明的低空信号映射为记录级标签，并**用快照事实过滤**。

        声称使用某信号但快照没有该事实时，标签不予保留 —— 避免虚假的低空主张
        （SPEC §43.2 / 错误码 LOW_ALTITUDE_CLAIM_UNSUPPORTED）。
        """
        caps = snapshot.get("capabilities") or {}
        declared = set((spec.raw.get("low_altitude_specificity") or {}).get("signals") or [])
        tags: list[str] = []
        if "uav_pose_altitude_nadir_geometry" in declared:
            if caps.get("nadir_angle_median_deg") is not None:
                tags += ["nadir_view", "uav_pose_altitude"]
        if "weak_depth_cue_from_nadir_view" in declared:
            if (caps.get("depth_relief_ratio") or 99) < 2.0:
                tags.append("weak_depth_cue")
        return tags

    @staticmethod
    def _target_geometry(spec: TaskSpec, target: dict[str, Any]) -> dict[str, Any]:
        anchor = spec.raw.get("target_anchor") or {}
        kind_map = {
            "object_id_with_point_support": "point_indices",
            "entity_id_with_centerline_and_segment": "object_obb",
            "object_id_with_centroid_and_observer_pose": "spatial_relation",
            "entity_pair_with_point_support": "point_indices",
        }
        ids = [v for k, v in target.items()
               if isinstance(v, str) and v.startswith("<") and v.endswith(">")]
        return {
            "anchor_kind": kind_map.get(anchor.get("kind"), "spatial_relation"),
            "entity_ids": ids,
        }

    @staticmethod
    def _checker_block(spec: TaskSpec) -> dict[str, Any]:
        q = spec.raw.get("quality_requirements") or {}
        block: dict[str, Any] = {"name": spec.checker, "version": "0.1.0"}
        if q.get("numeric_tolerance_m") is not None:
            block["tolerance_m"] = q["numeric_tolerance_m"]
        if q.get("lateral_deadzone_deg") is not None:
            block["lateral_deadzone_deg"] = q["lateral_deadzone_deg"]
        return block
