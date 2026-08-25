"""Adapter 基类与泄漏防护。

契约来源：SPEC §39/§41（Canonical Task Record 与三类 adapter）、铁律 6（禁止目标泄漏）。

## 为什么泄漏防护要放在基类而不是各 adapter 里

Canonical Task Record 同时装着**给模型看的输入**与**隐藏的答案**。
adapter 的职责是把前者投影成模型格式 —— 但一次疏忽就会把 `hidden_target`
或 `evidence` 带进模型可见的载荷，而这种 bug **不会报错、不会崩溃**，
只会安静地产出一批"模型能作弊的题"，直到有人发现指标好得可疑。

因此：

- :meth:`TaskAdapter.render` 是 ``final`` 语义 —— 子类实现 :meth:`_render`，
  基类在其返回值上**强制**跑一遍泄漏扫描；
- 扫描是**结构化 + 文本双重**的：既查嵌套字段名，也查答案值是否以字符串形式
  出现在问题文本里（例如 target 是 ``<obj_003>``，而问题里恰好写了它）。

绕过防护的唯一方式是不调用 :meth:`render` —— 而那会被测试抓到。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

from core.errors import ErrorCode

__all__ = [
    "AdapterError",
    "LeakageError",
    "RenderedSample",
    "TaskAdapter",
    "scan_for_leakage",
]

#: 绝不允许出现在模型可见载荷中的顶层键。
_FORBIDDEN_KEYS = frozenset({
    "hidden_target", "evidence", "checker", "target_geometry",
    "derivation_program", "derivation_inputs", "used_fields", "used_entities",
})

#: 实体 ID 的字面形式，用于文本层扫描。
_ID_RE = re.compile(r"<(?:obj|part|wire|region|route|track|pose)_\d{3,}>")


class AdapterError(RuntimeError):
    """adapter 无法完成投影（缺必需输入等）。"""


class LeakageError(AdapterError):
    """模型可见载荷中检出隐藏目标 —— 铁律 6 的硬失败。"""

    def __init__(self, message: str, findings: list[str]) -> None:
        super().__init__(message)
        self.code = ErrorCode.TARGET_LEAKAGE
        self.findings = findings


@dataclass(frozen=True)
class RenderedSample:
    """adapter 的产物。

    ``payload`` 是模型可见部分；``verification`` 是判分所需但**模型看不到**的部分。
    二者分开存放，使下游不可能"顺手"把 verification 喂给模型。
    """

    adapter: str
    sample_id: str
    payload: dict[str, Any]
    verification: dict[str, Any]
    label_paths: tuple[str, ...] = ()
    """payload 中**承载标签**（而非模型输入）的路径。

    某些训练格式要求标签与提示放在同一个文件里 —— 例如 3D-GRPO 的
    ``conversations`` 结构，其 ``gpt`` 轮就是 GT，模型在生成时看不到它。
    这类路径豁免泄漏扫描；**其余路径（尤其是提示词）照扫不误**。

    豁免必须**精确到路径**，不得整棵子树放行 —— 否则 ``human`` 轮的泄漏
    会跟着一起被放过。
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "sample_id": self.sample_id,
            "payload": self.payload,
            "verification": self.verification,
        }


