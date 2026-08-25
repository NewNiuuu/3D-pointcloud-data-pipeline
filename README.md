# 低空无人机 2D → 3D 数据生成项目

> **本文档是项目推进的追踪入口。** 想知道「还有什么要做、做到哪了」看下方进度表；
> 想知道「具体改了什么」看 `docs/CHANGELOG.md`。
>
> 当前阶段：第一层完成，第二层提取链路建设中  
> 对应主规格：`docs/DESIGN.md` v0.4.0  
> 最近更新：2026-08-25

## 🎯 这个项目要交付什么（2026-08-25 用户确立）

低空 3D 点云训练数据此前基本不存在。**首要交付物不是语料，而是方向。**

| 优先级 | 交付物 |
|---|---|
| **1** | **值得做的下游任务类型** —— 即使我们的数据在该任务上质量不高，任务本身指明方向 |
| **2** | **能力缺口的论证** —— 缺的能力是什么、为何现有数据供不上、为何该任务能训到它 |
| **3** | **「好数据」的判据** —— 给后来做数据的人的优化目标 |
| **4** | **可移植的生成方法** —— 纯视觉管线 + 实测误差刻画 |
| 5 | 语料本身 —— 存在性证明与基线，不是终点 |

**两条由此产生的硬约束：**

- **铁律 14（纯视觉）**：target 必须能从数据集自身的图像/视频 + 模型推出。
  LiDAR/RTK 只用于**验证与标定**，不得作为生产前提 ——
  否则方法只对极少数特殊数据集适用，失去意义。
- **每个任务必须有价值论证**（`DESIGN.md` §52 六问：能力缺口 / 为何能训到 / 当前上限 /
  好数据特征 / 衡量指标 / **3D 增益**）。**缺论证的任务不进 Release**，哪怕技术上能生成。
  当前上限**必须诚实写明**—— 写清做不到什么，正是「指方向」的一部分。
- **判据是「3D 增益」不是「2D 做不到」**（铁律 5，2026-08-25 修订）：
  我们的 3D metadata 是专家模型从同一批 2D 图像提取的，信息论上不存在 2D 绝对答不出的任务。
  改为实测 `lift = score(2D+metadata) − score(2D only)` 显著 > 0 且打乱后消失。
  **口子放宽但没放空** —— 从「断言不可解」变成「拿出数字」。

**项目定位（诚实版）**：不引入新数据集、不做人工标注、不训练新的三维基础模型。
本质是**把一批各有所长的三维专家模型的能力蒸馏进一个 VLM —— 博采百家之长**。
不可替代性从低到高分三层：单教师蒸馏 → 多教师融合 → **集成结构产生的新信号**
（教师间分歧 → 可靠性，任何单个教师的输出接口都没有）。**C1 之所以是旗舰，因为它在第三层。**

## 📚 文档导航（2026-08-25 重构：14 份 → 8 份）

| 文档 | 给谁看 | 装什么 |
|---|---|---|
| **README.md**（本文） | **你** | 进度追踪表、四层进度、项目全貌 |
| `CLAUDE.md` | Agent（自动加载） | 项目规则。**规则 0 是设计哲学总纲** |
| `docs/DESIGN.md` | Agent | 实施主规格。**Part 0 推导链**、铁律、四层、契约、门禁、**§52 任务价值论证**。附录含第三层 Skill 设计 |
| `docs/DECISIONS.md` | 人 + Agent | 决策与依据的历史（原 PROJECT_HANDOFF），只追加 |
| `docs/FINDINGS.md` | **你** | 调研结论摘要（结论先行）。附录 A/B/C 放完整数据与复现命令 |
| `docs/OPERATIONS.md` | Agent | 环境、模型部署、复现命令、踩过的坑 |
| `docs/USER_ACTIONS.md` | **你** | 只有两类：需要你提供的信息、需要你删的文件 |
| `docs/CHANGELOG.md` | 人 + Agent | 每次改动的流水账，只追加 |

> **想快速了解项目在干什么**：读 `DESIGN.md` 的 **Part 0**（设计哲学）与 **§52**（任务价值论证）。
> 这两节是全项目的总纲和首要交付物。

## 📋 进度追踪表

> **这是持续追踪用的主表。** 每次交付后更新状态，具体改动记录在 `docs/CHANGELOG.md`，不写进本表。
> 来源标记：**用户** = 你提出的 ｜ **商讨** = 讨论后共同确定 ｜ **建议** = Agent 依据 SPEC 判断应做

### 🔴 受阻（需要你处理）

| # | 需求 | 来源 | 阻塞原因 |
|---|---|---|---|
| R-02 | 米制尺度精度验证 | 商讨 | **M-008** 需 `calibration_results.py`（相机-LiDAR 外参），只在 OneDrive/GDrive 完整版根目录。**2026-08-25 降级：不再阻塞数据生产**——按铁律 14，LiDAR 只用于 Release D 的验证与标定。它现在卡的是「验证报告」，主干可继续推进 |
| R-27 | Blob 备份目录名跟随日期 | 用户 | **M-009** 需带删除权限的 SAS token（`sp=racwdl`）。当前 `racwl` 删不掉旧目录，跨天后目录名停在旧日期。**已改为手动备份**（`scripts/blob_backup.sh once`），全量一份已在 `nyp_0825` 落地。另有 **M-010**：当前 token **2026-08-29 过期**；以及 6.8G 误传的 git 临时 pack 待清（X-007） |

### 🟡 待办（现在就能做）

> **2026-08-25 方向调整**：先完整搭通**第一、二、四层**主干（数据输入 → 提取/生成/处理 → 下游任务输出）。
> **第三层降为润色层**，待主干可运行后再回来审视哪里值得用 Skill 提炼。详见 `DECISIONS.md` §19.4。

**主干（当前重点）**

