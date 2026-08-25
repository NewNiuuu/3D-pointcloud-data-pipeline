"""验证 Grounded-SAM（边界）+ OneFormer（类别）的融合，并量化两者的分歧。

产出三个数：

1. **融合成功率** —— 有多少实例拿到了类别（mask 落在有效语义上）；
2. **纯度分布** —— ``category_purity`` 的中位数与低纯度占比，
   反映实例边界与语义边界对不对得上；
3. **类别一致率** —— GDINO 的短语归一化后与 OneFormer 投票结果一致的比例。
   这个数**低才正常**（GDINO 的类别本就不可信），它的价值在于给出
   「分歧信号」的基线密度，供 C1 使用。

用法::
    PYTHONNOUSERSITE=1 python scripts/verify_instance_fusion.py --scenes 4 --frames 2
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCENES_ROOT = Path("/home/aiscuser/nyp/scenes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", type=int, default=4)
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--box-threshold", type=float, default=0.30)
    ap.add_argument("--out", type=Path,
                    default=Path("/home/aiscuser/nyp/metadata/_fusion_check.json"))
    args = ap.parse_args()

    from PIL import Image

    from pipeline.grounded_sam import GroundedSAM
    from pipeline.instance_fusion import fuse_instances
    from pipeline.segmentation import SemanticSegmenter

    gs = GroundedSAM(device="cuda")
    seg = SemanticSegmenter(device="cuda")

    scene_dirs = sorted(d for d in SCENES_ROOT.iterdir()
                        if (d / "scene_manifest.json").exists())[: args.scenes]

    fused_all: list[dict] = []
    n_raw = 0
    for sd in scene_dirs:
        man = json.loads((sd / "scene_manifest.json").read_text())["payload"]
        for f in man["frames"][: args.frames]:
            path = str(sd / f["image_uri"])
            H, W = Image.open(path).size[::-1]
            insts = gs.ground(path, box_threshold=args.box_threshold)
            n_raw += len(insts)
            if not insts:
                continue
            sem = seg.segment([path], target_hw=(H, W))[0]
            fused = fuse_instances(insts, sem.canonical, sem.canonical_names)
            for r in fused:
                r["scene_id"] = man["scene_id"]
                r["frame_id"] = f["frame_id"]
            fused_all.extend(fused)
            print(f"  {man['scene_id']}/{f['frame_id']}: "
                  f"{len(insts)} 提议 → {len(fused)} 定类")

    if not fused_all:
        print("没有实例，无法评估", file=sys.stderr)
        return 1

    purity = np.array([r["category_purity"] for r in fused_all])
    agree = np.array([r["category_agrees"] for r in fused_all])

    print(f"\n提议实例 {n_raw} → 成功定类 {len(fused_all)} "
          f"({len(fused_all) / max(n_raw, 1):.0%})")
    print(f"纯度: 中位 {np.median(purity):.3f} | "
          f"P25 {np.percentile(purity, 25):.3f} | <0.6 占 {(purity < 0.6).mean():.0%}")
    print(f"GDINO 与 OneFormer 类别一致率: {agree.mean():.0%} "
          f"（低是预期 —— GDINO 的类别本就不可信，分歧本身是 C1 的信号）")

    print("\nOneFormer 定出的类别分布:")
    for c, n in Counter(r["category"] for r in fused_all).most_common():
        print(f"  {c:<16} {n:>4}")
    print("\nGDINO 提议 → OneFormer 判定（前 10 组）:")
    pairs = Counter((r["label_proposed"], r["category"]) for r in fused_all)
    for (lp, c), n in pairs.most_common(10):
        mark = "✓" if canon_ok(lp, c) else "✗"
        print(f"  {mark} {lp:<18} → {c:<16} {n:>3}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "n_proposed": n_raw,
        "n_fused": len(fused_all),
        "box_threshold": args.box_threshold,
        "purity_median": round(float(np.median(purity)), 4),
        "purity_p25": round(float(np.percentile(purity, 25)), 4),
        "low_purity_frac": round(float((purity < 0.6).mean()), 4),
        "category_agreement": round(float(agree.mean()), 4),
        "category_distribution": dict(Counter(r["category"] for r in fused_all)),
        "instances": fused_all,
    }, ensure_ascii=False, indent=2))
    print(f"\n报告: {args.out}")
    return 0


def canon_ok(label: str, category: str) -> bool:
    from pipeline.segmentation import canonicalize
    return canonicalize(label) == category


if __name__ == "__main__":
    raise SystemExit(main())
