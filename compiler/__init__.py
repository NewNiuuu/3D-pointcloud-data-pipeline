"""L2-S6 任务编译：metadata snapshot + Task Spec → Canonical Task Record。

按 2026-08-25 决定（PROJECT_HANDOFF §19.4），实现为普通代码而非 Skill。
"""
from .task_compiler import (
    CompileResult, CompilerError, IneligibleScene, TaskCompiler, project_fields,
)
from .derivations import DERIVATION_PROGRAMS, get_derivation_program

__all__ = [
    "CompileResult", "CompilerError", "IneligibleScene", "TaskCompiler",
    "project_fields", "DERIVATION_PROGRAMS", "get_derivation_program",
]