| # | 需求 | 来源 | 层 | 说明 |
|---|---|---|---|---|
| R-01 | **VGGT-Ω 几何重建（L2-S1）** | 商讨 | 二 | 权重已就位并验证；已在 UAVScenes 真实场景多次跑通（24 帧 @512）。**仍缺**：与 LiDAR 逐点比对重建质量（属 Release D，不阻塞主干） |
| R-38 | **纯视觉自洽测量模块** | 建议 | 二 | **铁律 14 的落地件、C1 的真值来源**：多视重投影误差、前后向光流环路误差、估计器间分歧。都是可复算测量，checker 能独立重算 |
| R-39 | **扰动法脆弱度标注** | 建议 | 二 | 对场景施加受控退化 → 重新提取 → 测几何漂移。**日/暮实验已是一次完整演示**，需固化成模块。C1/C4 共用 |
| R-40 | **无尺度几何量计算**（坡度/平整度比值/共面性） | 建议 | 二 | C2 核心量 + C3-a。角度与比值在缩放下不变，**不需要任何尺度锚** |
| R-41 | **尺度锚分档探测**（T0–T4） | 建议 | 一 | 从 EXIF/GPS/飞控日志探测可用锚并定档，驱动 `metric_task_eligible`。默认目标 T3 |
| R-43 | **3D 增益实测（铁律 5 的准入线）** | 用户 | 四 | **当前最重要的未验证项。** 同题同模型三档消融：2D-only / 2D+metadata / 打乱 metadata，测 `lift` 与其置信区间。**在拿到数字前所有任务标 `lift_unmeasured`，不得进正式 Release。** 依赖 R-20（Qwen 调用，暂缓中）—— 需重新评估是否提前解禁 |
| R-42 | **任务价值论证补全**（`DESIGN.md` §52 六问） | 用户 | 四 | 每个任务族的能力缺口/为何能训到/**当前上限**/**好数据特征**/衡量指标。**缺论证的任务不进 Release**。C1–C4 已写，新增任务须同步 |
| R-13 | L2-S3 提升融合 / L2-S4 派生 | 建议 | 二 | 代码可先按契约写好，接口留给 VGGT-Ω 深度 |
| R-14 | 专家模型产出真实 artifact | 建议 | 二 | 模型已部署但未接线，按 §14.8 I/O 契约存盘。**多估计器分歧是 R-38 的输入**，优先级因此上升 |
| R-28 | **置信度校准**（→ 错误事件概率） | 建议 | 二 | 实测两重非平稳：**场景相对**（同类植被跨场景差 2.4 倍）+ **光照相关**（AUC 0.865→0.670）。**必须按成像条件分档标定**。标定本身属 Release D（需 M-008），产出的映射供主干引用 |
| R-29 | **成像条件分档字段** | 建议 | 一/二 | 场景快照需带图像亮度/对比度统计，供 R-28 分档、R-39 扰动、C4 配对使用 |
| R-15 | 接入校验（**普通函数，不封装 Skill**） | 建议 | 二 | 现在 adapter 产出的场景 `gate_status` 是 `None`，无人检查。可把基线/帧数退化在此拦掉 |
| R-16 | 样本校验（**普通函数，不封装 Skill**） | 建议 | 二 | checker 已备，缺调度与修复策略 |
| R-17 | 能力覆盖矩阵 | 建议 | 四 | 防止不同题型重复测同一能力 |

**次要**

| # | 需求 | 来源 | 层 | 说明 |
|---|---|---|---|---|
| R-18 | SEA-RAFT / CABiNet 部署 | 建议 | 二 | 权重不在 HF；SEA-RAFT 的残差光流最终仍需 R-01 |
| R-19 | 其余 21 个候选数据集建卡 | 建议 | 一 | Phase 2 |

### 📦 后续目标 backlog（优先级低于主干，但不放弃）

> **2026-08-25 用户补充**：细线检测、安全性检测这类能力相对 C1 没那么 novel，
> 但**模型需要足够的能力多样性（Diversity）**。因此它们不是被放弃，只是优先级放在 C1–C4 之后。
> **在 UAVScenes 上仍然不得生成** —— 数据不支持这一事实不因优先级调整而改变。

| # | 需求 | 来源 | 解锁条件 |
|---|---|---|---|
| R-30 | 薄障碍（电线/缆索/细枝）检测与中心线 | 商讨 | 前视/侧视数据集；SPEC §14.6 规则已就绪可直接启用 |
| R-31 | 前向避障、通道净空、最小净空 | 商讨 | 同上 |
| R-32 | Occupancy / free / unknown、可飞行体积 | 商讨 | 同上；SPEC §14.7 推导链已就绪 |
| R-33 | 航迹可行性、瓶颈定位 | 商讨 | 同上 |
| R-34 | 动态碰撞风险、TTC、扫掠体重叠 | 商讨 | 前视数据 + 动态目标丰富的场景 |
| R-35 | Next-best-view、检查视角规划 | 商讨 | 具备主动飞行决策的数据 |
| R-36 | 任务分解与计划批判 | 商讨 | 上述能力就绪后 |
| R-37 | **引入前视/侧视数据集**（原方案 B） | 商讨 | **这是解锁 R-30～R-36 的前置项**。候选 Mid-Air / FlyAwareV2 / UAVStereo，均需重做许可与可行性核验 |

详见 `DESIGN.md` §46.5 与 Release E。

### ⏸️ 暂缓（已决定推迟）

| # | 需求 | 来源 | 说明 |
|---|---|---|---|
| R-20 | Qwen 部署与调用 | 商讨 | 首批只编译 prompt bundle 不调模型。**⚠ 2026-08-25 出现冲突**：铁律 5 修订后，任务准入要求实测 3D 增益（R-43），而那必须调模型。**「暂缓调模型」与「任务须有增益数字才能进 Release」二者不能同时成立** —— 需你决定：提前解禁 R-20，还是接受首批任务全部标 `lift_unmeasured` 只进预发布 |
| R-21 | LLM Judge | 建议 | 首版只用确定性 checker |
| R-22 | DSINE 独立法向 | 建议 | 优先级下降 —— MoGe-3 已提供独立法向 |
| R-23 | 飞书清单去重 | 用户 | 仅 Phase 2 扩数据集时才需要（M-004） |
| R-24 | **第三层：8 个 Skill 封装** | 用户 | **2026-08-25 决定暂缓。** Skill 是润色性质，应在主干可运行后再提炼。功能仍以普通代码实现 |
| R-25 | **第三层：G1–G6 统一门禁框架** | 用户 | 同上。单点校验仍做，不建统一框架 |
| R-26 | **第三层：Orchestrator 执行器** | 用户 | 同上。状态机规则已实现并测试，执行器待主干成型后再建 |

