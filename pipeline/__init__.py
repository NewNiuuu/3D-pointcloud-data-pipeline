"""L2 抽取链：从场景包到可编译的 metadata snapshot。

`extract` —— L2-S1（VGGT-Ω 几何）+ L2-S3 的最小版（语义反投影成实体）。
"""
from .segmentation import SemanticSegmenter, canonicalize
from .extract import ExtractionConfig, build_snapshot, extract_l0, extract_l1

__all__ = ["ExtractionConfig", "extract_l0", "extract_l1", "build_snapshot",
           "SemanticSegmenter", "canonicalize"]
