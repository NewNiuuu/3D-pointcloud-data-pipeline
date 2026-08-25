"""L2-S3：实例边界与语义类别的融合 —— 两个教师各出自己擅长的那一半。

**为什么需要这一层**（2026-08-25 负控实验后确立，见 FINDINGS）：

Grounded-SAM 与 OneFormer 各自都不完整：

==================  ==============================  ==========================
                    Grounded-SAM-2                  OneFormer
==================  ==============================  ==========================
「哪一个」（边界）    ✅ 逐实例 mask                   ❌ 只有稠密语义，无实例
「是什么」（类别）    ❌ **实测无判别力**              ✅ 类别可信
==================  ==============================  ==========================

Grounding DINO 那一栏的 ❌ 是实测出来的：往提示词表里掺入画面中不可能存在的概念
（北极熊、恐龙、热气球），**它们的检出率与真实概念持平**（判别比 ≈ 1.0，
逐条单独送时 ``a dinosaur`` 峰值 0.610 压过 12 条真实词里的 10 条）。
也就是说它的短语得分回答不了「这个概念在不在」，只能回答
「在给定的这些短语里，哪一条最贴」。

于是分工就定死了：**边界（哪一个）取 Grounded-SAM，类别（是什么）取 OneFormer。**
GDINO 的短语只作为 ``label_proposed`` 留在血缘里备查，**不进 ``category``**。

**这不是妥协，是 §0.7 第二层的融合**：两个教师能力的并集，
且它们的**分歧**（``category_agrees``）是第三层信号 ——
单个教师给不出「我这个实例的类别有争议」。

**质量信号 ``category_purity``**：mask 内像素落在胜出类别上的比例。
0.95 说明实例干净；0.55 说明这个 mask 横跨了两类地物（框歪了或语义错了），
下游可以据此丢弃或降权。**这是可复算测量，不是观点**（§40.5 机制 1）。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from pipeline.segmentation import canonicalize

__all__ = ["FusedInstance", "fuse_instances"]


class FusedInstance(dict):
    """融合后的实例。刻意用 dict 子类 —— 直接就是 artifact 里那一条记录。"""


def fuse_instances(instances: Sequence[Any], seg_canonical: np.ndarray,
                   canonical_names: Sequence[str],
                   *, min_purity: float = 0.0,
                   ignore_classes: Sequence[str] = ("sky",),
                   ) -> list[FusedInstance]:
    """给每个实例定类别。

    :param instances: :class:`pipeline.grounded_sam.Instance` 列表
    :param seg_canonical: OneFormer 的项目类别图 ``(H, W) int``，**必须与 mask 同形**
    :param canonical_names: 类别名列表，索引对应 ``seg_canonical`` 的取值
    :param min_purity: 低于此纯度的实例直接丢弃。默认 0 = 全留，由下游决定
    :param ignore_classes: 投票时排除的类别（``sky`` 的深度不可信，§14.5）

    类别由 mask 内像素**多数投票**决定，而非取 mask 中心点 ——
    中心点在细长物体（杆、电线）上经常落在背景里。
    """
    names = list(canonical_names)
    ignore_idx = {names.index(c) for c in ignore_classes if c in names}

    out: list[FusedInstance] = []
    for inst in instances:
        mask = inst.mask
        if mask.shape != seg_canonical.shape:
            raise ValueError(
                f"mask {mask.shape} 与语义图 {seg_canonical.shape} 不同形 —— "
                "调用方必须先把两者对齐到同一分辨率（见 GroundedSAM.ground 的 target_hw）")
        vals = seg_canonical[mask]
        vals = vals[~np.isin(vals, list(ignore_idx))] if ignore_idx else vals
        if vals.size == 0:
            continue
        counts = np.bincount(vals.astype(np.int64), minlength=len(names))
        win = int(counts.argmax())
        purity = float(counts[win] / counts.sum())
        if purity < min_purity:
            continue

        proposed = canonicalize(inst.label)
        out.append(FusedInstance({
            # 类别只认 OneFormer —— GDINO 的短语不进这里，理由见模块 docstring
            "category": names[win],
            "category_purity": round(purity, 4),
            "category_source": "oneformer_majority_vote",
            # GDINO 的提议只作血缘留存
            "label_proposed": inst.label,
            "label_proposed_canonical": proposed,
            "category_agrees": proposed == names[win],
            "box": [float(v) for v in inst.box],
            "mask_pixels": int(mask.sum()),
            # §14.1：两个置信度分开存，不合成
            "confidence": {
                "detection": round(float(inst.score_detection), 4),
                "mask": round(float(inst.score_mask), 4),
                "calibrated": False,      # §14.13：未标定，不得当概率用
            },
            "provenance": {
                "boundary_from": "grounded_sam2::gdino_base+sam2.1_hiera_bplus",
                "category_from": "oneformer_ade20k_swin_large",
                "derivation_program": "instance_boundary_semantic_majority_vote",
                "supervision_level": "model_derived",
            },
        }))
    return out