### ✅ 已完成

| # | 需求 | 来源 | 产出 |
|---|---|---|---|
| R-60 | 设计改动立即同步文档 | 用户 | `CLAUDE.md` 规则 1 + 文档职责映射表 |
| R-61 | 占卡程序保持挂载 | 用户 | `CLAUDE.md` 规则 2 |
| R-62 | 显卡监听守护程序 | 用户 | `scripts/gpu_guard.sh`，20 分钟一轮，实测自动拉起 |
| R-63 | 人工输入登记簿 | 用户 | `docs/USER_ACTIONS.md` + `secrets/` 自屏蔽目录 |
| R-64 | 变更日志 | 用户 | `docs/CHANGELOG.md`，六类标签，只追加不改写 |
| R-65 | 待删除清单（Agent 不执行删除） | 用户 | `docs/USER_ACTIONS.md` |
| R-66 | 同步到独立 GitHub 仓库 | 用户 | `NewNiuuu/3D-pointcloud-data-pipeline` |
| R-67 | Blob 数据路径登记 | 用户 | `USER_ACTIONS.md` §3，D-001/D-002 含实测结构 |
| R-68 | 调研结果另记简明文档 | 用户 | `docs/FINDINGS.md`，结论先行 |
| R-69 | 项目专属 conda 环境 | 用户 | `nyp-3dpipe` + `nyp-moge`；`CLAUDE.md` 规则 3 |
| R-70 | 修正 git 提交作者 | 用户 | 9 个提交改写，仓库级身份固化 |
| R-71 | README 作为追踪文档 | 用户 | 本表 |
| R-72 | 四项实施边界决策 | 商讨 | 首批数据集 / metric 政策 / 首批任务 / Qwen 暂缓 |
| R-73 | 数据许可政策 | 商讨 | 接受 CC BY-NC-SA 4.0 学术用途 |
| R-74 | 项目定位与 3D-GRPO 关系 | 商讨 | 产出「点云 + 任务标注」一对；3D-GRPO 是下游训练框架 |
| R-75 | 首批数据集获取与 G0 | 建议 | UAVScenes 35 GB；card / 许可 / 文件清单 |
| R-76 | 冻结契约（vertical slice 1） | 建议 | `core/`：ID、状态机、枚举、57 错误码、artifact 血缘 |
| R-77 | Dataset Adapter（vertical slice 2） | 建议 | `adapters/uavscenes/`，3 个场景落盘 |
| R-78 | 确定性几何 + checker（vs 7） | 建议 | `geometry/` 17 函数 + `checkers/` 4 个 |
| R-12 | **L2-S6 任务编译** | 建议 | 编译器 + 4 个推导程序 + 19 项测试。运行时泄漏检查、候选确定性打乱、资格判定分离场景级与任务时量 |
| R-11 | **Canonical Task Record + 三类 adapter** | 建议 | schema + 三路 adapter + 基类强制的泄漏防护 + 31 项测试。产出为 **ShareGPT 格式** |
| R-10 | **冻结 L0/L1/L2 Metadata Schema** | 建议 | 4 个 schema（版本 0.1.0）+ `core/metadata.py` 跨层校验 + 39 项测试。新增 `surface` 实体类型（C2/C3 的锚点）；L2 强制 `derivation` |
| R-79 | Task Spec（vertical slice 8） | 建议 | 4 个，覆盖 3 个任务族 |
| R-80 | 专家模型许可核验与部署 | 用户 | 9 张专家卡；7 个已部署验证 |
| R-81 | 现有点云语料分析 | 用户 | `docs/FINDINGS.md 附录 C` |
| R-82 | VGGT-Ω 部署与输出契约 | 用户 | 代码就绪；输出契约实测确认 |
| R-83 | 尺度转换关系调查 | 用户 | `docs/FINDINGS.md 附录 B`。**结论：数学成立但精度受重建稳定性限制** |
| R-85 | **下游任务能力范围重定义（方案 A）** | 商讨 | 结合飞手痛点调研 + 数据实测，确定 C1 感知可信度 / C2 可降落性 / C3 米制地形 / C4 跨时相；移除全部导航类能力。已同步 17 个 SPEC 章节 + 4 份文档 + 3 个 Task Spec |
| R-84 | 基线阈值定准 | 用户 | **结论是定不出来** —— 推翻了此前两条结论，详见 §C |

---

## 文档维护规则

`DESIGN.md` 是 Agent 实施依据，本 README 是人类阅读入口。

**README 的职责是追踪「还有什么要做、做到哪了」，不是记录「改了什么」。**
具体改动一律记入 `docs/CHANGELOG.md`，不要往 README 里堆。

以下情况**必须**更新 README 的进度追踪表：

- 新需求产生（无论来自用户、商讨还是 Agent 判断）→ 加一行，标明来源；
- 需求状态变化（待办 → 完成 / 受阻 / 暂缓）→ 改状态并补产出或阻塞原因；
- 阻塞项解除或新增；
- 四层架构任一层的阶段状态变化。

以下情况**必须**更新 README 正文：

- 数据集新增、删除、评级或验证状态变化；
- Pipeline 阶段、数据流或模型职责变化；
- 质量门禁或关键技术路线变化。

## 项目目标

利用低空无人机 2D 图像/视频生成点云和结构化 3D metadata，再让 Qwen 基于 **2D 视觉输入 + 3D metadata** 生成可验证的三维场景理解数据。

```mermaid
flowchart LR
    A[第一层<br/>数据源] --> B[第二层<br/>3D Metadata 与数据生成]
    B --> D[第四层<br/>下游任务与能力补全]
    D --> E[训练集 / Benchmark / Pipeline]
    C[第三层<br/>Agent、Skill 与质量监管] -.控制与校验.-> A
    C -.控制与校验.-> B
    C -.控制与校验.-> D

    A1[22 个新增候选数据集] -.-> A
    B1[VGGT-Ω 点云] -.-> B
    B2[专家模型与几何程序] -.-> B
    D1[点云 / 语言 / 导航任务] -.-> D
    C1[Task Spec / 提示词 / Checker] -.-> C
    C2[质量门禁与监控] -.-> C
```