def _walk(node: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, v
            yield from _walk(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = f"{path}[{i}]"
            yield p, v
            yield from _walk(v, p)


#: 字符串原子的最小长度。短于此值的字符串不参与文本扫描。
#:
#: 取 8 是因为：``left`` / ``front`` / ``water`` / ``true`` 这类枚举值本就是
#: 合法的问题与选项词汇，用它们判泄漏会淹没在假阳里。真正需要防的是
#: **特异标识**（实体 ID）与**特异短语**（如 "the southern rooftop"）。
_MIN_STRING_ATOM_LEN = 8

#: hidden_target 中**描述答案而非答案本身**的键，不参与泄漏扫描。
#:
#: 典型是 ``target_type``：它标明「这是一道最近距离题」，而非「最近的是哪个、
#: 多远」。它与 ``task_spec_id`` 天然同名，若纳入原子会把每一条记录都误判为泄漏。
_NON_ANSWER_KEYS = frozenset({"target_type", "unit", "answer_mode", "reason"})

#: **身份字段**：其取值由 Task Spec 决定，在同类任务的所有样本上完全相同。
#:
#: 常量字段在信息论上不可能携带答案 —— 它对每个样本说同样的话。
#: 但按命名约定，``task_spec_id``（如 ``3d_vqa.situated.observer_relative_direction``）
#: 常常包含推导程序名或 target 类型名，从而与这两类原子**结构性撞名**。
#: 实测已撞过两次：先是 ``target_type``（已由 :data:`_NON_ANSWER_KEYS` 排除），
#: 后是 ``evidence.derivation_program``（2026-08-25）。
#:
#: 这些字段**必须对模型可见** —— 消费方要靠它知道这是什么任务。
#: 故不参与**文本层**扫描；数值层与结构层不受影响。
_IDENTITY_PATHS = frozenset({"task_spec_id", "adapter", "sample_id"})

#: 后缀命中即视为**结构性索引**而非答案，不参与扫描。
#:
#: ``nearest_segment_index`` 是"答案落在折线第几段"的辅助定位，不是答案本身。
#: 把它当原子会让 ``0`` 这个值匹配到任何含 0 的坐标或 ID。
_NON_ANSWER_KEY_SUFFIXES = ("_index", "_count", "_id_hint")

#: 数值原子的最小字符长度。``0`` / ``1`` / ``12`` 这类小数值毫无特异性，
#: 用它们判泄漏只会命中坐标分量与 ID 中的数字。
_MIN_NUMERIC_ATOM_CHARS = 3


def _target_atoms(hidden_target: dict[str, Any]) -> set[str]:
    """把 hidden_target 拆成可在文本中检索的原子串。

    纳入原子的三类值：

    - **实体 ID**（``<obj_042>``）—— 永远特异，出现即泄漏；
    - **足够特异的数值** —— 规范化后至少 :data:`_MIN_NUMERIC_ATOM_CHARS` 位；
      米制答案出现在可见字段即泄漏，但 ``0`` / ``1`` 这类不算；
    - **足够长的字符串**（≥ :data:`_MIN_STRING_ATOM_LEN`）—— 特异短语。

    **排除**两类键下的值：:data:`_NON_ANSWER_KEYS`（描述答案的类型而非答案本身），
    以及后缀命中 :data:`_NON_ANSWER_KEY_SUFFIXES` 的结构性索引。

    **不纳入** ``evidence`` 的 ``used_fields`` / ``used_entities``：
    对 program-first 任务，这些字段与候选实体**本来就该对模型可见**
    （模型的任务正是组合它们推出答案），隐藏的只有 target 本身。
    早期版本把它们算作泄漏，产生了大量假阳。
    """
    atoms: set[str] = set()
    for path, v in _walk(hidden_target):
        key = path.split(".")[-1].split("[")[0]
        if key in _NON_ANSWER_KEYS or key.endswith(_NON_ANSWER_KEY_SUFFIXES):
            continue
        if isinstance(v, str):
            if _ID_RE.fullmatch(v) or len(v) >= _MIN_STRING_ATOM_LEN:
                atoms.add(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            text = f"{float(v):.6g}"
            if len(text.lstrip("-")) >= _MIN_NUMERIC_ATOM_CHARS:
                atoms.add(text)
    return atoms


def scan_for_leakage(
    payload: Any,
    hidden_target: dict[str, Any],
    evidence: dict[str, Any] | None = None,
    exempt_paths: Iterable[str] = (),
) -> list[str]:
    """扫描模型可见载荷中的泄漏，返回问题描述列表（空表示干净）。

    三层检查：

    1. **结构层** —— 载荷中不得出现 :data:`_FORBIDDEN_KEYS` 里的键；
    2. **值层** —— hidden_target 的值不得作为载荷中任一字段的值原样出现；
    3. **文本层** —— hidden_target 的原子串不得出现在载荷的任何字符串里
       （典型场景：问题文本里写了正确答案的实体 ID）。

    两处刻意的豁免，否则会淹没在假阳里：

    - ``exempt_paths`` 列出的**精确路径**不参与扫描 —— 用于标签与提示同文件的
      训练格式（如 3D-GRPO 的 ``gpt`` 轮）。豁免精确到路径，不放行整棵子树；
    - ``choices`` 子树不参与文本扫描 —— 单选题的正确答案必在选项之中；
    - :data:`_IDENTITY_PATHS` 列出的**身份字段**不参与文本扫描 ——
      它们在同类任务的所有样本上取值相同，常量不可能携带答案；
    - 短于 :data:`_MIN_STRING_ATOM_LEN` 的字符串不作原子 ——
      ``left`` / ``water`` 这类枚举值本就是合法词汇。
    """
    findings: list[str] = []
    exempt = set(exempt_paths)
    atoms = _target_atoms(hidden_target)
    if evidence:
        # 只防推导程序名泄漏；used_fields / used_entities 对 program-first
        # 任务本就该可见，见 _target_atoms 的说明。
        prog = evidence.get("derivation_program")
        if isinstance(prog, str) and len(prog) >= _MIN_STRING_ATOM_LEN:
            atoms.add(prog)

    for path, value in _walk(payload):
        # choices 子树豁免文本扫描：单选题的定义就是正确答案必在选项之中。
        # 需要防的是**问题文本**泄漏「哪一个」是对的，那由下面的其余路径覆盖。
        if path == "choices" or path.startswith("choices["):
            continue
        if path in exempt:
            continue
        leaf = path.split(".")[-1].split("[")[0]
        if leaf in _FORBIDDEN_KEYS:
            findings.append(f"载荷含禁用键 {path!r}")
        if isinstance(value, str):
            if leaf in _IDENTITY_PATHS:
                continue                       # 身份字段：常量，不可能泄漏答案
            for atom in atoms:
                if atom in value:
                    findings.append(f"{path!r} 的文本中出现隐藏目标片段 {atom!r}")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if f"{float(value):.6g}" in atoms:
                findings.append(f"{path!r} 的数值 {value} 与隐藏目标一致")
    return findings


class TaskAdapter(ABC):
    """把 Canonical Task Record 投影为特定模型的输入。

    子类实现 :meth:`_render`；**不要覆写** :meth:`render` —— 那会绕过泄漏防护。
    """

    name: str = "base"

    @abstractmethod
    def _render(self, record: dict[str, Any]) -> RenderedSample:
        """子类实现：产出模型格式的样本。"""

    def supports(self, record: dict[str, Any]) -> bool:
        return self.name in (record.get("adapters") or [])

    def render(self, record: dict[str, Any]) -> RenderedSample:
        """投影并**强制**执行泄漏检查。"""
        if not self.supports(record):
            raise AdapterError(
                f"记录 {record.get('sample_id')} 未声明支持 adapter {self.name!r}；"
                f"已声明：{record.get('adapters')}")

        sample = self._render(record)

        if sample.adapter != self.name:
            raise AdapterError(
                f"adapter 名称不一致：{sample.adapter!r} != {self.name!r}")

        # 编译器登记的「结构性必需可见」ID 不参与扫描 —— 见记录 schema 中
        # structurally_visible_target_ids 的说明。
        structural = set(record.get("structurally_visible_target_ids") or [])
        target = {k: v for k, v in (record.get("hidden_target") or {}).items()
                  if v not in structural}
        findings = scan_for_leakage(
            sample.payload, target, record.get("evidence"),
            exempt_paths=sample.label_paths)
        if findings:
            raise LeakageError(
                f"adapter {self.name!r} 在样本 {record.get('sample_id')} 的可见载荷中"
                f"检出 {len(findings)} 处泄漏", findings)
        return sample

    # ---------- 子类可复用的工具 ----------

    @staticmethod
    def _require(record: dict[str, Any], path: str) -> Any:
        node: Any = record
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise AdapterError(f"记录缺少必需字段 {path!r}")
            node = node[part]
        if node is None:
            raise AdapterError(f"记录字段 {path!r} 为 null，但本 adapter 必需")
        return node

    @staticmethod
    def _verification_block(record: dict[str, Any]) -> dict[str, Any]:
        """判分所需信息。**与 payload 分开返回，绝不合并。**"""
        return {
            "hidden_target": record.get("hidden_target"),
            "checker": record.get("checker"),
            "evidence": record.get("evidence"),
            "target_geometry": record.get("target_geometry"),
            "ambiguity": record.get("ambiguity"),
            "task_spec_id": record.get("task_spec_id"),
        }
