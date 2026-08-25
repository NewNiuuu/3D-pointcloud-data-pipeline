"""L2-S2：Grounded-SAM-2 —— 开放词表**实例**分割。

与 :mod:`pipeline.segmentation`（OneFormer）是**互补**关系，不是替代关系：

===========  ==========================  ==========================
             OneFormer（语义分割）        Grounded-SAM-2（本模块）
===========  ==========================  ==========================
擅长          *stuff*：水面、植被、硬化面   *things*：车、人、杆、船
输出          稠密语义图，**无实例边界**    逐实例 mask + 名词短语
词表          固定 150 类 → 归并 10 类     **开放词表**（任意名词短语）
两辆并排的车   合成一个连通域              分成两个实例
===========  ==========================  ==========================

**为什么必须有这一层**（§0.3 反向证成，每条都指名下游能力）：

1. **Grounding 任务族（Release A / ``grounding/object_v1``）需要「可指称的个体」。**
   当前 ``extract_l1`` 的实体来自语义图的连通域 —— 那是个凑合：
   「vehicle」不是指称表达式，两辆挨着的车是同一个连通域，
   「最远的那个 vehicle」在这种候选集里没有意义。
2. **C2 的硬排除项需要计数。** ``segmentation.py`` 里写了「人群上方也是平的」，
   但语义图只能告诉你「这片是 person」，说不出**几个人**。
3. **跨视角对应（``cross_view_correspondence_v1``）需要实例身份。** stuff 没有身份。
4. **R-30 薄障碍的零样本兜底。** PowerLine-MTYOLO 卡在 A-YOLOM fork 上
   （见 ``registry/experts/powerline_mtyolo_nano.yaml``），
   文本提示 ``"power line"`` 是当前**唯一可部署**的路径 —— 精度未知，但能跑。
5. **开放词表是逃生口。** 归并后的 10 类是封闭集合；grounding 任务要的是任意名词短语。

**版本选择：为什么是 Grounded-SAM-2 而不是别的**（2026-08-25 核）：

- ``IDEA-Research/Grounded-SAM-2`` v1.0 仍是该系列**最新 tagged release**，Apache-2.0；
  初代 Grounded-Segment-Anything 用的是 SAM 1，已被它取代。
- Grounding DINO **1.5 / 1.6 Pro** 更强，但**只有 API、不放权重**，
  离线管线用不了 —— 因此检测端取开放权重里最新最大的 ``grounding-dino-base``。
- 不 clone 官方 repo，改用 **transformers 原生实现**
  （``GroundingDinoForObjectDetection`` + ``Sam2Model``）：官方 repo 的 GroundingDINO
  要编译 CUDA 自定义算子 ``_C``，会把本已脆弱的 numpy/torch 依赖再搅一遍（规则 3）。
  架构与权重完全一致，差别只在 runtime。
- **SAM 3**（2025-11）是另一条路线：单模型直接做「概念提示分割」，
  等于把 Grounded-SAM 两段合成一段。许可已核（见 FINDINGS），学术可用，
  但它不是「Grounded-SAM 的最新版」，另行评估。

**§14.1 的两条强制约束，本模块严格遵守**：

1. **检测置信度与 mask 置信度分开存**（``confidence.detection`` / ``confidence.mask``）——
   两者衡量的是不同的东西：前者是「这里有没有这个概念」，后者是「边界准不准」。
   合成一个数就没法在下游区分「认错了」与「认对了但描歪了」。
2. **绝不把框内像素整体提升到 3D。** 反投影只用 mask 内的像素。
   俯视图里一个框内往往有大片背景（车框里全是路面），
   整框提升会把路面的深度算进车的质心。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

__all__ = ["GroundedSAM", "Instance", "UAV_THING_PROMPTS", "build_prompt_text",
           "phrase_token_spans"]


def build_prompt_text(phrases: Sequence[str]) -> str:
    """按 Grounding DINO 要求拼提示词：小写、``". "`` 分隔、结尾带 ``"."``。"""
    return ". ".join(p.lower().strip(" .") for p in phrases) + "."


def phrase_token_spans(text: str, phrases: Sequence[str],
                       offsets: Sequence[tuple[int, int]]) -> list[list[int]]:
    """每条短语在 tokenize 结果里占哪些 token 下标。

    ``offsets`` 是 fast tokenizer 的 ``offset_mapping``（字符区间）。
    特殊 token 的区间是 ``(0, 0)``，被 ``b > a`` 条件排除。

    单独拎出来是为了可测 —— 短语归属出错时标签会串（见 :meth:`GroundedSAM.detect`），
    而那种错在集成测试里表现得很隐蔽。
    """
    spans: list[list[int]] = []
    cursor = 0
    for p in phrases:
        start = text.index(p, cursor)
        end = start + len(p)
        cursor = end
        spans.append([i for i, (a, b) in enumerate(offsets)
                      if a < end and b > start and b > a])
    return spans

#: 低空俯视场景的默认提示词表。**每条都得指名它服务哪个下游能力**，否则不该在这。
#:
#: 写成名词短语而非单词：Grounding DINO 是 phrase grounding 模型，
#: ``"a car"`` 与 ``"car"`` 的召回实测有差别，短语更贴合它的训练分布。
UAV_THING_PROMPTS: dict[str, str] = {
    "a car":            "C2 动态占用；Grounding 任务最常见的可指称个体",
    "a truck":          "同上，且尺寸档不同 —— C3 的尺度线索",
    "a bus":            "同上",
    "a boat":           "水域场景的可指称个体；与 water 这片 stuff 形成「物体在面上」关系",
    "a person":         "**C2 硬排除项的计数依据** —— 语义图说不出几个人",
    "a building":       "C2 排除项 / C3 结构对地高度。虽是 stuff-like，但个体边界明确",
    "a tree":           "C3 冠层高度需要**单棵**树，语义图的 vegetation 是连成片的",
    "a utility pole":   "R-30 薄障碍：杆是电线的锚点，比电线本身好检",
    "a power line":     "R-30 薄障碍的零样本兜底 —— 专用专家（PowerLine-MTYOLO）当前不可部署",
    "a street lamp":    "C2 障碍物；低空巡检的典型目标",
    "a solar panel":    "硬化面上的平面障碍 —— 「平坦≠可降落」的典型反例",
    "a swimming pool":  "C1 的失效样本源：水面 + 强反射，且边界规则易检",
}


@dataclass
class Instance:
    """一个实例。``mask`` 与原图同形的 bool 数组。

    ``score_detection`` 与 ``score_mask`` **刻意不合并**（§14.1）。
    """

    label: str                     # 命中的名词短语，如 "a car"
    box: tuple[float, float, float, float]     # xyxy，原图像素坐标
    score_detection: float         # Grounding DINO 的 box/phrase 置信度
    score_mask: float              # SAM 2.1 的 predicted IoU
    mask: np.ndarray = field(repr=False)       # (H, W) bool


class GroundedSAM:
    """Grounding DINO（文本→框） → SAM 2.1（框→mask）。一次加载，多帧复用。

    典型用法::

        gs = GroundedSAM(device="cuda")
        insts = gs.ground("frame.jpg")                       # 用默认词表
        insts = gs.ground("frame.jpg", prompts=["a car"])     # 指定词表

    显存：两个模型合计约 2.4 GB（bf16 下更低），可与占卡程序共存。
    """

    DETECTOR_ID = "IDEA-Research/grounding-dino-base"
    SEGMENTER_ID = "facebook/sam2.1-hiera-base-plus"
    VERSION = "grounded_sam2::gdino_base+sam2.1_hiera_bplus"

    #: box_threshold —— Grounding DINO 输出的框置信度下限。
    #: 0.25 是官方 demo 默认；俯视小目标召回差，实测再调。
    DEFAULT_BOX_THRESHOLD = 0.25
    # 没有 text_threshold —— 短语归属改走 token span argmax（见 detect），
    # 不再需要「token 超过多少算命中」这个阈值。

    def __init__(self, device: str = "cuda",
                 detector_id: str | None = None,
                 segmenter_id: str | None = None) -> None:
        import torch
        from transformers import (AutoProcessor, GroundingDinoForObjectDetection,
                                  Sam2Model, Sam2Processor)

        self._torch = torch
        self.device = device
        self.detector_id = detector_id or self.DETECTOR_ID
        self.segmenter_id = segmenter_id or self.SEGMENTER_ID

        self.det_processor = AutoProcessor.from_pretrained(self.detector_id)
        self.detector = (GroundingDinoForObjectDetection
                         .from_pretrained(self.detector_id).to(device).eval())
        self.seg_processor = Sam2Processor.from_pretrained(self.segmenter_id)
        self.segmenter = Sam2Model.from_pretrained(self.segmenter_id).to(device).eval()

    # ------------------------------------------------------------------ 检测

    def detect(self, image, prompts: Sequence[str] | None = None,
               box_threshold: float | None = None) -> dict[str, Any]:
        """文本 → 框。返回 ``{"boxes": (K,4) xyxy, "scores": (K,), "labels": [str]}``。

        **不用 transformers 自带的 ``post_process_grounded_object_detection`` 取标签。**
        它内部走 ``get_phrases_from_posmap``：把该 query 上所有超过 ``text_threshold``
        的 token 直接解码拼起来，**完全不管短语边界**。12 条提示词同时送进去时，
        实测产出 ``"a car a"``、``"a truck bus"``、``"a"`` 这样的碎片
        （2026-08-25 首次冒烟实测），标签根本不能用作类别。

        这里改为**按短语的 token span 归属**：用 fast tokenizer 的 offset mapping
        把每条短语的字符区间映射回 token 下标，对每个 query 取该 span 内的最大概率
        作为「这个框属于这条短语」的得分，取 argmax 定标签。
        得到的 ``scores`` 也因此是**短语级**得分，比 256 维取全局 max 更有意义。
        """
        phrases = [p.lower().strip(" .") for p in
                   (list(prompts) if prompts is not None else list(UAV_THING_PROMPTS))]
        text = build_prompt_text(phrases)

        inputs = self.det_processor(images=image, text=text, return_tensors="pt")
        # offset mapping 只用于定位 span，不能喂给模型
        enc = self.det_processor.tokenizer(text, return_offsets_mapping=True)
        spans = phrase_token_spans(text, phrases, enc["offset_mapping"])

        inputs = inputs.to(self.device)
        with self._torch.inference_mode():
            out = self.detector(**inputs)

        probs = out.logits[0].sigmoid()                      # (num_queries, 256)
        # (num_queries, num_phrases)：每条短语在其 token span 上的最强响应
        phrase_scores = self._torch.stack(
            [probs[:, s].max(dim=-1).values if s
             else self._torch.zeros(probs.shape[0], device=probs.device)
             for s in spans], dim=-1)
        best_score, best_phrase = phrase_scores.max(dim=-1)

        thr = box_threshold if box_threshold is not None else self.DEFAULT_BOX_THRESHOLD
        keep = best_score > thr

        from transformers.image_transforms import center_to_corners_format
        boxes = center_to_corners_format(out.pred_boxes[0][keep])
        H, W = image.size[1], image.size[0]
        boxes = boxes * self._torch.tensor([W, H, W, H], device=boxes.device,
                                           dtype=boxes.dtype)
        return {
            "boxes": boxes.cpu().numpy().astype(np.float64),
            "scores": best_score[keep].cpu().numpy().astype(np.float64),
            "labels": [phrases[i] for i in best_phrase[keep].cpu().tolist()],
        }

    # ------------------------------------------------------------------ 分割

    def masks_from_boxes(self, image, boxes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """框 → mask。返回 ``(masks (K,H,W) bool, iou (K,) float)``。

        SAM 2.1 对每个提示出 3 个候选 mask（粗/中/细三个粒度），
        这里按它自报的 predicted IoU 取最优的一个。
        """
        if len(boxes) == 0:
            H, W = image.size[1], image.size[0]
            return np.zeros((0, H, W), dtype=bool), np.zeros((0,), dtype=np.float64)

        inputs = self.seg_processor(
            images=image,
            input_boxes=[[[float(v) for v in b] for b in boxes]],
            return_tensors="pt",
        ).to(self.device)
        with self._torch.inference_mode():
            out = self.segmenter(**inputs, multimask_output=True)

        # (B, K, 3, h, w) → 还原到原图尺寸
        masks = self.seg_processor.post_process_masks(
            out.pred_masks, inputs["original_sizes"])[0]      # (K, 3, H, W)
        iou = out.iou_scores[0].float().cpu().numpy()          # (K, 3)

        best = iou.argmax(axis=-1)                             # (K,)
        idx = self._torch.as_tensor(best, device=masks.device)
        chosen = masks[self._torch.arange(masks.shape[0], device=masks.device), idx]
        return (chosen.cpu().numpy().astype(bool),
                iou[np.arange(len(best)), best].astype(np.float64))

    # ------------------------------------------------------------------ 串联

    def ground(self, image_path: str, prompts: Sequence[str] | None = None,
               box_threshold: float | None = None,
               target_hw: tuple[int, int] | None = None) -> list[Instance]:
        """一张图 → 实例列表。这是本模块的主入口。

        ``target_hw`` 给定时把 mask 最近邻缩放到该尺寸，并同比例缩放框 ——
        用于和 VGGT-Ω 的深度图对齐（深度是 512 长边预处理过的，不是原图尺寸）。
        **必须最近邻**：mask 是二值的，双线性会在边界造出 0.5。
        """
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        det = self.detect(img, prompts, box_threshold)
        masks, ious = self.masks_from_boxes(img, det["boxes"])

        insts: list[Instance] = []
        for k in range(len(det["boxes"])):
            m, box = masks[k], det["boxes"][k]
            if target_hw is not None and m.shape != tuple(target_hw):
                sy, sx = target_hw[0] / m.shape[0], target_hw[1] / m.shape[1]
                m = np.array(
                    Image.fromarray(m.astype(np.uint8)).resize(
                        (target_hw[1], target_hw[0]), Image.NEAREST), dtype=bool)
                box = np.array([box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy])
            insts.append(Instance(
                label=det["labels"][k] if k < len(det["labels"]) else "",
                box=tuple(float(v) for v in box),
                score_detection=float(det["scores"][k]),
                score_mask=float(ious[k]),
                mask=m,
            ))
        return insts

    # ------------------------------------------------------------------

    def expert_ref(self) -> dict[str, Any]:
        """供 artifact provenance 引用（§14.8 的 model_ref 契约）。

        **两个模型都要列**：下游要能追到是谁出的框、谁出的 mask。
        """
        return {
            "name": "Grounded-SAM-2",
            "version": self.VERSION,
            "precision": "fp32",
            "components": [
                {"role": "detector", "name": "GroundingDINO", "weights": self.detector_id,
                 "expert_card": "registry/experts/grounding_dino_base.yaml"},
                {"role": "segmenter", "name": "SAM2.1", "weights": self.segmenter_id,
                 "expert_card": "registry/experts/sam2_1_hiera_base_plus.yaml"},
            ],
        }