固定原则：

- 点云主路径是 **VGGT-Ω**。
- Qwen 不直接读取点云。
- 几何真值优先由程序计算，LLM 不负责创造真值。
- 任务必须有**实测的 3D 增益**（喂入 3D metadata 后显著提分，且打乱后增益消失）。
  **不要求 2D 绝对做不到** —— 我们的 3D 本就是从 2D 提取的，那个门槛信息论上不成立（2026-08-25 修订）。
- metric 与 relative scale 严格区分。
- **能力范围以数据实际支持为准** —— 不为迎合能力清单而生成无有效监督的任务（2026-08-25）。

---

## 第一层：数据集来源

### 当前统计

| 项目 | 数量 |
|---|---:|
| 新增候选 | 22 |
| S 级 | 7 |
| A 级 | 7 |
| B 级 | 6 |
| C 级 | 2 |
| 实拍 | 12 |
| 仿真 | 7 |
| 实拍 + 仿真 | 3 |

飞书历史清单已有：FloodNet、Open3DVQA、TDBench、LADI-v2、AVI-Math、AirCopBench、SpatialSky、UrbanVideo-Bench、MM-UAVBench、MME-RealWorld、Geo3DVQA。以下 22 个候选是在该历史快照基础上新增的。

### 新增数据集清单

| 级别 | 数据集 | 类型 | 主要特点 | 下一步用途 |
|---|---|---|---|---|
| S | UAVScenes | 实拍 | RGB、Livox、6DoF 位姿、标定、语义点云/网格 | 真实语义几何与首批闭环候选 |
| S | Dronescapes | 实拍 | 视频、SfM 位姿/内参、度量深度、法向 | 真实多视角重建候选 |
| S | H3D | 实拍 | 高密度 LiDAR、标注点云、纹理网格 | 高质量 3D 监督与评测参考 |
| S | SkyLume | 实拍 | 五向相机、RTK 重复飞行、COLMAP、LiDAR/网格 | 重复航线与跨时相研究 |
| S | UAVStereo | 混合 | 立体 RGB、视差、网格/LiDAR 几何 | 立体深度和尺度验证 |
| S | UrbanScene3D | 混合 | LiDAR、网格、多套影像/位姿、仿真标签 | 真实—仿真联合研究 |
| S | ClaraVid | 仿真 | 度量深度、语义/实例/动态 mask、相机、点云 | 完整标签与受控实验 |
| A | NTU VIRAL | 实拍 | 双相机、双 LiDAR、IMU、UWB、Leica 真值 | 传感器、位姿和尺度验证 |
| A | MUN-FRL | 实拍 | RGB、LiDAR、IMU、RTK-GNSS | 真实 metric 场景 |
| A | MARS-LVIG | 实拍 | RGB、Livox、IMU、GNSS/RTK、地图真值 | 真实度量几何 |
| A | Mid-Air | 仿真 | 深度、法向、语义、视差、遮挡、位姿 | 可控几何和遮挡任务 |
| A | UAV3D | 仿真 | 多机多视角、像素语义、3D box | 多视角对象任务 |
| A | U2UData+ | 仿真 | 多机 RGB + LiDAR、3D box/track | 协同感知与轨迹任务 |
| A | IllumUAV-Sim | 仿真 | 昼夜对齐 RGB、深度、法向、相机参数 | 光照鲁棒性测试 |
| B | UAPD / DAPM | 仿真 | RGB、深度、随机高度/姿态/FOV | 视角变化任务 |
| B | UAVPairs | 实拍 | 高重叠多视角、SfM 匹配关系 | Cross-view Correspondence |
| B | UAVID3D | 实拍 | RGB + 热红外、环绕影像、GPS | 多模态重建候选 |
| B | Ready for 3D Reconstruction | 实拍 | GCP、MVS、TLS 点云 | 重建和尺度评估 |
| B | FlyAwareV2 | 混合 | RGB、深度、语义；实拍含伪深度 | 障碍任务，需严格标记深度来源 |
| B | LAMBDA | 仿真 | RGB、LiDAR、4D radar、CSI、IMU、多机 | 后续多模态扩展 |
| C | UAVid | 实拍 | 4K 视频、8 类语义，几何较弱 | 语义专家与视频辅助数据 |
| C | VisDrone | 实拍 | 大规模检测/跟踪框，无深度和位姿 | 2D 专家训练或辅助任务 |

### 下一步

1. 重新只读核对最新飞书清单。
2. 为 22 个候选建立机器可读 Dataset Card。
3. 核验链接、许可、文件和尺度来源。
4. 每个首选数据集只下载 1–3 个场景样本。
5. 最终选择 1–2 个互补数据集跑通闭环。

---

## 第二层：3D Metadata 与数据生成 Pipeline

```mermaid
flowchart TD
    A[原始 2D 数据集<br/>图像 / 视频 / 原生标注] --> B[Dataset Adapter<br/>场景切分与格式统一]

    B --> C[VGGT-Ω<br/>相机 / 深度 / 置信度 / 点云]
    B --> D[语义与视频专家<br/>Mask / Track / Flow / 属性]
    B --> D2[独立几何专家<br/>Metric / Normal / Track / Validity]

    C --> E[2D-to-3D Lifting & Fusion]
    D --> E
    D2 --> E

    E --> F[结构化 3D Metadata]

    F --> F0[L0 原始几何]
    F --> F1[L1 3D 实体]
    F --> F2[L2 空间关系]
    F --> F3[L3 时间 / 功能 / 行动]

    F --> G[Task Compiler<br/>隐藏目标 / Evidence / Checker]
    B --> H[选择 2D 视角或视频片段]

    G --> I[Qwen 输入]
    H --> I

    I --> J[3D Grounding]
    I --> K[3D VQA]
    I --> L[3D Caption]
    I --> M[3D Task Decomposition]
    I --> N[3D Dialogue]
    I --> O[新增 3D 任务]

    J --> P[程序校验与质量门禁]
    K --> P
    L --> P
    M --> P
    N --> P
    O --> P
```

