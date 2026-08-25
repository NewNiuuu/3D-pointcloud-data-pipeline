#!/usr/bin/env python3
"""从已落盘的 metadata 重新编译任务样本 —— 不重跑 VGGT-Ω。

抽取（`pipeline/extract.py`）与编译是两件事：前者要 GPU、耗时几分钟；
后者是纯 CPU 的确定性变换。改任务措辞、换 Task Spec、调资格条件时
只需重跑后者。本脚本因此只读 `metadata/<scene>/` 下的三层文件。

**问题措辞为什么要点名目标**：
`observer_relative_direction` 问「目标在观察者的哪个方位」，
若问题里不指明**哪一个**实体是目标，模型无从作答 —— 那测到的是
「能不能猜中是哪个」而不是「能不能用 3D 算方位」，两者不是一回事。
点名目标**不是泄漏**：它是任务的前提，答案是方位本身。
编译器已把该 ID 登记进 `structurally_visible_target_ids`，泄漏扫描据此豁免。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compiler import DERIVATION_PROGRAMS, IneligibleScene, TaskCompiler   # noqa: E402
from core.metadata import validate_against_schema                          # noqa: E402
from core.task_spec import load_all_task_specs                             # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: 问题模板。``{target}`` 会被替换为目标实体 ID（见模块 docstring）。
QUESTIONS = {
    "3d_grounding.object":
        "Among the listed regions, which one is farthest from the drone?",
    "3d_vqa.situated.observer_relative_direction":
        "Relative to the drone's own viewing direction, where is region {target}? "
        "Answer both the longitudinal (front/behind) and lateral (left/right) placement.",
}


def _observer_from(l0: dict[str, Any], frame_id: str) -> dict[str, Any]:
    cam = next(c for c in l0["cameras"] if c["frame_id"] == frame_id)
    T = np.asarray(cam["T_world_from_camera"], dtype=float)
    return {"pose_id": "<pose_001>",
            "position": T[:3, 3].tolist(),
            "forward": T[:3, 2].tolist()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata-root", default="/home/aiscuser/nyp/metadata")
    ap.add_argument("--scenes-root", default="/home/aiscuser/nyp/scenes")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    meta_root = Path(args.metadata_root)
    out_path = Path(args.out or meta_root / "compiled_records.json")
    specs = {s.task_id: s for s in load_all_task_specs(ROOT / "task_specs")}
    comp = TaskCompiler(DERIVATION_PROGRAMS)

    records: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []

    scene_dirs = sorted(d for d in meta_root.iterdir()
                        if (d / "metadata_snapshot.json").exists())
    print(f"已落盘的场景 metadata：{len(scene_dirs)} 个\n")

    for d in scene_dirs:
        snap = json.loads((d / "metadata_snapshot.json").read_text())
        l0 = json.loads((d / "l0_geometry.json").read_text())
        l1 = json.loads((d / "l1_entities.json").read_text())
        l2 = json.loads((d / "l2_relations.json").read_text())
        scene = snap["scene_id"]

        if not l1["objects"]:
            skipped.append((scene, "无实体"))
            continue
        frame_id = l1["objects"][0]["visibility"]["best_view_frame_id"]
        l1c = dict(l1)
        l1c["cameras"] = [_observer_from(l0, frame_id)]
        image = Path(args.scenes_root) / scene / "images" / f"{frame_id}.jpg"

        got = 0
        for task_id, template in QUESTIONS.items():
            try:
                # 先编译一次拿到 target，再把它填进问题 —— 措辞依赖 target，
                # 而 target 由推导程序算出，顺序不能反。
                rec = comp.compile_one(
                    specs[task_id], snap, l1c, l2,
                    visual_inputs=[str(image)],
                    observer_pose_id="<pose_001>",
                    question=template)
                target_id = (rec.get("hidden_target") or {}).get("object_id")
                if "{target}" in template and target_id:
                    rec["inputs"]["question"] = template.format(target=target_id)
                validate_against_schema(rec, "canonical_task_record")
                records.append(rec)
                got += 1
            except IneligibleScene as exc:
                skipped.append((scene, f"{task_id}: {exc.reasons[0]}"))
            except Exception as exc:                              # noqa: BLE001
                skipped.append((scene, f"{task_id}: {type(exc).__name__} {exc}"))
        print(f"  {scene:46} 实体{len(l1['objects']):3} "
              f"视差{snap['capabilities']['parallax_ratio']:.3f}  样本+{got}")

    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    (meta_root / "skipped.json").write_text(
        json.dumps(skipped, ensure_ascii=False, indent=2))
    print(f"\n编译 {len(records)} 条 / 跳过 {len(skipped)} 项 → {out_path}")
    for scene, why in skipped:
        print(f"  ⊘ {scene}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
