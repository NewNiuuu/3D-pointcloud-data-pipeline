"""稳定 ID 命名空间。

契约来源：DESIGN.md §15。

ID 是语言输出与点云实体之间的唯一接口：模型输出 ID，系统据此映射回
点云实例 mask、OBB、中心线或轨迹。因此 ID 格式必须冻结，且在一个
metadata snapshot 内保持稳定（SPEC §15）。

设计决定：
- 采用 ``<ns_NNN>`` 形式（尖括号包裹），与 SPEC §15 给出的字面形式一致。
  尖括号使 ID 在自然语言提示词中可被无歧义地识别与提取。
- 序号零填充至 3 位，超过 999 时自然增长为 4 位，不重置、不复用。
- ID 在 snapshot 内不可变；实体分裂/合并时**分配新 ID**并记录血缘
  （SPEC §15：cross-version ID lineage SHOULD be recorded）。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterator

__all__ = [
    "Namespace",
    "ID_PATTERN",
    "format_id",
    "parse_id",
    "is_valid_id",
    "IdMinter",
]


class Namespace(str, Enum):
    """SPEC §15 定义的稳定 ID 命名空间。

    不得在此之外自行发明命名空间；新增需同步修改 SPEC §15。
    """

    OBJECT = "obj"      # 一般对象
    PART = "part"       # 对象部件
    WIRE = "wire"       # 细线状障碍（电线、缆索、枝条）
    REGION = "region"   # 空间区域
    ROUTE = "route"     # 候选航迹
    TRACK = "track"     # 时序轨迹
    POSE = "pose"       # 相机 / 观察者位姿

    def __str__(self) -> str:  # pragma: no cover - 仅便于日志输出
        return self.value


#: 匹配 ``<obj_021>`` 形式。序号至少 3 位，允许更多位以支持大场景。
ID_PATTERN = re.compile(
    r"^<(?P<ns>" + "|".join(ns.value for ns in Namespace) + r")_(?P<num>\d{3,})>$"
)


def format_id(namespace: Namespace | str, index: int) -> str:
    """构造稳定 ID。

    >>> format_id(Namespace.OBJECT, 21)
    '<obj_021>'
    >>> format_id("wire", 4)
    '<wire_004>'
    """
    ns = Namespace(namespace)
    if index < 0:
        raise ValueError(f"ID 序号不得为负：{index}")
    return f"<{ns.value}_{index:03d}>"


def parse_id(entity_id: str) -> tuple[Namespace, int]:
    """解析稳定 ID，返回 ``(命名空间, 序号)``。

    >>> parse_id("<track_011>")
    (<Namespace.TRACK: 'track'>, 11)
    """
    match = ID_PATTERN.match(entity_id)
    if match is None:
        raise ValueError(f"非法实体 ID：{entity_id!r}（期望形如 '<obj_021>'）")
    return Namespace(match.group("ns")), int(match.group("num"))


def is_valid_id(entity_id: str, namespace: Namespace | str | None = None) -> bool:
    """校验 ID 合法性；给定 ``namespace`` 时同时校验命名空间是否匹配。"""
    try:
        ns, _ = parse_id(entity_id)
    except ValueError:
        return False
    return namespace is None or ns == Namespace(namespace)


class IdMinter:
    """单个 snapshot 内的 ID 分配器。

    序号在每个命名空间内单调递增，**不复用已回收的序号** —— 复用会让
    跨版本血缘无法追溯（SPEC §15）。
    """

    def __init__(self, start: dict[Namespace, int] | None = None) -> None:
        self._next: dict[Namespace, int] = {ns: 0 for ns in Namespace}
        if start:
            for ns, value in start.items():
                self._next[Namespace(ns)] = value

    def mint(self, namespace: Namespace | str) -> str:
        """分配下一个 ID。"""
        ns = Namespace(namespace)
        entity_id = format_id(ns, self._next[ns])
        self._next[ns] += 1
        return entity_id

    def mint_many(self, namespace: Namespace | str, count: int) -> Iterator[str]:
        for _ in range(count):
            yield self.mint(namespace)

    def reserve(self, entity_id: str) -> None:
        """登记一个外部已存在的 ID，确保后续分配不与之冲突。"""
        ns, index = parse_id(entity_id)
        self._next[ns] = max(self._next[ns], index + 1)

    def state(self) -> dict[str, int]:
        """导出当前计数器，便于写入 artifact 以支持增量续分配。"""
        return {ns.value: value for ns, value in self._next.items()}
