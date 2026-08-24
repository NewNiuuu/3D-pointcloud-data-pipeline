"""UAVScenes dataset adapter：原始档案 → 归一化场景契约。

契约来源：CLAUDE_CODE_PROJECT_SPEC.md §11（L2-S0）、§12（Normalized Scene Contract）。

## 数据集事实（2026-08-24 实测，非文档转述）

- 4 个地点、20 个 run。同地点的 ``_GNSS`` / ``_Evening`` 变体属同一
  ``split_group_id``，必须绑定同一 split（SPEC 铁律 11）。
- ``sampleinfos_interpolated.json`` 覆盖 interval=1 全部帧，而 interval=5
  只发布其中 1/5 的图像。因此**必须按图像文件名做连接**，不能按下标取。
- ``T4x4`` 经 RTK 交叉验证确认为 **world_from_camera**（相机中心即平移列）：
  与 RTK 水平轨迹绝对相关 0.9877，而 camera_from_world 假设仅 0.2155。
- 世界系为**米制**：4 个地点的 Umeyama 相似变换尺度因子 0.9976~1.0022，
  偏离 1.0 最大 0.241%。
- LiDAR 为逐帧 ASCII XYZ 三列，**无 intensity/ring/time**，不得臆造这些字段。
- 图像与点云的配对已由官方完成，编码在点云文件名中：
  ``image<img_ts>_lidar<lidar_ts>.txt``。
- 两个标注档案各含 ``*_id``（类别 ID）与 ``*_color``（RGB 可视化）两份平行数据，
  **文件名完全相同**。语义真值取 ``*_id``；按文件名匹配而不指定子目录会随机
  命中其一（v0.1.0 的缺陷）。

## 场景切分

一个 run 是完整飞行，帧数达数千，远超 VGGT-Ω 单次可处理量
（PROJECT_HANDOFF §6.1：A100 上 100 帧约 13.4GB、500 帧约 43GB）。
因此 adapter 将 run 切成定长窗口，每个窗口是一个 scene。窗口**不跨 run**，
``split_group_id`` 一律取地点，保证同地点全部数据落在同一 split。
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

__all__ = ["UAVScenesAdapter", "AdapterConfig", "SCENE_SCHEMA_VERSION", "ADAPTER_VERSION"]

ADAPTER_VERSION = "0.2.0"
SCENE_SCHEMA_VERSION = "0.1.0"
DATASET_ID = "uavscenes"
DATASET_VERSION = "iccv2025_camera_ready"

_ARCHIVE_CAM_LIDAR = "interval5_CAM_LIDAR.zip"
_ARCHIVE_CAM_LABEL = "interval5_CAM_label.zip"
_ARCHIVE_LIDAR_LABEL = "interval5_LIDAR_label.zip"

#: run 目录名 -> 地点。``_GNSS`` 与 ``_Evening`` 是同地点的不同架次/时段。
_RUN_LOCATION = re.compile(r"^interval5_(?P<loc>[A-Za-z]+?)(?:_GNSS)?(?:_Evening)?(?P<idx>\d*)$")

#: 点云文件名内嵌的双时间戳
_LIDAR_NAME = re.compile(r"^image(?P<img>[\d.]+)_lidar(?P<lidar>[\d.]+)\.txt$")


def _ts_to_ns(timestamp: str) -> int:
    """秒.纳秒 字符串 -> 整数纳秒。避免 float 丢精度。"""
    if "." in timestamp:
        sec, frac = timestamp.split(".", 1)
    else:
        sec, frac = timestamp, ""
    return int(sec) * 1_000_000_000 + int(frac.ljust(9, "0")[:9])


@dataclass(frozen=True)
class AdapterConfig:
    """adapter 运行配置。不硬编码服务器路径（SPEC §33）。"""

    data_root: Path
    output_root: Path
    frames_per_scene: int = 50
    scene_stride: int | None = None      # None = 不重叠
    min_frames_per_scene: int = 20
    materialize: bool = True             # 是否把帧文件解出到场景目录

    def __post_init__(self) -> None:
        if self.frames_per_scene <= 0:
            raise ValueError("frames_per_scene 必须为正")
        if self.min_frames_per_scene > self.frames_per_scene:
            raise ValueError("min_frames_per_scene 不得大于 frames_per_scene")

    @property
    def stride(self) -> int:
        return self.scene_stride or self.frames_per_scene


class UAVScenesAdapter:
    """把 UAVScenes 的一个 run 切分并归一化为若干场景契约。"""

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config
        root = Path(config.data_root)
        self._zips: dict[str, zipfile.ZipFile] = {}
        for archive in (_ARCHIVE_CAM_LIDAR, _ARCHIVE_CAM_LABEL, _ARCHIVE_LIDAR_LABEL):
            path = root / archive
            if not path.exists():
                raise FileNotFoundError(f"缺少档案：{path}")
            self._zips[archive] = zipfile.ZipFile(path)
        self._members: dict[str, set[str]] = {
            name: set(zf.namelist()) for name, zf in self._zips.items()
        }

    # ---------- 发现 ----------

    def list_runs(self) -> list[str]:
        """返回全部 run 目录名，按字典序。"""
        zf = self._zips[_ARCHIVE_CAM_LIDAR]
        return sorted({n.split("/")[1] for n in zf.namelist() if n.count("/") >= 2})

    @staticmethod
    def split_group(run: str) -> str:
        """run -> split_group_id（地点）。

        同地点的全部 run（含 ``_GNSS`` / ``_Evening`` 变体）返回同一个值，
        以满足 SPEC 铁律 11。
        """
        match = _RUN_LOCATION.match(run)
        if match is None:
            raise ValueError(f"无法解析 run 名称：{run!r}")
        return match.group("loc")

    # ---------- 读取 ----------

    def _read_sampleinfos(self, run: str) -> dict[str, dict[str, Any]]:
        """读取位姿/内参表，按 ``OriginalImageName`` 索引。

        注意该表覆盖 interval=1 全部帧，条目数约为已发布图像的 5 倍。
        """
        path = f"interval5_CAM_LIDAR/{run}/sampleinfos_interpolated.json"
        entries = json.loads(self._zips[_ARCHIVE_CAM_LIDAR].read(path))
        return {e["OriginalImageName"]: e for e in entries}

    def _read_rtk(self, run: str) -> list[dict[str, float]]:
        path = f"interval5_CAM_LIDAR/{run}/rtk_positions_raw.csv"
        if path not in self._members[_ARCHIVE_CAM_LIDAR]:
            return []
        raw = self._zips[_ARCHIVE_CAM_LIDAR].open(path)
        rows = csv.DictReader(io.TextIOWrapper(raw, "utf-8"))
        return [
            {
                "timestamp_ns": _ts_to_ns(r["headerstamp"]),
                "lat": float(r["lat"]), "lon": float(r["lon"]), "alt": float(r["alt"]),
                "easting": float(r["easting"]), "northing": float(r["northing"]),
            }
            for r in rows
        ]

    def _lidar_index(self, run: str) -> dict[str, str]:
        """图像文件名 -> 点云成员路径。配对关系取自官方文件名，不自行按时间猜。"""
        prefix = f"interval5_CAM_LIDAR/{run}/interval5_LIDAR/"
        index: dict[str, str] = {}
        for member in self._members[_ARCHIVE_CAM_LIDAR]:
            if not member.startswith(prefix) or member.endswith("/"):
                continue
            match = _LIDAR_NAME.match(member.rsplit("/", 1)[-1])
            if match:
                index[f"{match.group('img')}.jpg"] = member
        return index

    def _image_members(self, run: str) -> list[str]:
        prefix = f"interval5_CAM_LIDAR/{run}/interval5_CAM/"
        members = [
            m for m in self._members[_ARCHIVE_CAM_LIDAR]
            if m.startswith(prefix) and m.endswith(".jpg")
        ]
        return sorted(members, key=lambda m: _ts_to_ns(m.rsplit("/", 1)[-1][:-4]))

    def _label_member(self, archive: str, run: str, subdir: str, stem: str,
                      suffix: str) -> str | None:
        """定位标注成员。

        **必须显式指定子目录**：两个标注档案各含 ``*_id`` 与 ``*_color`` 两份
        平行数据，**文件名完全相同**（各 2589 个）。早期实现用后缀匹配遍历无序
        ``set``，会在两者间随机命中，导致约半数帧拿到 RGB 可视化而非类别 ID。
        此处改为拼接确定路径并校验存在性。

        语义真值一律取 ``*_id``；``*_color`` 仅供人工查看，不进入 pipeline。
        """
        member = f"{subdir}/{run}/{subdir}_{'id'}/{stem}{suffix}"
        return member if member in self._members[archive] else None

    # ---------- 归一化 ----------

    def build_scenes(self, run: str) -> Iterator[dict[str, Any]]:
        """把一个 run 切成若干归一化场景。"""
        images = self._image_members(run)
        if not images:
            raise ValueError(f"run {run!r} 中没有图像")

        sampleinfos = self._read_sampleinfos(run)
        lidar_index = self._lidar_index(run)
        rtk = self._read_rtk(run)
        group = self.split_group(run)

        cfg = self.config
        for start in range(0, len(images), cfg.stride):
            window = images[start : start + cfg.frames_per_scene]
            if len(window) < cfg.min_frames_per_scene:
                break  # 尾部不足的窗口丢弃，避免产生无法重建的碎片场景
            scene_index = start // cfg.stride
            yield self._build_scene(run, group, scene_index, window,
                                    sampleinfos, lidar_index, rtk)

    def _build_scene(
        self,
        run: str,
        group: str,
        scene_index: int,
        window: list[str],
        sampleinfos: dict[str, dict[str, Any]],
        lidar_index: dict[str, str],
        rtk: list[dict[str, float]],
    ) -> dict[str, Any]:
        run_short = run.replace("interval5_", "")
        scene_id = f"{DATASET_ID}_{run_short}_{scene_index:04d}"
        scene_dir = Path(self.config.output_root) / scene_id

        frames: list[dict[str, Any]] = []
        missing_pose = 0
        missing_lidar = 0

        for member in window:
            image_name = member.rsplit("/", 1)[-1]
            stem = image_name[:-4]
            info = sampleinfos.get(image_name)
            if info is None:
                missing_pose += 1
                continue

            frame: dict[str, Any] = {
                "frame_id": stem,
                "timestamp_ns": _ts_to_ns(stem),
                "camera_id": "cam_0",
                "image_uri": f"images/{image_name}",
                "image_sha256": None,
                "original_size": [int(info["Height"]), int(info["Width"])],
                "camera": {
                    "K": info["P3x3"],
                    "distortion_model": "opencv",
                    "distortion": [info["K1"], info["K2"], info["P1"],
                                   info["P2"], info["K3"]],
                    "T_world_from_camera": info["T4x4"],
                    "coordinate_convention": "unknown",
                    "pose_source": "native",
                },
                "native_labels": {},
            }

            lidar_member = lidar_index.get(image_name)
            if lidar_member is None:
                missing_lidar += 1
            else:
                lidar_name = lidar_member.rsplit("/", 1)[-1]
                lidar_match = _LIDAR_NAME.match(lidar_name)
                frame["lidar"] = {
                    "point_uri": f"lidar/{lidar_name}",
                    "format": "ascii_xyz",
                    "timestamp_ns": _ts_to_ns(lidar_match.group("lidar")),
                    "point_count": None,
                    "fields": ["x", "y", "z"],
                    "native_label_uri": None,
                }

            cam_label = self._label_member(
                _ARCHIVE_CAM_LABEL, run, "interval5_CAM_label", stem, ".png")
            if cam_label:
                frame["native_labels"]["semantic_2d"] = f"labels_cam/{stem}.png"
            lidar_label = None
            if lidar_member:
                lidar_stem = lidar_member.rsplit("/", 1)[-1][:-4]
                lidar_label = self._label_member(
                    _ARCHIVE_LIDAR_LABEL, run, "interval5_LIDAR_label",
                    lidar_stem, ".txt")
                if lidar_label:
                    frame["lidar"]["native_label_uri"] = f"labels_lidar/{lidar_stem}.txt"

            if self.config.materialize:
                self._extract(_ARCHIVE_CAM_LIDAR, member, scene_dir / "images" / image_name)
                if lidar_member:
                    self._extract(_ARCHIVE_CAM_LIDAR, lidar_member,
                                  scene_dir / "lidar" / lidar_member.rsplit("/", 1)[-1])
                if cam_label:
                    self._extract(_ARCHIVE_CAM_LABEL, cam_label,
                                  scene_dir / "labels_cam" / f"{stem}.png")
                if lidar_label:
                    self._extract(_ARCHIVE_LIDAR_LABEL, lidar_label,
                                  scene_dir / "labels_lidar" / lidar_label.rsplit("/", 1)[-1])

            frames.append(frame)

        if not frames:
            raise ValueError(f"场景 {scene_id} 没有可用帧（位姿缺失 {missing_pose}）")

        window_rtk = self._rtk_window(rtk, frames)
        scene = {
            "schema_version": SCENE_SCHEMA_VERSION,
            "scene_id": scene_id,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "split_group_id": group,
            "source_type": "real",
            "frames": frames,
            "native_annotations": self._native_annotations(frames),
            "sensor_calibration": {
                "note": "相机-LiDAR 外参见数据集根目录 calibration_results.py；"
                        "adapter 未内联，避免复制易过期的常量",
                "camera_lidar_extrinsics_ref": "calibration_results.py",
            },
            "coordinate_frame": "uavscenes_world_metric",
            "unit": "meter",
            "scale": {
                "status": "metric",
                "source": "rtk_gps",
                "depth_source": "direct_lidar",
                "depth_type": "externally_anchored",
                "uncertainty_m": 2.0,
                "domain_calibrated": False,
                "anchor_provenance_verified": True,
            },
            "provenance": {
                "adapter_name": "uavscenes",
                "adapter_version": ADAPTER_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_paths": [
                    f"{_ARCHIVE_CAM_LIDAR}!{run}",
                    f"{_ARCHIVE_CAM_LABEL}!{run}",
                    f"{_ARCHIVE_LIDAR_LABEL}!{run}",
                ],
                "source_digests": {},
                "transforms_applied": [],
                "notes": (
                    "T4x4 原样保留为 world_from_camera，未做任何位姿变换；"
                    "该方向经 RTK 轨迹交叉验证（水平绝对相关 0.9877，"
                    "camera_from_world 假设仅 0.2155）。"
                    "世界系尺度经 Umeyama 对齐验证：4 地点尺度因子 "
                    "0.9976~1.0022，偏离 1.0 最大 0.241%。"
                ),
            },
            "diagnostics": {
                "run": run,
                "scene_index": scene_index,
                "frames_requested": len(window),
                "frames_emitted": len(frames),
                "frames_missing_pose": missing_pose,
                "frames_missing_lidar": missing_lidar,
                "duration_s": round(
                    (frames[-1]["timestamp_ns"] - frames[0]["timestamp_ns"]) / 1e9, 3),
                "rtk_samples_in_window": len(window_rtk),
                "camera_translation_span_m": self._translation_span(frames),
            },
        }
        return scene

    # ---------- 辅助 ----------

    def _extract(self, archive: str, member: str, target: Path) -> None:
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._zips[archive].open(member) as src, open(target, "wb") as dst:
            dst.write(src.read())

    @staticmethod
    def _rtk_window(rtk: list[dict[str, float]],
                    frames: list[dict[str, Any]]) -> list[dict[str, float]]:
        if not rtk:
            return []
        lo, hi = frames[0]["timestamp_ns"], frames[-1]["timestamp_ns"]
        return [r for r in rtk if lo <= r["timestamp_ns"] <= hi]

    @staticmethod
    def _translation_span(frames: list[dict[str, Any]]) -> list[float]:
        """相机中心在世界系中的包围盒尺寸（米），用于粗判视角覆盖。"""
        centers = [
            f["camera"]["T_world_from_camera"] for f in frames
            if f["camera"].get("T_world_from_camera")
        ]
        if not centers:
            return []
        xs = [c[0][3] for c in centers]
        ys = [c[1][3] for c in centers]
        zs = [c[2][3] for c in centers]
        return [round(max(v) - min(v), 3) for v in (xs, ys, zs)]

    @staticmethod
    def _native_annotations(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        annotations: list[dict[str, Any]] = []
        if any(f["native_labels"].get("semantic_2d") for f in frames):
            annotations.append({
                "annotation_type": "semantic_2d",
                "uri": "labels_cam/",
                "label_space": "uavscenes_cmap",
                "supervision_level": "strong",
                "notes": "官方人工标注（X-AnyLabeling）；色彩-ID 映射见 cmap.py",
            })
        if any((f.get("lidar") or {}).get("native_label_uri") for f in frames):
            annotations.append({
                "annotation_type": "semantic_3d",
                "uri": "labels_lidar/",
                "label_space": "uavscenes_cmap",
                "supervision_level": "strong",
                "notes": "官方人工标注（CloudCompare），逐点标签",
            })
        return annotations

    def close(self) -> None:
        for zf in self._zips.values():
            zf.close()

    def __enter__(self) -> "UAVScenesAdapter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
