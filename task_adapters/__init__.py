"""三类 adapter：把 Canonical Task Record 投影为各模型的输入（SPEC §39/§41）。"""
from .base import (
    AdapterError, LeakageError, RenderedSample, TaskAdapter, scan_for_leakage,
)
from .adapters import (
    ADAPTER_REGISTRY, Multimodal3DAdapter, PointcloudNativeAdapter,
    Qwen2DMetadataAdapter, get_adapter,
)

__all__ = [
    "AdapterError", "LeakageError", "RenderedSample", "TaskAdapter", "scan_for_leakage",
    "ADAPTER_REGISTRY", "Multimodal3DAdapter", "PointcloudNativeAdapter",
    "Qwen2DMetadataAdapter", "get_adapter",
]
