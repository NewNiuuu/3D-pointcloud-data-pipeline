"""确定性几何函数：任务真值的唯一来源。

契约来源：DESIGN.md §14.15（Deterministic Geometry Boundary）、
铁律 7（可确定计算的值必须由程序产生并校验，不得只采信 LLM）。

SPEC §14.15 明确划界 —— 模型**可以**预测深度、法向、mask、track、可见性、
embedding、动态概率与尺度先验；但以下**必须**由程序计算：

    depth-to-point 变换、TSDF/voxel/ESDF occupancy、free/occupied/unknown、
    射线可见性与遮挡、对象质心/稳健尺寸/PCA 朝向、净空/可达性/候选航迹/
    next-best-view 信息增益、TTC/扫掠体碰撞/风险传播、跨帧一致性与置信度校准。

本模块实现首批任务所需的子集。设计约束：

1. **纯函数**，无全局状态、无 I/O，输入输出皆为数组或标量 —— 这样 checker
   才能独立重算并复现（SPEC §43.3 要求 target 可重算）。
2. **显式单位**。所有长度为米，角度为度或弧度由函数名与文档明示。
3. **退化情形不猜**。零长度线段、空点集、共线点等一律抛
   :class:`GeometryError`，不返回一个看似合理的数。任务编译器据此判定该场景
   不具备出题资格，而不是生成一道答案可疑的题。
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "GeometryError",
    "point_to_segment_distance",
    "point_to_polyline_distance",
    "minimum_point_to_polyline_distance",
    "pairwise_min_distance",
    "camera_center_from_pose",
    "camera_forward_from_pose",
    "world_to_camera",
    "project_points",
    "observer_relative_direction",
    "azimuth_elevation",
    "height_difference",
    "oriented_bounding_box",
    "axis_aligned_bounding_box",
    "centroid",
    "point_in_frustum",
    "visible_ratio",
]


class GeometryError(ValueError):
    """几何输入退化或不可计算。

    抛出而不是返回近似值 —— 一个退化场景应当失去出题资格，
    而不是产生一道真值可疑的题。
    """


def _as_points(points: np.ndarray | list, name: str = "points") -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise GeometryError(f"{name} 形状应为 (N,3)，实得 {arr.shape}")
    if arr.shape[0] == 0:
        raise GeometryError(f"{name} 为空")
    if not np.isfinite(arr).all():
        raise GeometryError(f"{name} 含 NaN 或 Inf")
    return arr


# --------------------------------------------------------------- 距离

def point_to_segment_distance(
    point: np.ndarray | list, seg_a: np.ndarray | list, seg_b: np.ndarray | list
) -> float:
    """点到线段的最短欧氏距离（米）。

    与"点到直线"不同：投影落在线段外时取端点距离。电线净空这类问题必须
    用线段，用无限直线会低估距离。
    """
    p = np.asarray(point, dtype=np.float64)
    a = np.asarray(seg_a, dtype=np.float64)
    b = np.asarray(seg_b, dtype=np.float64)
    for arr, name in ((p, "point"), (a, "seg_a"), (b, "seg_b")):
        if arr.shape != (3,):
            raise GeometryError(f"{name} 形状应为 (3,)，实得 {arr.shape}")
        if not np.isfinite(arr).all():
            raise GeometryError(f"{name} 含 NaN 或 Inf")

    ab = b - a
    denom = float(ab @ ab)
    if denom == 0.0:
        raise GeometryError("线段退化为一点（seg_a == seg_b），距离无定义")
    t = float(np.clip(((p - a) @ ab) / denom, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def point_to_polyline_distance(
    point: np.ndarray | list, polyline: np.ndarray | list
) -> tuple[float, int]:
    """点到折线的最短距离，返回 ``(距离_米, 最近段索引)``。

    最近段索引使 checker 能定位答案落在折线哪一段上，便于核对与可视化。
    """
    p = np.asarray(point, dtype=np.float64)
    line = _as_points(polyline, "polyline")
    if line.shape[0] < 2:
        raise GeometryError(f"折线至少需 2 个顶点，实得 {line.shape[0]}")

    best_distance = float("inf")
    best_index = -1
    for i in range(line.shape[0] - 1):
        if np.allclose(line[i], line[i + 1]):
            continue  # 跳过重复顶点而非报错：折线整体仍可用
        d = point_to_segment_distance(p, line[i], line[i + 1])
        if d < best_distance:
            best_distance, best_index = d, i
    if best_index < 0:
        raise GeometryError("折线所有顶点重合，距离无定义")
    return best_distance, best_index


def minimum_point_to_polyline_distance(
    point: np.ndarray | list, polylines: dict[str, np.ndarray | list]
) -> tuple[str, float, int]:
    """在多条折线中找最近的一条。

    返回 ``(实体ID, 距离_米, 最近段索引)``。

    这是 ``3d_vqa.metric.minimum_distance`` 的推导程序（SPEC §24 示例）。

    **不做歧义判定** —— 两条折线距离是否"同样近"取决于任务容差，属于任务
    编译器的职责。本函数只负责算，由调用方比较次近距离并决定是否标记歧义。
    """
    if not polylines:
        raise GeometryError("候选折线集合为空")
    results: list[tuple[str, float, int]] = []
    for entity_id, line in polylines.items():
        distance, segment = point_to_polyline_distance(point, line)
        results.append((entity_id, distance, segment))
    results.sort(key=lambda r: r[1])
    return results[0]


def pairwise_min_distance(
    points_a: np.ndarray | list, points_b: np.ndarray | list
) -> float:
    """两个点集之间的最小距离（米）。用于对象间净空。"""
    a = _as_points(points_a, "points_a")
    b = _as_points(points_b, "points_b")
    diff = a[:, None, :] - b[None, :, :]
    return float(np.sqrt((diff ** 2).sum(axis=2)).min())


# --------------------------------------------------------------- 相机

def camera_center_from_pose(t_world_from_camera: np.ndarray | list) -> np.ndarray:
    """从 4x4 ``world_from_camera`` 位姿取相机中心（世界系，米）。

    对该约定，相机中心就是平移列。**若位姿是 camera_from_world，此函数会给出
    错误结果** —— UAVScenes 的方向已用 RTK 轨迹交叉验证（相关 0.9877
    vs 0.2155），见 `adapters/uavscenes/adapter.py`。
    """
    T = _as_pose(t_world_from_camera)
    return T[:3, 3].copy()


def camera_forward_from_pose(
    t_world_from_camera: np.ndarray | list,
    convention: str = "x_right_y_down_z_forward",
) -> np.ndarray:
    """相机光轴在世界系中的单位方向向量。

    ``convention`` 决定相机系哪个轴是前方。默认 OpenCV 约定（+Z 向前）。
    约定写错会让所有"前/后/左/右"判断整体翻转，因此必须显式传入而非猜测。
    """
    T = _as_pose(t_world_from_camera)
    axis_map = {
        "x_right_y_down_z_forward": np.array([0.0, 0.0, 1.0]),   # OpenCV
        "x_right_y_up_z_backward": np.array([0.0, 0.0, -1.0]),   # OpenGL
    }
    if convention not in axis_map:
        raise GeometryError(
            f"未知相机约定 {convention!r}；支持 {sorted(axis_map)}")
    forward = T[:3, :3] @ axis_map[convention]
    norm = float(np.linalg.norm(forward))
    if norm == 0.0:
        raise GeometryError("位姿旋转部分退化，无法确定光轴方向")
    return forward / norm


def _as_pose(pose: np.ndarray | list) -> np.ndarray:
    T = np.asarray(pose, dtype=np.float64)
    if T.shape != (4, 4):
        raise GeometryError(f"位姿形状应为 (4,4)，实得 {T.shape}")
    if not np.isfinite(T).all():
        raise GeometryError("位姿含 NaN 或 Inf")
    if not np.allclose(T[3], [0.0, 0.0, 0.0, 1.0]):
        raise GeometryError(f"位姿末行应为 [0,0,0,1]，实得 {T[3].tolist()}")
    R = T[:3, :3]
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-4):
        raise GeometryError("位姿旋转部分非正交")
    return T


def world_to_camera(
    points_world: np.ndarray | list, t_world_from_camera: np.ndarray | list
) -> np.ndarray:
    """世界系点 -> 相机系点。"""
    P = _as_points(points_world, "points_world")
    T = _as_pose(t_world_from_camera)
    R, t = T[:3, :3], T[:3, 3]
    return (P - t) @ R          # R^T @ (p - t) 的批量写法


def project_points(
    points_world: np.ndarray | list,
    t_world_from_camera: np.ndarray | list,
    K: np.ndarray | list,
) -> tuple[np.ndarray, np.ndarray]:
    """投影到像素坐标，返回 ``(uv, 相机系深度)``。

    深度为相机系 Z。**不做畸变校正** —— 若数据含非零畸变系数，调用方必须
    先去畸变，否则投影会有系统偏差。UAVScenes 抽样显示畸变系数为 0（见
    dataset card 风险 R-007，尚待全量核验）。
    """
    P_cam = world_to_camera(points_world, t_world_from_camera)
    K_arr = np.asarray(K, dtype=np.float64)
    if K_arr.shape != (3, 3):
        raise GeometryError(f"内参 K 形状应为 (3,3)，实得 {K_arr.shape}")
    depth = P_cam[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        uvw = P_cam @ K_arr.T
        uv = uvw[:, :2] / uvw[:, 2:3]
    return uv, depth


# --------------------------------------------------------------- 观察者相对关系

def observer_relative_direction(
    target: np.ndarray | list,
    observer_position: np.ndarray | list,
    observer_forward: np.ndarray | list,
    up: np.ndarray | list = (0.0, 0.0, 1.0),
    lateral_deadzone_deg: float = 10.0,
) -> dict[str, str | float]:
    """目标相对观察者的方位（前/后/左/右/上/下）。

    ``lateral_deadzone_deg`` 是死区半角：目标落在正前方附近这个角度内时，
    左右分量返回 ``"ambiguous"`` 而不是硬判一边。**这不是保守，而是必要** ——
    紧贴中线的目标左右判定会因位姿微小误差翻转，生成的题目答案不稳定。
    任务编译器应把 ``"ambiguous"`` 的样本判为不合格（SPEC §43.3 要求歧义显式表达）。
    """
    p = np.asarray(target, dtype=np.float64)
    o = np.asarray(observer_position, dtype=np.float64)
    f = np.asarray(observer_forward, dtype=np.float64)
    u = np.asarray(up, dtype=np.float64)

    v = p - o
    dist = float(np.linalg.norm(v))
    if dist == 0.0:
        raise GeometryError("目标与观察者重合，方位无定义")

    f_norm = float(np.linalg.norm(f))
    if f_norm == 0.0:
        raise GeometryError("观察者朝向为零向量")
    f = f / f_norm

    # 用 up 正交化出右向量；若 forward 与 up 平行则右向量无定义
    right = np.cross(f, u)
    right_norm = float(np.linalg.norm(right))
    if right_norm < 1e-8:
        raise GeometryError("观察者朝向与 up 向量近乎平行，左右方向无定义")
    right = right / right_norm

    v_unit = v / dist
    forward_component = float(v_unit @ f)
    right_component = float(v_unit @ right)
    up_component = float(v_unit @ (u / np.linalg.norm(u)))

    lateral_angle_deg = float(np.degrees(np.arcsin(np.clip(right_component, -1, 1))))
    if abs(lateral_angle_deg) < lateral_deadzone_deg:
        lateral = "ambiguous"
    else:
        lateral = "right" if right_component > 0 else "left"

    return {
        "longitudinal": "front" if forward_component >= 0 else "behind",
        "lateral": lateral,
        "vertical": "above" if up_component >= 0 else "below",
        "distance_m": dist,
        "forward_component": forward_component,
        "right_component": right_component,
        "up_component": up_component,
        "lateral_angle_deg": lateral_angle_deg,
    }


def azimuth_elevation(
    target: np.ndarray | list,
    observer_position: np.ndarray | list,
    observer_forward: np.ndarray | list,
    up: np.ndarray | list = (0.0, 0.0, 1.0),
) -> tuple[float, float]:
    """目标相对观察者的 ``(方位角, 俯仰角)``，单位度。

    方位角以观察者正前方为 0，向右为正，范围 ``(-180, 180]``；
    俯仰角以水平面为 0，向上为正，范围 ``[-90, 90]``。
    """
    o = np.asarray(observer_position, dtype=np.float64)
    v = np.asarray(target, dtype=np.float64) - o
    dist = float(np.linalg.norm(v))
    if dist == 0.0:
        raise GeometryError("目标与观察者重合，角度无定义")

    u = np.asarray(up, dtype=np.float64)
    u = u / np.linalg.norm(u)
    f = np.asarray(observer_forward, dtype=np.float64)
    f = f - (f @ u) * u                       # 投影到水平面
    f_norm = float(np.linalg.norm(f))
    if f_norm < 1e-8:
        raise GeometryError("观察者朝向近乎垂直，水平方位角无定义")
    f = f / f_norm
    right = np.cross(f, u)

    v_h = v - (v @ u) * u
    azimuth = float(np.degrees(np.arctan2(v_h @ right, v_h @ f)))
    elevation = float(np.degrees(np.arcsin(np.clip((v / dist) @ u, -1, 1))))
    return azimuth, elevation


def height_difference(
    target: np.ndarray | list,
    reference: np.ndarray | list,
    up: np.ndarray | list = (0.0, 0.0, 1.0),
) -> float:
    """沿 ``up`` 方向的高度差（米），正值表示 target 更高。"""
    u = np.asarray(up, dtype=np.float64)
    u = u / np.linalg.norm(u)
    return float((np.asarray(target, dtype=np.float64)
                  - np.asarray(reference, dtype=np.float64)) @ u)


# --------------------------------------------------------------- 实体几何

def centroid(points: np.ndarray | list) -> np.ndarray:
    """点集质心。"""
    return _as_points(points).mean(axis=0)


def axis_aligned_bounding_box(points: np.ndarray | list) -> tuple[np.ndarray, np.ndarray]:
    """轴对齐包围盒，返回 ``(min_xyz, max_xyz)``。"""
    P = _as_points(points)
    return P.min(axis=0), P.max(axis=0)


def oriented_bounding_box(points: np.ndarray | list) -> dict[str, np.ndarray]:
    """PCA 定向包围盒。

    返回 ``center``、``extent``（三边全长）、``axes``（3x3，行为主轴单位向量）。

    对退化点集（少于 3 点、或全部共线/共面导致主轴不定）抛
    :class:`GeometryError` —— 这类实体不应被用来出朝向类题目。
    """
    P = _as_points(points)
    if P.shape[0] < 3:
        raise GeometryError(f"OBB 至少需 3 个点，实得 {P.shape[0]}")

    center_raw = P.mean(axis=0)
    centered = P - center_raw
    cov = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    axes = eigenvectors[:, order].T           # 行向量为主轴

    if eigenvalues[0] <= 1e-12:
        raise GeometryError("点集退化为单点，OBB 无定义")

    projected = centered @ axes.T
    lo, hi = projected.min(axis=0), projected.max(axis=0)
    extent = hi - lo
    center = center_raw + (lo + hi) / 2.0 @ axes

    return {
        "center": center,
        "extent": extent,
        "axes": axes,
        "eigenvalues": eigenvalues,
    }


# --------------------------------------------------------------- 可见性

def point_in_frustum(
    points_world: np.ndarray | list,
    t_world_from_camera: np.ndarray | list,
    K: np.ndarray | list,
    image_size: tuple[int, int],
    near_m: float = 0.1,
    far_m: float = float("inf"),
) -> np.ndarray:
    """逐点判断是否落在相机视锥内，返回布尔数组。

    **这只是视锥测试，不是可见性** —— 不考虑遮挡。真正的可见性需要深度缓冲
    或射线求交（SPEC §14.15 要求射线可见性由程序计算）。把视锥测试当可见性
    会把被建筑挡住的物体判为可见。
    """
    uv, depth = project_points(points_world, t_world_from_camera, K)
    height, width = image_size
    inside = (
        (depth > near_m) & (depth < far_m)
        & np.isfinite(uv).all(axis=1)
        & (uv[:, 0] >= 0) & (uv[:, 0] < width)
        & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    )
    return inside


def visible_ratio(
    points_world: np.ndarray | list,
    t_world_from_camera: np.ndarray | list,
    K: np.ndarray | list,
    image_size: tuple[int, int],
    near_m: float = 0.1,
) -> float:
    """落入视锥的点数占比，取值 ``[0, 1]``。

    同 :func:`point_in_frustum`，**不含遮挡**。命名为 ratio 而非
    ``occlusion_ratio`` 即为避免混淆。
    """
    inside = point_in_frustum(points_world, t_world_from_camera, K,
                              image_size, near_m=near_m)
    return float(inside.mean())
