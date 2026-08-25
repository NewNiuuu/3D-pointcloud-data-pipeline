"""L2-S1 / L2-S3 的最小真实实现：从场景包抽出 L0 几何与 L1 实体。

**这是第一条真实（非合成）的抽取链。** 此前编译器只在 `tests/` 的合成 fixture
上跑过；本模块让它第一次吃到真实场景。

设计取舍（对应 `docs/DESIGN.md` Part 0 的反向证成规则 §0.3）：

- **L0 走 VGGT-Ω 自洽坐标系，scale_status = relative。**
  不做米制锚定 —— 实测（FINDINGS 附录 B）相对深度锚定为米制后 CV 仍达 19.5%，
  拿它去出米制题会产出伪精度。按 §40.5 机制 5，够不着的档位**静默降级**，
  由 `metric_task_eligible=False` 自动关掉米制任务，而不是伪造一个尺度因子。

- **L1 实体来自数据集自带的逐像素语义标注 + VGGT-Ω 深度反投影。**
  语义是 UAVScenes 的人工标注（strong 监督），几何来自视觉重建 ——
  二者在同一像素空间，无需相机-LiDAR 外参（M-008）。
  这条路子在 C1 实测中已经验证过一次（FINDINGS 附录 A）。

**本模块不产出米制量，也不产出失效原因码。** 前者按上面的理由主动放弃；
后者属于 R-38（纯视觉自洽测量），尚未实现。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np

__all__ = ["ExtractionConfig", "extract_l0", "extract_l1", "build_snapshot"]

CODE_VERSION = "extract/0.1.0"
_MIN_COMPONENT_PIXELS = 400          # 小于此的连通域不成实体 —— 反投影噪声太大
_MIN_VALID_POINTS = 120              # 有效 3D 点少于此的实体丢弃
_CONF_PERCENTILE_FLOOR = 25          # 低于本场 P25 置信度的像素不参与实体几何


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


@dataclass(frozen=True)
class ExtractionConfig:
    """抽取参数。`frames` 控制送进 VGGT-Ω 的帧数 —— 显存与基线的折中。"""

    scene_dir: Path
    output_dir: Path
    frames: int = 24
    image_resolution: int = 512
    device: str = "cuda"


# --------------------------------------------------------------------- L0

def extract_l0(cfg: ExtractionConfig, model: Any) -> dict[str, Any]:
    """跑 VGGT-Ω，落 L0 几何制品。

    `model` 由调用者传入（已 load_state_dict 的 VGGTOmega），
    便于一次加载、多场景复用 —— 权重 4.3 GB，反复加载不划算。
    """
    import torch
    from vggt_omega.utils.load_fn import load_and_preprocess_images
    from vggt_omega.utils.pose_enc import encoding_to_camera

    manifest = json.loads((cfg.scene_dir / "scene_manifest.json").read_text())["payload"]
    scene_id = manifest["scene_id"]
    frames = manifest["frames"][: cfg.frames]
    if len(frames) < 2:
        raise ValueError(f"{scene_id}: 帧数不足（{len(frames)}），无法多视重建")

    paths = [str(cfg.scene_dir / f["image_uri"]) for f in frames]
    images = load_and_preprocess_images(
        paths, image_resolution=cfg.image_resolution).to(cfg.device)
    with torch.inference_mode():
        pred = model(images[None] if images.dim() == 4 else images)

    depth = pred["depth"].float()[0].cpu().numpy()          # (S,H,W,1)
    conf = pred["depth_conf"].float()[0].cpu().numpy()      # (S,H,W)
    if depth.ndim == 4:
        depth = depth[..., 0]
    S, H, W = conf.shape

    # VGGT-Ω 不直接给 extrinsic/intrinsic，只给 9 维 pose_enc，需显式解码。
    # extrinsic 是 camera_from_world（3×4）。
    extr_t, intr_t = encoding_to_camera(pred["pose_enc"].float(), (H, W))
    extr = extr_t[0].cpu().numpy()
    intr = intr_t[0].cpu().numpy()

    out = cfg.output_dir / scene_id
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "depth.npz", depth=depth.astype(np.float16),
                        conf=conf.astype(np.float16))

    cameras = []
    for i, f in enumerate(frames):
        T = np.eye(4, dtype=np.float64)
        T[:3, :4] = extr[i]
        # VGGT 的 extrinsic 是 camera_from_world，取逆得 world_from_camera
        T_wc = np.linalg.inv(T)
        cameras.append({
            "frame_id": f["frame_id"],
            "K": intr[i].tolist(),
            "T_world_from_camera": T_wc.tolist(),
            "coordinate_convention": "opencv_rdf",
            "pose_source": "estimated",           # VGGT 估计，不是数据集原生
            "image_size_hw": [int(H), int(W)],
        })

    span = float(np.linalg.norm(
        np.array([c["T_world_from_camera"] for c in cameras])[:, :3, 3].ptp(axis=0)))

    l0 = {
        "schema_version": "0.1.0",
        "scene_id": scene_id,
        "coordinate_frame": f"vggt_omega_local::{scene_id}",
        "unit": "unknown",          # relative 深度没有物理单位 —— schema 只允许 meter/unknown
        "scale": {
            # 铁律 9：没有外部锚就 MUST NOT 声称米制
            "status": "relative",
            "source": "none",
            "depth_type": "relative",
            "scale_factor": None,
            "uncertainty_m": None,
            "domain_calibrated": False,
            "anchor_provenance_verified": False,
            "camera_baseline_m": None,          # relative 尺度下「米」无意义
            "alignment_residual_m": None,
            "alignment_version": None,
        },
        "cameras": cameras,
        "depth": [{
            "artifact_id": f"dep_{_short_hash(scene_id, 'vggt')}",
            "producer": {"name": "VGGT-Omega", "version": "1b_512",
                         "precision": "bf16",
                         "expert_card": "registry/experts/vggt_omega_1b_512.yaml"},
            "role": "primary",
            "depth_uri": str((out / "depth.npz").relative_to(cfg.output_dir)),
            "confidence_uri": str((out / "depth.npz").relative_to(cfg.output_dir)),
            "depth_type": "relative",
            "frame_ids": [c["frame_id"] for c in cameras],
            "preprocessing": {
                "original_size_hw": list(frames[0].get("original_size") or [H, W]),
                "processed_size_hw": [int(H), int(W)],
                "resize_mode": "load_and_preprocess_images",
            },
        }],
        "diagnostics": {
            "coverage_ratio": float((conf > np.percentile(conf, _CONF_PERCENTILE_FLOOR)).mean()),
            "invalid_depth_ratio": float((~np.isfinite(depth)).mean()),
            "camera_translation_span_relative": span,
            "median_depth_relative": float(np.nanmedian(depth)),
            # **视差比 = 基线 / 景深**，是「基线够不够」的**尺度无关**判据。
            # 米制基线阈值在 relative 场景里无从判定（见 task_spec 的说明），
            # 而这个比值在任何尺度下都可比。
            "parallax_ratio": float(span / max(np.nanmedian(depth), 1e-9)),
        },
        "provenance": {
            "created_at": _now(),
            "code_version": CODE_VERSION,
            "source_scene_manifest": str(cfg.scene_dir / "scene_manifest.json"),
            "notes": "relative 尺度：未做米制锚定（见模块 docstring）",
        },
    }
    (out / "l0_geometry.json").write_text(
        json.dumps(l0, ensure_ascii=False, indent=2))
    return {"l0": l0, "depth": depth, "conf": conf, "frames": frames,
            "cameras": cameras, "out_dir": out, "manifest": manifest}


# --------------------------------------------------------------------- L1

def _components(mask: np.ndarray) -> Iterator[np.ndarray]:
    """朴素连通域（4-邻域，BFS）。避免为一个功能引入 scipy/cv2 依赖。"""
    seen = np.zeros_like(mask, dtype=bool)
    H, W = mask.shape
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        pix = []
        while stack:
            y, x = stack.pop()
            pix.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        yield np.array(pix)


def _backproject(ys, xs, d, K, T_wc):
    """像素 + 深度 → 世界坐标（VGGT 的相对尺度系）。"""
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    x_cam = (xs - cx) / fx * d
    y_cam = (ys - cy) / fy * d
    pts_cam = np.stack([x_cam, y_cam, d, np.ones_like(d)], axis=1)
    return (T_wc @ pts_cam.T).T[:, :3]


def extract_l1(l0_bundle: dict[str, Any], cfg: ExtractionConfig,
               class_names: dict[int, str] | None = None) -> dict[str, Any]:
    """把逐像素语义标注反投影成 L1 对象实体。"""
    from PIL import Image

    depth, conf = l0_bundle["depth"], l0_bundle["conf"]
    frames, cameras = l0_bundle["frames"], l0_bundle["cameras"]
    scene_id = l0_bundle["l0"]["scene_id"]
    S, H, W = conf.shape
    class_names = class_names or {}
    conf_floor = float(np.percentile(conf, _CONF_PERCENTILE_FLOOR))

    objects: list[dict[str, Any]] = []
    counter = 0
    for i, f in enumerate(frames):
        sem_rel = (f.get("native_labels") or {}).get("semantic_2d")
        if not sem_rel:
            continue
        arr = np.array(Image.open(cfg.scene_dir / sem_rel).resize((W, H), Image.NEAREST))
        sem = arr[..., 0] if arr.ndim == 3 else arr
        K = np.asarray(cameras[i]["K"], dtype=np.float64)
        T_wc = np.asarray(cameras[i]["T_world_from_camera"], dtype=np.float64)

        for cls in np.unique(sem):
            if cls == 0:                       # 0 = unlabeled
                continue
            for pix in _components(sem == cls):
                if len(pix) < _MIN_COMPONENT_PIXELS:
                    continue
                ys, xs = pix[:, 0], pix[:, 1]
                d = depth[i][ys, xs].astype(np.float64)
                c = conf[i][ys, xs]
                keep = np.isfinite(d) & (d > 0) & (c >= conf_floor)
                if keep.sum() < _MIN_VALID_POINTS:
                    continue
                pts = _backproject(ys[keep], xs[keep], d[keep], K, T_wc)
                centroid = pts.mean(axis=0)
                lo, hi = pts.min(axis=0), pts.max(axis=0)
                counter += 1
                objects.append({
                    "object_id": f"<obj_{counter:03d}>",
                    "category": class_names.get(int(cls), f"class_{int(cls)}"),
                    "geometry": {
                        "centroid": centroid.tolist(),
                        "aabb": [*lo.tolist(), *hi.tolist()],
                        "obb": {"center": centroid.tolist(),
                                "extent": (hi - lo).tolist(),
                                "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
                    },
                    "point_support": {"point_count": int(keep.sum()),
                                      "source_frames": [f["frame_id"]]},
                    "visibility": {"visible_frames": [f["frame_id"]],
                                   "best_view_frame_id": f["frame_id"]},
                    "dynamic_state": "unknown",
                    "confidence": {
                        # 语义来自人工标注 → 高；几何来自视觉重建 → 用本场相对置信度
                        "semantic": 0.95,
                        "geometry": float(np.clip(c[keep].mean() / (conf.max() + 1e-9), 0, 1)),
                        "calibrated": False,        # §14.13：未标定，不得当概率用
                    },
                    "provenance": {
                        "source_frames": [f["frame_id"]],
                        "producers": ["uavscenes_native_semantic", "VGGT-Omega/1b_512"],
                        "derivation_program": "semantic_mask_backprojection",
                        "supervision_level": "deterministic_derived",
                    },
                })

    objects = _merge_across_frames(objects)

    l1 = {
        "schema_version": "0.1.0",
        "scene_id": scene_id,
        "objects": objects,
        "surfaces": [],
        "regions": [],
        "unresolved_conflicts": [],
        "provenance": {
            "created_at": _now(),
            "code_version": CODE_VERSION,
            "l0_geometry_ref": str(l0_bundle["out_dir"] / "l0_geometry.json"),
            "notes": ("实体 = 逐像素语义标注的连通域反投影；未做跨帧融合"
                      "（那是 L2-S3 / R-13）；跨帧只做了质心邻近的**粗**归并，见 _merge_across_frames。"),
        },
    }
    (l0_bundle["out_dir"] / "l1_entities.json").write_text(
        json.dumps(l1, ensure_ascii=False, indent=2))
    return l1


def _merge_across_frames(objects: list[dict[str, Any]],
                         rel_tol: float = 0.25) -> list[dict[str, Any]]:
    """**粗**跨帧合并：同类别且质心距离小于场景尺度 ``rel_tol`` 倍的实体归为一个。

    没有这一步，同一片水面会在每帧各产生一个实体 —— 实测 12 帧出 33 个 water，
    grounding 的候选列表因此退化（「最远的那个」在一堆重复项里没有意义）。

    **这不是 L2-S3 的真实融合**（那需要跨视角关联图、概率化匹配与
    merge/split 血缘，见 §14.9 与 R-13）。这里只做质心邻近的贪心归并，
    足够让第一条真实切片产出有意义的候选集，且在血缘里如实标注。
    """
    if not objects:
        return objects
    cent = np.array([o["geometry"]["centroid"] for o in objects], dtype=float)
    scale = float(np.linalg.norm(cent.max(axis=0) - cent.min(axis=0))) or 1.0
    thresh = rel_tol * scale

    merged: list[dict[str, Any]] = []
    used = np.zeros(len(objects), dtype=bool)
    for i, obj in enumerate(objects):
        if used[i]:
            continue
        same = [j for j in range(i, len(objects))
                if not used[j]
                and objects[j]["category"] == obj["category"]
                and np.linalg.norm(cent[j] - cent[i]) <= thresh]
        used[same] = True
        group = [objects[j] for j in same]
        pts = np.array([g["geometry"]["centroid"] for g in group], dtype=float)
        weights = np.array([g["point_support"]["point_count"] for g in group], dtype=float)
        centroid = (pts * weights[:, None]).sum(axis=0) / weights.sum()
        aabbs = np.array([g["geometry"]["aabb"] for g in group], dtype=float)
        lo, hi = aabbs[:, :3].min(axis=0), aabbs[:, 3:].max(axis=0)
        frames = sorted({fr for g in group for fr in g["visibility"]["visible_frames"]})
        rep = dict(group[0])
        rep["geometry"] = {
            "centroid": centroid.tolist(),
            "aabb": [*lo.tolist(), *hi.tolist()],
            "obb": {"center": centroid.tolist(), "extent": (hi - lo).tolist(),
                    "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        }
        rep["point_support"] = {"point_count": int(weights.sum()),
                                "source_frames": frames}
        rep["visibility"] = {"visible_frames": frames,
                             "visible_ratio": None,
                             "best_view_frame_id": group[0]["visibility"]["best_view_frame_id"]}
        rep["lineage"] = {"merged_from": [g["object_id"] for g in group]}
        rep["confidence"] = dict(rep["confidence"])
        rep["confidence"]["cross_view_support"] = len(frames)
        merged.append(rep)

    for k, obj in enumerate(merged, start=1):     # 合并后重新编号，保持连续
        obj["object_id"] = f"<obj_{k:03d}>"
    return merged


def _layer_ref(path: Path) -> dict[str, Any]:
    """层引用 = 路径 + schema 版本 + **内容摘要**。

    摘要是快照不可变的技术保证（schema 的要求）——
    任一层文件被改动，摘要即不匹配，下游能立刻发现引用的不是当初那份 metadata。
    """
    data = path.read_bytes()
    return {
        "uri": str(path),
        "schema_version": json.loads(data)["schema_version"],
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }


# ---------------------------------------------------------------- snapshot

def build_snapshot(l0_bundle: dict[str, Any], l1: dict[str, Any],
                   dataset_id: str, split_group_id: str) -> dict[str, Any]:
    """汇成 metadata snapshot —— 任务编译器的唯一输入口。"""
    scene_id = l1["scene_id"]
    n_obj = len(l1["objects"])
    diag = l0_bundle["l0"].get("diagnostics") or {}
    out = l0_bundle["out_dir"]

    l2_path = out / "l2_relations.json"
    l2_path.write_text(json.dumps({
        "schema_version": "0.1.0",
        "scene_id": scene_id,
        "relations": [],
        "cross_view_links": [],
        "provenance": {
            "created_at": _now(),
            "code_version": CODE_VERSION,
            "notes": "空层：L2-S3/S4 的关系派生尚未实现（R-13）。空 ≠ 缺失。",
        },
    }, ensure_ascii=False, indent=2))
    snap = {
        "schema_version": "0.1.0",
        "snapshot_id": f"meta_{_short_hash(scene_id, CODE_VERSION)}",
        "scene_id": scene_id,
        "dataset_id": dataset_id,
        "split_group_id": split_group_id,
        "layers": {
            "l0_geometry": _layer_ref(out / "l0_geometry.json"),
            "l1_entities": _layer_ref(out / "l1_entities.json"),
            # L2 关系层的**派生程序**尚未实现（R-13），但 schema 要求本层存在且带内容摘要。
            # 因此产出一份**空而合规**的 L2 —— 空与缺失是两回事，
            # 前者说「算过，没有关系」，后者说「没算」。理由记在 provenance.notes。
            "l2_relations": _layer_ref(l2_path),
        },
        "capabilities": {
            "scale_status": "relative",
            "depth_type": "relative",
            # 铁律 8/9：relative 场景 MUST NOT 出绝对米制题
            "metric_task_eligible": False,
            "available_entity_types": ["object"],
            "camera_baseline_m": None,          # relative 尺度下无从给出
            "parallax_ratio": diag.get("parallax_ratio"),
            "nadir_angle_median_deg": None,
            "depth_relief_ratio": None,
            "entity_count": n_obj,
            "reasons": ["scale_status=relative：未做米制锚定，绝对米制任务不解锁"],
        },
        "gate": {
            "gate_id": "G2",
            "status": "warn" if n_obj < 3 else "pass",
            "warnings": ([f"实体数 {n_obj} < 3，多数任务的候选下限不满足"]
                         if n_obj < 3 else []),
        },
        "provenance": {
            "created_at": _now(),
            "code_version": CODE_VERSION,
            "schema_versions": {"l0_geometry": "0.1.0", "l1_entities": "0.1.0",
                                "metadata_snapshot": "0.1.0"},
        },
    }
    (l0_bundle["out_dir"] / "metadata_snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2))
    return snap
