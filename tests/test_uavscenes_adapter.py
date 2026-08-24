"""UAVScenes adapter 的契约测试。

用**真实数据**跑（不是合成 fixture）—— adapter 的价值在于处理真实数据集的
不规则之处，合成 fixture 只会验证我对格式的假设，而假设正是最容易错的部分。
数据不存在时跳过，以免在没有数据的机器上误报失败。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from adapters.uavscenes import AdapterConfig, UAVScenesAdapter  # noqa: E402

DATA_ROOT = Path("/home/aiscuser/nyp/data_raw/UAVScenes")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "normalized_scene.schema.json"

pytestmark = pytest.mark.skipif(
    not (DATA_ROOT / "interval5_CAM_LIDAR.zip").exists(),
    reason="UAVScenes 原始档案不在本机",
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adapter(tmp_path_factory) -> UAVScenesAdapter:
    cfg = AdapterConfig(
        data_root=DATA_ROOT,
        output_root=tmp_path_factory.mktemp("scenes"),
        frames_per_scene=25,
        min_frames_per_scene=10,
        materialize=False,          # 契约测试不落盘，只验证结构
    )
    with UAVScenesAdapter(cfg) as ad:
        yield ad


@pytest.fixture(scope="module")
def scene(adapter) -> dict:
    return next(adapter.build_scenes("interval5_AMtown01"))


class TestRunDiscovery:
    def test_finds_all_twenty_runs(self, adapter):
        runs = adapter.list_runs()
        assert len(runs) == 20, runs

    def test_split_groups_collapse_gnss_and_evening_variants(self, adapter):
        """SPEC 铁律 11：同地点的全部架次必须归入同一 split group。"""
        groups = {UAVScenesAdapter.split_group(r) for r in adapter.list_runs()}
        assert groups == {"AMtown", "AMvalley", "HKairport", "HKisland"}

    @pytest.mark.parametrize("run,expected", [
        ("interval5_AMtown01", "AMtown"),
        ("interval5_HKairport03", "HKairport"),
        ("interval5_HKairport_GNSS02", "HKairport"),
        ("interval5_HKairport_GNSS_Evening", "HKairport"),
        ("interval5_HKisland_GNSS_Evening", "HKisland"),
    ])
    def test_split_group_mapping(self, run, expected):
        assert UAVScenesAdapter.split_group(run) == expected


class TestSceneContract:
    def test_validates_against_schema(self, scene, schema):
        jsonschema.validate(instance=scene, schema=schema)

    def test_scale_declares_metric_with_rtk_anchor(self, scene):
        scale = scene["scale"]
        assert scale["status"] == "metric"
        assert scale["source"] == "rtk_gps"
        assert scale["depth_source"] == "direct_lidar"
        assert scale["depth_type"] == "externally_anchored"
        assert scale["anchor_provenance_verified"] is True
        # 域校准尚未做，必须如实为 False
        assert scale["domain_calibrated"] is False

    def test_frames_are_time_ordered_and_unique(self, scene):
        stamps = [f["timestamp_ns"] for f in scene["frames"]]
        assert stamps == sorted(stamps)
        assert len(set(stamps)) == len(stamps)

    def test_timestamps_are_integers_not_floats(self, scene):
        """纳秒必须是整数，float 会丢精度导致帧错配。"""
        for frame in scene["frames"]:
            assert isinstance(frame["timestamp_ns"], int)

    def test_every_frame_has_pose_and_intrinsics(self, scene):
        for frame in scene["frames"]:
            cam = frame["camera"]
            assert cam["T_world_from_camera"] is not None
            assert len(cam["T_world_from_camera"]) == 4
            assert len(cam["K"]) == 3
            assert cam["pose_source"] == "native"

    def test_pose_bottom_row_is_homogeneous(self, scene):
        for frame in scene["frames"]:
            assert frame["camera"]["T_world_from_camera"][3] == [0.0, 0.0, 0.0, 1.0]

    def test_lidar_fields_are_not_fabricated(self, scene):
        """数据只有 XYZ 三列，不得声称有 intensity/ring/time。"""
        for frame in scene["frames"]:
            lidar = frame.get("lidar")
            if lidar:
                assert lidar["fields"] == ["x", "y", "z"]
                assert lidar["format"] == "ascii_xyz"

    def test_image_lidar_pairing_comes_from_official_filenames(self, scene):
        """配对取自官方文件名，图像与点云时间戳应当接近但不相等。"""
        paired = [f for f in scene["frames"] if f.get("lidar")]
        assert paired, "该场景没有配对到任何点云"
        for frame in paired:
            delta_s = abs(frame["timestamp_ns"] - frame["lidar"]["timestamp_ns"]) / 1e9
            assert delta_s < 0.1, f"{frame['frame_id']} 图像-点云时差 {delta_s}s 过大"

    def test_provenance_records_no_silent_pose_transform(self, scene):
        """位姿方向是核验出来的，不是猜的；未做变换就必须记为空。"""
        prov = scene["provenance"]
        assert prov["transforms_applied"] == []
        assert "world_from_camera" in prov["notes"]
        assert len(prov["source_paths"]) == 3

    def test_diagnostics_expose_missing_data_counts(self, scene):
        diag = scene["diagnostics"]
        assert diag["frames_emitted"] == len(scene["frames"])
        assert diag["frames_missing_pose"] >= 0
        assert diag["frames_missing_lidar"] >= 0
        assert diag["duration_s"] > 0
        assert len(diag["camera_translation_span_m"]) == 3


class TestSceneSlicing:
    def test_scenes_do_not_cross_runs(self, adapter):
        scenes = list(adapter.build_scenes("interval5_AMvalley02"))
        assert scenes
        for sc in scenes:
            assert sc["diagnostics"]["run"] == "interval5_AMvalley02"
            assert sc["split_group_id"] == "AMvalley"

    def test_scene_ids_unique_within_run(self, adapter):
        ids = [s["scene_id"] for s in adapter.build_scenes("interval5_AMvalley02")]
        assert len(set(ids)) == len(ids)

    def test_short_tail_window_is_dropped(self, adapter):
        """不足最小帧数的尾部窗口应被丢弃，避免产生无法重建的碎片。"""
        for sc in adapter.build_scenes("interval5_AMvalley02"):
            assert len(sc["frames"]) >= 10

    def test_config_rejects_invalid_window(self):
        with pytest.raises(ValueError):
            AdapterConfig(data_root=DATA_ROOT, output_root=DATA_ROOT,
                          frames_per_scene=0)
        with pytest.raises(ValueError):
            AdapterConfig(data_root=DATA_ROOT, output_root=DATA_ROOT,
                          frames_per_scene=10, min_frames_per_scene=20)
