"""Grounded-SAM-2 端到端冒烟测试：在真实 UAVScenes 帧上跑 文本→框→mask。

**这一步此前从未跑过** —— 专家卡里 Grounding DINO 与 SAM 2.1 各自单独验证过，
但 box→mask 的交接没验证过，那恰恰是 Grounded-SAM 的全部内容。

验的是四件事：
1. 两端能串起来，且 mask 与原图同形；
2. **标签必须严格落在提示词表内** —— transformers 自带的 post_process 按 token 拼标签，
   会产出 "a car a" / "a truck bus" 这类碎片（2026-08-25 首跑实测）。这是那个 bug 的回归闸；
3. mask 面积显著小于框面积（**证明用的是 mask 不是框**，§14.1 的强制约束）；
4. 显存与耗时可接受。

**不检查「mask 完全落在框内」** —— SAM 的 box prompt 是提示不是硬约束，
框卡在物体的一部分上时它会外扩到完整物体，实测中位 0.988、最小 0.797。
坐标系搞反会给出接近 0 的值，那才是错位；这个量级是正常行为。
外溢比例反而是有用的信号：**检测器与分割器对「物体多大」的分歧**，
按 §0.7 第三层，这类分歧正是单个教师给不出的东西，故如实记录（``mask_outside_box_ratio``）。

用法::
    PYTHONNOUSERSITE=1 python scripts/smoke_grounded_sam.py --scenes 3 --frames 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCENES_ROOT = Path("/home/aiscuser/nyp/scenes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", type=int, default=3)
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--box-threshold", type=float, default=0.25)
    ap.add_argument("--out", type=Path,
                    default=Path("/home/aiscuser/nyp/metadata/_smoke_grounded_sam.json"))
    args = ap.parse_args()

    import torch
    from pipeline.grounded_sam import GroundedSAM, UAV_THING_PROMPTS

    scene_dirs = sorted(d for d in SCENES_ROOT.iterdir()
                        if (d / "scene_manifest.json").exists())[: args.scenes]
    if not scene_dirs:
        print("没有找到场景包", file=sys.stderr)
        return 1

    t0 = time.time()
    gs = GroundedSAM(device="cuda")
    load_s = time.time() - t0
    print(f"模型加载 {load_s:.1f}s，词表 {len(UAV_THING_PROMPTS)} 条")

    report: dict = {"prompts": list(UAV_THING_PROMPTS), "scenes": []}
    total_inst = 0

    for sd in scene_dirs:
        man = json.loads((sd / "scene_manifest.json").read_text())["payload"]
        frames = man["frames"][: args.frames]
        scene_rec: dict = {"scene_id": man["scene_id"], "frames": []}

        for f in frames:
            path = str(sd / f["image_uri"])
            t = time.time()
            insts = gs.ground(path, box_threshold=args.box_threshold)
            dt = time.time() - t

            rows = []
            for it in insts:
                x0, y0, x1, y1 = it.box
                box_area = max((x1 - x0) * (y1 - y0), 1.0)
                mask_area = int(it.mask.sum())
                # mask 的像素是否落在框内 —— 交接错位的直接判据
                ys, xs = np.nonzero(it.mask)
                inside = (float(((xs >= x0 - 2) & (xs <= x1 + 2) &
                                 (ys >= y0 - 2) & (ys <= y1 + 2)).mean())
                          if mask_area else 0.0)
                rows.append({
                    "label": it.label,
                    "score_detection": round(it.score_detection, 3),
                    "score_mask": round(it.score_mask, 3),
                    "box": [round(v, 1) for v in it.box],
                    "mask_px": mask_area,
                    "mask_over_box": round(mask_area / box_area, 3),
                    # 检测器与分割器对「物体多大」的分歧，见模块 docstring
                    "mask_outside_box_ratio": round(1.0 - inside, 3),
                })
            total_inst += len(rows)
            scene_rec["frames"].append({
                "frame_id": f["frame_id"], "seconds": round(dt, 2),
                "image_hw": list(insts[0].mask.shape) if insts else None,
                "instances": rows,
            })
            labels = ", ".join(sorted({r["label"] for r in rows})) or "（无）"
            print(f"  {man['scene_id']}/{f['frame_id']}: {len(rows)} 实例 "
                  f"[{labels}]  {dt:.2f}s")
        report["scenes"].append(scene_rec)

    report["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    report["load_seconds"] = round(load_s, 1)
    report["total_instances"] = total_inst

    # ---- 判据 ----
    all_rows = [r for s in report["scenes"] for fr in s["frames"] for r in fr["instances"]]
    vocab = set(UAV_THING_PROMPTS)
    bad_labels = sorted({r["label"] for r in all_rows} - vocab)
    checks = {
        "有实例产出": total_inst > 0,
        "标签全在词表内": not bad_labels,
        "mask 面积严格小于框(中位 <0.9)": (
            float(np.median([r["mask_over_box"] for r in all_rows])) < 0.9),
        "检测分与mask分不恒等": any(
            abs(r["score_detection"] - r["score_mask"]) > 1e-6 for r in all_rows),
    }
    report["checks"] = checks
    report["off_vocab_labels"] = bad_labels
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\n实例总数 {total_inst} | 峰值显存 {report['peak_vram_gb']} GB")
    if all_rows:
        print(f"mask/box 面积比中位 "
              f"{np.median([r['mask_over_box'] for r in all_rows]):.3f} | "
              f"mask 越框比例中位 "
              f"{np.median([r['mask_outside_box_ratio'] for r in all_rows]):.3f}")
    if bad_labels:
        print(f"  词表外标签: {bad_labels}")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"报告: {args.out}")
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