### Metadata 分层

| 层级 | 核心内容 | 首版策略 |
|---|---|---|
| L0 原始几何 | 相机、深度、点云、法向、坐标系、尺度 | 必做 |
| L1 3D 实体 | 稳定 ID、centroid、OBB、可见性、对象/部件/轨迹 | 必做对象级字段 |
| L2 3D 关系 | 距离、方向、高差、遮挡、连接、拓扑 | 按首批任务实现 |
| L3 可信度与表面 | 深度可信度与失效原因、可降落性属性、地形量、跨时相变化 | 按 C1–C4 实现（2026-08-25 重定义，原为轨迹/TTC/自由空间/路线/NBV） |

### 模型的正确职责

| 类型 | 真值来源 | Qwen 的作用 |
|---|---|---|
| Grounding / metric VQA / correspondence | 几何程序、原生标注 | 理解问题并输出结构化答案 |
| Caption / Dialogue | 程序生成的 claims 与状态 | 组织语言、组合事实、保持对话状态 |
| Task Decomposition / 规划 | 模型候选 + 几何规则验证 | 生成计划候选和解释 |

### 当前推荐的首版专家组合

> 已完成官方资料调研，尚未下载 checkpoint，也未在本地 UAV 数据上实测。

| 功能 | 当前首选 | 在 Pipeline 中的作用 |
|---|---|---|
| 开放词汇实例 mask | Grounded-SAM-2 | 检测候选、类别和像素级实例 mask |
| 视频 mask tracking | SAM 2.1 Base+ | 跨帧传播 mask 和 2D track ID |
| 光流与动态证据 | SEA-RAFT | 生成 flow/uncertainty；扣除相机自运动后判断动态区域 |
| 天空、水面和 stuff | OneFormer | 生成独立的无效几何原因 mask |
| UAV 障碍语义 | CABiNet MobileNetV3-Small | 补充低空障碍、地表和植被语义 |
| 独立 metric 几何 | MoGe-3 ViT-L | 当前优先的尺度、法向、valid mask 和细节第二意见 |
| 独立法向 | DSINE | 避免所有法向都由深度微分产生；启用前审查许可 |
| 深度/位姿复核 | DA3 / DA3-1.1 | 提供第二份深度、相机、sky 和尺度意见；不融合其点云为真值 |
| 长视频几何 | DA3-Streaming | 分段 pose/depth/confidence 和 loop closure；仅长视频启用 |
| 点轨迹与可见性 | CoTracker3 | 提供 2D tracks/visibility；当前许可限制生产使用 |
| 属性与描述候选 | Florence-2 | 对稳定实例生成受约束的属性和描述候选 |
| 跨视角外观特征 | DINOv2 Small/Base | ReID、聚类和跨视角关联 |
| 电线专项 | PowerLine-MTYOLO Nano | 电力线 mask；仅作领域专项证据 |

三个重要规则：

- 光流幅值不等于物体运动，必须先扣除 VGGT-Ω 深度和相机运动产生的静态流。
- `sky`、`water`、`reflection`、`low_depth_confidence`、`dynamic_geometry` 等原因必须分别保存。
- ~~可飞行空间不能由 2D 模型直接决定~~ —— **该规则当前不适用**（2026-08-25：近垂直下视数据不支持可飞行空间，见第四层说明）。等价的现行规则是：**可降落性不能由 2D 模型直接决定**，必须联合 LiDAR 几何、语义与深度可信度判断。
- 多模型不能投票产生真值；必须先对齐、计算残差，再形成置信度、弱标签或复核标志。
- WorldMirror 目前只能用于推理/评估，不能把输出作为 Qwen 训练 metadata。

几何专家接入顺序：`MoGe-3 → DSINE → DA3-1.1 → DA3-Streaming（长视频）→ Trace Anything（动态）`。WorldMirror最后作为独立评估或受控修复实验。

| 深度类型 | 能否直接生成米制任务 |
|---|---|
| Metric | 通过 UAV 域尺度校准后才可以 |
| 外部锚定 | 锚点和误差记录完整时可以 |
| Relative / Affine-invariant | 不可以 |
| Pseudo depth | 只能作弱标签或质量信号 |

---

## 第三层：Agent、Skill 与质量监管

> ⏸️ **本层已于 2026-08-25 暂缓** —— 先搭通一、二、四层主干，Skill 作为润色层后置。
> 其中的**校验功能**仍以普通代码实现在主干上，只是不封装为 Skill、不建统一门禁框架。
> 详见 `DECISIONS.md` §19.4。

```mermaid
flowchart LR
    O[Pipeline Orchestrator Agent]

    S1[dataset-registry-manager]
    S2[expert-registry-manager]
    S3[scene-ingestion-validator]
    S4[metadata-quality-gate]
    S5[task-spec-designer]
    S6[task-prompt-compiler]
    S7[task-sample-auditor]
    S8[dataset-quality-monitor]

    D[数据集注册] --> S1 --> E[专家注册与许可]
    E --> S2 --> I[数据接入]
    I --> S3 --> G[几何与专家模型]
    G --> S4 --> TD[任务规格设计]
    TD --> S5 --> T[任务编译]
    T --> S6 --> Q[Qwen 生成]
    Q --> S7 --> R[合格样本]
    R --> S8 --> P[候选发布]

    O -.调度与门禁.-> S1
    O -.调度与门禁.-> S2
    O -.调度与门禁.-> S3
    O -.调度与门禁.-> S4
    O -.调度与门禁.-> S5
    O -.调度与门禁.-> S6
    O -.调度与门禁.-> S7
    O -.调度与门禁.-> S8
```

### Skill 作用表

