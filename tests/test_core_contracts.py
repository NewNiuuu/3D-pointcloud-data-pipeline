"""冻结契约的单元测试。

这些测试的作用不是"验证代码能跑"，而是**锁住架构铁律**：任何让它们失败的
改动都意味着契约被放宽，必须先改 SPEC。
"""

from __future__ import annotations

import pytest

from core import (
    Artifact,
    ArtifactKind,
    DepthType,
    ErrorCode,
    Gate,
    GateStatus,
    IdMinter,
    Namespace,
    PipelineState,
    Severity,
    SupervisionLevel,
    TransitionError,
    default_status,
    describe,
    format_id,
    is_valid_id,
    parse_id,
    supports_absolute_metric_target,
    validate_transition,
)
from core.errors import ERROR_CATALOG


# ---------------------------------------------------------------- IDs

class TestIds:
    def test_format_matches_spec_literal(self):
        """SPEC §15 给出的字面形式必须原样可复现。"""
        assert format_id(Namespace.OBJECT, 21) == "<obj_021>"
        assert format_id(Namespace.PART, 6) == "<part_006>"
        assert format_id(Namespace.WIRE, 4) == "<wire_004>"
        assert format_id(Namespace.REGION, 9) == "<region_009>"
        assert format_id(Namespace.ROUTE, 2) == "<route_002>"
        assert format_id(Namespace.TRACK, 11) == "<track_011>"
        assert format_id(Namespace.POSE, 7) == "<pose_007>"

    def test_roundtrip(self):
        for ns in Namespace:
            assert parse_id(format_id(ns, 42)) == (ns, 42)

    def test_index_beyond_999_grows(self):
        assert format_id(Namespace.OBJECT, 1234) == "<obj_1234>"
        assert parse_id("<obj_1234>") == (Namespace.OBJECT, 1234)

    @pytest.mark.parametrize("bad", [
        "obj_021",        # 缺尖括号
        "<obj_21>",       # 位数不足
        "<thing_021>",    # 未知命名空间
        "<obj_021> ",     # 尾随空格
        "<OBJ_021>",      # 大写
        "",
    ])
    def test_rejects_malformed(self, bad):
        assert not is_valid_id(bad)
        with pytest.raises(ValueError):
            parse_id(bad)

    def test_namespace_scoped_validation(self):
        assert is_valid_id("<wire_004>", Namespace.WIRE)
        assert not is_valid_id("<wire_004>", Namespace.OBJECT)

    def test_minter_never_reuses_index(self):
        """序号复用会破坏跨版本血缘（SPEC §15）。"""
        minter = IdMinter()
        first = [minter.mint(Namespace.OBJECT) for _ in range(3)]
        assert first == ["<obj_000>", "<obj_001>", "<obj_002>"]
        minter.reserve("<obj_010>")
        assert minter.mint(Namespace.OBJECT) == "<obj_011>"
        assert minter.state()["obj"] == 12

    def test_minter_namespaces_are_independent(self):
        minter = IdMinter()
        assert minter.mint(Namespace.OBJECT) == "<obj_000>"
        assert minter.mint(Namespace.WIRE) == "<wire_000>"


# ---------------------------------------------------------------- 状态机

class TestStateMachine:
    def test_linear_progress_requires_gate_report(self):
        """SPEC §31：仅有状态标签不足以迁移。"""
        with pytest.raises(TransitionError, match="门禁报告"):
            validate_transition(PipelineState.INGESTED, PipelineState.GEOMETRY_READY)

        validate_transition(
            PipelineState.INGESTED, PipelineState.GEOMETRY_READY, GateStatus.PASS
        )

    def test_warn_allows_progress_but_quarantine_does_not(self):
        validate_transition(
            PipelineState.INGESTED, PipelineState.GEOMETRY_READY, GateStatus.WARN
        )
        for blocking in (GateStatus.QUARANTINE, GateStatus.REJECT):
            with pytest.raises(TransitionError, match="不得推进"):
                validate_transition(
                    PipelineState.INGESTED, PipelineState.GEOMETRY_READY, blocking
                )

    def test_cannot_skip_stages(self):
        with pytest.raises(TransitionError, match="不允许的状态迁移"):
            validate_transition(
                PipelineState.INGESTED, PipelineState.TASK_COMPILED, GateStatus.PASS
            )

    def test_quarantine_reachable_from_any_nonterminal_state(self):
        for state in PipelineState:
            if state in (PipelineState.RELEASED, PipelineState.REJECTED,
                         PipelineState.QUARANTINED):
                continue
            validate_transition(state, PipelineState.QUARANTINED)

    def test_quarantined_reruns_from_registered_not_midway(self):
        """隔离后必须重跑，不得跳回中间态 —— 中间产物 provenance 已失效。"""
        validate_transition(PipelineState.QUARANTINED, PipelineState.REGISTERED)
        with pytest.raises(TransitionError):
            validate_transition(
                PipelineState.QUARANTINED, PipelineState.GEOMETRY_READY, GateStatus.PASS
            )

    def test_terminal_states_are_terminal(self):
        for terminal in (PipelineState.RELEASED, PipelineState.REJECTED):
            with pytest.raises(TransitionError, match="终态"):
                validate_transition(terminal, PipelineState.QUARANTINED)

    def test_only_four_gate_statuses(self):
        """SPEC §27 只允许四种状态。"""
        assert {s.value for s in GateStatus} == {
            "pass", "warn", "quarantine", "reject"}


