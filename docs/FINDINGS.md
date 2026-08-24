# 调研发现

> **面向人类阅读的调研笔记。** 只记结论和它为什么重要，细节在对应的详细文档里。
> 每条的格式：**结论一句话** → 为什么重要 → 详情去哪看。
> 最新在最上方。建立于 2026-08-24。

---

## 专家模型

### 三个深度模型给出三个不同答案，而且都对不上 LiDAR

同一帧 UAVScenes 图像上：

| 来源 | 深度 |
|---|---|
| DA3-LARGE-1.1 | 0.57 – 1.02（归一化，非米制） |
| DA3Metric-Large | 6.97 – 23.78 m，中位 13.30 |
| MoGe-3 ViT-L | 16.74 – 22.96 m |
| LiDAR 真值 | 31.09 – 38.02 m，中位 33.13（射线距离） |

**为什么重要**：这正是"多模型不能投票产生真值"的现实例证 —— 取平均或多数决只会得到一个同样错的数。正确做法是先对齐、算残差、再校准成错误概率。

**注意这个对比本身不严谨**：LiDAR 给的是射线距离，模型给的是垂直深度，两者传感器原点和视场都不同。**严格验证需要相机-LiDAR 外参**，而 `calibration_results.py` 不在我们下载的 interval=5 档案里，只在完整版。在做完投影验证前，所有模型的 `domain_calibrated` 都保持 `false`。

📄 `EXPERT_DEPLOYMENT.md`

### DA3Metric-Large 有米制深度，但没有置信度和相机参数

它只输出 `depth` 和 `sky` 掩码，`conf`、`extrinsics`、`intrinsics` 全是 `None`。

**为什么重要**：**过不了需要置信度的质量门禁**。它只能当单目尺度先验和天空掩码来源，不能参与位姿交叉校验。选模型时得看它到底给什么字段，不能只看任务名。

📄 `registry/experts/da3_metric_large.yaml`

### MoGe 的独立环境方案跑通了

MoGe 在自己的 conda 环境里正常工作，输出 `points`/`depth`/`normal`/`mask`/`intrinsics`，峰值 2.87 GB。

**为什么重要**：它的 `normal` 是**独立法向**，不是从深度微分算出来的 —— 这满足了"至少要有一路独立法向信号"的要求。环境冲突不必强行调和，按角色拆环境就行。

📄 `registry/experts/moge_3_vitl.yaml`

### DA3 的不同变体许可不一样，别选错

`DA3-LARGE-1.1`、`DA3-BASE`、`DA3METRIC-LARGE` 和代码都是 **Apache-2.0**，但 **`DA3NESTED-GIANT-LARGE` 是 `cc-by-nc-4.0`**。

**为什么重要**：同一个 GitHub 项目下的权重许可可以不同。只看仓库 LICENSE 就下权重会踩到 NC。

📄 `EXPERT_DEPLOYMENT.md`

### DA3-LARGE-1.1 给的是相对深度，不是米制

实测 `is_metric` 为空、`scale_factor` 是 `None`、depth 落在 0.57–1.02。

**为什么重要**：首批任务强制 metric，所以**它不能直接用来出"距离几米"的题**。要 metric 第二意见得换 `DA3METRIC-LARGE`。模型名字里没有 "metric" 不代表输出就是相对的，反过来也一样 —— 必须实测。

📄 `EXPERT_DEPLOYMENT.md`

### OneFormer 能跑，但输出可能是错的

`transformers 5.15.1` 加载时 `swin.layernorm.weight/bias` 报 `MISSING`，被**随机初始化**了。模型照常输出 13 类语义图，看不出异常。

**为什么重要**：这种"能跑但悄悄是错的"比直接报错危险得多。而它产出的正是天空/水面无效几何掩码，错了会污染整个质量门禁。**确定兼容版本前不启用。**

📄 `EXPERT_DEPLOYMENT.md`

### MoGe 和 VGGT-Ω 装不进同一个环境

MoGe 要 `numpy>=2`，VGGT-Ω 和 DA3 都要 `numpy<2`。另外 MoGe 还要一个指定 commit 的 CUDA 扩展 `flex-gemm`。

**为什么重要**：这不是配置问题，是硬冲突。但也不必强求 —— MoGe 的角色是**关键帧上的离线交叉校验**，本来就不需要和 VGGT-Ω 同进程跑。**独立环境 + 文件交换**即可。

📄 `EXPERT_DEPLOYMENT.md`

### 装依赖时 numpy 会被反复偷偷升到 2.x

`imageio`、`plyfile`、`utils3d`、`opencv 5.x` 都会触发。

**为什么重要**：升上去之后 VGGT-Ω 和 DA3 会**静默失效**，不会报错。每装完一批依赖必须重新 `pip install "numpy<2"` 并校验。

📄 `EXPERT_DEPLOYMENT.md`

---

## VGGT-Ω（点云主路径）

### 代码能装，权重要申请

代码在 GitHub 公开可克隆，**权重在 HuggingFace 是 `gated: manual`**，需要用账号提交申请、自动流程审核。

**为什么重要**：这是整条几何链路的入口。权重没批下来之前，Layer 2 从 L2-S1 往后全部停住。

📄 `VGGT_OMEGA_DEPLOYMENT.md`、`MANUAL_INPUTS.md` M-007

### 它的输出可以用来训练，WorldMirror 不行

