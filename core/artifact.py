"""Artifact 信封：血缘、版本与不可变性。

契约来源：DESIGN.md §30。

SPEC §30 要求每个 artifact 至少携带：artifact ID 与 schema 版本、父 artifact ID、
dataset/scene/split/run ID、代码/模型/schema/task/prompt 版本、创建时间与运行配置、
输入校验和、状态与错误码/警告/重试记录。

并且：**修复与重生成必须产生新 artifact，禁止静默覆盖**（SPEC §30、§23.5）。
本模块用 ``frozen`` dataclass + :meth:`Artifact.derive` 在类型层面强制这一点。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict, replace
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import ErrorCode
from .states import GateStatus, PipelineState

__all__ = ["Artifact", "ArtifactKind", "content_digest", "new_artifact_id"]

#: 本 artifact 信封自身的 schema 版本。字段增删必须提升此版本。
ENVELOPE_SCHEMA_VERSION = "0.1.0"


class ArtifactKind(str, Enum):
    """SPEC §30 列出的不可变制品类型。"""

    RUN_MANIFEST = "run_manifest"
    DATASET_CARD = "dataset_card"
    SAMPLE_MANIFEST = "sample_manifest"
    SCENE_MANIFEST = "scene_manifest"
    INGESTION_REPORT = "ingestion_report"
    GEOMETRY_MANIFEST = "geometry_manifest"
    METADATA_SNAPSHOT = "metadata_snapshot"
    METADATA_VALIDATION_REPORT = "metadata_validation_report"
    TASK_SPEC = "task_spec"
    PROMPT_BUNDLE = "prompt_bundle"
    RAW_MODEL_OUTPUT = "raw_model_output"
    VALIDATED_SAMPLE = "validated_sample"
    QUALITY_EVENT = "quality_event"
    QUALITY_DASHBOARD = "quality_dashboard"
    RELEASE_MANIFEST = "release_manifest"


def new_artifact_id(kind: ArtifactKind | str) -> str:
    """生成 artifact ID，形如 ``scene_manifest_3f1a9c2b``。"""
    prefix = kind.value if isinstance(kind, ArtifactKind) else str(kind)
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def content_digest(payload: Any) -> str:
    """对 payload 计算稳定的 sha256 摘要。

    使用排序键与紧凑分隔符，确保同内容不同书写顺序得到相同摘要。
    """
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Artifact:
    """不可变的 artifact 信封。

    ``payload`` 承载具体内容；信封本身承载血缘与状态。修改内容请用
    :meth:`derive` 生成新 artifact，不要试图原地改写。
    """

    kind: ArtifactKind
    payload: dict[str, Any]

    artifact_id: str = ""
    schema_version: str = ENVELOPE_SCHEMA_VERSION
    parent_ids: tuple[str, ...] = ()

    dataset_id: str | None = None
    scene_id: str | None = None
    split_group_id: str | None = None
    run_id: str | None = None

    code_version: str | None = None
    model_versions: dict[str, str] = field(default_factory=dict)
    task_spec_version: str | None = None
    prompt_version: str | None = None

    created_at: str | None = None
    runtime_profile: dict[str, Any] = field(default_factory=dict)
    input_digests: dict[str, str] = field(default_factory=dict)

    state: PipelineState | None = None
    gate_status: GateStatus | None = None
    error_codes: tuple[ErrorCode, ...] = ()
    warnings: tuple[str, ...] = ()
    retry_history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.artifact_id:
            object.__setattr__(self, "artifact_id", new_artifact_id(self.kind))

    @property
    def payload_digest(self) -> str:
        return content_digest(self.payload)

    def derive(self, **changes: Any) -> "Artifact":
        """派生新 artifact：自动串联血缘并分配新 ID。

        这是修改 artifact 的**唯一**正当方式（SPEC §30 禁止静默覆盖）。
        """
        changes.setdefault("parent_ids", self.parent_ids + (self.artifact_id,))
        changes["artifact_id"] = new_artifact_id(changes.get("kind", self.kind))
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["parent_ids"] = list(self.parent_ids)
        data["error_codes"] = [c.value for c in self.error_codes]
        data["warnings"] = list(self.warnings)
        data["retry_history"] = list(self.retry_history)
        data["state"] = self.state.value if self.state else None
        data["gate_status"] = self.gate_status.value if self.gate_status else None
        data["payload_digest"] = self.payload_digest
        return data

    def write(self, path: str | Path) -> Path:
        """写出 artifact。若目标已存在则拒绝覆盖（SPEC §30）。"""
        target = Path(path)
        if target.exists():
            raise FileExistsError(
                f"artifact 已存在，禁止静默覆盖：{target}。"
                "修复或重生成请使用 derive() 产生新 artifact（SPEC §30）"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return target