# ---------------------------------------------------------------- 枚举

class TestScaleDiscipline:
    @pytest.mark.parametrize("depth_type", [
        DepthType.RELATIVE, DepthType.AFFINE_INVARIANT, DepthType.PSEUDO,
    ])
    def test_non_metric_never_supports_absolute_targets(self, depth_type):
        """铁律 8/9：相对与伪深度永远不得产出绝对米制目标。"""
        assert not supports_absolute_metric_target(
            depth_type, domain_calibrated=True, anchor_provenance_verified=True
        )

    def test_metric_requires_domain_calibration(self):
        """SPEC §14.11：model card 写 metric 不等于 UAV 域尺度可信。"""
        assert not supports_absolute_metric_target(DepthType.METRIC)
        assert supports_absolute_metric_target(
            DepthType.METRIC, domain_calibrated=True)

    def test_externally_anchored_requires_verified_provenance(self):
        assert not supports_absolute_metric_target(DepthType.EXTERNALLY_ANCHORED)
        assert supports_absolute_metric_target(
            DepthType.EXTERNALLY_ANCHORED, anchor_provenance_verified=True)

    def test_supervision_levels_eligible_for_evaluation(self):
        """SPEC §42：只有强监督与程序派生适合直接做评测数据。"""
        assert SupervisionLevel.STRONG.eligible_for_evaluation
        assert SupervisionLevel.DETERMINISTIC_DERIVED.eligible_for_evaluation
        assert not SupervisionLevel.FILTERED_PSEUDO.eligible_for_evaluation
        assert not SupervisionLevel.WEAK.eligible_for_evaluation
        assert not SupervisionLevel.LANGUAGE_GENERATED.eligible_for_evaluation


# ---------------------------------------------------------------- 错误码

class TestErrorCodes:
    def test_every_code_has_catalog_entry(self):
        missing = [c for c in ErrorCode if c not in ERROR_CATALOG]
        assert not missing, f"缺少目录条目：{missing}"

    def test_code_value_matches_catalog_and_gate_prefix(self):
        for code, spec in ERROR_CATALOG.items():
            assert code.value == spec.code
            assert spec.code.startswith(spec.gate.value + "-")

    def test_hard_and_stop_never_allow_progress(self):
        """硬失败不得被加权总分抵消（SPEC §27）。"""
        for code, spec in ERROR_CATALOG.items():
            status = default_status(code)
            if spec.severity in (Severity.HARD, Severity.STOP):
                assert not status.allows_progress, code
            else:
                assert status is GateStatus.WARN, code

    def test_stop_conditions_are_registered(self):
        """SPEC §35 的停止条件必须有对应错误码。"""
        stops = {c for c, s in ERROR_CATALOG.items() if s.severity is Severity.STOP}
        assert ErrorCode.LICENSE_BLOCKS_INTENDED_USE in stops
        assert ErrorCode.QUALITY_THRESHOLD_LOWERING_REQUIRED in stops
        assert ErrorCode.EXPERT_NOT_APPROVED_FOR_USE in stops

    def test_leakage_and_metric_violations_are_hard(self):
        for code in (ErrorCode.TARGET_LEAKAGE,
                     ErrorCode.METRIC_TASK_ON_NONMETRIC_SCENE,
                     ErrorCode.SPLIT_LEAKAGE,
                     ErrorCode.THREE_D_NECESSITY_FAILED):
            assert describe(code).severity is Severity.HARD


# ---------------------------------------------------------------- Artifact

class TestArtifact:
    def _make(self) -> Artifact:
        return Artifact(kind=ArtifactKind.SCENE_MANIFEST, payload={"a": 1},
                        dataset_id="uavscenes")

    def test_auto_id_uses_kind_prefix(self):
        art = self._make()
        assert art.artifact_id.startswith("scene_manifest_")

    def test_is_immutable(self):
        art = self._make()
        with pytest.raises(Exception):
            art.payload_digest = "x"  # type: ignore[misc]

    def test_derive_chains_lineage_and_mints_new_id(self):
        """SPEC §30：修复与重生成必须产生新 artifact。"""
        first = self._make()
        second = first.derive(payload={"a": 2})
        third = second.derive(payload={"a": 3})
        assert second.artifact_id != first.artifact_id
        assert second.parent_ids == (first.artifact_id,)
        assert third.parent_ids == (first.artifact_id, second.artifact_id)
        assert first.payload == {"a": 1}  # 原件未被改动

    def test_digest_is_order_independent(self):
        a = Artifact(kind=ArtifactKind.SCENE_MANIFEST, payload={"x": 1, "y": 2})
        b = Artifact(kind=ArtifactKind.SCENE_MANIFEST, payload={"y": 2, "x": 1})
        assert a.payload_digest == b.payload_digest

    def test_write_refuses_to_overwrite(self, tmp_path):
        """SPEC §30 禁止静默覆盖。"""
        target = tmp_path / "scene.json"
        self._make().write(target)
        with pytest.raises(FileExistsError, match="禁止静默覆盖"):
            self._make().write(target)
