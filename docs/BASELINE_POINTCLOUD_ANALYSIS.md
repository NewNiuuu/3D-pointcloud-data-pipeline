# 现有点云语料分析

> 对象：blob 上 `Pointcloud-VQA/` 与 `PointCloud-grounding/` 中同事已用 VGGT-Ω 生成的点云
> 目的：在自行部署 VGGT-Ω 之前，先摸清其实际输出形态，降低 Layer 2 的未知风险
> 实测日期：2026-08-24
> 样本：`Pointcloud-VQA/Floodnet/train/` 的 10165 / 10166 / 10168.ply（各 2.0 MB）

## 1. 文件格式

```
format binary_little_endian 1.0
comment https://github.com/mikedh/trimesh
element vertex 129305
property float x / y / z
property uchar red / green / blue / alpha
end_header
```

**逐点字段只有 xyz 与 rgba。** 缺少：

| 本项目需要的字段 | 是否存在 | SPEC 依据 |
|---|---|---|
| 法向 | ✗ | §16 L0 |
| 深度置信度 | ✗ | §13 要求保留阈值化前的原始置信度 |
| 相机内参/外参/位姿 | ✗ | §16 L0、§14.10 |
| 坐标系与单位声明 | ✗ | §12、铁律 10 |
| provenance（模型版本、checkpoint hash、输入帧） | ✗ | 铁律 10 |
| 逐点有效性/无效原因 | ✗ | §14.5 |

alpha 恒为 255，无 NaN/Inf，无重复点。

**结论**：这些 `.ply` 是**可视化/交付形态**，不是 VGGT-Ω 的完整输出。本 Pipeline 的 metadata 层无法直接消费它们 —— 缺置信度就无法做质量门禁（G1/G2），缺相机参数就无法做投影、可见性与跨视角关联。

## 2. 几何与尺度

| 文件 | 点数 | x 跨度 | y 跨度 | z 跨度 | 到原点距离中位数 |
|---|---:|---:|---:|---:|---:|
| 10165 | 129305 | 0.814 | 0.540 | 0.118 | 1.002 |
| 10166 | 129304 | 0.787 | 0.513 | 0.104 | 1.007 |
| 10168 | 129305 | 0.811 | 0.483 | 0.052 | 1.018 |

**尺度是 relative，不是 metric。** 到原点距离中位数 ≈ 1.00，整个场景跨度不足 1 个单位 —— 对一片洪涝航拍区域而言，这只能是归一化坐标。按铁律 8/9 与 SPEC §14.11，`relative` 深度**禁止**用于生成绝对米制目标。

**深度起伏很小**：`z_max/z_min ≈ 1.13`。这有两重含义 ——

1. 航拍近垂直视角下，地表相对观测距离本就接近平面，这是低空/航拍数据的固有特性，不是重建缺陷；
2. 但它意味着这类场景**可供 3D 任务利用的深度信息有限**，距离/高差类问题的可区分度低。

## 3. 组织方式

每个 QA 样本对应**恰好一个** `.ply`（全部 9 个数据集、约 38 万样本，`point_clouds` 长度分布均为 `{1: N}`）。文件名即图像 ID。故这些点云是**逐图像的单视角深度反投影**，不是多视角融合重建。

样本格式为 `<point_cloud>` token + conversations，即原生点云模型（PointLLM/SpatialLM 系）的训练格式，对应 `3D-GRPO` 那条路线，而非 Qwen 的 2D+metadata 路线。

## 4. 任务形态

已标注题型的两个数据集：

- **Floodnet**（4511 条）：`Condition_Recognition` 2315、`Yes_No` 867、`Complex_Counting` 693、`Simple_Counting` 636
- **AirCopBench**（2286 条）：`When to Collaborate`、`Object Counting`、`Quality Assessment`、`What to Collaborate`

示例：

```
Q: <point_cloud> What is the overall condition of the given image?
A: flooded
```

这类问题是**把 2D 识别题搬到点云上**：答案可由单张图像的外观直接得出，不依赖三维信息。PROJECT_HANDOFF §2.2 与 SPEC 铁律 5 明确把这种形态排除在项目范围之外。

这不是对既有工作的否定 —— 它恰好说明本 Pipeline 要补的是什么：**从"点云 + 2D 题"变成"点云 + 真正依赖三维的题"**，并且点云本身要带尺度、置信度与 provenance。

## 5. 对本 Pipeline 的直接影响

1. **不能把这批点云当作首批闭环的几何输入。** 缺置信度与相机参数，过不了 G1/G2；且为 relative 尺度，与首版"强制 metric"政策冲突。
2. **本 Pipeline 必须保存 VGGT-Ω 的完整输出**，而不只是导出一个可视化 `.ply`。至少需要：depth、depth confidence、相机内外参、坐标系与尺度声明、checkpoint hash。
3. **UAVScenes 的多视角 + RTK 是关键差异点。** 它能提供本批语料缺失的两样东西：真实多视角基线（而非单视角反投影）与米制锚点（已实测尺度因子偏离 1.0 不超过 0.241%）。
4. **深度起伏小是航拍固有难点**，需在任务设计时正面处理：优先选取有高差的场景（建筑、杆塔、植被冠层），并在 Task Spec 的 `eligibility` 中加入深度起伏下限。

## 6. 复现方式

```bash
export PATH="/home/aiscuser:$PATH"            # azcopy 不在默认 PATH
cd /home/aiscuser
echo y | python tools/blob_manager.py download \
    Pointcloud-VQA/Floodnet/train/10165.ply /目标/路径/10165.ply
```

注意 azcopy 会把单文件放进同名目录，实际文件在 `10165.ply/10165.ply`。
