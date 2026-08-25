"""错误码。

契约来源：DESIGN.md §30（artifact 必须记录 error codes）、
§27（门禁硬失败）、§35（实施停止条件）。

编码规则 ``<GATE>-<CATEGORY><NN>``：

- 前缀为触发该错误的门禁（G0–G6），便于按阶段聚合失败模式；
- ``E`` = 硬失败（hard failure），**不得**被加权总分抵消，必须导致
  quarantine 或 reject；
- ``W`` = 警告，允许携带警告推进，但必须计入监控；
- ``S`` = 停止条件（SPEC §35），必须停下来请示用户，不得自行解决。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .states import Gate, GateStatus

__all__ = ["Severity", "ErrorCode", "ERROR_CATALOG", "describe", "default_status"]


class Severity(str, Enum):
    HARD = "hard"    # 硬失败
    WARN = "warn"    # 警告
    STOP = "stop"    # 需请示用户


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    gate: Gate
    severity: Severity
    message: str
    spec_ref: str


class ErrorCode(str, Enum):
    """冻结的错误码集合。新增错误码需同步更新 SPEC。"""

    # ---- G0 数据集 / 专家注册与接入 ----
    UNREADABLE_FILE = "G0-E01"
    UNKNOWN_SOURCE_IDENTITY = "G0-E02"
    DATASET_ALIAS_COLLISION = "G0-E03"
    UNSUPPORTED_HIGH_ALTITUDE_SOURCE = "G0-E04"
    SPLIT_LEAKAGE = "G0-E05"
    MISSING_REQUIRED_MODALITY = "G0-E06"
    CHECKSUM_MISMATCH = "G0-E07"
    LICENSE_BLOCKS_INTENDED_USE = "G0-S01"
    LICENSE_UNRESOLVED = "G0-S02"
    SCALE_CLAIM_INCONSISTENT = "G0-E08"
    INSUFFICIENT_VIEW_OVERLAP = "G0-W01"
    TIMESTAMP_MISALIGNMENT = "G0-W02"

    # ---- G1 几何与专家推理 ----
    UNKNOWN_COORDINATE_FRAME = "G1-E01"
    CONFLICTING_SCALE_CLAIM = "G1-E02"
    RECONSTRUCTION_UNUSABLE = "G1-E03"
    MISSING_PREPROCESSING_TRANSFORM = "G1-E04"
    EXPERT_NOT_APPROVED_FOR_USE = "G1-S01"
    DEGENERATE_GEOMETRY_SIGNATURE = "G1-W01"

    # ---- G2 Metadata ----
    BROKEN_ID_REFERENCE = "G2-E01"
    DUPLICATE_ENTITY_ID = "G2-E02"
    MISSING_PROVENANCE = "G2-E03"
    INVALID_GEOMETRY_VALUE = "G2-E04"
    DERIVED_FIELD_NOT_RECOMPUTABLE = "G2-E05"
    REASON_MASKS_COLLAPSED = "G2-E06"
    CONFIDENCE_COMPONENTS_COLLAPSED = "G2-E07"
    DYNAMIC_PROB_NOT_RESIDUAL_BASED = "G2-E08"
    THIN_OBSTACLE_EVIDENCE_INSUFFICIENT = "G2-W01"
    CIRCULAR_VALIDATION_DETECTED = "G2-E09"

    # ---- G3 任务设计与编译 ----
    THREE_D_NECESSITY_FAILED = "G3-E01"
    LOW_ALTITUDE_CLAIM_UNSUPPORTED = "G3-E02"
    TARGET_LEAKAGE = "G3-E03"
    NON_UNIQUE_ANSWER = "G3-E04"
    MISSING_CHECKER = "G3-E05"
    SCENE_CAPABILITY_UNMET = "G3-E06"
    TARGET_NOT_RECOMPUTABLE = "G3-E07"
    METRIC_TASK_ON_NONMETRIC_SCENE = "G3-E08"
    QUALITY_THRESHOLD_LOWERING_REQUIRED = "G3-S01"

    # ---- G4 模型输出 ----
    SCHEMA_UNREPAIRABLE = "G4-E01"
    NONEXISTENT_ENTITY_REFERENCE = "G4-E02"
    INVALID_UNIT = "G4-E03"
    FORMAT_REPAIRED = "G4-W01"

    # ---- G5 样本审核 ----
    CHECKER_DISAGREEMENT = "G5-E01"
    INSUFFICIENT_EVIDENCE = "G5-E02"
    UNSUPPORTED_CLAIM = "G5-E03"
    AMBIGUITY_UNMARKED = "G5-E04"
    TWO_D_SHORTCUT_DETECTED = "G5-E05"
    SEMANTIC_REWRITTEN = "G5-W01"

    # ---- G6 数据集发布 ----
    LEAKAGE_RATE_EXCEEDED = "G6-E01"
    DUPLICATE_RATE_EXCEEDED = "G6-E02"
    DEPENDENCY_TEST_FAILED = "G6-E03"
    DISTRIBUTION_FAILURE = "G6-E04"
    DERIVATIVE_LICENSE_UNRESOLVED = "G6-S01"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


ERROR_CATALOG: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.UNREADABLE_FILE: ErrorSpec(
        "G0-E01", Gate.G0, Severity.HARD, "文件不可读或损坏", "§23.3"),
    ErrorCode.UNKNOWN_SOURCE_IDENTITY: ErrorSpec(
        "G0-E02", Gate.G0, Severity.HARD, "数据集来源身份不明", "§23.1"),
    ErrorCode.DATASET_ALIAS_COLLISION: ErrorSpec(
        "G0-E03", Gate.G0, Severity.HARD, "数据集别名冲突", "§23.1"),
    ErrorCode.UNSUPPORTED_HIGH_ALTITUDE_SOURCE: ErrorSpec(
        "G0-E04", Gate.G0, Severity.HARD, "高空卫星/遥感来源，超出项目范围", "§23.1"),
    ErrorCode.SPLIT_LEAKAGE: ErrorSpec(
        "G0-E05", Gate.G0, Severity.HARD, "场景/地域/轨迹跨 split 泄漏", "铁律 11"),
    ErrorCode.MISSING_REQUIRED_MODALITY: ErrorSpec(
        "G0-E06", Gate.G0, Severity.HARD, "缺少任务所需模态", "§23.3"),
    ErrorCode.CHECKSUM_MISMATCH: ErrorSpec(
        "G0-E07", Gate.G0, Severity.HARD, "校验和不匹配", "§30"),
    ErrorCode.LICENSE_BLOCKS_INTENDED_USE: ErrorSpec(
        "G0-S01", Gate.G0, Severity.STOP, "许可条件阻碍预期用途，必须请示", "§35"),
    ErrorCode.LICENSE_UNRESOLVED: ErrorSpec(
        "G0-S02", Gate.G0, Severity.STOP, "请求全量接入但许可未决", "§23.1"),
    ErrorCode.SCALE_CLAIM_INCONSISTENT: ErrorSpec(
        "G0-E08", Gate.G0, Severity.HARD, "depth_source 与 metric_scale 声称不一致", "§23.3"),
    ErrorCode.INSUFFICIENT_VIEW_OVERLAP: ErrorSpec(
        "G0-W01", Gate.G0, Severity.WARN, "视角重叠不足，重建质量存疑", "§23.3"),
    ErrorCode.TIMESTAMP_MISALIGNMENT: ErrorSpec(
        "G0-W02", Gate.G0, Severity.WARN, "时间戳对齐存在偏差", "§23.3"),

    ErrorCode.UNKNOWN_COORDINATE_FRAME: ErrorSpec(
        "G1-E01", Gate.G1, Severity.HARD, "坐标系未知", "§27"),
    ErrorCode.CONFLICTING_SCALE_CLAIM: ErrorSpec(
        "G1-E02", Gate.G1, Severity.HARD, "尺度声称冲突", "§27"),
    ErrorCode.RECONSTRUCTION_UNUSABLE: ErrorSpec(
        "G1-E03", Gate.G1, Severity.HARD, "重建结果不可用", "§27"),
    ErrorCode.MISSING_PREPROCESSING_TRANSFORM: ErrorSpec(
        "G1-E04", Gate.G1, Severity.HARD, "缺少预处理坐标变换记录", "§14.12"),
    ErrorCode.EXPERT_NOT_APPROVED_FOR_USE: ErrorSpec(
        "G1-S01", Gate.G1, Severity.STOP, "专家模型未获使用授权", "§23.2"),
    ErrorCode.DEGENERATE_GEOMETRY_SIGNATURE: ErrorSpec(
        "G1-W01", Gate.G1, Severity.WARN, "检出已知几何失败特征（动态拖影/天空深度等）", "§13"),

    ErrorCode.BROKEN_ID_REFERENCE: ErrorSpec(
        "G2-E01", Gate.G2, Severity.HARD, "实体 ID 引用断裂", "§23.4"),
    ErrorCode.DUPLICATE_ENTITY_ID: ErrorSpec(
        "G2-E02", Gate.G2, Severity.HARD, "实体 ID 重复", "§23.4"),
    ErrorCode.MISSING_PROVENANCE: ErrorSpec(
        "G2-E03", Gate.G2, Severity.HARD, "关键 provenance 缺失", "铁律 10"),
    ErrorCode.INVALID_GEOMETRY_VALUE: ErrorSpec(
        "G2-E04", Gate.G2, Severity.HARD, "几何数值非法（NaN/退化 OBB 等）", "§23.4"),
    ErrorCode.DERIVED_FIELD_NOT_RECOMPUTABLE: ErrorSpec(
        "G2-E05", Gate.G2, Severity.HARD, "派生字段无法由上游重算", "§23.4"),
    ErrorCode.REASON_MASKS_COLLAPSED: ErrorSpec(
        "G2-E06", Gate.G2, Severity.HARD, "无效几何原因掩码被合并丢失", "§14.5"),
    ErrorCode.CONFIDENCE_COMPONENTS_COLLAPSED: ErrorSpec(
        "G2-E07", Gate.G2, Severity.HARD, "检测/掩码/跟踪/深度置信度被压成单一分数", "§14.8"),
    ErrorCode.DYNAMIC_PROB_NOT_RESIDUAL_BASED: ErrorSpec(
        "G2-E08", Gate.G2, Severity.HARD, "动态概率未基于扣除自运动的残差光流", "§14.4"),
    ErrorCode.THIN_OBSTACLE_EVIDENCE_INSUFFICIENT: ErrorSpec(
        "G2-W01", Gate.G2, Severity.WARN, "薄障碍缺乏跨帧或几何支持，应标记弱证据", "§14.6"),
    ErrorCode.CIRCULAR_VALIDATION_DETECTED: ErrorSpec(
        "G2-E09", Gate.G2, Severity.HARD, "以 refiner 或同谱系模型充当独立验证", "§14.14"),

    ErrorCode.THREE_D_NECESSITY_FAILED: ErrorSpec(
        "G3-E01", Gate.G3, Severity.HARD, "任务不具备 3D 必要性", "§43.1"),
    ErrorCode.LOW_ALTITUDE_CLAIM_UNSUPPORTED: ErrorSpec(
        "G3-E02", Gate.G3, Severity.HARD, "宣称低空特性但未使用相应信息", "§43.2"),
    ErrorCode.TARGET_LEAKAGE: ErrorSpec(
        "G3-E03", Gate.G3, Severity.HARD, "可见输入泄露隐藏 target 或等价派生字段", "铁律 6"),
    ErrorCode.NON_UNIQUE_ANSWER: ErrorSpec(
        "G3-E04", Gate.G3, Severity.HARD, "存在多个同等答案且未标记歧义", "§43.3"),
    ErrorCode.MISSING_CHECKER: ErrorSpec(
        "G3-E05", Gate.G3, Severity.HARD, "缺少确定性 checker", "§43.3"),
    ErrorCode.SCENE_CAPABILITY_UNMET: ErrorSpec(
        "G3-E06", Gate.G3, Severity.HARD, "场景不满足 Task Spec 要求的能力", "§24"),
    ErrorCode.TARGET_NOT_RECOMPUTABLE: ErrorSpec(
        "G3-E07", Gate.G3, Severity.HARD, "target 不可重算且无独立真值", "§43.3"),
    ErrorCode.METRIC_TASK_ON_NONMETRIC_SCENE: ErrorSpec(
        "G3-E08", Gate.G3, Severity.HARD, "在非 metric 场景上生成绝对米制任务", "铁律 8/§14.11"),
    ErrorCode.QUALITY_THRESHOLD_LOWERING_REQUIRED: ErrorSpec(
        "G3-S01", Gate.G3, Severity.STOP, "需降低质量阈值才能推进，必须请示", "§35"),

    ErrorCode.SCHEMA_UNREPAIRABLE: ErrorSpec(
        "G4-E01", Gate.G4, Severity.HARD, "输出 schema 无法修复", "§23.7"),
    ErrorCode.NONEXISTENT_ENTITY_REFERENCE: ErrorSpec(
        "G4-E02", Gate.G4, Severity.HARD, "引用了不存在的实体", "§27"),
    ErrorCode.INVALID_UNIT: ErrorSpec(
        "G4-E03", Gate.G4, Severity.HARD, "单位非法或缺失", "§27"),
    ErrorCode.FORMAT_REPAIRED: ErrorSpec(
        "G4-W01", Gate.G4, Severity.WARN, "经过一次格式修复", "§23.7"),

    ErrorCode.CHECKER_DISAGREEMENT: ErrorSpec(
        "G5-E01", Gate.G5, Severity.HARD, "与 checker 重算结果不一致", "§23.7"),
    ErrorCode.INSUFFICIENT_EVIDENCE: ErrorSpec(
        "G5-E02", Gate.G5, Severity.HARD, "证据不足以支持答案", "§23.7"),
    ErrorCode.UNSUPPORTED_CLAIM: ErrorSpec(
        "G5-E03", Gate.G5, Severity.HARD, "包含 metadata 与视觉证据均不支持的断言", "§26.3"),
    ErrorCode.AMBIGUITY_UNMARKED: ErrorSpec(
        "G5-E04", Gate.G5, Severity.HARD, "存在歧义但未标记", "§26.1"),
    ErrorCode.TWO_D_SHORTCUT_DETECTED: ErrorSpec(
        "G5-E05", Gate.G5, Severity.HARD, "可由纯 2D 或字段查找捷径解决", "§23.7"),
    ErrorCode.SEMANTIC_REWRITTEN: ErrorSpec(
        "G5-W01", Gate.G5, Severity.WARN, "经过一次受约束改写", "§23.7"),

    ErrorCode.LEAKAGE_RATE_EXCEEDED: ErrorSpec(
        "G6-E01", Gate.G6, Severity.HARD, "目标泄漏率超阈值", "§27"),
    ErrorCode.DUPLICATE_RATE_EXCEEDED: ErrorSpec(
        "G6-E02", Gate.G6, Severity.HARD, "重复/近重复率超阈值", "§27"),
    ErrorCode.DEPENDENCY_TEST_FAILED: ErrorSpec(
        "G6-E03", Gate.G6, Severity.HARD, "3D 依赖性对照实验不成立", "§29"),
    ErrorCode.DISTRIBUTION_FAILURE: ErrorSpec(
        "G6-E04", Gate.G6, Severity.HARD, "分布检查失败", "§27"),
    ErrorCode.DERIVATIVE_LICENSE_UNRESOLVED: ErrorSpec(
        "G6-S01", Gate.G6, Severity.STOP, "衍生数据许可未决，不得发布", "§23.1"),
}


def describe(code: ErrorCode) -> ErrorSpec:
    """返回错误码的完整说明。"""
    return ERROR_CATALOG[code]


def default_status(code: ErrorCode) -> GateStatus:
    """错误码对应的默认门禁状态。

    硬失败与停止条件均**不允许**推进：前者转入隔离，后者必须请示用户。
    """
    severity = ERROR_CATALOG[code].severity
    if severity is Severity.WARN:
        return GateStatus.WARN
    return GateStatus.QUARANTINE