VGGT-Ω 的 FAIR NC 许可限制"输出仅限非商用研究"，但**没有**"禁止用输出改进其他 AI 模型"这一条 —— 而 WorldMirror 有。

**为什么重要**：意味着 VGGT-Ω 的输出**可以进训练 metadata**，这是它能当主路径的前提。许可条款的细微差别直接决定模型能不能用在训练链路上。

📄 `VGGT_OMEGA_DEPLOYMENT.md`

### 文档声称的输出能力，实测全部属实

`depth`、`depth_conf`、`extrinsics`、`intrinsics`、`camera_and_register_tokens` 全部存在。2 帧 @512 峰值 6.53 GB，与官方参考量级一致。

**为什么重要**：`depth_conf` 是质量门禁的输入，相机参数是投影与跨视角关联的前提。这些正是现有点云语料缺的东西。

📄 `VGGT_OMEGA_DEPLOYMENT.md`

---

## 现有点云语料（blob 上同事已生成的）

### 它们只有坐标和颜色，没有置信度和相机参数

逐点字段只有 `xyz + rgba`。没有法向、没有置信度、没有相机内外参、没有来源记录。

**为什么重要**：**我们的管线没法直接用它们。** 缺置信度过不了质量门禁，缺相机参数做不了投影和跨视角关联。这也说明本管线必须保存 VGGT-Ω 的**完整输出**，而不只是导出一个能看的点云文件。

📄 `BASELINE_POINTCLOUD_ANALYSIS.md`

### 尺度是相对的，不是米制

到原点距离中位数 ≈ 1.00，整片航拍区域坐标跨度不到 1 个单位 —— 归一化坐标。

**为什么重要**：不能用来出米制题。UAVScenes 带 RTK，正好补上这块。

📄 `BASELINE_POINTCLOUD_ANALYSIS.md`

### 每个样本一个点云，题目是 2D 识别搬过去的

38 万样本、9 个数据集，全部是"一张图 → 一个点云"，题型是 `Condition_Recognition`、`Yes_No`、`Counting` 这类，例如「这张图的整体状况如何？」答「flooded」。

**为什么重要**：这类问题看一眼图就能答，**不依赖三维**。这不是否定既有工作 —— 它恰好界定了我们要补的差距：**点云要带尺度和置信度，题目要真正依赖三维**。

📄 `BASELINE_POINTCLOUD_ANALYSIS.md`

---

## UAVScenes（首批数据集）

### 不用申请，HuggingFace 上直接能下

官方提供 HF 镜像，非 gated、非 private，无需 token，35 GB。

**为什么重要**：我一开始判断"需要许可申请、是唯一硬阻塞项"，**是错的** —— 那是基于"多数 UAV 数据集需申请"的一般规律外推，没有先核实这一个。

📄 `MANUAL_INPUTS.md`、`CHANGELOG.md` 对应的 `[修正]` 条

### 相机位姿的方向是实测出来的，不是猜的

用 RTK 轨迹交叉验证：`world_from_camera` 假设相关度 **0.9877**，`camera_from_world` 只有 **0.2155**。

**为什么重要**：位姿方向猜错，整条几何链路会**静默出错**且极难排查。凡是有两种可能约定的地方，都应该找一个独立信号去验证。

📄 `PROJECT_HANDOFF.md` §19.3

### 世界坐标系确实是米制，误差 0.24%

4 个地点做 Umeyama 相似变换，尺度因子 0.9976–1.0022。残差 0.44–1.89 m 来自 RTK 天线与相机光心的杆臂，不是尺度误差。

**为什么重要**：这个数字直接变成了任务容差的依据 —— metric 题容差取 0.10 m、左右判定死区取 10°，都是从它推出来的，不是拍脑袋。

📄 `registry/datasets/uavscenes/dataset_card.yaml`

### 20 个架次，但只有 4 个独立切分单元

`HKairport` 和 `HKairport_GNSS`、`HKairport_GNSS_Evening` 是同一地点的不同架次，必须绑在同一个 split 里。

**为什么重要**：不这么切就是数据泄漏。代价是跨场景泛化评测的统计效力有限，得靠引入第二个数据集来补。

📄 `registry/datasets/uavscenes/file_inventory.json`

### 数据集是 CC BY-NC-SA，我们的产出也得跟着

UAVScenes 和它的上游 MARS-LVIG 都是 CC BY-NC-SA 4.0，仅限学术。

**为什么重要**：ShareAlike 意味着我们生成的 metadata 和任务标注按**演绎作品**处理，发布时要沿用同一许可并署名。另外 HF 上的元数据标签**漏了 NC**，以 GitHub 的 LICENSE 文件为准。

📄 `registry/datasets/uavscenes/license_review.yaml`

---

## 环境与工程

### `~/.local` 里的包会渗进任何 Python 环境

那里有 35 个包（wandb、webdataset 等），**conda 环境也挡不住**。

**为什么重要**：不加 `PYTHONNOUSERSITE=1` 的话，所谓的"隔离环境"是假的。

📄 `CLAUDE.md` 规则 3

### 占卡程序留的余量够跑模型，不用停

它占 27 GB/卡，还剩约 13 GB。实测最大的单模型峰值是 6.53 GB。

**为什么重要**：可以在**不中断服务器保活**的前提下做模型验证。只有真正需要大显存时才停占卡。

📄 `CLAUDE.md` 规则 2
