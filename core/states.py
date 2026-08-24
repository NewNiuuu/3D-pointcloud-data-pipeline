"""Pipeline 状态机与门禁状态。

契约来源：CLAUDE_CODE_PROJECT_SPEC.md §27（门禁）、§31（Orchestrator 状态机）。

两条不可放宽的规则：

1. **状态迁移必须携带前置门禁报告**（SPEC §31：
   "Transitions MUST require the preceding gate report. A state label alone is
   not sufficient."）。因此 :func:`can_transition` 只回答"拓扑上是否允许"，
   实际迁移必须走 :func:`validate_transition` 并提供 gate 报告。
2. **硬失败不得被加权总分抵消**（SPEC §27：
   "Hard failures MUST NOT be converted into a weighted quality score."）。
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "PipelineState",
    "GateStatus",
    "Gate",
    "TERMINAL_STATES",
    "GATE_FOR_STATE",
    "ALLOWED_TRANSITIONS",
    "can_transition",
    "validate_transition",
    "TransitionError",
]


class PipelineState(str, Enum):
    """SPEC §31 的场景/样本生命周期状态。"""

    REGISTERED = "REGISTERED"
    SAMPLE_VERIFIED = "SAMPLE_VERIFIED"
    INGESTED = "INGESTED"
    GEOMETRY_READY = "GEOMETRY_READY"
    EXPERT_OUTPUTS_READY = "EXPERT_OUTPUTS_READY"
    METADATA_FUSED = "METADATA_FUSED"
    METADATA_VALIDATED = "METADATA_VALIDATED"
    TASK_COMPILED = "TASK_COMPILED"
    MODEL_OUTPUT_READY = "MODEL_OUTPUT_READY"
    SAMPLE_VALIDATED = "SAMPLE_VALIDATED"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    RELEASED = "RELEASED"

    # 任意阶段均可进入的两个出口
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


class GateStatus(str, Enum):
    """SPEC §27 允许的门禁状态，仅此四种。

    - ``PASS``       可进入下一阶段
    - ``WARN``       可进入下一阶段，但必须记录警告并计入监控
    - ``QUARANTINE`` 隔离，等待人工或上游重新处理
    - ``REJECT``     当前配置下不可用
    """

    PASS = "pass"
    WARN = "warn"
    QUARANTINE = "quarantine"
    REJECT = "reject"

    @property
    def allows_progress(self) -> bool:
        """是否允许推进到下一状态。只有 pass / warn 可以。"""
        return self in (GateStatus.PASS, GateStatus.WARN)

    def __str__(self) -> str:  # pragma: no cover
        return self.value


class Gate(str, Enum):
    """SPEC §27 的六道质量门禁。"""

    G0 = "G0"  # 数据集 / 专家注册与接入
    G1 = "G1"  # 几何与专家推理
    G2 = "G2"  # Metadata
    G3 = "G3"  # 任务设计与编译
    G4 = "G4"  # 模型输出
    G5 = "G5"  # 样本审核
    G6 = "G6"  # 数据集发布

    def __str__(self) -> str:  # pragma: no cover
        return self.value


#: 终态：不可再迁出。
TERMINAL_STATES = frozenset({PipelineState.RELEASED, PipelineState.REJECTED})

#: 进入某状态所需通过的门禁。QUARANTINED / REJECTED 由门禁失败本身产生，
#: 故不在此表中；REGISTERED 是入口状态，无前置门禁。
GATE_FOR_STATE: dict[PipelineState, Gate] = {
    PipelineState.SAMPLE_VERIFIED: Gate.G0,
    PipelineState.INGESTED: Gate.G0,
    PipelineState.GEOMETRY_READY: Gate.G1,
    PipelineState.EXPERT_OUTPUTS_READY: Gate.G1,
    PipelineState.METADATA_FUSED: Gate.G2,
    PipelineState.METADATA_VALIDATED: Gate.G2,
    PipelineState.TASK_COMPILED: Gate.G3,
    PipelineState.MODEL_OUTPUT_READY: Gate.G4,
    PipelineState.SAMPLE_VALIDATED: Gate.G5,
    PipelineState.RELEASE_CANDIDATE: Gate.G5,
    PipelineState.RELEASED: Gate.G6,
}

_LINEAR_ORDER = [
    PipelineState.REGISTERED,
    PipelineState.SAMPLE_VERIFIED,
    PipelineState.INGESTED,
    PipelineState.GEOMETRY_READY,
    PipelineState.EXPERT_OUTPUTS_READY,
    PipelineState.METADATA_FUSED,
    PipelineState.METADATA_VALIDATED,
    PipelineState.TASK_COMPILED,
    PipelineState.MODEL_OUTPUT_READY,
    PipelineState.SAMPLE_VALIDATED,
    PipelineState.RELEASE_CANDIDATE,
    PipelineState.RELEASED,
]


def _build_transitions() -> dict[PipelineState, frozenset[PipelineState]]:
    table: dict[PipelineState, set[PipelineState]] = {}
    for current, nxt in zip(_LINEAR_ORDER, _LINEAR_ORDER[1:]):
        table.setdefault(current, set()).add(nxt)
    # 任意非终态均可进入隔离或拒绝（SPEC §31）
    for state in PipelineState:
        if state in TERMINAL_STATES:
            continue
        table.setdefault(state, set()).update(
            {PipelineState.QUARANTINED, PipelineState.REJECTED}
        )
    # 隔离样本经上游重新处理后可回到 REGISTERED 重跑；不得直接跳回中间状态，
    # 因为中间产物的 provenance 已失效（SPEC §30：修复必须产生新 artifact）。
    table[PipelineState.QUARANTINED] = {
        PipelineState.REGISTERED,
        PipelineState.REJECTED,
    }
    return {state: frozenset(nxts) for state, nxts in table.items()}


#: 拓扑上允许的状态迁移。**不代表可以迁移** —— 还需门禁报告，见
#: :func:`validate_transition`。
ALLOWED_TRANSITIONS = _build_transitions()


class TransitionError(RuntimeError):
    """非法的状态迁移。"""


def can_transition(current: PipelineState, target: PipelineState) -> bool:
    """拓扑上是否允许从 ``current`` 迁移到 ``target``。"""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(
    current: PipelineState,
    target: PipelineState,
    gate_status: GateStatus | None = None,
) -> None:
    """校验一次状态迁移，非法则抛 :class:`TransitionError`。

    规则：

    1. 目标状态必须在拓扑允许集合内；
    2. 若目标状态在 :data:`GATE_FOR_STATE` 中登记了门禁，则**必须**提供
       ``gate_status``，且该状态必须允许推进（SPEC §31）；
    3. 迁入 ``QUARANTINED`` / ``REJECTED`` 不需要门禁通过 —— 它们正是门禁
       失败的去处。
    """
    if not can_transition(current, target):
        raise TransitionError(
            f"不允许的状态迁移：{current.value} -> {target.value}"
            + ("（源状态为终态）" if current in TERMINAL_STATES else "")
        )

    if target in (PipelineState.QUARANTINED, PipelineState.REJECTED):
        return

    required_gate = GATE_FOR_STATE.get(target)
    if required_gate is None:
        return

    if gate_status is None:
        raise TransitionError(
            f"迁移到 {target.value} 需要 {required_gate.value} 门禁报告；"
            "仅有状态标签不足（SPEC §31）"
        )
    if not gate_status.allows_progress:
        raise TransitionError(
            f"{required_gate.value} 门禁状态为 {gate_status.value}，不得推进到 "
            f"{target.value}；应转入 QUARANTINED 或 REJECTED"
        )
