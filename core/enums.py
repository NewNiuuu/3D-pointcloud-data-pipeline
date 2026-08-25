"""冻结的枚举：尺度、深度来源、无效几何原因、监督等级等。

契约来源：DESIGN.md §7、§13、§14.5、§14.11、§42。

本模块承载几条架构铁律中的关键区分。放宽这些枚举等同于放宽铁律，
必须先改 SPEC。
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "SourceType",
    "DepthSource",
    "ScaleStatus",
    "DepthType",
    "InvalidGeometryReason",
    "SupervisionLevel",
    "METRIC_CAPABLE_DEPTH_TYPES",
    "supports_absolute_metric_target",
]


class SourceType(str, Enum):
    """数据集来源类型（SPEC §7）。真实与仿真必须分别统计与报告。"""

    REAL = "real"
    SIMULATED = "simulated"
    MIXED = "mixed"


class DepthSource(str, Enum):
    """深度的物理来源（SPEC §7 允许值）。

    这是"深度**怎么来的**"，与 :class:`DepthType`（"尺度**可不可信**"）
    是两个正交维度，不得混为一谈。
    """

    DIRECT_LIDAR = "direct_lidar"
    STEREO = "stereo"
    SFM_MVS = "sfm_mvs"
    RENDERED_DEPTH = "rendered_depth"
    PSEUDO_DEPTH = "pseudo_depth"
    NONE = "none"


class ScaleStatus(str, Enum):
    """场景级尺度状态（SPEC §13）。"""

    METRIC = "metric"
    RELATIVE = "relative"
    UNKNOWN = "unknown"


class DepthType(str, Enum):
    """深度制品的尺度分类（SPEC §14.11）。

    每份深度制品必须且只能声明其中一种。SPEC §14.11 明确：
    "A model card using the word 'metric' MUST NOT be treated as proof of
    acceptable UAV scale accuracy." —— 即 ``METRIC`` 也需域内校准后才可
    用于绝对米制任务。
    """

    METRIC = "metric"
    """输出以米定义，但 UAV 域尺度偏差仍未验证；需域校准/门禁后方可用。"""

    EXTERNALLY_ANCHORED = "externally_anchored"
    """尺度由 RTK/GPS/IMU/高度计/ToF/LiDAR/已知基线恢复。"""

    RELATIVE = "relative"
    """乘性尺度未知。禁止绝对米制任务。"""

    AFFINE_INVARIANT = "affine_invariant"
    """尺度与位移均可能未知。禁止绝对米制任务。"""

    PSEUDO = "pseudo"
    """未经验证的模型估计。只能作弱标签或质量信号。"""


#: 在通过相应门禁后，**可能**支持绝对米制目标的深度类型。
#: 注意 ``METRIC`` 仍需域内尺度校准（SPEC §14.11）。
METRIC_CAPABLE_DEPTH_TYPES = frozenset(
    {DepthType.METRIC, DepthType.EXTERNALLY_ANCHORED}
)


def supports_absolute_metric_target(
    depth_type: DepthType,
    *,
    domain_calibrated: bool = False,
    anchor_provenance_verified: bool = False,
) -> bool:
    """判断某深度类型当前是否有资格产出绝对米制目标（SPEC §14.11）。

    - ``RELATIVE`` / ``AFFINE_INVARIANT`` / ``PSEUDO``：永远不可以。
    - ``METRIC``：需 ``domain_calibrated=True``。
    - ``EXTERNALLY_ANCHORED``：需 ``anchor_provenance_verified=True``。
    """
    if depth_type not in METRIC_CAPABLE_DEPTH_TYPES:
        return False
    if depth_type is DepthType.METRIC:
        return domain_calibrated
    return anchor_provenance_verified


class InvalidGeometryReason(str, Enum):
    """无效几何原因码（SPEC §14.5）。

    这些原因**必须分别保存概率图**，不得合并为单一 invalid 概率后丢弃分量。
    尤其：水面不等于空域，它是常常违反朗伯/刚体重建假设的几何。
    """

    SKY = "sky"
    WATER = "water"
    REFLECTION_OR_TRANSPARENCY = "reflection_or_transparency"
    LOW_DEPTH_CONFIDENCE = "low_depth_confidence"
    REPROJECTION_INCONSISTENT = "reprojection_inconsistent"
    DYNAMIC_GEOMETRY = "dynamic_geometry"
    OUT_OF_BOUNDS = "out_of_bounds"


class SupervisionLevel(str, Enum):
    """监督强度（SPEC §42）。

    SPEC §42：强监督与程序派生标签**应当**构成评测数据；过滤伪标签与弱标签
    除非经人工复核，否则**应当**只进入训练数据。
    """

    STRONG = "strong"
    """原生传感器、人工标注、RTK/LiDAR/GCP 或已验证真值。"""

    DETERMINISTIC_DERIVED = "deterministic_derived"
    """由通过门禁的几何经版本化程序计算得到。"""

    FILTERED_PSEUDO = "filtered_pseudo"
    """VGGT-Ω/专家输出，通过置信度与多视角检查。"""

    WEAK = "weak"
    """模型提议、不确定的薄结构、属性或关系候选。"""

    LANGUAGE_GENERATED = "language_generated"
    """自然语言表达，其结构化 claims/target 经独立校验。"""

    @property
    def eligible_for_evaluation(self) -> bool:
        """是否适合直接用作评测数据（SPEC §42）。"""
        return self in (
            SupervisionLevel.STRONG,
            SupervisionLevel.DETERMINISTIC_DERIVED,
        )