| Skill | Pipeline 位置 | 目的 | 主要输出 |
|---|---|---|---|
| `dataset-registry-manager` | 数据集调研与选择 | 去重、维护 Dataset Card、核验数据和许可 | 数据集注册表与选择建议 |
| `expert-registry-manager` | 专家模型启用之前 | 核验代码/权重许可、checkpoint、能力、输入输出和 UAV 验证状态 | 专家卡、启用清单与运行策略 |
| `scene-ingestion-validator` | Adapter 之后 | 检查文件、标定、时间戳、尺度和 split | 接入验证报告 |
| `metadata-quality-gate` | 3D 融合之后 | 检查坐标系、ID、几何一致性、来源和置信度 | 合格 metadata snapshot |
| `task-spec-designer` | 下游任务设计阶段 | 将点云和metadata能力映射为可验证、具备3D及低空特性的任务规格 | Task Spec与能力覆盖矩阵 |
| `task-prompt-compiler` | Qwen 调用之前 | 根据 Task Spec 生成任务提示词、隐藏目标和 Checker | Prompt Bundle |
| `task-sample-auditor` | Qwen 返回之后 | 检查答案、证据、泄漏、歧义和幻觉 | 合格样本或隔离记录 |
| `dataset-quality-monitor` | 批次与发布阶段 | 监控分布、重复、通过率、漂移和 3D 依赖性 | Dashboard 与发布清单 |

### 质量门禁

```mermaid
flowchart LR
    G0[G0 数据源 / 专家许可] --> G1[G1 几何与专家输出]
    G1 --> G2[G2 Metadata]
    G2 --> G3[G3 任务设计与编译]
    G3 --> G4[G4 模型输出]
    G4 --> G5[G5 样本审核]
    G5 --> G6[G6 数据集发布]

    X[硬错误] --> Q[Quarantine / Reject]
```

每个阶段只有四种状态：`pass`、`warn`、`quarantine`、`reject`。硬错误不能通过“综合评分较高”被抵消。

关键监控指标：

- Checker 一致率；
- target 泄漏率；
- 无依据内容率；
- 歧义样本率；
- 重复与模板坍缩率；
- 格式修复和重新生成率；
- 数据集、任务、难度、真实/仿真分布；
- `2D-only` 与 `2D+metadata` 的性能差异；
- metadata shuffle / masking / counterfactual 后的性能变化。

---

## 第四层：下游任务与能力补全

> **2026-08-25 能力范围重定义（[用户已确认]）。** 原设计的低空差异化能力
> （薄障碍 / 可飞行体积 / 净空 / 航迹 / TTC / Next-best-view）是在**尚未拿到数据**时的规划。
> UAVScenes 实测为**近垂直下视航测飞行**（俯角中位 87.6°，对地约 33 m），
> 相机看不到飞行方向前方，这些能力**无法产生有效监督**。
> 详见 `DESIGN.md` §40 与 `DECISIONS.md` §19.5。

最终任务标注采用统一格式，同时服务三类模型：

```mermaid
flowchart TD
    S[点云 + 相机 + LiDAR真值 + 语义标注 + 可信度信息]

    S --> A[原生3D感知]
    S --> B[空间与视角推理]
    S --> C[航拍可信度与可降落性]
    S --> D[Grounded 3D语言]

    A --> O1[Point-cloud模型]
    B --> O2[Qwen<br/>2D + Metadata]
    C --> O3[安全决策模型]
    D --> O4[多模态3D模型]
```

### 设计原则：造模型学不到的能力

排序依据**不是**「无人机需要什么能力」，而是
**「哪些能力的监督信号极难获得，而我们的数据恰好能可靠产出」**。

模型在图像-答案对上训练会学到「外观→答案」的捷径。
**捷径能解决的能力都不缺数据；捷径会给出错误答案的能力，才是真正的空白。**

三种难获取的监督形态，我们都能大规模产出：

| 监督形态 | 为何难获取 | 我们为何能产出 |
|---|---|---|
| 与外观矛盾的答案 | 需要能反驳视觉的独立真值 | LiDAR 米制真值 vs 视觉深度残差 |
| 外观相同但答案不同 | 需要米制位姿做反事实 | RTK 验证过的 6-DoF 位姿 |
| 无外观对应物的数值 | 需要米制几何真值 | LiDAR + 标定 |

### 四类目标能力（按优先级）

| 优先级 | 能力 | 为什么是我们的不可替代之处 |
|---|---|---|
| **C1** | **感知可信度与失效归因** | 失效标注由**纯视觉可复算测量**产出：多视重投影/光流环路误差、估计器分歧、**扰动漂移**。**结构性优势**：对别的能力，「提取的 3D 是错的」是噪声；对 C1，**教师犯错就是数据**。已实测（未用 LiDAR）：水面/陆面判别 AUC 0.865。对应社区头号诉求 |
| **C2** | **安全降落区评估** | **垂直下视正是评估降落区的视角**。**坡度是角度、粗糙度可取比值 —— 均在缩放下不变，无需尺度锚**，视觉点云即可算。核心是「平坦 ≠ 可降落」—— 水面平、车顶平、人群上方也平，必须几何+语义联合。软肋：弱纹理地面上视觉几何最差，而那恰是最需要判断的地方 |
| **C3** | **地形与高度推理（分档）** | Nadir 图像**几乎不提供深度线索**，同色屋顶与地面外观相近——**外观捷径必然给错**，选题最干净。**C3-a 序数/比值**（默认，任何数据集，对深度误差稳健）；**C3-b 绝对米制**（需 T3 的 GPS/EXIF 锚，无锚静默降级） |
| **C4** | **成像退化鲁棒与二阶不确定性** | **改用合成退化**（调暗/模糊/加噪/抽视角），任何数据集可做，不需要重复航次。实测发现最被忽视的一层：模型的**不确定性估计本身**在退化下失准（判别力 AUC 0.865→0.670，水面进高置信区 8.1%→19.1%）——**在最该谨慎时反而更自信**。真实日/暮配对退为「检验合成退化像不像真的」 |

> 每个能力的完整价值论证（能力缺口 / 为何能训到 / **当前上限** / **好数据特征** / 衡量指标）见 SPEC §52。

> ⚠ **配对不能只按航次名。** `_Evening` 内部有 4 倍亮度梯度（17:43 比日间还亮，18:04 才真暗），
> 配对须同时约束 RTK 质心距离、亮度比、相机基线三项。详见 `docs/FINDINGS.md 附录 A` §7。

### 能够生成的任务

