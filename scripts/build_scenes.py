#!/usr/bin/env python
"""把 UAVScenes 的 run 切分并落地为归一化场景包。

用法：

    python scripts/build_scenes.py --run interval5_AMtown01 --limit 2
    python scripts/build_scenes.py --run interval5_AMtown01 --no-materialize

输出：``<output-root>/<scene_id>/scene_manifest.json``，以及 materialize 模式下
的 ``images/`` ``lidar/`` ``labels_cam/`` ``labels_lidar/``。

场景清单以 Artifact 信封写出（SPEC §30），已存在时**拒绝覆盖** —— 重跑请换
输出目录或先删除，修复请走 derive 产生新 artifact。
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.uavscenes import ADAPTER_VERSION, AdapterConfig, UAVScenesAdapter  # noqa: E402
from core import Artifact, ArtifactKind, GateStatus, PipelineState, content_digest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path,
                        default=Path("/home/aiscuser/nyp/data_raw/UAVScenes"))
    parser.add_argument("--output-root", type=Path,
                        default=Path("/home/aiscuser/nyp/scenes"))
    parser.add_argument("--run", required=True, help="run 目录名，如 interval5_AMtown01")
    parser.add_argument("--frames-per-scene", type=int, default=50)
    parser.add_argument("--min-frames", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="最多产出多少个场景")
    parser.add_argument("--no-materialize", action="store_true",
                        help="只写清单，不解出帧文件")
    parser.add_argument("--list-runs", action="store_true")
    args = parser.parse_args()

    config = AdapterConfig(
        data_root=args.data_root,
        output_root=args.output_root,
        frames_per_scene=args.frames_per_scene,
        min_frames_per_scene=args.min_frames,
        materialize=not args.no_materialize,
    )

    with UAVScenesAdapter(config) as adapter:
        if args.list_runs:
            for run in adapter.list_runs():
                print(f"{run:<40} split_group={UAVScenesAdapter.split_group(run)}")
            return 0

        written = 0
        # 用 islice 限流：_build_scene 在 yield 前就会解出帧文件，若在循环体内
        # 才 break，生成器已多构建一个场景，留下没有清单的孤儿目录。
        scenes = adapter.build_scenes(args.run)
        if args.limit is not None:
            scenes = itertools.islice(scenes, args.limit)
        for scene in scenes:
            scene_dir = Path(args.output_root) / scene["scene_id"]
            artifact = Artifact(
                kind=ArtifactKind.SCENE_MANIFEST,
                payload=scene,
                dataset_id=scene["dataset_id"],
                scene_id=scene["scene_id"],
                split_group_id=scene["split_group_id"],
                run_id=scene["diagnostics"]["run"],
                code_version=ADAPTER_VERSION,
                created_at=scene["provenance"]["created_at"],
                input_digests={"scene_payload": content_digest(scene)},
                # adapter 只负责产出契约；G0 由 scene-ingestion-validator 判定，
                # 此处不代它给结论。
                state=PipelineState.INGESTED,
                gate_status=None,
            )
            target = scene_dir / "scene_manifest.json"
            if target.exists():
                print(f"跳过已存在：{target}", file=sys.stderr)
                continue
            artifact.write(target)
            diag = scene["diagnostics"]
            print(
                f"{scene['scene_id']}  帧={diag['frames_emitted']}"
                f"  时长={diag['duration_s']}s"
                f"  相机跨度={diag['camera_translation_span_m']}m"
                f"  缺位姿={diag['frames_missing_pose']}"
                f"  缺点云={diag['frames_missing_lidar']}"
            )
            written += 1

    print(f"\n已写出 {written} 个场景 -> {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
