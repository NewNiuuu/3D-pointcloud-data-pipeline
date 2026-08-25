"""L2-S2：语义分割专家 —— 让 L1 实体不再依赖数据集自带的人工标注。

**为什么必须有这一步**（铁律 14）：
`extract_l1` 的第一版直接消费 UAVScenes 的逐像素人工标注。那在本数据集上省事，
但换一个没有语义标注的数据集就断了 —— 方法就不可移植了，这正是铁律 14 要防的。
本模块用**模型**产出同样形态的稠密语义图，使整条链回到「只要有图就能跑」。

**为什么用 OneFormer 而不是 Grounded-SAM**：
航拍画面的主体是**水面、植被、裸地、硬化面**这类 *stuff*（无定形、不可数），
不是 *things*（可数物体）。Grounding DINO 出的是框，对 stuff 不好使；
语义分割才是对的工具。Grounded-SAM 留给「指认某个具体物体」那类任务。

**关于 OneFormer 的加载警告**（2026-08-25 已验证）：
`transformers 5.15.1` 加载时报 `swin.layernorm.weight/bias` MISSING（随机初始化）。
实测该模块**虽被调用但输出被丢弃** —— 把它的权重改成 7.0/-3.0 后，
`class_queries_logits` 与 `masks_queries_logits` 变化**恰为 0**。
OneFormer 取的是 Swin 的特征金字塔中间层，不是池化输出。**缺失无害。**

**类别体系**：不直接用 ADE20K 的 150 类，而是按**下游能力需要什么**归并
（§0.3 反向证成）—— C2 判可降落必须区分水面/植被/硬化面，
C3 的地形推理需要自然地表与建筑分开。原始标签保留在 `category_raw` 里备查。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

__all__ = ["SemanticSegmenter", "CANONICAL_CLASSES", "canonicalize"]

#: 项目级类别。**每一类都得指名它服务哪个下游能力**，否则不该存在。
CANONICAL_CLASSES: dict[str, str] = {
    "water":          "C2 可降落性的头号排除项；C1 的天然失效样本",
    "vegetation":     "C2：树冠不可降落；C3：冠层高度",
    "ground_natural": "C2 的主要候选面（裸地、草地、土坡）",
    "ground_paved":   "C2 的最优候选面（硬化面）；C1 的均质弱纹理失效样本",
    "building":       "C2 排除项（屋顶平但不可降落）；C3 结构对地高度",
    "structure":      "杆、栏杆、围墙等 —— C2 的障碍物",
    "vehicle":        "C2 动态占用",
    "person":         "**C2 的硬排除项** —— 人群上方也是平的。2026-08-25 实测发现 "
                      "person 曾落进 other，那等于把最危险的降落区判成候选",
    "sky":            "几何无效区（§14.5 的 sky 原因码）",
    "other":          "未归入上述的一切。**占比过高说明映射需要补**",
}

#: ADE20K 标签 → 项目类别。**按关键词匹配，顺序敏感**（先匹配到的胜出）。
#:
#: 用关键词而非逐个枚举 150 类：ADE20K 的标签本身是英文短语
#: （``"water"``、``"tree"``、``"sidewalk, pavement"``），关键词规则可读、可维护，
#: 换成别的分割模型（COCO-Stuff、Cityscapes）时改动最小。
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("sky",            ("sky",)),
    ("water",          ("water", "sea", "lake", "river", "pool", "waterfall")),
    ("vegetation",     ("tree", "plant", "grass", "flower", "palm", "bush", "field")),
    ("building",       ("building", "house", "skyscraper", "hut", "tower", "roof")),
    # person 必须排在 vehicle 之前独立成类：C2 判可降落时它是硬排除项，
    # 归进 other 会让「人群上方」被当成候选面（2026-08-25 实测踩到）。
    ("person",         ("person", "man", "woman", "child", "crowd")),
    ("vehicle",        ("car", "truck", "bus", "van", "boat", "ship", "bicycle",
                        "motorbike", "airplane", "minibike")),
    ("ground_paved",   ("road", "sidewalk", "pavement", "runway", "path", "floor",
                        "court", "parking")),
    ("ground_natural", ("earth", "ground", "sand", "dirt", "land", "hill",
                        "mountain", "mount", "rock", "stone")),
    # 台阶、长椅、雕塑这类「街道家具」都是障碍物 —— 对 C2 与 structure 同性质。
    # 2026-08-25 补：它们原先落进 other，而 other 是不该出现在可降落候选里的。
    ("structure",      ("fence", "pole", "railing", "wall", "bridge", "bannister",
                        "column", "rail", "signboard", "streetlight",
                        "stair", "step", "bench", "table", "chair", "sculpture",
                        "trash", "door", "awning", "booth", "kiosk")),
]


def canonicalize(raw_label: str) -> str:
    """ADE20K 标签 → 项目类别。命中不了归 ``other``。"""
    low = raw_label.lower()
    for canon, keys in _RULES:
        if any(k in low for k in keys):
            return canon
    return "other"


@dataclass
class SegmentationResult:
    """一帧的分割结果。

    ``canonical`` 与 ``raw`` 同形，前者是项目类别的整数编码，
    后者是模型原生标签 id —— 两个都留，便于事后换类别体系而不用重跑模型。
    """

    canonical: np.ndarray          # (H, W) int16，索引对应 canonical_names
    raw: np.ndarray                # (H, W) int16，模型原生 label id
    canonical_names: list[str]
    raw_id2label: dict[int, str]


class SemanticSegmenter:
    """OneFormer 语义分割封装。一次加载，多帧复用。

    典型用法::

        seg = SemanticSegmenter(device="cuda")
        results = seg.segment(["a.jpg", "b.jpg"], target_hw=(464, 560))
    """

    MODEL_ID = "shi-labs/oneformer_ade20k_swin_large"
    VERSION = "oneformer_ade20k_swin_large"

    def __init__(self, device: str = "cuda", model_id: str | None = None) -> None:
        import torch
        from transformers import AutoProcessor, OneFormerForUniversalSegmentation

        self._torch = torch
        self.model_id = model_id or self.MODEL_ID
        self.device = device
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = (OneFormerForUniversalSegmentation
                      .from_pretrained(self.model_id).to(device).eval())
        self.raw_id2label = {int(k): v for k, v in self.model.config.id2label.items()}
        self.canonical_names = list(CANONICAL_CLASSES)
        self._raw_to_canon_idx = np.array(
            [self.canonical_names.index(canonicalize(self.raw_id2label[i]))
             for i in range(len(self.raw_id2label))], dtype=np.int16)

    # ------------------------------------------------------------------

    def segment(self, image_paths: Sequence[str],
                target_hw: tuple[int, int] | None = None,
                ) -> list[SegmentationResult]:
        """逐帧分割。``target_hw`` 给定时按最近邻缩放到该尺寸。

        **必须最近邻**：语义 id 是标称量，双线性插值会在类别边界造出
        根本不存在的中间类别。
        """
        from PIL import Image

        out: list[SegmentationResult] = []
        for path in image_paths:
            img = Image.open(path).convert("RGB")
            inputs = self.processor(images=img, task_inputs=["semantic"],
                                    return_tensors="pt").to(self.device)
            with self._torch.inference_mode():
                pred = self.model(**inputs)
            raw = self.processor.post_process_semantic_segmentation(
                pred, target_sizes=[img.size[::-1]])[0].cpu().numpy().astype(np.int16)

            if target_hw is not None and raw.shape != tuple(target_hw):
                raw = np.array(
                    Image.fromarray(raw.astype(np.int32)).resize(
                        (target_hw[1], target_hw[0]), Image.NEAREST),
                    dtype=np.int16)

            out.append(SegmentationResult(
                canonical=self._raw_to_canon_idx[raw],
                raw=raw,
                canonical_names=self.canonical_names,
                raw_id2label=self.raw_id2label,
            ))
        return out

    # ------------------------------------------------------------------

    def expert_ref(self) -> dict[str, Any]:
        """供 artifact provenance 引用的模型标识（§14.8 的 model_ref 契约）。"""
        return {
            "name": "OneFormer",
            "version": self.VERSION,
            "precision": "fp32",
            "expert_card": "registry/experts/oneformer_ade20k_swin_large.yaml",
        }