| 任务方向 | 代表任务 | 主要3D标注 |
|---|---|---|
| 原生3D感知 | 语义/实例分割、3D检测、表面解析 | 点标签、实例点集、OBB、平面拟合 |
| 感知可信度 | 深度可信度判定、失效原因归因、不确定性感知回答 | 区域可信标志、LiDAR-视觉残差、原因码 |
| 可降落性 | 坡度估计、可降落区分割、动态占用、风险排序 | 平面、坡度、连通面积、语义风险 |
| 米制地形 | 高差、结构高度、起伏幅度、坡向、GSD | 高程统计、地面参考面、法向 |
| 跨时相 | 真实变化检测、表观差异归因 | 跨航次点云差分 |
| 空间与视角 | 距离/尺寸/方位、跨视角对应、可见性、视角变换 | 位姿、对象几何、可见性 |
| Grounded 3D语言 | Grounding、VQA、Caption、Dialogue | 稳定ID、点/区域/表面目标 |

### 任务设计要求

每个任务必须：

- 映射到点索引、OBB、平面/表面、区域体素或相机位姿等具体3D锚点；
- 证明不能只靠单张2D图像稳定解决；
- 对宣称"低空特色"的任务，使用**下视几何、对地高度、深度可信度、可降落性属性、米制地形量、或跨航次重复观测**；
- 保存隐藏target、evidence、derivation program和checker；
- 标记监督等级；
- 在尺度或几何不足时输出`unknown`、区间或拒答。

### 任务优先级

1. **Release A** 可移植基础监督：3D分割、Grounding、metric/situated VQA、跨视角对应、可见性。
2. **Release B** 航拍差异化能力（**本项目核心贡献**）：C1 → C2 → C3 → C4。**全部走纯视觉。**
3. **Release C** 语言与长时程：Caption、Dialogue、Scene Graph、空间反事实。
4. **Release D** 验证与标定报告（**非训练数据**）：在 UAVScenes 上用 LiDAR 测一次
   纯视觉管线错多少、置信度准不准、合成退化像不像真的。**这是「方法可移植」的证据。**
5. **Release E** 导航类能力 backlog —— 解锁条件是 R-37（引入前视/侧视数据集）。

---

## 当前进度（按四层架构，2026-08-25）

### 第一层：数据源注册与选择

| 环节 | 状态 |
|---|---|
| 首批数据集选定 | ✅ UAVScenes（用户确认） |
| Dataset Card + 许可审查 + 文件清单 | ✅ `registry/datasets/uavscenes/` |
| G0 门禁 | ✅ `pass_with_constraints`（CC BY-NC-SA 4.0） |
| 小样本落盘与结构核验 | ✅ 35 GB，20 run / 4 split group，帧级契约已实测 |
| 其余 21 个候选建卡 | ⬜ 未做（Phase 2） |
| `dataset-registry-manager` Skill | ⬜ 规则已在文档，未落为 Skill |

**这一层对首批数据集已经走完。**

### 第二层：2D→3D Metadata 提取与场景构建

| 阶段 | 内容 | 状态 |
|---|---|---|
| L2-S0 | Dataset Adapter / 场景切分 | ✅ `adapters/uavscenes/`，3 个场景已落盘 |
| L2-S1 | **VGGT-Ω 几何重建** | ❌ **权重待批（M-007）—— 本层的卡点** |
| L2-S2 | 2D/视频专家推理 | ⚠️ 模型已部署验证，**尚未产出 artifact** |
| L2-S2B | 独立几何专家 | ⚠️ 同上（MoGe-3 / DA3 已跑通） |
| L2-S3 | 2D→3D 提升与融合 | ❌ 依赖 S1 的深度 |
| L2-S4 | Metadata 派生 | ⚠️ 几何函数已备（`geometry/`），无输入可派生 |
| L2-S5 | 质量与 provenance | ⚠️ artifact 信封已备（`core/artifact.py`），门禁未实现 |
| L2-S6 | **Task 编译** | ⬜ 未开始 ← `task-prompt-compiler` |
| L2-S7 | 模型生成 | ⏸️ 按决策暂缓 |
| L2-S8 | 样本校验 | ⚠️ checker 已备，auditor 未实现 |

**这一层卡在 S1。** S0 完成，S2/S2B 的模型就位但没接线，S3–S5 全部等 S1 的深度。

### 第三层：Agent、Skill、编译、校验与质量监管

| 内容 | 状态 |
|---|---|
| 冻结契约（ID / 状态机 / 枚举 / 57 错误码 / artifact 血缘） | ✅ `core/` |
| 8 个 Skill | ⬜ **0 个已建目录**；部分规则已硬编码进 `core/task_spec.py` 与 `checkers/` |
| 质量门禁 G0 | ⚠️ UAVScenes 手工走过，未实现为可复用门禁 |
| 质量门禁 G1–G6 | ⬜ 未实现 |
| Orchestrator 状态机 | ⚠️ 迁移规则已实现并测试，**驱动它的执行器未写** |

**这一层已暂缓（2026-08-25）**：契约与规则都在，Skill 封装与门禁框架推迟到主干可运行之后。
必要的校验动作仍以普通代码实现在主干上。

### 第四层：下游任务设计与能力补全

| 内容 | 状态 |
|---|---|
| Task Spec | ✅ 4 个，覆盖用户确认的 3 个任务族 |
| 确定性推导程序与 checker | ✅ `geometry/` 17 个函数 + `checkers/` 4 个 |
| 输出 schema | ✅ `schemas/answers/` 4 个 |
| Canonical Task Record | ⬜ 契约在 SPEC §41，未实现 |
| 三类 adapter（qwen / pointcloud_native / multimodal_3d） | ⬜ Spec 中已声明，未实现 |
| 能力覆盖矩阵 | ⬜ 未做 |

**这一层的"配方"齐了，"产线"没建。**

### 一句话总结

**第一层走完，第四层定好了规格，第三层有契约无执行，第二层卡在 VGGT-Ω 权重。**
当前所有可推进的工作都在"等权重期间把周边机器造好"这个范畴内。

### 阻塞项

| 编号 | 内容 | 影响 |
|---|---|---|
| M-007 | VGGT-Ω 权重（已申请） | 第二层 S1 及其下游全停 |
| M-008 | 相机-LiDAR 标定文件 | 米制精度无法验证，`domain_calibrated` 无法置位 |

