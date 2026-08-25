"""冻结的 Pipeline 契约：ID、状态、枚举、错误码、artifact 信封。

本包是 SPEC §34 vertical slice 第 1 步"Freeze IDs, artifact states,
minimal schemas, and error codes"的实现，是全 Pipeline 的单一事实来源。

修改本包中的任何枚举值或状态迁移规则，等同于修改架构契约，
**必须同步修改 `docs/CLAUDE_CODE_PROJECT_SPEC.md` 并记入 `docs/CHANGELOG.md`**。
"""

from .artifact import Artifact, ArtifactKind, content_digest, new_artifact_id
from .enums import (
    DepthSource,
    DepthType,
    InvalidGeometryReason,
    METRIC_CAPABLE_DEPTH_TYPES,
    ScaleStatus,
    SourceType,
    SupervisionLevel,
    supports_absolute_metric_target,
)
from .errors import ERROR_CATALOG, ErrorCode, Severity, default_status, describe
from .ids import IdMinter, Namespace, format_id, is_valid_id, parse_id
from .metadata import (
    MetadataError,
    SCHEMA_VERSION as METADATA_SCHEMA_VERSION,
    ValidationIssue,
    derive_metric_eligibility,
    load_schema,
    validate_against_schema,
    validate_snapshot_consistency,
)
from .states import (
    ALLOWED_TRANSITIONS,
    Gate,
    GATE_FOR_STATE,
    GateStatus,
    PipelineState,
    TERMINAL_STATES,
    TransitionError,
    can_transition,
    validate_transition,
)

#: 契约版本。任何破坏性改动必须提升主/次版本并记入 CHANGELOG。
CONTRACT_VERSION = "0.1.0"

__all__ = [
    "CONTRACT_VERSION",
    # artifact
    "Artifact", "ArtifactKind", "content_digest", "new_artifact_id",
    # enums
    "DepthSource", "DepthType", "InvalidGeometryReason", "ScaleStatus",
    "SourceType", "SupervisionLevel", "METRIC_CAPABLE_DEPTH_TYPES",
    "supports_absolute_metric_target",
    # errors
    "ERROR_CATALOG", "ErrorCode", "Severity", "default_status", "describe",
    # ids
    "IdMinter", "Namespace", "format_id", "is_valid_id", "parse_id",
    # metadata
    "MetadataError", "METADATA_SCHEMA_VERSION", "ValidationIssue",
    "derive_metric_eligibility", "load_schema", "validate_against_schema",
    "validate_snapshot_consistency",
    # states
    "ALLOWED_TRANSITIONS", "Gate", "GATE_FOR_STATE", "GateStatus",
    "PipelineState", "TERMINAL_STATES", "TransitionError",
    "can_transition", "validate_transition",
]
