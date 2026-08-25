"""L2-S2 专家模块的单元测试：类别映射、短语归属、实例融合。

**不加载任何模型权重** —— 这里测的是纯逻辑部分。
模型能不能跑由 ``scripts/smoke_grounded_sam.py`` 等冒烟脚本负责，那需要 GPU。
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.grounded_sam import (UAV_THING_PROMPTS, build_prompt_text,
                                   phrase_token_spans)
from pipeline.instance_fusion import fuse_instances
from pipeline.segmentation import CANONICAL_CLASSES, canonicalize


# --------------------------------------------------------------- canonicalize

class TestCanonicalizeWordBoundary:
    """2026-08-25 实测踩到的中缀误配 —— 这些是回归闸，不要放宽。"""

    @pytest.mark.parametrize("label,expected", [
        # "street" 里含 "tree" —— 曾被判成 vegetation
        ("street lamp", "structure"),
        ("streetlight", "structure"),
        # "ottoman" 里含 "man" —— 曾被判成 person，而 person 是 C2 的硬排除项
        ("ottoman, pouf, pouffe, puff, hassock", "other"),
        # "kitchen island" 里含 "land"
        ("kitchen island", "other"),
    ])
    def test_infix_must_not_match(self, label, expected):
        assert canonicalize(label) == expected

    @pytest.mark.parametrize("label,expected", [
        # 词首匹配必须仍然生效（前缀匹配，不是全词匹配）
        ("tree", "vegetation"),
        ("trees", "vegetation"),
        ("mountain", "ground_natural"),
        ("water", "water"),
        ("sidewalk, pavement", "ground_paved"),
        ("person", "person"),
        ("car", "vehicle"),
    ])
    def test_word_start_still_matches(self, label, expected):
        assert canonicalize(label) == expected

    def test_all_canonical_names_are_declared(self):
        """规则里出现的每个类别都必须在 CANONICAL_CLASSES 里有证成说明（§0.3）。"""
        from pipeline.segmentation import _RULES
        for canon, _ in _RULES:
            assert canon in CANONICAL_CLASSES, f"{canon} 缺少下游能力证成"


class TestPromptVocabularyMapping:
    def test_every_prompt_maps_to_a_real_class(self):
        """提示词表里的每条短语都得能落到一个非 other 的类别上。

        落进 other 意味着该实例在下游拿不到有意义的类别 —— 那这条提示词就白提了。
        """
        unmapped = [p for p in UAV_THING_PROMPTS if canonicalize(p) == "other"]
        assert not unmapped, f"这些提示词映射不到类别: {unmapped}"

    @pytest.mark.parametrize("phrase,expected", [
        ("a car", "vehicle"),
        ("a person", "person"),
        ("a utility pole", "structure"),
        ("a power line", "structure"),
        ("a solar panel", "structure"),
        ("a street lamp", "structure"),      # 不是 vegetation
        ("a swimming pool", "water"),
    ])
    def test_specific(self, phrase, expected):
        assert canonicalize(phrase) == expected


# ---------------------------------------------------------------- 短语 token 归属

class TestPhraseTokenSpans:
    def test_spans_are_disjoint_and_ordered(self):
        phrases = ["a car", "a truck", "a utility pole"]
        text = build_prompt_text(phrases)
        # 模拟 offset_mapping：逐字符一个 token，外加首尾特殊 token
        offsets = [(0, 0)] + [(i, i + 1) for i in range(len(text))] + [(0, 0)]
        spans = phrase_token_spans(text, phrases, offsets)
        assert len(spans) == 3
        assert all(spans), "每条短语都必须分到 token"
        flat = [i for s in spans for i in s]
        assert len(flat) == len(set(flat)), "短语的 token span 不得重叠"
        assert flat == sorted(flat), "span 顺序必须与短语顺序一致"

    def test_repeated_substring_does_not_collapse(self):
        """``a car`` 是 ``a carrier`` 的前缀 —— 游标必须防止两条短语抢同一段。"""
        phrases = ["a car", "a carrier"]
        text = build_prompt_text(phrases)
        offsets = [(0, 0)] + [(i, i + 1) for i in range(len(text))] + [(0, 0)]
        spans = phrase_token_spans(text, phrases, offsets)
        assert not (set(spans[0]) & set(spans[1]))

    def test_prompt_text_format(self):
        assert build_prompt_text(["A Car", "a truck."]) == "a car. a truck."


# ------------------------------------------------------------------- 实例融合

class _FakeInstance:
    def __init__(self, mask, label="a car", det=0.4, msk=0.9):
        self.mask = mask
        self.label = label
        self.box = (0.0, 0.0, 10.0, 10.0)
        self.score_detection = det
        self.score_mask = msk


NAMES = list(CANONICAL_CLASSES)


def _sem(fill: str, shape=(8, 8)) -> np.ndarray:
    return np.full(shape, NAMES.index(fill), dtype=np.int16)


class TestFuseInstances:
    def test_category_comes_from_segmentation_not_from_label(self):
        """核心契约：类别只认 OneFormer，GDINO 的短语不得进 ``category``。"""
        mask = np.zeros((8, 8), bool)
        mask[2:6, 2:6] = True
        out = fuse_instances([_FakeInstance(mask, label="a car")],
                             _sem("water"), NAMES)
        assert out[0]["category"] == "water"
        assert out[0]["label_proposed"] == "a car"
        assert out[0]["label_proposed_canonical"] == "vehicle"
        assert out[0]["category_agrees"] is False

    def test_majority_vote_and_purity(self):
        sem = _sem("ground_paved")
        sem[:, 4:] = NAMES.index("vegetation")
        mask = np.zeros((8, 8), bool)
        mask[:, 2:6] = True            # 一半 paved 一半 vegetation
        out = fuse_instances([_FakeInstance(mask)], sem, NAMES)
        assert out[0]["category_purity"] == pytest.approx(0.5)

    def test_sky_is_excluded_from_vote(self):
        """sky 的深度不可信（§14.5），不能靠它定类别。"""
        sem = _sem("sky")
        sem[7, :] = NAMES.index("building")
        mask = np.ones((8, 8), bool)
        out = fuse_instances([_FakeInstance(mask)], sem, NAMES)
        assert out[0]["category"] == "building"
        assert out[0]["category_purity"] == pytest.approx(1.0)

    def test_all_sky_instance_is_dropped(self):
        out = fuse_instances([_FakeInstance(np.ones((8, 8), bool))], _sem("sky"), NAMES)
        assert out == []

    def test_min_purity_filter(self):
        sem = _sem("ground_paved")
        sem[:, 4:] = NAMES.index("vegetation")
        mask = np.ones((8, 8), bool)
        assert fuse_instances([_FakeInstance(mask)], sem, NAMES, min_purity=0.8) == []
        assert len(fuse_instances([_FakeInstance(mask)], sem, NAMES, min_purity=0.4)) == 1

    def test_shape_mismatch_raises(self):
        """静默广播比报错危险得多 —— 分辨率对不上必须炸。"""
        with pytest.raises(ValueError, match="不同形"):
            fuse_instances([_FakeInstance(np.ones((8, 8), bool))],
                           _sem("water", (4, 4)), NAMES)

    def test_two_confidences_kept_separate(self):
        """§14.1：检测置信度与 mask 置信度不得合成一个数。"""
        mask = np.ones((8, 8), bool)
        out = fuse_instances([_FakeInstance(mask, det=0.31, msk=0.92)],
                             _sem("building"), NAMES)
        conf = out[0]["confidence"]
        assert conf["detection"] == pytest.approx(0.31)
        assert conf["mask"] == pytest.approx(0.92)
        assert conf["calibrated"] is False       # §14.13

    def test_provenance_names_both_teachers(self):
        out = fuse_instances([_FakeInstance(np.ones((8, 8), bool))],
                             _sem("building"), NAMES)
        prov = out[0]["provenance"]
        assert "grounded_sam2" in prov["boundary_from"]
        assert "oneformer" in prov["category_from"]