### 已产出代码与产物

```text
core/            冻结契约：ID 命名空间、状态机、枚举、57 个错误码、artifact 信封、Task Spec 加载器
geometry/        17 个确定性几何函数（任务真值的唯一来源）
checkers/        4 个确定性 checker（独立重算 target，不采信样本存值）
adapters/        UAVScenes adapter（run 发现 / split group 归并 / 场景切分）
schemas/         归一化场景契约 + 4 个答案输出 schema
task_specs/      4 个 Task Spec，覆盖首批 3 个任务族
registry/        UAVScenes 的 dataset_card / license_review / file_inventory
scripts/         build_scenes.py CLI
tests/           141 项，全部通过
```

对应 SPEC §34 vertical slice 的第 1、2、7、8 步。**尚未接入模型，也未使用 GPU。**

| Spec | 族 | checker |
|---|---|---|
| `3d_grounding.object` | grounding | `check_object_grounding_answer` |
| `3d_vqa.metric.minimum_distance` | vqa | `check_minimum_distance_answer` |
| `3d_vqa.situated.observer_relative_direction` | vqa | `check_observer_relative_direction_answer` |
| `cross_view_correspondence.object` | cross_view | `check_cross_view_correspondence_answer` |

## 实施边界（2026-08-24 已确定）

| 项 | 决定 |
|---|---|
| 首批数据集 | **UAVScenes** 单个（真实多视角，含 Livox 点云与 6DoF 位姿）。**已下载 35 GB**，20 个 run / 4 个 split group |
| 是否强制 metric scale | **强制**。UAVScenes 每 run 带 RTK，锚点确认存在；relative / affine-invariant / pseudo 深度场景首版不具备任务资格 |
| 首批任务 | **3D Grounding（对象级）+ metric/situated 3D VQA + Cross-view Correspondence** |
| Qwen 版本与部署 | **暂缓**。首批只编译 prompt bundle、跑泄漏检查与 checker 复现，不调用模型 |
| 数据许可 | **接受 CC BY-NC-SA 4.0，仅学术用途**。衍生 metadata 与任务标注按演绎作品处理，发布时沿用同一许可并署名 MARS-LVIG 与 UAVScenes |
| 服务器调度框架 | 不绑定框架，脚本 + 文件状态机 |
| 质量阈值 | 沿用文档建议值，待真实数据后校准；首批样本 100% 人工复核 |

细节与理由见 `DECISIONS.md` §19，机器可读形式见 `DESIGN.md` §36。

### 环境现实约束

- 本地 `data/` 只有 QA 标注 JSON，**无图像/视频/点云**，且属飞书已有清单，不能作为本 Pipeline 的重建输入。
- UAVScenes 已下载至 `data_raw/UAVScenes`（**HF 镜像开放，无需 token**）；其余 21 个候选未落盘。
- HF 镜像仅含 **interval=5**（1/5 帧率）。降采样可能降低帧间重叠，影响 VGGT-Ω 重建质量，需实测；不足则改取 interval=1。
- VGGT-Ω 尚未安装，其可获取性需在 Layer 2 开工前核验。
- 需用户手动提供的凭证与材料统一登记在 `docs/USER_ACTIONS.md`（当前仅剩飞书导出一项待办）。

### 项目定位（2026-08-24 已澄清）

**本 Pipeline 的最终产物是一对交付物**：2D 数据集对应的**点云** + 该点云对应的**下游任务标注**。只生成点云不算完成。

- Blob 上 `Pointcloud-VQA/`、`PointCloud-grounding/` 中的点云，是同事已用 VGGT-Ω 转出的**最终点云结果**（对应 `data/` 那批数据集）。它们**也可以**作为生成下游标注的中间产物，是否纳入取决于后续任务设计。
- 同级 `3D-GRPO` 是本 Pipeline **下游的训练框架**：用产出的点云 + 任务标注做 SFT，再用 GRPO 训练自有点云理解模型。**当前与数据生成解耦**，无需为其调整排期。
- 因此 SPEC §39/§41 三类 adapter 中，`pointcloud_native` 有了明确消费方，优先级不低于 `qwen_2d_metadata`。这不改变铁律 2/3 —— Qwen 仍只读 2D + metadata。

建议首批范围：UAVScenes 单数据集、对象级 L0/L1/L2 metadata、3D Grounding、metric/situated 3D VQA，加 Cross-view Correspondence。

## 文档入口

| 文件 | 阅读对象 | 用途 |
|---|---|---|
| `README.md` | 人类 | 项目方向、架构、数据集和当前状态 |
| `DESIGN.md` | Claude Code / Agent | 服务器实现的主规格 |
| `DECISIONS.md` | 人类与 Agent | 历史决策、调研依据和约束来源 |
| `DESIGN.md（附录：第三层）` | Agent / 开发者 | Skill 与质量系统的详细设计草案 |
| `USER_ACTIONS.md` | 用户与 Agent | 需要用户手动提供的信息登记（token、凭证、许可申请、飞书导出）；只记位置不记真实值 |
| `CHANGELOG.md` | 用户与 Agent | 每一次改动的流水账：需求、决策、实现、文档同步、事实修正 |
| `USER_ACTIONS.md` | 用户 | 待删除内容与删除命令（Agent 不执行删除） |
| `FINDINGS.md 附录 C` | 人类与 Agent | blob 上现有 VGGT-Ω 点云语料的实测分析：格式、尺度、任务形态 |
| `OPERATIONS.md` | 人类与 Agent | VGGT-Ω 的可获取性、许可分层、环境部署与实测输出契约 |
| `OPERATIONS.md` | 人类与 Agent | 专家模型的许可核验、部署状态与实测；逐模型详情见 `registry/experts/` |
| `FINDINGS.md` | **人类** | 调研发现的简明摘要：结论、影响、详情链接 |
| `FINDINGS.md 附录 B` | 人类与 Agent | 相对深度如何锚定为米制、失效边界与基线阈值 |
| `FINDINGS.md 附录 A` | 人类与 Agent | VGGT-Ω 置信度按语义类别的实测：水面失效信号、场景相对性 |
