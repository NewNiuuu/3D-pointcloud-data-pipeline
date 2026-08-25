"""Metadata 层的加载与跨层校验。

契约来源：`schemas/l0_geometry.schema.json`、`l1_entities`、`l2_relations`、
`metadata_snapshot`，以及 SPEC §16/§23.4/§27。

## 为什么需要这一层而不只是 JSON Schema

JSON Schema 只能表达**单文档内的结构约束**。以下不变量它表达不了，
但恰恰是最容易出错、后果最严重的部分：

1. **跨层引用完整性** —— L2 引用的实体 ID 必须在 L1 中存在
   （错误码 `BROKEN_ID_REFERENCE`）。
2. **ID 唯一性** —— 同一 snapshot 内实体 ID 不得重复（`DUPLICATE_ENTITY_ID`）。
3. **米制资格的推导正确性** —— `metric_task_eligible` 不能由人随手填，
   必须能从 `depth_type` + 校准标志重新推出（铁律 8/9）。
4. **置信度分量未被压缩** —— 只填一个总分而丢掉分量是硬失败
   （`CONFIDENCE_COMPONENTS_COLLAPSED`，§14.8）。
5. **派生字段可重算** —— 每条关系的 `derivation.program` 必须已注册
   （`DERIVED_FIELD_NOT_RECOMPUTABLE`，§23.4）。
6. **无效原因未被合并** —— 只有 `combined_uri` 而无分量掩码是硬失败
   （`REASON_MASKS_COLLAPSED`，§14.5）。

这些检查在**任务编译之前**执行，属于 G2 门禁的静态部分。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from core.enums import DepthType, supports_absolute_metric_target
from core.errors import ErrorCode
from core.ids import is_valid_id

__all__ = [
    "MetadataError",
    "ValidationIssue",
    "SCHEMA_DIR",
    "SCHEMA_VERSION",
    "load_schema",
    "validate_against_schema",
    "validate_snapshot_consistency",
    "derive_metric_eligibility",
]

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

#: 本组 metadata schema 的冻结版本。字段增删或语义变化 MUST 提升此版本，
#: 并在 CHANGELOG 记录 —— 旧快照据此仍可被正确解读。
SCHEMA_VERSION = "0.1.0"

_SCHEMA_FILES = {
    "l0_geometry": "l0_geometry.schema.json",
    "l1_entities": "l1_entities.schema.json",
    "l2_relations": "l2_relations.schema.json",
    "metadata_snapshot": "metadata_snapshot.schema.json",
    "canonical_task_record": "canonical_task_record.schema.json",
}


class MetadataError(ValueError):
    """metadata 结构或跨层一致性错误。"""


@dataclass(frozen=True)
class ValidationIssue:
    """一条校验问题。硬失败与警告都用它表示，靠 ``code`` 区分严重度。"""

    code: ErrorCode
    message: str
    location: str = ""

    def __str__(self) -> str:  # pragma: no cover
        where = f" @ {self.location}" if self.location else ""
        return f"[{self.code.value}] {self.message}{where}"


@dataclass
class _Index:
    """L1 实体索引，供跨层检查复用。"""

    ids: set[str] = field(default_factory=set)
    duplicates: list[str] = field(default_factory=list)
    by_type: dict[str, set[str]] = field(default_factory=dict)


def load_schema(name: str) -> dict[str, Any]:
    """按名加载 schema。名字取自 :data:`_SCHEMA_FILES`。"""
    if name not in _SCHEMA_FILES:
        raise MetadataError(
            f"未知 schema {name!r}；可用：{sorted(_SCHEMA_FILES)}")
    return json.loads((SCHEMA_DIR / _SCHEMA_FILES[name]).read_text(encoding="utf-8"))


def validate_against_schema(instance: dict[str, Any], name: str) -> None:
    """用 JSON Schema 校验单个文档。不合规抛 :class:`MetadataError`。"""
    import jsonschema

    try:
        jsonschema.validate(instance=instance, schema=load_schema(name))
    except jsonschema.ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise MetadataError(f"{name} 不符合 schema @ {path}：{exc.message}") from exc


def derive_metric_eligibility(
    depth_type: str | DepthType,
    *,
    domain_calibrated: bool,
    anchor_provenance_verified: bool,
) -> bool:
    """从深度类型与校准标志推出米制任务资格。

    这是铁律 8/9 的唯一权威推导。**快照里的 ``metric_task_eligible``
    必须与本函数的结果一致** —— 否则说明有人手工放宽了资格。
    """
    return supports_absolute_metric_target(
        DepthType(depth_type),
        domain_calibrated=domain_calibrated,
        anchor_provenance_verified=anchor_provenance_verified,
    )


def _index_entities(l1: dict[str, Any]) -> _Index:
    idx = _Index()
    for kind, key in (("object", "objects"), ("surface", "surfaces"), ("region", "regions")):
        bucket: set[str] = set()
        for item in l1.get(key) or []:
            eid = item.get(f"{kind}_id")
            if eid is None:
                continue
            if eid in idx.ids:
                idx.duplicates.append(eid)
            idx.ids.add(eid)
            bucket.add(eid)
        idx.by_type[kind] = bucket
    return idx


def _check_confidence_components(
    entities: Iterable[dict[str, Any]], id_key: str, location: str,
    issues: list[ValidationIssue],
) -> None:
    """§14.8：置信度分量不得被压成单一分数。"""
    components = ("semantic", "detector_box", "mask", "geometry", "association")
    for ent in entities:
        conf = ent.get("confidence") or ent.get("quality") or {}
        present = [c for c in components if conf.get(c) is not None]
        if len(present) == 1 and conf.get("cross_view_support") is None:
            issues.append(ValidationIssue(
                ErrorCode.CONFIDENCE_COMPONENTS_COLLAPSED,
                f"实体 {ent.get(id_key)} 只有单一置信度分量 {present[0]!r}，"
                "疑似把 detector/mask/geometry/association 压成了一个分数",
                location))


def validate_snapshot_consistency(
    snapshot: dict[str, Any],
    l0: dict[str, Any],
    l1: dict[str, Any],
    l2: dict[str, Any],
    *,
    known_programs: Iterable[str] | None = None,
) -> list[ValidationIssue]:
    """跨层一致性检查，返回问题列表（空列表表示通过）。

    ``known_programs`` 是已注册的推导程序名集合；不传则跳过第 5 项检查。
    调用方通常传入 ``geometry`` 与 ``checkers`` 中导出的函数名。
    """
    issues: list[ValidationIssue] = []
    idx = _index_entities(l1)

    # --- 1. ID 唯一性 ---
    for dup in idx.duplicates:
        issues.append(ValidationIssue(
            ErrorCode.DUPLICATE_ENTITY_ID, f"实体 ID 重复：{dup}", "l1_entities"))

    # --- 2. ID 格式 ---
    for eid in idx.ids:
        if not is_valid_id(eid):
            issues.append(ValidationIssue(
                ErrorCode.BROKEN_ID_REFERENCE,
                f"实体 ID 格式非法：{eid!r}（期望 <ns_NNN>）", "l1_entities"))

    # --- 3. 跨层引用完整性 ---
    for rel in l2.get("relations") or []:
        for key in ("subject_id", "object_id"):
            ref = rel.get(key)
            if ref and ref not in idx.ids:
                issues.append(ValidationIssue(
                    ErrorCode.BROKEN_ID_REFERENCE,
                    f"关系 {rel.get('relation_id')} 的 {key}={ref} 在 L1 中不存在",
                    "l2_relations"))
    for link in l2.get("cross_view_links") or []:
        ref = link.get("entity_id")
        if ref and ref not in idx.ids:
            issues.append(ValidationIssue(
                ErrorCode.BROKEN_ID_REFERENCE,
                f"跨视角链接 {link.get('link_id')} 的 entity_id={ref} 在 L1 中不存在",
                "l2_relations"))

    # --- 4. 米制资格必须可重推 ---
    caps = snapshot.get("capabilities") or {}
    scale = (l0.get("scale") or {})
    declared = bool(caps.get("metric_task_eligible"))
    try:
        expected = derive_metric_eligibility(
            caps.get("depth_type", scale.get("depth_type", "pseudo")),
            domain_calibrated=bool(scale.get("domain_calibrated")),
            anchor_provenance_verified=bool(scale.get("anchor_provenance_verified")),
        )
    except ValueError as exc:
        issues.append(ValidationIssue(
            ErrorCode.SCALE_CLAIM_INCONSISTENT, f"深度类型非法：{exc}", "capabilities"))
    else:
        if declared != expected:
            issues.append(ValidationIssue(
                ErrorCode.SCALE_CLAIM_INCONSISTENT,
                f"metric_task_eligible 声明为 {declared}，但由 depth_type="
                f"{caps.get('depth_type')!r}、domain_calibrated="
                f"{scale.get('domain_calibrated')}、anchor_provenance_verified="
                f"{scale.get('anchor_provenance_verified')} 推出应为 {expected}",
                "capabilities"))
        if declared and (snapshot.get("capabilities") or {}).get("scale_status") != "metric":
            issues.append(ValidationIssue(
                ErrorCode.SCALE_CLAIM_INCONSISTENT,
                "metric_task_eligible 为 true 但 scale_status 不是 metric",
                "capabilities"))

    # --- 5. 派生程序必须已注册 ---
    if known_programs is not None:
        known = set(known_programs)
        for rel in l2.get("relations") or []:
            prog = (rel.get("derivation") or {}).get("program")
            if prog and prog not in known:
                issues.append(ValidationIssue(
                    ErrorCode.DERIVED_FIELD_NOT_RECOMPUTABLE,
                    f"关系 {rel.get('relation_id')} 的推导程序 {prog!r} 未注册，无法重算",
                    "l2_relations"))

    # --- 6. 无效几何原因不得被合并 ---
    invalid = l0.get("invalid_geometry") or {}
    if invalid.get("combined_uri") and not (invalid.get("reason_masks") or {}):
        issues.append(ValidationIssue(
            ErrorCode.REASON_MASKS_COLLAPSED,
            "只提供了 combined_uri 而无分量 reason_masks —— "
            "§14.5 要求各失效原因分别保存",
            "l0_geometry"))

    # --- 7. 置信度分量未被压缩 ---
    _check_confidence_components(l1.get("objects") or [], "object_id", "l1_entities.objects", issues)
    _check_confidence_components(l1.get("surfaces") or [], "surface_id", "l1_entities.surfaces", issues)

    # --- 8. 主路径必须是 VGGT-Ω（铁律 1/4）---
    primaries = [d for d in (l0.get("depth") or []) if d.get("role") == "primary"]
    if primaries:
        names = {(d.get("producer") or {}).get("name", "") for d in primaries}
        if not any("vggt" in n.lower() for n in names):
            issues.append(ValidationIssue(
                ErrorCode.CONFLICTING_SCALE_CLAIM,
                f"primary 深度制品的产出模型为 {sorted(names)}，"
                "但铁律 1/4 规定点云主路径 MUST 为 VGGT-Ω",
                "l0_geometry.depth"))
    if len(primaries) > 1:
        issues.append(ValidationIssue(
            ErrorCode.CONFLICTING_SCALE_CLAIM,
            f"存在 {len(primaries)} 份 role=primary 的深度制品，应当只有一份",
            "l0_geometry.depth"))

    # --- 9. 层引用摘要必须存在 ---
    for name, ref in (snapshot.get("layers") or {}).items():
        if ref is None:
            continue
        if not (ref.get("content_sha256") or "").strip():
            issues.append(ValidationIssue(
                ErrorCode.MISSING_PROVENANCE,
                f"层 {name} 缺少 content_sha256 —— 快照的不可变性无从保证",
                "layers"))

    return issues
