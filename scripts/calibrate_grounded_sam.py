"""Grounded-SAM-2 在低空俯视图上的**幻觉标定**：负控词表 + 阈值扫描。

起因：首次冒烟（2026-08-25）在 UAVScenes 近垂直下视帧上，
threshold=0.25 时几乎每帧都检出 ``a power line`` / ``a solar panel`` /
``a swimming pool``。这些东西**在俯视图里本就罕见**，直觉判断是幻觉 ——
但按 §40.5 机制 1「测量优于观点」，直觉不算数，要拿数字。

**负控（negative control）**：往词表里掺入**画面里不可能有**的名词短语
（北极熊、潜艇、宇宙飞船…）。若模型对负控词的响应与真实词同量级，
说明它在「凑合匹配」而非真的认出来了 —— 那么这批标签就不能当类别用，
只能当「候选提议」，且阈值必须抬到把负控压下去的位置。

这个数直接决定 ``GroundedSAM.DEFAULT_BOX_THRESHOLD`` 该取多少，
也是 ``registry/experts/`` 里 ``uav_validation_status`` 的证据。

用法::
    PYTHONNOUSERSITE=1 python scripts/calibrate_grounded_sam.py --scenes 4 --frames 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCENES_ROOT = Path("/home/aiscuser/nyp/scenes")

#: 负控词表 —— 低空城市/海岛俯视图里**不可能**出现的东西。
#: 挑选原则：既要跨语义域（动物/载具/幻想物），也要有和真实词形近的
#: （``a submarine`` vs ``a boat``），这样才能测出「近义漂移」。
NEGATIVE_PROMPTS = [
    "a polar bear",
    "a submarine",
    "a spaceship",
    "a grand piano",
    "a dinosaur",
    "a hot air balloon",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", type=int, default=4)
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--out", type=Path,
                    default=Path("/home/aiscuser/nyp/metadata/_calib_grounded_sam.json"))
    ap.add_argument("--isolated", action="store_true",
                    help="每条短语单独一次前向（排除长提示词串扰这个替代解释）")
    args = ap.parse_args()

    from pipeline.grounded_sam import GroundedSAM, UAV_THING_PROMPTS

    real = list(UAV_THING_PROMPTS)
    prompts = real + NEGATIVE_PROMPTS
    gs = GroundedSAM(device="cuda")

    scene_dirs = sorted(d for d in SCENES_ROOT.iterdir()
                        if (d / "scene_manifest.json").exists())[: args.scenes]

    # 阈值设 0，把**所有** query 的短语得分都收上来，事后再扫阈值
    per_phrase: dict[str, list[float]] = {p: [] for p in prompts}
    n_frames = 0
    from PIL import Image

    for sd in scene_dirs:
        man = json.loads((sd / "scene_manifest.json").read_text())["payload"]
        for f in man["frames"][: args.frames]:
            img = Image.open(str(sd / f["image_uri"])).convert("RGB")
            n_frames += 1
            if args.isolated:
                # 每条短语单独一次前向：此时不存在跨短语的文本自注意力串扰，
                # 也不存在「必须从给定短语里挑一个」的竞争 —— 分数是该短语的独立响应
                for p in prompts:
                    det = gs.detect(img, prompts=[p], box_threshold=0.0)
                    per_phrase[p].extend(float(s) for s in det["scores"])
            else:
                det = gs.detect(img, prompts=prompts, box_threshold=0.0)
                for lab, sc in zip(det["labels"], det["scores"]):
                    per_phrase[lab].append(float(sc))
    mode = "逐条单独" if args.isolated else "全部拼成一段"
    print(f"扫描 {n_frames} 帧（{mode}），"
          f"真实词 {len(real)} 条 + 负控 {len(NEGATIVE_PROMPTS)} 条\n")

    def top(scores: list[float]) -> float:
        return max(scores) if scores else 0.0

    real_scores = [s for p in real for s in per_phrase[p]]
    neg_scores = [s for p in NEGATIVE_PROMPTS for s in per_phrase[p]]

    print(f"{'短语':<20}{'峰值':>8}{'P99':>8}{'检出数':>8}")
    for p in prompts:
        s = per_phrase[p]
        tag = "  ← 负控" if p in NEGATIVE_PROMPTS else ""
        print(f"{p:<20}{top(s):>8.3f}"
              f"{(np.percentile(s, 99) if s else 0):>8.3f}{len(s):>8}{tag}")

    # 阈值扫描：每档保留多少真实词 / 多少负控词
    #
    # **必须按词数归一化。** 真实词 12 条、负控 6 条，直接比总数天然 2:1，
    # 那个 2:1 全部来自词表大小，不含任何判别力。
    # 归一化后的「判别比」= 真实词每词每帧检出 / 负控每词每帧检出：
    #   ≈ 1.0 → 模型分不出「这概念在不在」；越大越有判别力。
    sweep = []
    for t in (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        r = sum(1 for s in real_scores if s > t)
        n = sum(1 for s in neg_scores if s > t)
        rr = r / max(n_frames, 1) / len(real)
        nn = n / max(n_frames, 1) / len(NEGATIVE_PROMPTS)
        sweep.append({"threshold": t, "real_kept": r, "neg_kept": n,
                      "neg_per_frame": round(n / max(n_frames, 1), 2),
                      "real_per_frame": round(r / max(n_frames, 1), 2),
                      "real_rate_per_prompt": round(rr, 4),
                      "neg_rate_per_prompt": round(nn, 4),
                      "discriminability": round(rr / nn, 2) if nn else None})
    print(f"\n{'阈值':>6}{'真实/词/帧':>13}{'负控/词/帧':>13}{'判别比':>9}   判读")
    for row in sweep:
        d = row["discriminability"]
        verdict = ("负控已压净" if row["neg_kept"] == 0
                   else "无判别力" if d is not None and d < 1.5 else "有相对判别力")
        print(f"{row['threshold']:>6.2f}{row['real_rate_per_prompt']:>13.3f}"
              f"{row['neg_rate_per_prompt']:>13.3f}"
              f"{(d if d is not None else float('inf')):>9.2f}   {verdict}")

    clean = [r["threshold"] for r in sweep if r["neg_kept"] == 0]
    recommended = min(clean) if clean else None
    print(f"\n负控归零的最低阈值: {recommended}")
    if recommended is not None:
        kept = next(r for r in sweep if r["threshold"] == recommended)
        print(f"  该阈值下真实词还剩 {kept['real_per_frame']} 个/帧")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "n_frames": n_frames,
        "real_prompts": real,
        "negative_prompts": NEGATIVE_PROMPTS,
        "peak_score": {p: round(top(s), 4) for p, s in per_phrase.items()},
        "n_detections": {p: len(s) for p, s in per_phrase.items()},
        "sweep": sweep,
        "recommended_threshold": recommended,
    }, ensure_ascii=False, indent=2))
    print(f"报告: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
