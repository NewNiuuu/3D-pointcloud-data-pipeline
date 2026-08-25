# 设计主规格：低空 2D → 3D 数据生成管线

> ## ⚠️ 两次重定义，按时间顺序读（2026-08-25，均 [用户已确认]）
>
> ### 第二次（当日较晚）：纯视觉优先 + 交付重心转向任务类型 —— **优先级最高，覆盖以下第一次的部分结论**
>
> **v0.3.0 中「target 由 LiDAR 与视觉深度残差程序化产生」的设计已被推翻。**
>
> 用户确立：本 pipeline **MUST 对任何低空视觉数据集可用**，
> 应假设数据集**只提供图片或视频**，3D metadata 由模型提取、**允许不准**。
> 要求数据集自带 LiDAR + 标定 + RTK，会让方法只适用于极少数特殊数据集。
>
> → **新增铁律 14**；LiDAR/RTK 降为**一次性标尺**（§40.6，只做验证与标定，产出 Release D 报告）；
> **M-008 从阻塞项降为非阻塞项**。
> → 应对「提取不准」的方法论见 **§40.5 五条机制**。
> → **纠正的技术错误**：坡度是角度、粗糙度可取比值，**均在缩放下不变** ——
> C2 的核心几何量本就不需要任何传感器真值。
>
> 同日用户进一步明确**交付重心**：低空 3D 点云数据此前没有过，
> 数据的「高质量」只能是相对的；**相较数据质量，更重要的是提出值得做的下游任务类型** ——
> 即便我们的数据在该任务上质量不高，任务本身**指明后来者该优化的方向**。
>
> → 新增 **§1.1 交付物优先级**（任务类型 > 能力缺口论证 > 好数据判据 > 可移植方法 > 语料）
> 与 **§52 任务价值论证与数据演进目标**（每能力五问，**缺论证的任务不进 Release**）。
> → 写作纪律：**当前数据的质量上限 MUST 诚实写明**，写清做不到什么正是「指方向」的一部分。
>
> 决策依据见 `DECISIONS.md` §19.8、§19.9。
>
> ---
>
> ### 第一次（当日较早）：能力范围重定义 —— 结论仍有效，但其中的 LiDAR 依赖已被上面覆盖
>
> **本规格 v0.2.0 中关于「低空差异化能力」的定义已被推翻并替换。**
>
> 原定义（薄障碍 / 可飞行体积 / 净空 / 航迹 / TTC / Next-best-view / occupancy）
> 是在**尚未获得数据**时做的规划。首批数据集 UAVScenes 落地后实测发现：
>
> - **相机为近垂直下视，俯角中位 87.6°（范围 84.6–88.8°），对地约 33 m；**
> - 这是**航测飞行，不是导航飞行** —— 相机永远看不到飞行方向前方的障碍。
>
> 因此薄障碍、前向避障、通道净空、航迹可行性、TTC、Next-best-view 等能力
> **在本数据集上无法产生有效监督**。强行生成会得到「看起来像导航训练数据、
> 实际不是」的样本，训练出虚假能力 —— 这违反铁律 5。
>
> **但它们不是被放弃，而是降级为后续目标（2026-08-25 用户补充）。**
> 理由是模型需要足够的能力**多样性（Diversity）**。实现路径是引入前视/侧视
> 数据集（原方案 B），届时 §14.6/§14.7 与本节移下的设计可直接启用。
> 现登记为 **Release E**，解锁条件是 R-37。
> **当前阶段全力攻坚 §40.3 的 C1–C4，Task Family B 进入待办 backlog。**
>
> **新的能力范围见 §40。** 以下章节已按新定义重写：
> §1（输出族）、§34（vertical slice）、§40（能力目标）、§43.2（低空特异性）、
> §44/§45/§46（任务族）、§49（覆盖矩阵）、§51（发布顺序）。
>
> **§14.6（薄障碍）与 §14.7（可飞行空间）予以保留但当前不适用** ——
> 它们是针对前视/侧视数据的正确规则，待引入此类数据集后再启用。
>
> 决策依据见 `DECISIONS.md` §19.5。


```yaml
document_type: agent_implementation_spec
target_reader: Claude Code
spec_version: 0.4.0
status: vision_only_mandate_and_deliverable_repriority
fact_verification_cutoff: 2026-08-25
execution_target: remote_server
local_workspace_role: design_and_control_plane
```

---

# Part 0. 设计哲学：一切为下游任务服务

> **本章是全文的总纲，2026-08-25 由用户确立。**
> 后续所有章节都是这条哲学的展开；与本章冲突的表述以本章为准。

## 0.1 项目身份带来的两难

这是一个 **3D 点云理解**项目。因此产出的数据**必须真实体现三维特征** ——
否则它只是换了个壳的 2D 数据集，没有存在的理由。

但低空数据集**只提供 2D 图像或视频**（铁律 14）。

于是唯一可行的路径是：**用 3D 专家模型从 2D 数据中提取三维特征。**

这两句话之间的张力就是本项目要解决的全部问题。它同时决定了：
为什么必须有 VGGT-Ω（要点云）、为什么要多个专家模型（要交叉验证）、
为什么要置信度与门禁（提取会错）、为什么任务形态要精心挑选（错了还得能用）。

## 0.2 推导链：设计时从右往左，执行时从左往右

```text
        执行方向（运行时）  →→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→

  数据源        3D 专家模型提取         结构化 3D metadata        任务编译           下游任务数据
  (2D 图像/     VGGT-Ω / MoGe / DA3 /   点云·位姿·深度·置信度·    隐藏 target +      训练集 /
   视频)        分割 / 光流 / 跟踪      法向·平面·语义·关联       evidence+checker   Benchmark

        ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←  推导方向（设计时）
```

**设计时 MUST 从右端出发**：先确定要什么下游任务 → 倒推它需要哪些 3D metadata →
倒推哪些专家模型能提供 → 最后才是数据源要满足什么条件。

**反过来做是被明确拒绝的工作方式**：先看有什么数据、有什么模型、能提取什么，
再想能出什么题 —— 那会得到一堆「能生成但没价值」的任务。

## 0.3 反向证成规则（MUST）

> **每一个提取阶段、metadata 字段、专家模型、Skill 与门禁，
> MUST 能指名它服务的下游任务能力。**
> 指不出来的，MUST 标注 `UNJUSTIFIED`，并在下次交付中删除或补上论证。

正向读是执行链，反向读是证成链：

| 上游组件 | 它为什么存在 | 服务的下游能力 |
|---|---|---|
| VGGT-Ω 点云 | 点云是 3D-GRPO 的直接消费对象，也是所有 3D 锚点的载体 | 全部 |
| 相机位姿与内参 | situated 任务需要观察者视角；GSD 需要内参 | situated VQA、C3 |
| `depth_conf` | 任务要回答「这里可不可信」 | **C1** |
| 多估计器（MoGe / DA3） | **分歧是失效标注的来源** —— 不是为了投票求真值（§14.13） | **C1** |
| 光流 / 前后向环路误差 | 自洽违反是纯视觉的失效证据（§40.5 机制 1） | **C1** |
| 扰动重提取 | 几何脆弱度标注 | **C1、C4** |
| 法向与局部平面拟合 | 坡度、共面性 —— **角度无尺度，是 C2 的核心量** | **C2、C3-a** |
| 语义分割 | 「平坦 ≠ 可降落」必须联合语义才能判 | **C2** |
| 跨视角关联与实例融合 | 同一实体在不同视角的指认 | grounding、cross-view |
| 尺度锚探测（EXIF/GPS） | 决定能不能出米制题（§40.5 机制 5） | **C3-b** |
| 泄漏防护（§41、`task_adapters/base.py`） | 答案出现在输入里，题就白出了 | 全部 |
| 确定性 checker | **判不了分的题不该被生成**（§27 G3） | 全部 |
| Split group | 同场景样本跨 split 会虚高指标 | 全部 |

**本表 MUST 随设计变更同步更新。** 新增任何上游组件前，先在此登记它服务谁。

## 0.4 什么才算「体现了 3D 特征」

> **2026-08-25 修订**：本节原第 2 条为「单张 2D 图像回答不了」，
> 已按铁律 5 的修订改为可测量的增益判据。理由见铁律 5 的说明框。

三条判据，**缺一不可**：

1. **答案锚定在三维实体上**（§41）：target MUST 映射到点索引、点掩码、OBB、平面、
   区域或相机位姿。只给一个字符串 ID **不算** —— 点云模型无从消费。
2. **3D metadata 带来可测量的增益**（铁律 5、§29）：
   `score(2D+metadata) − score(2D only)` MUST 显著大于 0，
   且打乱/屏蔽相关字段后该增益 MUST 选择性消失。
   **不要求 2D 完全答不出** —— 那在信息论上不可能，因为我们的 3D 就是从 2D 提取的。
3. **三维信息是因果性的**：改变三维结构会改变答案，
   而只改变外观（光照、色彩、曝光）**不应**改变答案。**这正是 C4 的直接检验。**

**仍然出局的形态（MUST NOT 生成）：**

- **增益为零**的题 —— 给不给 3D metadata 得分一样，说明它只是披了层壳的 2D 识别题；
- **伪增益** —— 打乱 metadata 后得分不掉（蒙对/泄漏/长度效应，§29.2）；
- 答案能从 metadata 字段名或字段值直接读出（泄漏，铁律 6）。

> **注意与旧表述的区别**：先前把「数值来自 3D 但与外观强相关」一概判为假 3D。
> 现在的判据是**实测增益**：若 3D metadata 确实提分且经得起打乱检验，
> 即便外观也提供部分线索，任务依然成立。**外观有线索 ≠ 3D 没用。**

## 0.5 提取一定不准，怎么办

这是本设计最核心的工程现实。应对方式**不是**换更好的传感器（那违反铁律 14），
而是 §40.5 的五条机制。一句话概括：

> **让任务形态去适应误差的结构，而不是让误差去适应任务形态。**

- 深度误差以**尺度与低频偏置**为主 → 用序数、角度、比值这些缩放下不变的目标（机制 2）；
- 提取器会失效 → **把失效本身做成标签**（机制 4）；
- 不知道哪些样本可信 → 一致性**做筛子不做真值**（机制 3）；
- 分不清测量与观点 → 只让可复算的测量定义答案（机制 1）；
- 尺度不总是可得 → 分档，够不着就静默降级（机制 5）。

## 0.6 四层架构的从属关系

四层不是并列的，是**目的与手段**的关系：

| 层 | 地位 | 说明 |
|---|---|---|
| **第四层 下游任务** | **目的** | 其余三层存在的唯一理由 |
| **第二层 提取与生成** | **手段** | 提供第四层**点名要**的 3D metadata，不多做 |
| **第一层 数据源** | **前提** | 满足第二层可提取的最低要求（§40.5 机制 5 的 T0–T4 分档） |
| **第三层 Agent/Skill/门禁** | **保障** | 保证前三者的产出可信、可复现、可判定 |

**第三层当前降为「润色层」**（`DECISIONS.md` §19.4）——
保障机制应当在被保障的东西成型之后再固化。不是不重要，是次序问题。
详细设计完整保留在本文附录。

## 0.7 项目的价值定位：蒸馏，与博采百家之长（2026-08-25 [用户已确认]）

诚实地讲清楚本项目是什么、不是什么 —— 这决定了能宣称什么、不能宣称什么。

**不是什么：**

- 不引入新采集的数据集；
- 不做人工标注；
- 不训练新的三维基础模型。

**是什么：**

> **把一批各有所长的三维专家模型的能力，蒸馏进一个当前不具备这些能力的 VLM。**

价值分三层，**越往下越不可替代**：

| 层 | 做法 | 能力上限 |
|---|---|---|
| **1. 单教师蒸馏** | 把 VGGT-Ω 的几何能力搬进 VLM | 不超过该教师 |
| **2. 多教师融合（博采百家之长）** | 几何、语义、分割、跟踪、光流各取所长，集中到一个模型 | 各教师能力的**并集** |
| **3. 集成结构产生的新信号** | 教师之间的**分歧**、几何**自洽违反**、扰动下的**漂移** | **超出任何单个教师的输出接口** |

**第 3 层值得单独说清楚。**

任何一个专家模型都**不会告诉你「我这里不可靠」** ——
`depth_conf` 是模型的自评，不是错误率，实测已证明它既是场景相对的、
又在退化下判别力坍缩（`FINDINGS.md`）。
但把多个独立教师放在一起，**它们的分歧就成了任何单个教师无法从其输出接口提供的信号**。

**这正是 C1 成为旗舰能力的根本原因** —— 它坐落在第 3 层。
C2/C3 主要在第 2 层，Release A 的基础任务在第 1 层。
优先级排序（C1 > C2 > C3 > C4）与这三层的不可替代性是一致的，不是巧合。

### 由此得到的自我约束

**MUST NOT 宣称**产出了超越现有专家模型的三维能力 —— 我们没有。

**MAY 宣称**的是三条：

1. **把分散在多个模型里的能力集中**到一个可用的 VLM 上；
2. **用集成结构造出单教师没有的信号**（可靠性、失效归因）；
3. **给出一套可移植的方法与实测误差刻画**（§40.6、Release D）。

严格说，第 2 条的信息仍在「各教师输出的并集」之内 —— 分歧是从教师输出算出来的。
**准确的表述是：它超出任何单个教师的输出接口，而不是超出信息论上限。**
写作时 MUST 用后一种表述，不得含糊成「创造了新信息」。

## 0.8 建议阅读顺序

代码、schema 与 task spec 中有 **245 处引用现有章节号**，
因此本次文档重构**不重新编号**。但推荐按推导链的顺序阅读：

| 步骤 | 问题 | 章节 |
|---|---|---|
| 1 | **要产出什么** | §1.1 交付物优先级 → §40 能力目标 → **§52 任务价值论证** → §44–§48 任务族 → §51 发布顺序 |
| 2 | **任务需要什么** | §41 任务记录契约 → §19 任务样本契约 → §24 Task Spec → §42 监督等级 → §27/§50 门禁 |
| 3 | **从哪里提取** | §13 几何重建 → §14 专家模型系统 → §15 提升融合 → §16 metadata 分层 |
| 4 | **数据源要满足什么** | §7 数据集卡 → §8 准入门禁 → §40.5 机制 5（T0–T4 分档） |
| 5 | **怎么保障** | §21–§33（第三层，当前降级）+ 附录 |

**只读一节的话读 §52** —— 它是本项目的首要交付物（§1.1）。

---

## 0. Agent Directive

This file is the canonical implementation specification for the initial server-side repository.

Normative terms:

- `MUST`: required invariant; do not change without explicit user approval.
- `MUST NOT`: prohibited behavior.
- `SHOULD`: default implementation choice; deviation requires a recorded reason.
- `MAY`: optional extension.
- `UNRESOLVED`: configuration requiring user decision or empirical validation.

Before modifying implementation:

1. Read this file completely.
2. Read `DECISIONS.md` for provenance and historical context.
3. Treat this file as authoritative for system organization.
4. If this file conflicts with a user-confirmed rule in `DECISIONS.md`, stop and report the conflict.
5. Do not silently resolve `UNRESOLVED` items.

## 1. System Objective

Build a data-generation and evaluation system for low-altitude UAV / near-ground aerial 3D scene understanding.

### 1.1 交付物的优先级（2026-08-25 用户确立）

低空 3D 点云训练数据此前基本不存在。本项目**不以「产出绝对高质量的语料」为首要目标** ——
在现有工具下，数据质量只能是**相对的**。首要目标是：

| 优先级 | 交付物 | 说明 |
|---|---|---|
| **1** | **值得做的下游任务类型** | 哪些任务能补上现有训练数据缺失的能力。**即使我们自己的数据在该任务上质量不高，任务本身指明了方向** |
| **2** | **能力缺口的论证** | 那个缺失的能力究竟是什么、为何现有数据供不上、为何该任务能训到它 |
| **3** | **「好数据」的判据** | 要把这类任务做好，数据需要满足什么特征 —— 这是给后来做数据的人的**优化目标** |
| **4** | **可移植的生成方法** | 纯视觉管线 + 实测误差刻画（铁律 14、§40.6） |
| 5 | 语料本身 | **存在性证明与基线**，不是终点 |

**因此写作与实现 MUST 遵守**：

- 每个任务族 MUST 有 §52 的价值论证（能力缺口 / 为何能训到 / 当前上限 / 好数据特征 / 衡量指标）；
  **缺论证的任务不进 Release**，哪怕它技术上能生成；
- 当前数据的质量上限 MUST 诚实写明，**不得用「已足够」掩盖** ——
  写清上限正是「指方向」的一部分；
- 在「提高本批数据质量」与「把任务类型论证清楚」之间冲突时，**优先后者**。

```text
Low-altitude 2D datasets
    ├── VGGT-Ω
    │     └── cameras + depth + confidence + point cloud
    ├── native labels + 2D/video expert models
    │     └── masks + tracks + semantics + specialist detections
    ├── 2D-to-3D lifting and fusion
    │     └── structured 3D metadata + provenance + confidence
    ├── downstream task designer/compiler
    │     └── 3D anchors + hidden targets + evidence + checkers + prompt bundles
    ├── Qwen adapter: 2D visual inputs + task-local 3D metadata
    ├── native point-cloud adapter
    └── multimodal 3D adapter
          └── portable low-altitude 3D task supervision
```

The initial output families are（2026-08-25 按 §40 新能力范围修订）:

- 3D Semantic / Instance Segmentation
- Perception Reliability and Failure Attribution（感知可信度与失效归因）
- Landing Zone Assessment（安全降落区评估）
- Metric Terrain and Height Reasoning（米制地形与高度推理）
- Cross-temporal Change and Illumination Robustness（跨时相变化与光照鲁棒）
- Cross-view Correspondence and Visibility

以语言/结构化形式承载上述能力的题型：

- 3D Grounding
- 3D VQA
- 3D Caption
- 3D Dialogue

Candidate extensions include:

- 3D Metadata Verification
- 3D Metadata Completion
- Viewpoint Transformation
- 3D Scene Graph Query
- Geometry-aware Retrieval
- Spatial Counterfactual Simulation
- Uncertainty-aware 3D Reasoning
- Grounded Measurement Dialogue

**降级为后续目标**（需前视/侧视导航数据，UAVScenes 不支持；保留以确保能力多样性）：
Thin-Structure Annotation、Occupancy / Flyable Volume、Route Feasibility、
Minimum Clearance、TTC / Collision Risk、Next-best-view、Inspection-view Planning、
Route / Plan Critique、3D Task Decomposition（其步骤绑定 waypoint 与航迹约束）。

## 2. Immutable Architecture Rules

1. VGGT-Ω MUST be the primary point-cloud reconstruction path.
2. Qwen MUST consume 2D images/video plus structured 3D metadata.
3. Qwen MUST NOT consume raw PLY/LAS point clouds in this architecture.
4. Depth Anything 3, WorldMirror, or other geometry models MAY be used as experts or consistency checks; they MUST NOT replace VGGT-Ω as the primary path.
5. A generated task MUST demonstrate **measurable 3D lift**: supplying the extracted 3D metadata MUST improve performance over the 2D-only baseline by a margin recorded in the task's evaluation record (§29). Ordinary 2D recognition questions — where the lift is nil — remain out of scope. **A task is NOT required to be unanswerable from 2D alone.**

> **铁律 5 的 2026-08-25 修订（[用户已确认]）**
>
> 原文为「A generated task MUST require 3D information」。**该表述在信息论上站不住。**
>
> 本项目的 3D metadata 由专家模型从同一批 2D 图像中提取（铁律 14），
> target 也由视觉信息推出。即 **M = f(I)、Y = g(I)** ——
> 由数据处理不等式 `I(M;Y) ≤ I(I;Y)`，**凡是能从 M 回答的，原则上都能从 I 回答**。
> 提取过程只会丢信息，不会凭空造信息。所以「2D 绝对做不到」是**不可能达成**的门槛。
>
> 真正的差别不在信息**有没有**，而在信息**取不取得到**：
> 现有 VLM 在图文对上训练，从未被奖励去做多视三角化、平面拟合、
> 跨视角关联这类计算，于是**系统性地忽略图像里本就存在的三维线索**。
> 我们把当前最擅长提取三维的专家模型的输出**显式喂进去**，
> 它应当带来**增益**——是连续的提升，不是 0/1 的开关。
>
> 因此判据由**断言**改为**测量**（§29）。
> 若确实存在只有 3D 能做、原始 2D 做不到的任务，那当然最好 ——
> **但不作为准入门槛**（唯一的真例外见 §29.3）。
>
> **口子放宽了，但没有放空**：要求从「必须不可解」变成
> 「必须实测有显著增益，且能排除三种伪增益」。
> 原判据从未被验证过，新判据每一条都要跑数字 —— 这是收紧，不是放松。

6. Metadata input MUST NOT directly expose the hidden answer or an equivalent derived field.
7. Deterministically computable values MUST be generated and checked by geometry/rule programs, not accepted solely from an LLM.
8. Metric and relative scale MUST remain distinct throughout the pipeline.
9. Pseudo-depth MUST NOT be represented as metric ground truth without an external metric anchor.
10. Every generated artifact MUST preserve provenance, version, source frames, coordinate frame, units, confidence, and parent artifact references.
11. Dataset splits MUST be scene-, location-, or trajectory-level. Per-frame random splitting is prohibited.
12. The initial implementation SHOULD prioritize a small end-to-end scene closure before large-scale generation.
13. Feishu source documents and existing Obsidian notes MUST NOT be modified by this project.
14. **Target values MUST be derivable from the dataset's own visual information (images or video) plus models that operate on it.** Sensor ground truth such as LiDAR, RTK, or surveyed control points MAY be used to *validate and calibrate* the pipeline, but MUST NOT be a precondition for producing training data. A capability that can only be supervised on LiDAR-equipped datasets is out of scope for the main path.

> **铁律 14 的来源与用意**（2026-08-25 用户确立）：本项目的价值在于
> **一套能用在任何低空视觉数据集上的生成方法**，而不是一个从特殊传感器派生的语料库。
> 若要求数据集自带 LiDAR + 标定 + RTK，方法就只对极少数数据集适用，失去意义。
>
> 提取出来的 3D metadata **允许不准**。应对不准的手段是
> §40.5 的五条机制（测量优于观点、序数优于米制、一致性做筛子、失效即标签、尺度分档），
> **不是**换一个更准的传感器。
>
> 这条铁律**推翻了 2026-08-25 早前 §40.3/§46 中「target 由 LiDAR 残差程序化产生」的设计**，
> 该设计已按本条重写。LiDAR 的新角色见 §40.6。

## 3. Four-Layer Architecture

```text
Layer 1: Dataset Source Registry and Selection
    output: verified dataset cards + sample manifests + selection decision

Layer 2: 2D-to-3D Metadata Extraction and Scene Construction
    output: versioned point clouds + scene packages + geometry/semantic/temporal metadata

Layer 3: Agent, Skills, Prompt Compilation, Validation, and Quality Monitoring
    output: validated samples + quality events + release manifests

Layer 4: Downstream Task Design and Capability Completion
    input: point cloud + cameras + scene metadata + quality/provenance
    output: portable 3D task annotations for Qwen, native point-cloud models, and multimodal 3D models
```

Layer boundaries MUST be implemented through versioned artifacts. In-memory-only implicit contracts are prohibited for production runs.

---

# Layer 1. Dataset Source Registry and Selection

## 4. Purpose

Layer 1 maintains a machine-readable registry of low-altitude / near-ground aerial datasets that can supply images, videos, labels, geometry anchors, or evaluation ground truth.

Layer 1 MUST:

- distinguish real and simulated data;
- distinguish native depth, rendered depth, stereo, SfM/MVS, direct LiDAR, and pseudo-depth;
- record metric-scale availability and scale source;
- record camera calibration, pose, timestamps, labels, and point-cloud availability;
- verify current official links, version, file inventory, license, redistribution constraints, and checksums before ingestion;
- compare candidates with the current Feishu registry without modifying Feishu;
- output dataset cards and small-sample manifests before any full download.

## 5. Existing Feishu Registry Snapshot

The following names were present in the Feishu snapshot captured on 2026-08-23 and were excluded from the prior “new candidate” list:

```yaml
feishu_existing_snapshot:
  - FloodNet
  - Open3DVQA
  - TDBench
  - LADI-v2
  - AVI-Math
  - AirCopBench
  - SpatialSky
  - UrbanVideo-Bench
  - MM-UAVBench
  - MME-RealWorld
  - Geo3DVQA
```

This is a historical snapshot, not a current truth. Before a new dataset-review cycle, an authorized read-only process SHOULD obtain the latest Feishu list and rerun name/alias/content deduplication.

## 6. Previously Identified New Candidates

The following candidates were not present in the historical Feishu snapshot. Their detailed availability and licensing are not yet fully verified.

| Priority | Dataset | Source | Available 3D-enabling signals | Initial role |
|---|---|---|---|---|
| S | UAVScenes | Real | RGB, Livox point cloud, 6DoF poses, calibration, semantic cloud/mesh | real semantic geometry anchor |
| S | Dronescapes | Real | video, SfM intrinsics/poses, metric depth, normals, semantic subset | real multi-view reconstruction |
| S | H3D / Hessigheim 3D | Real | dense airborne LiDAR, RGB, labeled cloud, textured mesh, multi-temporal data | high-quality 3D supervision |
| S | SkyLume | Real | five-direction cameras, repeated RTK flights, COLMAP poses, mesh/LiDAR depth, normals | repeated-flight geometry |
| S | UAVStereo | Real + simulated | stereo RGB, PFM disparity, mesh/LiDAR geometry | stereo geometry validation |
| S | UrbanScene3D | Real + simulated | LiDAR, textured mesh, images/poses, simulated depth/boxes/segmentation | mixed-domain scene understanding |
| S | ClaraVid | Simulated | metric depth, semantic/instance/dynamic masks, cameras, scene cloud | complete synthetic labels |
| A | NTU VIRAL | Real | stereo cameras, dual 3D LiDAR, IMU, UWB, Leica truth, calibration | sensor/pose validation |
| A | MUN-FRL | Real | monocular RGB, 3D LiDAR, IMU, RTK-GNSS, calibration | metric-scale real sequences |
| A | MARS-LVIG | Real | RGB, Livox, IMU, GNSS, RTK, DJI L1 map truth | real metric geometry |
| A | Mid-Air | Simulated | depth, normals, semantics, disparity, occlusion mask, poses, IMU/GPS | controlled synthetic scenes |
| A | UAV3D | Simulated | multi-UAV/multi-view RGB, pixel semantics, 3D boxes | multi-view object tasks |
| A | U2UData+ | Simulated | multi-UAV RGB + LiDAR, 3D boxes/tracks | collaborative perception |
| A | IllumUAV-Sim | Simulated | aligned day/night RGB, depth, normals, cameras | illumination robustness |
| B | UAPD / DAPM | Simulated | RGB, depth, randomized altitude/pose/FOV | viewpoint diversity |
| B | UAVPairs | Real | high-overlap multi-view images, SfM matching relations | correspondence tasks |
| B | UAVID3D | Real | RGB + thermal, high-overlap orbit imagery, GPS | multimodal reconstruction |
| B | Ready for 3D Reconstruction | Real | GCP/checkpoints, 2D correspondences, MVS subset, TLS cloud | scale/reconstruction evaluation |
| B | FlyAwareV2 | Real + simulated | RGB, depth, semantic masks; real depth includes monocular pseudo-depth | obstacle tasks with provenance caution |
| B | LAMBDA | Simulated | RGB, LiDAR, 4D radar, CSI, depth, IMU, multi-UAV | multimodal extension |
| C | UAVid | Real | 4K video, eight semantic classes; weak geometry/pose | semantic expert input |
| C | VisDrone | Real | large detection/tracking annotations; no depth or pose | 2D expert/task auxiliary source |

## 7. Dataset Card Contract

Each dataset MUST have a versioned card before ingestion.

```yaml
dataset_id: uavscenes
display_name: UAVScenes
card_version: 0.1.0
dataset_version: UNRESOLVED
source_type: real  # real | simulated | mixed

official_sources:
  project_url: UNRESOLVED
  repository_url: UNRESOLVED
  download_url: UNRESOLVED
  paper_url: UNRESOLVED

license:
  identifier: UNRESOLVED
  commercial_training: unknown
  derivative_point_cloud_redistribution: unknown
  model_weight_release: unknown
  verified_at: null

modalities:
  rgb: true
  video: UNRESOLVED
  lidar: true
  depth: false
  camera_intrinsics: true
  camera_extrinsics: true
  imu: UNRESOLVED
  gps_rtk: UNRESOLVED

geometry:
  depth_source: direct_lidar
  metric_scale: true
  scale_source: lidar
  coordinate_system: UNRESOLVED

annotations:
  semantic_2d: UNRESOLVED
  instance_2d: UNRESOLVED
  semantic_3d: true
  instance_3d: UNRESOLVED
  tracking: UNRESOLVED

ingestion:
  adapter_status: not_started
  sample_download_status: not_started
  verified_file_inventory: null
  checksums: null

risks: []
```

Allowed `depth_source` values:

```text
direct_lidar
stereo
sfm_mvs
rendered_depth
pseudo_depth
none
```

## 8. Dataset Selection Gates

A dataset MUST NOT enter full ingestion until:

1. Official source and version are recorded.
2. License and derivative-data constraints are reviewed.
3. A 1–3 scene sample is downloaded and inspected.
4. Required files are readable and aligned.
5. Camera and scale assumptions are validated.
6. Scene-level splitting is possible.
7. Its role in the initial benchmark is explicit.

Recommended initial roles, not final selections:

```yaml
real_multiview_reconstruction_candidates:
  - UAVScenes
  - Dronescapes

high_quality_3d_reference_candidates:
  - H3D
  - UAVStereo

complete_simulated_label_candidate:
  - ClaraVid
```

Dataset choice was resolved on 2026-08-24: **UAVScenes** is the single Phase-1 dataset. The
remaining names above stay candidates for later phases and MUST NOT be treated as selected.
Phase-1 eligibility additionally requires `metric_scale_policy: metric_required` (SPEC §36),
so relative-scale-only scenes are ineligible regardless of tier.

## 9. Layer 1 Outputs

```text
registry/datasets/<dataset_id>/dataset_card.yaml
registry/datasets/<dataset_id>/file_inventory.json
registry/datasets/<dataset_id>/license_review.yaml
registry/datasets/<dataset_id>/sample_manifest.json
registry/datasets/<dataset_id>/verification_report.json
registry/feishu_snapshot/<date>.yaml
registry/selection/phase_<n>.yaml
```

---

# Layer 2. 2D-to-3D Metadata Extraction and Data Pipeline

## 10. Purpose

Layer 2 transforms raw dataset scenes into point clouds, structured 3D metadata, deterministic targets, and task-local context suitable for Qwen.

## 11. Stage Graph

```text
L2-S0 Dataset Adapter / Scene Slicing
    input: raw dataset files + dataset card
    output: normalized scene manifest

L2-S1 Geometry Reconstruction
    input: normalized images/video + optional camera priors
    model: VGGT-Ω
    output: camera estimates + depth + confidence + point cloud

L2-S2 2D / Video Expert Perception
    input: normalized frames/video
    output: masks + detections + tracks + specialist predictions

L2-S2B Independent Geometry Experts
    input: normalized frames/video + optional camera priors
    output: metric/relative depth opinions + normals + validity + tracks + alignment residuals
    default priority: MoGe-3 -> DSINE -> DA3-1.1; DA3-Streaming only for long video

L2-S3 2D-to-3D Lifting and Fusion
    input: VGGT-Ω geometry + semantic/video predictions + aligned independent geometry evidence
    output: stable 3D objects/parts/regions/tracks

L2-S4 Metadata Derivation
    input: L0/L1 entities
    output: L2 relations + selected L3 temporal/action fields

L2-S5 Quality and Provenance
    input: all upstream artifacts
    output: immutable metadata snapshot + validation report

L2-S6 Task Compilation
    input: metadata snapshot + task spec
    output: hidden target + evidence + prompt bundle

L2-S7 Model Generation
    input: 2D views/video + task-local metadata + prompt bundle
    model: configured Qwen variant
    output: raw structured response

L2-S8 Sample Validation
    input: raw response + hidden target + checker
    output: validated sample or quarantine event
```

## 12. Normalized Scene Contract

```json
{
  "scene_id": "scene_000018",
  "dataset_id": "dataset_name",
  "dataset_version": "...",
  "split_group_id": "location_or_flight_id",
  "source_type": "real",
  "frames": [],
  "native_annotations": [],
  "sensor_calibration": {},
  "coordinate_frame": "dataset_native",
  "unit": "unknown",
  "scale": {
    "status": "relative",
    "source": "none",
    "uncertainty_m": null
  },
  "provenance": {}
}
```

All adapters MUST emit this contract or a versioned successor.

## 13. Geometry Reconstruction

VGGT-Ω outputs MAY include:

- camera pose encoding;
- camera extrinsics/intrinsics;
- depth;
- depth confidence;
- camera/register tokens;
- point cloud derived by depth back-projection;
- optional text-alignment embedding when a compatible checkpoint is used.

Implementation requirements:

1. Record exact model checkpoint and code revision.
2. Preserve input-frame IDs and sampling strategy.
3. Preserve raw depth confidence before thresholding.
4. Record all coordinate transforms.
5. Record whether metric alignment was applied and its anchor.
6. Generate geometry diagnostics for coverage, reprojection, density, drift, and invalid depth.
7. Detect and flag likely dynamic ghosting、sky depth、**water/glass/mirror failures**、
   repeated-texture drift、以及**无纹理均质面**。
   （2026-08-25：移除 thin-structure loss；新增的几项正是 §46.1 C1 的直接输入。）

Metric scale example:

```json
{
  "coordinate_frame": "world",
  "unit": "meter",
  "scale": {
    "status": "metric",
    "source": "rtk_gps",
    "uncertainty_m": 0.08
  }
}
```

Relative-scale scenes MAY support topology, correspondence, relative position, visibility, and scale-invariant tasks. They MUST NOT generate absolute-meter targets.

## 14. Expert Model System

Two expert surveys dated 2026-08-23 establish separate semantic/video and independent-geometry stacks. Official assets were reviewed, but no checkpoint was downloaded and no candidate was tested on local UAV data. All recommendations remain subject to license review. The geometry validation baseline is 40–60 short clips plus 8–12 long clips; the full semantic comparison MAY expand to 100–300 clips.

### 14.1 Research Baseline Stack

| Function | Initial expert | Role in this pipeline |
|---|---|---|
| Open-vocabulary instance proposals and masks | Grounded-SAM-2: Grounding DINO + SAM 2.1 Base+ | semantic proposal, pixel mask, initial object identity |
| Video mask tracking | SAM 2.1 Base+ | propagate masks and 2D track IDs; periodically reinitialize from detector |
| Optical flow and motion evidence | SEA-RAFT | flow, uncertainty, forward/backward consistency, residual-motion evidence |
| Sky/water/stuff semantics | OneFormer with ADE20K/Mapillary labels | independent semantic reason masks |
| UAV obstacle semantics | CABiNet MobileNetV3-Small | UAV-specific obstacle/ground/vegetation evidence |
| Power-line specialist | PowerLine-MTYOLO Nano | cable masks and power-line proposals; domain-specific only |
| Independent metric geometry | MoGe-3 ViT-L | primary scale/normal/valid-mask/fine-detail second opinion; never replaces VGGT-Ω |
| Independent normal | DSINE with uncertainty | normal evidence independent of depth differentiation; license-gated |
| Depth/pose/scale cross-check | Depth Anything 3 / DA3-1.1 Apache-compatible variant | secondary depth/camera/sky/scale opinion; never fuse its second point cloud as truth |
| Long-video geometry | DA3-Streaming | chunked pose/depth/confidence with overlap and loop closure; activation is optional and license-gated |
| Point tracks and visibility | CoTracker3 | 2D tracks/visibility for temporal support; noncommercial license restricts deployment |
| Attribute/caption proposals | Florence-2 Base or Large | structured attribute/caption proposals, not geometric truth |
| Cross-view appearance embedding | DINOv2 Small or Base | ReID, clustering, and cross-view association features |

Grounded-SAM-2 is a modular system. Detector box/class confidence and SAM mask confidence MUST be stored separately. Bounding boxes MUST NOT be lifted as though every enclosed pixel belongs to the object.

### 14.2 Candidate Tiers

```yaml
A0_initial_candidates:
  - Grounded-SAM-2
  - SAM 2.1
  - SEA-RAFT
  - OneFormer
  - CABiNet
  - MoGe-3 ViT-L after weight-license confirmation
  - Depth Anything 3 / DA3-1.1 Apache-compatible variant
  - Florence-2

A1_accuracy_or_ablation_candidates:
  - FC-CLIP
  - Cutie
  - XMem
  - EdgeTAM
  - UniMatch
  - SAM 3.1 after license review
  - AerialMetric
  - MetricAnything
  - DSINE after license review
  - DA3-Streaming after dependency-license review
  - CoTracker3 for noncommercial research or separately authorized use
  - Trace Anything for noncommercial research or quality evaluation
  - MASt3R as sampled correspondence expert
  - OVMono3D or DetAny3D as UAV-unverified object-level ablation
  - PowerLine-MTYOLO
  - TTPLA-YOLACT
  - DINOv2
  - OTAS

B_or_later_candidates:
  - OpenSeeD
  - MemFlow
  - UFM
  - EDFNet after training and license clarification
  - PBSeg after license clarification
  - DINO-X API subject to deployment/privacy/version review
  - U2MOT
  - AnyChange
  - ChangeSAM
  - DAM subject to weight license
  - WorldMirror for inference/evaluation only; never training metadata
  - CUT3R as secondary long-video cross-check
```

Candidate tier is not permission to download, install, or use a model. `expert-registry-manager` MUST verify current source, checkpoint, code license, weight license, derivative-data constraints, runtime, and UAV validation status before activation.

### 14.3 Expert Scheduling

Recommended initial cadence:

```yaml
mask_tracking: every_frame
detector_reinitialization: every_5_to_15_frames_or_confidence_drop
optical_flow: adjacent_frames
depth_cross_check: keyframes
normal_cross_check: keyframes
uav_semantic_segmentation: keyframes_or_low_rate
attribute_extraction: 1_to_3_best_views_per_stable_track
change_detection: scene_level_offline_only
```

Exact cadence MUST remain configurable and MUST be profiled on the target server.

### 14.4 Dynamic Geometry Rule

Raw optical-flow magnitude MUST NOT be interpreted as object motion because UAV ego-motion produces global image flow.

Dynamic evidence MUST be based on residual flow:

```text
observed flow
  - static flow rendered from VGGT-Ω depth + camera motion
  = residual flow
```

The dynamic probability SHOULD combine:

- residual-flow magnitude;
- flow uncertainty;
- forward/backward consistency;
- instance mask membership;
- depth/reprojection consistency;
- temporal support.

Water, reflection, moving foliage, shadows, motion blur, and propeller artifacts MUST remain separate failure reasons rather than being silently classified as physical object motion.

### 14.5 Invalid Geometry Reasons

The pipeline MUST retain independent probability maps and reason codes for:

```text
sky
water
reflection_or_transparency
low_depth_confidence
reprojection_inconsistent
dynamic_geometry
out_of_bounds
```

A combined invalid probability MAY be computed, but it MUST NOT replace the component reason masks. Water MUST NOT be treated as equivalent to empty space; it is geometry that often violates stable Lambertian/rigid reconstruction assumptions.

### 14.6 Thin Obstacles

> ⏸️ **当前数据集不适用（2026-08-25）。** UAVScenes 为 33 m 近垂直下视航测数据，
> 无法为薄障碍提供有效监督。本节规则**本身正确**，保留待引入前视/侧视数据集后启用。见 §40.1。

Thin-obstacle evidence is not mature enough to become automatic high-confidence truth.

Every thin-obstacle observation MUST retain:

- soft probability;
- skeleton/centerline;
- local width;
- boundary confidence;
- connected components;
- support-frame count;
- 3D line-fitting residual;
- source model and prompt/class definition.

A single-frame one-pixel detection without cross-frame or geometric support MUST be marked weak evidence or quarantined.

### 14.7 Flyable Space

> ⏸️ **当前数据集不适用（2026-08-25）。** 可飞行空间需前视/侧视几何与航线上下文，
> 近垂直下视无法支撑。本节推导链**本身正确**，保留待前视数据集。见 §40.1。

No 2D segmentation model may directly emit the final `flyable_volume` truth.

```text
2D obstacle / ground / vegetation / sky / water evidence
    -> depth + camera lifting
    -> 3D occupied and uncertain evidence
    -> multi-view fusion
    -> occupancy / free-space representation
    -> UAV radius + clearance + uncertainty inflation
    -> flyable volume / unsafe corridor / bottleneck
```

Final free-space and route values MUST be derived in 3D by deterministic geometry or planning modules.

### 14.8 Expert Output Invariants

All experts MUST preserve:

- original frame, camera, timestamp, and image checksum;
- original image size;
- exact preprocessing homography or resize/crop transform;
- raw and calibrated confidence separately;
- model name, version, commit, checkpoint hash, license, runtime, and precision;
- dense output URI rather than embedding large arrays in metadata JSON;
- separate detection, mask, track, depth, and association confidence values.

No expert prediction becomes ground truth solely because a model emitted it. Fusion MUST retain source-specific confidence, expert disagreement, support views, and failure reason codes.

### 14.9 Cross-view Association

Video mask trackers MUST NOT be treated as complete cross-view ReID systems. Cross-view association SHOULD combine:

```text
appearance embedding
3D centroid / size / orientation
reprojection overlap
class compatibility
temporal gap and reachable-motion constraints
```

Hard merges SHOULD be avoided when evidence conflicts. The initial implementation SHOULD retain a probabilistic association/track graph and record merge/split lineage.

### 14.10 Common Expert I/O Contract

Common expert input MUST include:

```json
{
  "sample_id": "scene_001/cam_02/frame_000123",
  "scene_id": "scene_001",
  "camera_id": "cam_02",
  "frame_id": 123,
  "timestamp_ns": 1723456789000000000,
  "image_uri": "images/cam_02/000123.jpg",
  "image_sha256": "...",
  "original_size": [2160, 3840],
  "camera": {
    "K": [],
    "distortion_model": "opencv",
    "distortion": [],
    "T_world_from_camera": [],
    "coordinate_convention": "x_right_y_down_z_forward"
  },
  "vggt_omega": {
    "depth_uri": "depth/000123.exr",
    "confidence_uri": "depth_conf/000123.exr",
    "model_version": "...",
    "checkpoint_sha256": "..."
  }
}
```

Mask/track observations MUST preserve separate scores:

```json
{
  "observation_id": "obs_123_07",
  "track_id_2d": "track_0042",
  "class_candidates": [],
  "mask": {
    "encoding": "coco_rle",
    "data": "...",
    "mask_score": 0.91,
    "boundary_score": 0.72
  },
  "box_xyxy_original": [120.3, 88.2, 209.5, 164.8],
  "embedding_uri": "embeddings/obs_123_07.npy",
  "occlusion_score": 0.26,
  "is_keyframe_detection": true,
  "provenance": {}
}
```

Flow output MUST include observed flow, uncertainty, forward/backward error, rendered static flow, residual flow, and dynamic probability as separately addressable artifacts.

Lifted 3D instances SHOULD include centroid covariance, velocity covariance, point-support URI, mask confidence, depth confidence, multiview consistency, reprojection IoU, and expert disagreement.

### 14.11 Depth and Scale Taxonomy

Every depth artifact MUST declare exactly one of:

| Type | Meaning | Absolute metric tasks |
|---|---|---|
| `metric` | output is defined in meters, but UAV domain scale bias is still unverified | allowed only after domain calibration/gating |
| `externally_anchored` | scale recovered from RTK/GPS/IMU/altimeter/ToF/LiDAR/known baseline | allowed when anchor provenance and uncertainty pass |
| `relative` | multiplicative scale is unknown | prohibited |
| `affine_invariant` | scale and shift may both be unknown | prohibited |
| `pseudo` | unverified model estimate | weak label or quality signal only |

A model card using the word “metric” MUST NOT be treated as proof of acceptable UAV scale accuracy.

### 14.12 Coordinate and Scale Alignment

Every expert MUST store `H_original_to_model`, crop, padding, camera convention, and alignment version. Expert pixels MUST be transformed back to original-image coordinates before indexing VGGT-Ω rays or points.

Alignment rules:

1. Reliable metric expert plus external metric frame: solve SE(3) with fixed `scale=1`.
2. Relative expert geometry: solve robust Sim(3) using static camera centers and static 3D correspondences.
3. Framewise relative or affine depth: fit log-depth scale or scale+shift only on static, non-sky, non-water, non-reflective regions.
4. Dynamic objects MUST NOT participate in scene alignment.
5. Metric evaluation MUST report raw metric error before any Sim(3) fitting; otherwise scale error is hidden.
6. Loop closure or realignment MUST create a new coordinate/alignment version and MUST NOT silently overwrite prior metadata.

### 14.13 Disagreement and Confidence Calibration

Experts MUST NOT vote directly to create truth. After alignment, compute at least:

- log-depth disagreement;
- scale residual;
- normal-angle disagreement;
- cross-view reprojection error;
- camera translation/rotation residual;
- forward/backward track-cycle error;
- static-region temporal inconsistency;
- RGB/mask/depth-boundary displacement;
- valid/invalid reason conflicts.

Raw model confidence and agreement MUST be calibrated on held-out data into error-event probabilities such as:

```text
P(depth_error < threshold)
P(normal_error < threshold)
P(reprojection_error < threshold)
P(point_is_valid)
```

Calibration MAY use isotonic regression, Platt scaling, conformal calibration, or another validated method. Safety-related confidence SHOULD use a conservative composition such as the minimum of VGGT, expert, agreement, and visibility confidence. Multi-model agreement alone is not ground truth.

**校准 MUST 以场景与成像条件为条件变量，不得拟合一条全局曲线。** 实测（2026-08-25）：

- **场景相关**：同为植被，VGGT-Ω 的 `depth_conf` 中位在 HKisland 为 20.59、
  AMtown 仅 8.54，相差 2.4 倍；
- **光照相关**：同地点同航线、亮度降至 0.25× 时，全场 conf 中位降 35%，
  且**类别间判别力显著坍缩** —— 水面 vs 陆面的 AUC 从 0.865 掉到 0.670，
  四分位距从 6.91 压缩到 1.86。

第二条的含义比第一条严重：置信度不只是**偏移**了，是**信息量变少**了。
因此 `P(depth_error < threshold)` 的映射 MUST 按成像条件分档标定，
且在低照度档位上，**MUST NOT 假定置信度仍能区分失效原因**（§14.5 的原因码
在该档位需要**其他纯视觉机制**交叉指认 —— 估计器分歧、重投影/环路误差、
扰动敏感度、语义先验 —— 不能只靠 conf 推）。
详见 `docs/FINDINGS.md 附录 A`。

**标定数据从哪来（铁律 14）**：标定**本身**需要误差真值，因此 MUST 在一个
T4 数据集（带 LiDAR/RTK）上离线完成**一次**，产出的是**映射函数与其不确定性**；
生产路径上的其他数据集**引用该映射，不重新要求传感器真值**。
迁移时 MUST 声明标定来源域与迁移不确定性 —— 跨域迁移的有效性本身是待验证项。
这是 §40.6「一次性标尺」在本节的具体形式。

### 14.14 Circular-Validation Rules

- WorldMirror without VGGT priors MAY act as an independent evaluation cross-check.
- WorldMirror conditioned on VGGT depth/pose/K is a refiner and MUST NOT be used to prove VGGT correctness.
- WorldMirror outputs MUST NOT be used as Qwen/VLM training metadata under the currently reviewed license; it is inference/evaluation-only pending legal approval.
- MetricAnything and MoGe share architectural lineage and MUST NOT be counted as two independent votes.
- DA3 and VGGT-Ω may share representation/training biases; agreement does not imply independence.
- At least one normal signal SHOULD come from an independent normal estimator such as DSINE rather than only depth-derived normals.

### 14.15 Deterministic Geometry Boundary

Models MAY predict depth, normals, masks, tracks, visibility, embeddings, dynamic probability, and metric-scale priors.

Programs MUST compute:

- depth-to-point transforms；
- ray visibility and occlusion；
- object centroid, robust size, and PCA orientation；
- **平面拟合、坡度、粗糙度、平面度、连通域面积**（C2/C3 的真值来源）——
  **在视觉点云上计算**；角度与比值无需尺度锚，绝对面积需 T3 锚（§40.5 机制 5）；
- **几何自洽测量与失效原因判定**（C1 的真值来源）：多视重投影误差、
  前后向光流环路误差、估计器间分歧、扰动漂移量。**均为纯视觉可复算量**（铁律 14）；
- **跨观测几何差分**（C4；重复航次为可选输入，合成退化为默认路径）；
- cross-frame consistency, expert disagreement, and confidence calibration。

> **2026-08-25 移除**：TSDF/voxel/ESDF occupancy、free/occupied/unknown、clearance、
> reachability、candidate routes、next-best-view information gain、TTC、swept-volume collision。见 §40.1。

**安全相关的坡度、可降落性、深度可信度判定 MUST NOT 由 Qwen 或通用 VLM 直接估计** —— 必须由几何程序计算。
（2026-08-25：原文为 clearance/TTC/collision risk/flyability，已按 §40.1 替换为当前范围内的安全量。）

## 15. 2D-to-3D Lifting and Fusion

Minimum expected flow:

1. Associate every 2D prediction with frame ID and pixel mask/box.
2. Use valid depth and camera parameters to lift pixels to 3D support points.
3. Reject or downweight uncertain depth and boundary pixels.
4. Transform support points into the canonical scene frame.
5. Match instances across views using semantic, appearance, geometry, and visibility constraints.
6. Fuse matched support into a stable entity.
7. Assign immutable entity IDs.
8. Compute geometry primitives and support statistics.
9. Record unresolved conflicts instead of force-merging.

Stable ID namespaces:

```text
<obj_021>    general object
<part_006>   object part
<wire_004>   thin linear obstacle
<region_009> spatial region
<route_002>  candidate route
<track_011>  temporal trajectory
<pose_007>   camera or observer pose
```

IDs MUST be stable within a metadata snapshot. Cross-version ID lineage SHOULD be recorded when entities split or merge.

## 16. Metadata Layers

> ✅ **L0/L1/L2 schema 已于 2026-08-25 冻结**（版本 `0.1.0`）：
> `schemas/l0_geometry.schema.json`、`l1_entities`、`l2_relations`、`metadata_snapshot`。
> 跨层不变量由 `core/metadata.py` 强制（JSON Schema 表达不了的部分）。
>
> **相对本节文字描述的两处实质变化**：
> 1. **新增 `surface` 实体类型** —— C2 可降落性与 C3 地形推理的锚点是平面/表面而非对象，
>    原 L1 列表缺这一类；
> 2. **L2 每条关系强制携带 `derivation.program` 与 `inputs`** ——
>    否则 §23.4 的「派生字段可重算」无从执行。
>
> schema 升版 MUST 提升 `SCHEMA_VERSION` 并记入 CHANGELOG；旧快照据此仍可正确解读。

### L0: Raw Geometry

- camera intrinsics/extrinsics and poses;
- depth and depth confidence;
- XYZ/RGB points;
- normals;
- coordinate frame, unit, scale status/source;
- reprojection error, coverage, density;
- transforms and geometry provenance.

### L1: 3D Entities

- object/part/region/route/track IDs;
- category and attributes;
- centroid, AABB, OBB, size, orientation;
- point/voxel/mesh instance support;
- visible views and occlusion ratio;
- static/dynamic state;
- wire centerline, endpoints, radius;
- planes and surfaces;
- semantic, geometry, and cross-view confidence.

### L2: 3D Relations

- distance and height difference;
- azimuth and elevation;
- observer-relative front/back/left/right/above/below;
- near/intersect/contain/support/connect/hang;
- occludes/visible-from;
- cross-view correspondence;
- topology and connectivity.

### L3: Temporal, Reliability, and Surface Metadata（2026-08-25 重定义）

- **深度可信度与失效原因**（C1）：逐区域 reliable 标志、**自洽测量残差与估计器分歧、
  扰动漂移量**、原因码；
- **表面可降落性属性**（C2）：坡度、粗糙度、平面度、连通面积、语义风险、动态占用；
- **地形量**（C3）：局部地面拟合面、高程统计、坡向；
- **跨时相变化**（C4）：**合成退化响应**、跨观测几何差分、变化类型、表观差异归因；
- visibility coverage；
- scene change。

> **2026-08-25 移除**：3D trajectories/velocity/acceleration、TTC、occupancy and free space、
> reachability、routes and minimum clearance、next-best-view、task preconditions/completion conditions。
> 见 §40.1。

Initial release MUST implement only the L3 fields required by selected tasks.

## 17. Object Contract

```json
{
  "object_id": "<wire_004>",
  "category": "power_line",
  "geometry": {
    "centerline": [[12.4, 8.1, 6.3], [15.7, 9.8, 6.6]],
    "radius_m": 0.012,
    "bbox_3d": [12.4, 8.1, 6.2, 15.7, 9.8, 6.7]
  },
  "visibility": {
    "visible_frames": ["f0012", "f0015"],
    "occlusion_ratio": 0.42
  },
  "confidence": {
    "semantic": 0.81,
    "geometry": 0.74,
    "cross_view_support": 3
  },
  "provenance": {
    "geometry_model": "VGGT-Omega",
    "semantic_model": "EDFNet",
    "source_frames": ["f0012", "f0015", "f0018"]
  }
}
```

## 18. Scene Package

```text
scene_000018/
├── scene.ply
├── scene_manifest.json
├── cameras.json
├── frames.json
├── objects.json
├── relations.json
├── tracks.json
├── navigation.json
├── quality.json
├── provenance.json
├── renders/
│   ├── rgb/
│   ├── depth/
│   ├── normal/
│   ├── semantic_id/
│   ├── instance_id/
│   └── bev/
└── tasks/
    ├── grounding.jsonl
    ├── vqa.jsonl
    ├── caption.jsonl
    ├── dialogue.jsonl
    └── task_decomposition.jsonl
```

`navigation.json` and some render directories MAY be absent in the initial version. Their absence MUST be explicit in `scene_manifest.json`.

## 19. Task Sample Contract

```json
{
  "sample_id": "sample_...",
  "task_type": "3d_vqa.metric_reasoning",
  "task_spec_version": "0.1.0",
  "scene_id": "scene_000018",
  "visual_inputs": ["view_003.jpg", "view_007.jpg"],
  "metadata_inputs": {
    "observer": {},
    "entities": [],
    "geometry_primitives": {}
  },
  "metadata_input_fields": [
    "observer.position",
    "entities.centerline"
  ],
  "hidden_target_fields": [
    "derived.minimum_distance"
  ],
  "question": "Which wire is closest to the UAV?",
  "target": {
    "object_id": "<wire_004>",
    "distance_m": 6.3
  },
  "evidence": {
    "used_entities": ["<wire_004>", "<wire_007>"],
    "used_fields": ["observer.position", "entities.centerline"],
    "derivation_program": "minimum_point_to_polyline_distance"
  },
  "checker": {
    "name": "check_minimum_distance_answer",
    "version": "0.1.0",
    "tolerance_m": 0.1
  },
  "quality": {
    "status": "pass",
    "answer_confidence": 0.88,
    "geometry_confidence": 0.84
  },
  "provenance": {}
}
```

## 20. Task Construction Rules

### 20.1 Program-first tasks

Applicable to grounding, metric VQA, situated relations, topology, correspondence, and many verification tasks.

Required order:

1. Select eligible scene/entity configuration.
2. Compute hidden target deterministically.
3. Record evidence and checker.
4. Construct visible metadata by applying field masks.
5. Verify absence of target leakage.
6. Ask the LLM to naturalize the question or produce the requested structured answer.
7. Validate against the hidden target.

### 20.2 Hybrid tasks

Applicable to caption and dialogue.

Required order:

1. Generate a deterministic structured claim set or dialogue state.
2. Provide only allowed claims/state to the LLM.
3. Generate natural language.
4. Extract or retain structured claims alongside text.
5. Validate factual coverage and unsupported-claim rate.

### 20.3 Model-first constrained tasks

Applicable to 需要模型先给候选、再由程序验证的任务。

> **2026-08-25**：原文列举 task decomposition / plan critique / next-best-view，
> 三者当前无数据支撑（§40.1），已降级为后续目标。本模式**无首批任务使用**，
> 待前视数据集引入后启用。

Required order:

1. Provide explicit entities, goals, constraints, and allowed actions.
2. Generate one or more structured candidates.
3. Validate geometry, preconditions, completion conditions, and constraint conflicts.
4. Accept, repair once, or quarantine.
5. Do not convert an infeasible task into a fabricated feasible plan.

---

# Layer 3. Agent, Skills, Prompts, Validation, and Quality

## 21. Purpose

Layer 3 converts repeatable decision procedures into Skills, compiles task-specific prompts from declarative specifications, validates outputs at every stage, and monitors sample/batch/release quality.

Skills MUST encode reusable workflow and decision rules. Individual prompt wording SHOULD live in versioned templates or task specifications rather than one Skill per task.

## 22. Agent Topology

Initial topology:

```text
Pipeline Orchestrator Agent
├── dataset-registry-manager
├── expert-registry-manager
├── scene-ingestion-validator
├── metadata-quality-gate
├── task-spec-designer
├── task-prompt-compiler
├── task-sample-auditor
└── dataset-quality-monitor
```

The Orchestrator Agent MUST:

- implement a state machine over immutable artifacts;
- pass only task-relevant context to each Skill;
- record transitions, failures, retries, and quarantine reasons;
- enforce hard quality gates;
- stop when required inputs, scale anchors, or provenance are missing;
- never lower quality thresholds to improve throughput;
- never alter a hidden target to match an LLM response.

## 23. Skill Contracts

### 23.1 `dataset-registry-manager`

Input:

- Feishu snapshot or current read-only export;
- prior registry;
- dataset research evidence;
- sample verification reports.

Output:

- normalized dataset cards;
- alias-aware deduplication report;
- verification status;
- phase-selection recommendation.

Hard failures:

- unknown source identity;
- unresolved license when full ingestion is requested;
- dataset alias collision;
- unsupported high-altitude satellite/remote-sensing source.

### 23.2 `expert-registry-manager`

Input:

- expert survey evidence;
- official repository/model-card metadata;
- server profiles;
- license review and UAV validation reports.

Output:

- versioned expert cards;
- enabled/disabled expert set per server profile;
- checkpoint and license manifest;
- scheduling policy;
- compatibility and fallback report.

Responsibilities:

- distinguish code license, weight license, API terms, and derivative-data constraints;
- audit transitive model/dependency licenses rather than only the top-level repository;
- record whether outputs may be used for training, evaluation-only, or quality-control-only;
- record input/output capability and coordinate convention;
- record model lineage/shared-bias groups so correlated experts are not counted as independent votes;
- prevent activation of models without an approved use status;
- preserve A0/A1/B/C research tier separately from deployment approval;
- bind preprocessing, checkpoint hash, runtime precision, and cadence;
- require UAV small-sample evidence before promoting an expert to production.

Hard failures:

- missing or incompatible license;
- unavailable or unverifiable checkpoint;
- undocumented input coordinate transform;
- output that cannot be aligned to frame/camera IDs;
- unrecorded API version or remote-data handling policy.
- output-use restrictions incompatible with the requested training/release purpose;
- unreviewed transitive checkpoint or dependency license.

### 23.3 `scene-ingestion-validator`

Input: raw sample + dataset card + adapter output.

Output: `ingestion_report.json`.

Checks:

- readability;
- timestamp/frame/calibration alignment;
- split leakage;
- required modality presence;
- depth source and metric-scale claim;
- minimum view overlap and reconstruction readiness.

### 23.4 `metadata-quality-gate`

Input: geometry, expert outputs, fused entities, derived metadata.

Output: immutable `metadata_snapshot.json` plus validation report.

Checks:

- JSON/schema validity;
- coordinate system and units;
- ID uniqueness and referential integrity;
- reprojection and cross-view consistency;
- numeric validity of boxes, lines, poses, and tracks;
- support views and confidence;
- provenance completeness;
- recomputability of derived fields;
- known geometry failure signatures.

The gate MUST additionally validate residual-flow construction、invalid-geometry reason masks、
separation of detector/mask/track confidence、以及 **纯视觉自洽测量（重投影/环路误差、
估计器分歧、扰动漂移）的可重算性**。
（2026-08-25：原文末项为 thin-obstacle support evidence，已按 §40.1 替换；
同日第二次修订将「LiDAR-视觉残差」改为纯视觉自洽测量，见铁律 14。）

### 23.5 `task-spec-designer`

Input:

- available scene/metadata capabilities;
- downstream capability taxonomy;
- supervision strength and quality policy;
- target model adapters.

Output:

- versioned Task Specs;
- task capability-coverage matrix;
- 3D-necessity and low-altitude-specificity tests;
- required target/evidence/checker contracts.

Responsibilities:

- design tasks that cannot be solved by ordinary 2D recognition alone;
- bind every target to point-cloud geometry, stable IDs, voxels, routes, tracks, or deterministic spatial programs;
- mark supervision as strong, deterministic-derived, filtered pseudo, weak, or language-generated;
- define task eligibility by scale, visibility, uncertainty, and scene content;
- prevent duplicate task families that test the same capability under different wording;
- keep canonical task annotations independent of Qwen or any single model architecture.

### 23.6 `task-prompt-compiler`

Input: validated metadata snapshot + task spec + prompt template.

Output: `prompt_bundle.json`.

Responsibilities:

- enforce scene eligibility;
- compute hidden target;
- select visual inputs;
- extract the minimal task-local metadata subgraph;
- apply visible/hidden field masks;
- run target-leakage detection;
- bind output schema, checker, tolerance, refusal rules, and retry policy;
- generate primary and repair prompts.

### 23.7 `task-sample-auditor`

Input: prompt bundle + raw model output + hidden target + checker.

Output: validated sample or quarantine record.

Checks:

- schema compliance;
- valid IDs, enums, units, and numeric ranges;
- checker agreement;
- evidence sufficiency;
- ambiguity and solvability;
- target leakage;
- 3D necessity;
- unsupported entities/claims;
- caption claim fidelity;
- dialogue state consistency;
- plan constraint satisfaction.

Repair policy:

```yaml
format_error:
  action: structured_repair
  max_attempts: 1

language_error_with_correct_target:
  action: constrained_rewrite
  max_attempts: 1

geometry_or_evidence_error:
  action: return_upstream_or_quarantine
  max_attempts: 0

retry_exhausted:
  action: quarantine
```

### 23.8 `dataset-quality-monitor`

Input: quality events and validated samples across a run/batch/release.

Output:

- `quality_dashboard.json`;
- drift and failure reports;
- `release_manifest.json` or release block.

The monitor MUST report but MUST NOT autonomously change release thresholds.

## 24. Declarative Task Spec

```yaml
task_id: 3d_vqa.metric.minimum_distance
version: 0.1.0
task_family: 3d_vqa
generation_mode: program_first

required_scene_capabilities:
  scale_status: metric
  geometry:
    - observer_position
    - centerline

visual_input_policy:
  input_type: multi_view_image
  min_views: 2
  selection: support_and_context

metadata_input_fields:
  - observer.position
  - entities.object_id
  - entities.category
  - entities.geometry.centerline

hidden_target_fields:
  - derived.minimum_distance
  - target.object_id

derivation_program: minimum_point_to_polyline_distance
checker: check_minimum_distance_answer
prompt_template: 3d_vqa/metric_v1
output_schema: schemas/3d_vqa_metric_answer.schema.json

leakage_rules:
  forbidden_input_fields:
    - entities.distance_to_observer
    - derived.minimum_distance

quality_requirements:
  minimum_geometry_confidence: 0.80
  maximum_answer_count: 1
  numeric_tolerance_m: 0.10
```

Every Task Spec MUST define:

- why the task requires 3D;
- required scene capabilities;
- visible metadata fields;
- hidden targets;
- target derivation;
- visual input policy;
- output schema;
- checker and tolerance;
- leakage rules;
- refusal/eligibility conditions;
- quality thresholds.

## 25. Prompt Bundle

```json
{
  "prompt_bundle_id": "pb_...",
  "task_spec_id": "3d_vqa.metric.minimum_distance@0.1.0",
  "scene_id": "scene_000018",
  "metadata_snapshot_id": "meta_...",
  "model": {
    "provider": "UNRESOLVED",
    "name": "UNRESOLVED",
    "version": "UNRESOLVED",
    "parameters": {}
  },
  "visual_inputs": [],
  "system_prompt": "...",
  "task_prompt": "...",
  "metadata_context": {},
  "output_schema": {},
  "hidden_target_ref": "target_...",
  "checker": "check_minimum_distance_answer",
  "retry_policy": {
    "max_format_repairs": 1,
    "max_semantic_rewrites": 1
  }
}
```

Every generation prompt MUST state:

1. task role and coordinate-frame convention;
2. allowed visual and metadata evidence;
3. prohibition on inventing objects, relations, units, or scale;
4. ambiguity/insufficient-evidence refusal format;
5. strict output schema;
6. ID, enum, unit, and numeric precision rules;
7. requirement to output auditable evidence references;
8. prohibition on copying example IDs/numbers as current answers.

## 26. Task-Specific Prompt Requirements

### 26.1 3D Grounding

- Return only valid object/part/region/route/track IDs and required scores.
- Candidate metadata MUST NOT mark the target.
- Observer-relative language MUST bind to an explicit observer pose.
- Equal valid candidates MUST produce an ambiguity response.

### 26.2 3D VQA

- Metric questions require metric-scale eligibility.
- Situated questions require observer position, orientation, and axis convention.
- Numeric answers require units and checker tolerance.
- LLM-generated numbers MUST NOT replace deterministic targets.

### 26.3 3D Caption

- Input SHOULD contain a deterministic claim set.
- Output MUST preserve both natural language and structured claims.
- Claims unsupported by metadata and visual evidence are prohibited.

### 26.4 3D Task Decomposition

Each step MUST bind:

- action;
- target ID;
- goal region or waypoint;
- spatial constraints;
- preconditions;
- completion conditions;
- evidence.

Candidate plans MUST pass geometry and rule validation.

### 26.5 3D Dialogue

Every turn SHOULD include:

- dialogue state version;
- currently bound entities;
- observer pose;
- metadata snapshot version;
- unresolved references.

The model MUST ask for clarification when reference resolution is non-unique.

### 26.6 New Tasks

New task families MUST reuse the same compilation interface. Adding a task normally means adding:

```text
task spec
prompt template
output schema
derivation program
checker
quality tests
```

Creating a new Skill is justified only when the workflow or decision procedure differs materially from existing Skills.

## 27. Quality Gates

| Gate | Stage | Hard failure examples |
|---|---|---|
| G0 | Dataset / expert registry and ingestion | unreadable files, unknown source, split leakage, blocking dataset/model license issue |
| G1 | Geometry and expert inference | unknown coordinate frame, conflicting scale claim, unusable reconstruction, missing preprocessing transform |
| G2 | Metadata | broken IDs, missing critical provenance, invalid geometry, unrecomputable derived data, missing reason masks or confidence components |
| G3 | Task design and compilation | failed 3D necessity/low-altitude claim, leaked target, non-unique answer, missing checker, unmet scene capability |
| G4 | Model output | unrepairable schema, nonexistent entity references, invalid units |
| G5 | Sample audit | checker disagreement, insufficient evidence, unsupported claims, failed 3D necessity |
| G6 | Dataset release | excessive leakage/duplicates, distribution failure, dependency tests fail |

Allowed states:

```text
pass
warn
quarantine
reject
```

Hard failures MUST NOT be converted into a weighted quality score. Only gate-passing samples receive soft scores.

## 28. Quality Metrics

### 28.1 Sample Level

- schema validity;
- provenance completeness;
- geometry confidence;
- answer determinism;
- evidence sufficiency;
- target leakage;
- ambiguity;
- 3D necessity;
- visual/metadata consistency;
- language quality;
- uncertainty calibration.

### 28.2 Batch and Release Level

- pass/warn/quarantine/reject rates by gate;
- first-pass schema compliance;
- format-repair and semantic-rewrite rates;
- deterministic checker agreement;
- unsupported-claim rate;
- target-leakage rate;
- ambiguous-sample rate;
- exact and near-duplicate rate;
- task/category/difficulty/scene/scale/source distributions;
- real versus simulated distribution;
- quality drift between versions;
- failures grouped by dataset, model, task spec, prompt version, and reconstruction configuration.

Expert and lifting validation SHOULD additionally track:

- mask AP, mIoU, and boundary F-score;
- **平面拟合残差、坡度估计误差、可降落区 IoU**（C2/C3）；
- **深度可信度判定的 AUC 与失效原因分类准确率**（C1）；
- tracking J&F, HOTA, IDF1, and ID switches;
- optical-flow EPE, forward/backward error, and ego-compensated dynamic IoU;
- lifted-point purity/completeness, cross-view 3D IoU, and reprojection IoU;
- depth disagreement, normal angular error, and scale drift;
- confidence calibration using ECE, Brier score, NLL, AUSE, and risk-coverage/AURC;
- latency, peak memory, FPS, joules/frame, temporary disk, final metadata bytes/frame, video-minute cost, and failure-retry rate.

## 29. 3D 增益评估（3D Lift Evaluation，2026-08-25 重定位）

> **本节由「事后验证」升格为任务准入的操作性判据**（铁律 5 修订）。
> 原标题为 3D Dependency Evaluation —— 「依赖」暗示 0/1，
> 而实际要衡量的是**增益**。

Every initial task family MUST be evaluated under:

```text
2D-only
metadata-only
2D+metadata
metadata field masking
metadata shuffle
spatial counterfactual
occluded or weak-visual-evidence subset
```

### 29.1 3D 增益的定义与准入线

对同一批样本、同一个模型：

```text
lift = score(2D + 3D metadata) − score(2D only)
```

**准入要求（MUST）：**

- `lift` **MUST > 0 且统计显著** —— 报告置信区间，**不得只报点估计**；
- `lift` 的数值 MUST 记入该任务在 §52 的「衡量指标」一栏；
- **`lift ≈ 0` 的任务 MUST NOT 进 Release** —— 它没有证明 3D metadata 起了作用，
  哪怕它看起来很像 3D 任务。

### 29.2 光有 lift 还不够：MUST 排除三种伪增益

| 伪增益 | 表现 | 排除手段 |
|---|---|---|
| **泄漏** | metadata 里直接含答案或等价派生量 | 铁律 6 + `task_adapters/base.py` 的运行时扫描 |
| **蒙对** | metadata 只是提示了答案的格式或取值范围 | **metadata shuffle** —— 打乱后 lift 应当消失 |
| **无关增益** | 任何额外 token 都能提分（长度效应） | **metadata field masking** —— 只屏蔽相关字段，lift 应当**选择性**消失 |

Claims that the model uses 3D metadata require both:

1. `2D+metadata` improves over `2D-only` on the task；
2. Shuffling, masking, or counterfactually changing relevant metadata produces
   predictable degradation or answer changes。

**第 2 条是关键**：只有 lift 而没有「打乱后 lift 消失」，无法区分真增益与伪增益。

### 29.3 与「2D 绝对做不到」的关系

**不要求任务对 2D 不可解**（铁律 5 修订说明）。

**唯一的真例外**是**信息确实不在像素里**的情形：米制尺度锚来自
EXIF / GPS / 飞控日志 / 气压高度（§40.5 机制 5 的 T3 档），
这类信息**不在图像信息内容之中**，纯图像模型无从获知。

**C3-b（绝对米制）因此是本项目里少数真正 2D-不可解的任务。**
这是加分项，**不是门槛** —— C1、C2、C3-a、C4 都不满足这一条，
它们靠的是可测量的增益。

## 30. Artifact Lineage

Recommended immutable artifacts:

```text
run_manifest.json
dataset_card.yaml
sample_manifest.json
scene_manifest.json
ingestion_report.json
geometry_manifest.json
metadata_snapshot.json
metadata_validation_report.json
task_spec.yaml
prompt_bundle.json
raw_model_output.json
validated_sample.json
quality_event.jsonl
quality_dashboard.json
release_manifest.json
```

Every artifact MUST include:

- artifact ID and schema version;
- parent artifact IDs;
- dataset, scene, split, and run IDs;
- code/model/schema/task/prompt versions;
- creation timestamp and runtime profile;
- input checksums or content digests;
- state, error codes, warnings, and retry history.

Repair and regeneration MUST create new artifacts. Silent overwrite is prohibited.

## 31. Orchestrator State Machine

```text
REGISTERED
  -> SAMPLE_VERIFIED
  -> INGESTED
  -> GEOMETRY_READY
  -> EXPERT_OUTPUTS_READY
  -> METADATA_FUSED
  -> METADATA_VALIDATED
  -> TASK_COMPILED
  -> MODEL_OUTPUT_READY
  -> SAMPLE_VALIDATED
  -> RELEASE_CANDIDATE
  -> RELEASED

Any stage
  -> QUARANTINED
  -> REJECTED
```

Transitions MUST require the preceding gate report. A state label alone is not sufficient.

## 32. Recommended Repository Layout

```text
3D-data-Gen/
├── DESIGN.md
├── DECISIONS.md
├── docs/
│   ├── architecture.md
│   ├── quality-policy.md
│   └── server-profiles.md
├── registry/
│   ├── datasets/
│   ├── feishu_snapshot/
│   └── selection/
├── agents/
│   └── pipeline-orchestrator/
├── skills/
│   ├── dataset-registry-manager/
│   ├── expert-registry-manager/
│   ├── scene-ingestion-validator/
│   ├── metadata-quality-gate/
│   ├── task-spec-designer/
│   ├── task-prompt-compiler/
│   ├── task-sample-auditor/
│   └── dataset-quality-monitor/
├── adapters/
├── geometry/
├── experts/
├── fusion/
├── metadata/
├── task_specs/
│   ├── grounding/
│   ├── vqa/
│   ├── caption/
│   ├── task_decomposition/
│   ├── dialogue/
│   └── new_tasks/
├── task_adapters/
│   ├── qwen_2d_metadata/
│   ├── pointcloud_native/
│   └── multimodal_3d/
├── prompt_templates/
├── schemas/
├── checkers/
├── configs/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   └── integration/
└── scripts/
```

Do not scaffold the entire tree before the first vertical slice requires it.

## 33. Local Control Plane vs Server Execution Plane

### Local Control Plane

MUST own:

- specifications and Skills;
- schemas and Task Specs;
- prompt templates and checker contracts;
- quality thresholds and release rules;
- synthetic fixtures and contract tests;
- versioned server configuration bundles.

### Server Execution Plane

MUST own:

- dataset download/cache;
- VGGT-Ω and expert inference;
- 2D-to-3D lifting/fusion;
- configured Qwen calls;
- large-scale deterministic validation;
- metrics aggregation, quarantine, and release candidates.

The design MUST NOT hard-code local paths, server secrets, API keys, GPU models, or a specific scheduler. These belong in server profiles or secret management.

## 34. Initial Vertical Slice

Recommended default if the user does not override:

```yaml
datasets:
  count: 1
  type: real_multiview
  selection: UAVScenes                # RESOLVED 2026-08-24

scale_policy:
  metric_required: true               # RESOLVED 2026-08-24
  ineligible: [relative, affine_invariant, pseudo]

metadata_scope:
  layers: [L0, L1, minimal_L2]
  entities: [object]
  required_geometry: [camera, depth, point_cloud, centroid, obb, visibility]

task_scope:                            # Release A，见 §51
  - 3d_grounding.object
  - 3d_vqa.metric_or_situated
  - cross_view_correspondence          # RESOLVED 2026-08-24
# Release B（§40.3 的 C1–C4）在 Release A 跑通后接入，
# 其中 C1 感知可信度为最高优先级

evaluation:
  - 2d_only
  - metadata_only
  - 2d_plus_metadata
  - metadata_shuffle

expert_scope:
  instance_masks: Grounded-SAM-2
  tracking: SAM-2.1-BasePlus
  optical_flow: SEA-RAFT
  invalid_region_semantics: OneFormer
  uav_semantics: CABiNet-MobileNetV3-Small
  primary_geometry_cross_check: MoGe-3-ViT-L-after-license-confirmation
  independent_normal_cross_check: DSINE-after-license-confirmation
  secondary_depth_pose_cross_check: DA3-1.1-Apache-compatible-variant
  point_track_visibility: CoTracker3-noncommercial-research-only
  cross_view_embedding: DINOv2-Small-or-Base
  deterministic_geometry: TSDF-voxel-ESDF-raycast
```

Vertical-slice order:

1. Freeze IDs, artifact states, minimal schemas, and error codes.
2. Implement one dataset adapter over 1–3 scenes.
3. Run VGGT-Ω and produce geometry diagnostics.
4. Activate the minimum expert set only after license/checkpoint review.
5. Generate masks, tracks, residual-flow evidence, invalid-region masks, and MoGe-3 keyframe geometry cross-checks.
6. Lift/fuse masks into stable object-level metadata.
7. Implement deterministic geometry functions and checkers.
8. Define three Task Specs.
9. Compile prompt bundles without invoking Qwen.
10. Validate leakage and checker reproducibility.
11. Invoke Qwen on a small batch.
12. Audit samples and run dependency baselines.
13. Add DSINE only after testing whether independent normals provide measurable information gain.
14. Evaluate DA3-1.1 disagreement calibration; add DA3-Streaming only for long-video scope.
15. Only then consider Trace Anything、WorldMirror evaluation、或 §40.3 的 C1–C4 能力扩展。
    （2026-08-25：thin-obstacle expansion 降级为后续目标，需前视数据集，见 §40.1。）

## 35. Implementation Stop Conditions

Claude Code MUST stop and request direction when:

- the initial dataset is not selected and implementation would become dataset-specific;
- metric-scale policy is required but unresolved;
- a license condition blocks the intended use;
- the configured Qwen deployment mode is required but unresolved;
- a schema change would invalidate user-confirmed invariants;
- a quality threshold must be lowered to make progress;
- a task lacks a deterministic or independently auditable target;
- the proposed action would modify Feishu, existing Obsidian notes, or project-governance files outside explicit authorization.

## 36. Unresolved Decisions

```yaml
initial_dataset_selection: UAVScenes          # RESOLVED 2026-08-24; single real multi-view dataset
metric_scale_policy: metric_required          # RESOLVED 2026-08-24; relative-scale scenes are ineligible in v1
initial_task_selection:                       # RESOLVED 2026-08-24
  - 3d_grounding.object
  - 3d_vqa.metric_or_situated
  - cross_view_correspondence
qwen_deployment:
  provider: DEFERRED                          # RESOLVED 2026-08-24: compile-only phase, no model invocation
  model: DEFERRED
  api_or_local: DEFERRED
  budget: DEFERRED
  note: >
    Vertical-slice steps 1-10 (through leakage and checker-reproducibility validation)
    require no model call. Revisit before step 11.
independent_llm_judge: not_in_v1              # deterministic checkers only
quality_thresholds: spec_defaults_pending_calibration
human_audit_ratio: 1.0                        # first batch fully human-reviewed
server_orchestration_framework: none          # scripts + file-based state machine
final_primary_deliverable:
  options: [dataset, benchmark, trained_model, pipeline_toolchain]
  selection: pipeline_toolchain_plus_small_benchmark   # provisional; revisitable after Release A
```

Resolution provenance: the four blocking items were decided by the user on 2026-08-24; see
`DECISIONS.md` §19. The remaining entries are working defaults, not user-confirmed
invariants, and MAY be revised with a recorded reason.

## 37. Evidence Boundaries

- External fact verification cutoff: 2026-08-23.
- The 22 candidate datasets were researched but not all downloaded or fully validated.
- License, current download availability, file inventory, aliases, versions, and redistribution rights MUST be rechecked before ingestion.
- VGGT-Ω performance on target UAV scenes, thin structures, dynamic objects, weak textures, and large-scale blocks remains empirical.
- Two 2026-08-23 expert surveys reviewed official assets but downloaded no checkpoints and performed no local UAV tests.
- The semantic chain remains Grounded-SAM-2/SAM 2.1/SEA-RAFT/OneFormer/CABiNet; the revised geometry priority is MoGe-3 first, DSINE for independent normals, DA3-1.1 for secondary depth/pose/scale checks, and DA3-Streaming only for long-video scope.
- WorldMirror is restricted to inference/evaluation under the currently reviewed license and MUST NOT supply Qwen/VLM training metadata.
- MoGe, DSINE, CoTracker3, Trace Anything, MASt3R, WorldMirror, DA3 variants, and transitive dependencies all require per-checkpoint license review before activation.
- Thin-obstacle, small-aerial-target, dynamic-geometry, and attribute experts are especially dependent on domain validation.
- No claim of zero dataset-search omissions is allowed.

## 38. Primary External Components

```yaml
vggt_omega:
  repository: https://github.com/facebookresearch/vggt-omega
  project: https://vggt-omega.github.io/
  paper: https://arxiv.org/abs/2605.15195

depth_anything_3:
  repository: https://github.com/ByteDance-Seed/Depth-Anything-3

moge_3:
  repository: https://github.com/microsoft/MoGe

dsine:
  repository: https://github.com/baegwangbin/DSINE

cotracker_3:
  repository: https://github.com/facebookresearch/co-tracker

trace_anything:
  repository: https://github.com/ByteDance-Seed/TraceAnything

metric_anything:
  repository: https://github.com/metric-anything/metric-anything

hunyuan_worldmirror:
  repository: https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

hy_world_2:
  repository: https://github.com/Tencent-Hunyuan/HY-World-2.0

qwen_3_5:
  documentation: https://help.aliyun.com/zh/model-studio/qwen3-5-plus
```

These URLs are references, not authorization to download, install, or execute components.

---

# Layer 4. Downstream Task Design and Capability Completion

## 39. Purpose

Layer 4 turns the scene package into high-quality downstream supervision. It is the product layer of the pipeline, not an optional language-generation appendix.

The canonical task representation MUST be model-independent. The same task record SHOULD support:

```text
Qwen adapter
    input: 2D images/video + task-local 3D metadata

Native point-cloud adapter
    input: point cloud/voxel/mesh + point/object/route targets

Multimodal 3D adapter
    input: point cloud + images/video + cameras + metadata
```

Qwen still MUST NOT consume raw point clouds in the current architecture. Point-cloud references remain part of the canonical annotation so future 3D models can use the same data.

## 40. Capability Objective（2026-08-25 重定义）

### 40.1 重定义的依据

首批数据集 UAVScenes 实测：**相机近垂直下视，俯角中位 87.6°（范围 84.6–88.8°），
对地约 33 m**。这是航测/测绘飞行，相机**永远看不到飞行方向前方**。

由此产生的硬约束：

| 原设想能力 | 在本数据集上的可行性 |
|---|---|
| 前向避障、通道净空、航迹可行性 | ❌ 相机几何不支持 —— 看不到前方 |
| 薄障碍（电线/细枝）避让 | ❌ 33 m 下视，且它们不在航线上 |
| TTC / 动态碰撞风险 | ❌ 无前视，动态目标稀少且像素占比极小 |
| Next-best-view / 主动感知 | ❌ 航测航线预先规划，无主动视角决策 |
| 有人驾驶飞机、鸟类避让 | ❌ 数据中不存在 |

**MUST NOT** 在本数据集上生成上述任务。强行生成会产出「形似导航训练数据、
实则无效监督」的样本，训练出虚假能力，违反铁律 5。

> ### ⚠ 「不生成任务」≠「不准备提取能力」（2026-08-25 用户指出，本节原先没说清）
>
> 上表说的是**在本数据集上不生成这些任务**。它**不意味着**这些能力不重要，
> 也**不意味着**相关专家模型要等到拿到前视数据集才开始准备。用户原话：
>
> > 「作为点云理解模型，这种能够识别出细线、能够感知到飞行器的能力是需要的。
> > 由于数据集的局限，我们可能不在这个数据集中采集这些数据，但是在准备 pipeline
> > 材料的时候得考虑可能需要在别的数据集下实现这两个下游功能，
> > 所以需要下载测试一些相关专家模型。」
>
> **因此把两件事分开门禁**：
>
> | | 是否受数据集限制 | 现在做不做 |
> |---|---|---|
> | **生成**导航类任务样本 | **受限** —— 本数据集无有效监督 | ❌ 不做（铁律 5） |
> | **准备**相应的专家模型（许可核验、部署、实测） | **不受限** | ✅ **现在就做** |
>
> **为什么不能等**：许可核验与部署验证**会失败**，而且失败得很隐蔽。
> 本项目已踩过三次 —— `DA3NESTED-GIANT-LARGE` 是 `cc-by-nc-4.0`（同仓库不同权重许可不同）、
> OneFormer 静默加载错误、SEA-RAFT 权重不在 HF。
> 等拿到数据集才发现细线专家不可用，等于把两件本可并行的事**白白串行**。
>
> 按 §0.3 的反向证成规则，这些专家模型指得出它们服务的下游能力
> （R-30 薄障碍、R-34 动态碰撞风险），**因此它们的存在是被证成的**，
> 只是消费方还在 backlog 里。专家准备清单见 §46.6。

### 40.2 新的能力范围

设计原则**不是**「无人机需要什么能力」，而是
**「哪些能力的监督信号极难获得，而纯视觉管线恰好能可靠产出」**。

三种难获取的监督形态，及其**纯视觉**的产出路径（铁律 14）：

| 监督形态 | 为何难获取 | 纯视觉如何产出 |
|---|---|---|
| **与外观矛盾的答案** | 需要能反驳视觉表象的证据 | 多视几何的**可复算测量**：重投影误差、光流环路误差、多估计器分歧。这些能反驳单帧外观，且不需要外部传感器 |
| **外观相同但答案不同** | 需要位姿做反事实 | SfM/VGGT-Ω 的相对位姿（自洽即可，无需 RTK）；跨视角同一性在任何单调深度变换下保持 |
| **无外观对应物的数值** | 需要几何量 | **无尺度几何量**：坡度（角度）、共面性、序数高低、平整度比值 —— 均在均匀缩放下不变，不需要米制锚 |

模型在图像-答案对上训练时会学到「外观→答案」的捷径。**凡是捷径能解决的能力都不缺数据；
凡是捷径会给出错误答案的能力，才是真正的空白。**

> **2026-08-25 修正**：本表原先三行分别写「LiDAR 米制真值残差」「RTK 验证过的位姿」
> 「LiDAR + 标定」。那是把方法绑死在特殊传感器上，违反铁律 14，已按纯视觉重写。
> 传感器真值的正确用途见 §40.6。

### 40.3 四类目标能力（按优先级）

> **2026-08-25 第二次修正**：本节四类能力原先均以 LiDAR 真值定义 target，违反铁律 14。
> 以下为按纯视觉重新推导的版本。产出机制的细节见 §40.5，传感器真值的新角色见 §40.6。

#### C1 感知可信度与失效归因（最高优先级）

模型须判断**当前区域的视觉深度是否可信，以及不可信的原因**，而非强行给出一个深度。

**C1 是最契合纯视觉管线的能力，理由是结构性的**：对其他所有能力，
「提取出的 3D 是错的」是需要压制的噪声；**对 C1，它就是训练信号本身**。
要模型学的正是「视觉三维在哪里会失效」，那么提取器的失效模式就是标注来源。
**教师犯错不污染数据，教师犯错就是数据。**

失效标注的三条纯视觉产出路径（详见 §40.5 机制 4）：

| 路径 | 做法 | 产出的 target |
|---|---|---|
| **扰动法** | 调暗/模糊/加噪/抽视角 → 重新提取 → 测几何漂移 | 该区域几何的**脆弱度** |
| **分歧法** | VGGT-Ω / MoGe / DA3 等独立估计器互相比对 | 分歧区域 + 分歧幅度 |
| **自洽违反** | 多视重投影误差、前后向光流环路误差、静态区时间不一致 | 违反自洽的区域 + 违反量 |

三者都是**可复算的测量**，不是模型观点，因此 checker 能独立重算（铁律 7）。

- 天然大样本：HKisland 约 40% 水面、HKairport 约 52% 均质硬化面 ——
  但**这只是恰好方便，不是必要条件**。任何低空数据集都有弱纹理区与反射面；
- 失效原因必须分别保留（§14.5）：`water`、`reflection_or_transparency`、
  `low_depth_confidence`、`sky`、`reprojection_inconsistent`、纹理缺失。
  **原因码 SHOULD 由不同机制交叉指认**（如：语义提示水面 + 分歧大 + 扰动敏感），
  单一机制不足以定原因。

**已实测支撑**（`docs/FINDINGS.md 附录 A`，全程未用 LiDAR）：
水面 `depth_conf` 与陆面分布基本分离（AUC 0.865）；扰动（亮度降至 0.25×）后
判别力坍缩到 AUC 0.670。**后者正是扰动法的一次完整演示。**

这对应社区调研的头号诉求：飞手最怕的不是损失飞机，而是**不知道系统当前状态是否可信**。

#### C2 安全降落区评估

**垂直下视正是评估降落区的视角。**

真值来源按是否需要尺度锚分开 —— **核心几何量不需要**：

| 量 | 尺度依赖 | 纯视觉可得性 |
|---|---|---|
| **坡度（角度）** | **无** —— 角度在均匀缩放下不变 | ✅ 点云局部平面拟合即可 |
| **平整度/粗糙度比值** | 无（取残差 RMS 与局部尺寸之比） | ✅ |
| **共面性、台阶存在性** | 无（仿射下保持） | ✅ |
| 连通可降落**面积（m²）** | **有** | ⚠️ 需 T3 尺度锚（§40.5 机制 5） |
| 语义表面类型 | 无 | ✅ 分割模型（观点，只用于筛选与联合判断） |
| 可信度联动 | 无 | ✅ 来自 C1 |

> **纠正一处此前的错误**：§46.2 原写「坡度由 LiDAR 确定性计算」。
> **坡度是无尺度量**，视觉点云在尺度未知时依然给出正确角度。
> C2 的核心判据因此**不阻塞于任何传感器**。

核心判据是「平坦 ≠ 可降落」：水面平、车顶平、人群上方也平。必须几何与语义联合判断。
**且深度不可信区域 MUST NOT 判为可降落** —— 这是 C1 与 C2 的强耦合点。

#### C3 地形与高度推理（分档）

垂直下视图像**几乎不提供深度线索** —— 同色的屋顶与地面在 nadir 视角下外观相近。
因此这类任务 3D 必要性最强：**答案与外观几乎无关**。

按尺度锚拆成两档（用户 2026-08-25 决定：**按尺度锚分档保留，默认走 GPS/EXIF**）：

| 档 | 目标形态 | 尺度锚 |
|---|---|---|
| **C3-a（默认，任何数据集）** | 序数与比值：「哪个更高」「高差是这段距离的几倍」「起伏幅度排序」 | 不需要 |
| **C3-b（T3 及以上）** | 绝对米制：两点高差（米）、结构对地高度（米） | GPS/EXIF 相对高度或更强的锚 |

C3-a **MUST** 在所有数据集上可产；C3-b 由 `metric_task_eligible` 资格机制自动门控 ——
无锚的数据集**静默降级为 C3-a，而不是报错或伪造米制值**（铁律 9）。

#### C4 成像退化鲁棒与跨时相变化

**核心机制改为合成退化，不再依赖配对拍摄**（铁律 14）：
对同一场景施加可控退化（调暗、降对比、模糊、加噪、抽视角）后重新提取几何，
考察答案与置信度的变化。**任何数据集都能做，不需要重复航次。**

三层任务形态，难度递增：

1. **一阶**：退化后模型是否改口说「不确定」；
2. **二阶**：模型是否知道**自己的不确定性估计在退化下也不可靠** ——
   实测发现置信度的判别力会坍缩（AUC 0.865→0.670），
   这对应飞手的真实诉求「系统说它有把握，这个把握本身可信吗」；
3. **跨时相**（需重复航次，非必需）：区分**真实三维变化**与**仅由光照造成的表观差异**。

**真实配对拍摄的新角色**：`*_GNSS_Evening` 与日间航次不再是数据来源，
而是**检验合成退化是否像真实退化**的对照组。若合成退化下的置信度响应与
真实日/暮对照一致，则合成退化可信，可推广到无配对数据的数据集。

配对**若要使用**，MUST 同时约束三项：绝对坐标质心距离（航线一致）、
图像亮度比（退化真实存在）、相机基线（两侧都有足够视差）。
**仅按航次名配对是错的** —— `_Evening` 内部有 4 倍亮度梯度，17:43 段比日间还亮，
只有 18:00 后才真暗（实测详见 `docs/FINDINGS.md 附录 A` §7）。

### 40.4 保留但当前不适用

§14.6（薄障碍证据规则）与 §14.7（可飞行空间推导链）**规则本身正确**，
只是本数据集不提供相应输入。引入前视/侧视数据集后**应当**启用，届时无需重写。

### 40.5 从不可靠的 3D 提取得到可靠 target 的五条机制

> 铁律 14 允许提取结果不准。本节是**应对不准的方法论** ——
> 所有 target 设计 MUST 说明自己依赖其中哪一条。

#### 机制 1：区分「测量」与「观点」

| | 例子 | 能否自查 |
|---|---|---|
| **观点** | 单目深度值、语义类别、检测框 | 不能。一次前向，无第二个说法 |
| **测量** | 多视重投影误差、光流环路误差、静态区时间一致性、光度一致性、估计器间分歧 | **能**。同输入可复算，且在数据内部即可证伪 |

**target MUST 优先从「测量」推导；「观点」MAY 用于筛选样本，MUST NOT 单独定义答案。**
这是铁律 7 在纯视觉前提下的具体化。

#### 机制 2：序数/关系目标优于米制目标

视觉深度误差以**尺度与低频偏置**为主。在未知单调（或仿射）变换下：

| 目标形态 | 是否幸存 |
|---|---|
| 绝对距离「多少米」 | ❌ 被摧毁 |
| 序数「A 比 B 近/高」 | ✅ |
| 共面性 | ✅（仿射下） |
| **坡度（角度）** | ✅ **均匀缩放下不变** |
| 相对平整度比值 | ✅ |
| 遮挡次序 | ✅ |
| 跨视角同一性 | ✅ |

**把目标从「多少米」改成「哪个更近/更高/更平/是否共面/谁遮挡谁」，
误差的主要成分被直接消掉。** 而在近垂直下视里这些量**仍然没有外观对应物**，
3D 必要性不降反升。这是本项目最重要的设计杠杆。

#### 机制 3：一致性做筛子，不做真值

多估计器 + 几何自检：一致 → 保留样本；分歧 → 丢弃，或转给机制 4 当失效标注。

**一致性决定「保留哪些样本」，不决定「答案是什么」**（§14.13 已有此原则）。
代价是覆盖率下降。**丢弃比例 MUST 记录并公布**，不得静默截断 ——
静默截断会让读者以为覆盖是完整的。

#### 机制 4：失效即标签

见 C1。扰动法、分歧法、自洽违反三条路径均为纯视觉、可复算。

#### 机制 5：尺度分档，而非尺度必需

米制需要外部锚。按在真实低空数据集里的**可得性**排序：

| 档 | 锚 | 可得性 | 解锁 |
|---|---|---|---|
| T0 | 无序图像 | 总是 | 单帧任务，几乎不产 3D 题 |
| T1 | 视频/有序序列 | 常见 | SfM 相对位姿、时间一致性、自洽测量 |
| T2 | + 相机内参 | 常见（EXIF 常含） | 更好的几何、正确的角度量 |
| **T3** | **+ GPS/EXIF 相对高度或气压高度** | **近乎普遍** | **绝对米制（C3-b、面积 m²）** |
| T4 | + RTK / LiDAR / 控制点 | 罕见 | **仅用于验证与标定，见 §40.6** |

**默认目标档位是 T3。** 数据集达不到某档时，`metric_task_eligible` 等资格字段
自动关闭对应任务（已有机制，见 §41、`core/enums.py`），**降级 MUST 是静默降级 + 记录原因**，
不得伪造米制值。

### 40.6 传感器真值（LiDAR/RTK）的新角色：一次性标尺

**LiDAR 与 RTK MUST NOT 出现在生产路径上**（铁律 14）。它们的唯一用途是**离线标定与验证**：

1. **测量纯视觉管线到底错多少** —— 在一个 T4 数据集上比对，得到误差分布；
2. **标定自报置信度** —— 把原始 `depth_conf` 映射到 `P(depth_error < threshold)`（§14.13）；
3. **验证合成退化的真实性** —— 合成退化的响应是否与真实日/暮对照一致（C4）。

产出物是**一份带误差棒的验证报告**，不是训练数据。之后每个数据集走纯视觉路径，
**带着一个已测量过的误差率**。

> **为什么这样更有价值**：一个 LiDAR 派生的语料库只是一个数据集；
> **一套纯视觉管线 + 实测误差刻画，是别人能在自己数据上跑的方法。**
> 本项目的交付物定位为后者。
>
> 直接后果：**M-008（相机-LiDAR 外参）从阻塞项降为非阻塞项** ——
> 它卡的是验证报告，不是数据生产。生产可以立即推进。


## 41. Canonical Task Record

```json
{
  "sample_id": "task_sample_...",
  "task_spec_id": "uav.reliability.depth_trustworthiness@0.1.0",
  "scene_id": "scene_000018",
  "capability_tags": ["perception_reliability", "failure_attribution"],
  "low_altitude_tags": ["nadir_view", "water_surface"],
  "supervision_level": "deterministic_derived",
  "inputs": {
    "pointcloud_ref": "scene.ply",
    "visual_inputs": ["f0012.jpg"],
    "camera_refs": ["<pose_007>"],
    "metadata_snapshot_id": "meta_...",
    "visible_metadata_fields": []
  },
  "hidden_target": {
    "target_type": "depth_reliability",
    "region_id": "<region_009>",
    "reliable": false,
    "failure_reason": "water",
    "lidar_vision_residual_m": 4.82
  },
  "target_geometry": {
    "region_point_indices_ref": "indices/region_009.bin",
    "lidar_reference_ref": "lidar/f0012.npy"
  },
  "evidence": {
    "used_entities": ["<region_009>"],
    "used_fields": [],
    "derivation_program": "lidar_vision_depth_residual_with_reason"
  },
  "checker": {
    "name": "check_depth_reliability",
    "version": "0.1.0",
    "residual_threshold_m": 1.0
  },
  "quality": {},
  "provenance": {},
  "adapters": ["qwen_2d_metadata", "pointcloud_native", "multimodal_3d"]
}
```

> **2026-08-25**：本示例原为 `uav.route.minimum_clearance`（航迹净空），
> 该任务族当前无数据支撑（§40.1），示例改为 C1 感知可信度。原任务族保留为后续目标。

Every target MUST map to at least one concrete 3D anchor:

- point indices or point mask；
- object/part ID and OBB；
- surface / plane fit（地面、屋顶、水面 —— 可降落性与地形推理的锚点）；
- **region 区域**（voxel 或点集，如可降落区、深度不可信区）；
- camera/observer pose；
- deterministic spatial relation over these anchors。

> **2026-08-25 移除**：centerline（薄结构）、3D trajectory、route/waypoint graph。见 §40.1。

## 42. Supervision Levels

```text
strong
    native sensor, manual annotation, RTK/LiDAR/GCP, or verified ground truth

deterministic_derived
    computed from gate-passing geometry by a versioned program

filtered_pseudo
    VGGT-Ω/expert output passing confidence and multiview checks

weak
    model proposal, uncertain thin structure, attribute, or relation candidate

language_generated
    natural-language realization whose structured claims/target are independently checked
```

Strong and deterministic-derived labels SHOULD form evaluation data. Filtered-pseudo and weak labels SHOULD primarily form training data unless manually reviewed.

## 43. Task Design Invariants

Every Task Spec MUST pass:

### 43.1 3D Necessity

At least one condition MUST hold:

- target requires metric/relative 3D geometry;
- target is anchored to point-cloud entities not uniquely identifiable from one 2D view;
- answer changes under camera-pose or spatial counterfactual while appearance remains similar;
- task requires cross-view、occlusion、topology、**地形几何**、或**独立真值与视觉的分歧**信息；
- a 2D-only baseline is demonstrably insufficient on the selected subset.

### 43.2 Low-Altitude Specificity（2026-08-25 重定义）

Each low-altitude-specialized task MUST use at least one of：

- **UAV 位姿、对地高度与近垂直下视几何**（俯角、飞行高度、地面采样距离）；
- **视觉几何的自洽违反与估计器分歧区域**，含其失效原因码
  （纯视觉可复算；2026-08-25 由「与独立真值 LiDAR 的分歧」改写，见铁律 14）；
- **航拍表面的可降落性属性**：坡度、粗糙度、平面度、连通面积、语义风险、动态占用；
- **米制地形量**：高差、起伏幅度、结构相对地面高度 —— 这些在 nadir 视角下无外观对应物；
- **同地点跨航次/跨时段的重复观测**（`*_GNSS` 与 `*_GNSS_Evening` 变体）；
- **航测视角特有的弱深度线索**：低深度起伏、同色平面歧义、阴影与反射。

**MUST NOT** 再以下列信号主张低空特性（当前数据集无法支撑，见 §40.1）：
薄障碍、可飞行体积、飞行走廊净空、航迹可达性、ego-motion 补偿后的动态风险、
主动视角/Next-best-view。

### 43.3 Verifiability

- target MUST be recomputable or linked to independently reviewed ground truth;
- target MUST NOT appear in visible metadata;
- ambiguity MUST be represented explicitly;
- scale eligibility MUST be enforced;
- evidence and checker MUST be versioned;
- point-cloud/voxel/route target mapping MUST be valid;
- uncertain geometry MUST support `unknown`, interval, or refusal targets.

## 44. Task Family A: Native 3D Perception

| Task | Input | Target | Low-altitude contribution |
|---|---|---|---|
| 3D semantic segmentation | point cloud/voxel | point-wise semantic IDs | 航拍地表、屋顶、植被、水面、硬化面 |
| 3D instance segmentation | point cloud + optional images | instance point masks and stable IDs | 大视角变化下的稀疏对象 |
| 3D object detection | point cloud/multimodal | centroid, size, orientation, OBB | 俯视视角的建筑、车辆、地面结构 |
| Surface/region parsing | cloud/mesh | 地面、屋顶、立面、植被、水面、unknown | 航拍场景布局与可降落性的输入 |
| 3D tracking | point cloud sequence + cameras | trajectory, visibility, velocity, covariance | 数据中动态目标稀少，**首批不做** |

> **2026-08-25 移除**：Thin-structure extraction（电线/缆索/细枝的 centerline 与连通性）。
> 33 m 近垂直下视无法提供有效监督，且这些结构不在航线上。规则保留在 §14.6 待前视数据集。

## 45. Task Family B: 3D Spatial and Viewpoint Reasoning

| Task | Required metadata | Target/checker |
|---|---|---|
| Metric measurement | metric scale, object geometry, pose | 距离/尺寸/高度/角度 + 容差 |
| Observer-relative relation | observer pose, object centers/OBBs | left/right/front/behind/above/below |
| Structural topology | objects, surfaces | connect/intersect/contain/support |
| Visibility and occlusion | cameras, depth, object geometry | 可见比例、遮挡者 ID |
| Cross-view correspondence | masks, cameras, point support, embedding | same-object link + probability |
| Viewpoint transformation | two observer poses, object geometry | 变换后的 situated relations |
| Spatial counterfactual | 可编辑的位姿/对象状态 | 重算后的关系或可见性 |
| Geometry-aware retrieval | scene/object spatial signature | 匹配的场景/对象组 |

These tasks SHOULD include hard cases where similar 2D appearance corresponds to different 3D answers.
**近垂直下视天然富含此类困难样本** —— 同色平面、阴影、反射在图像上高度相似而三维答案不同。

> **2026-08-25 移除**：`best view` 选择（属主动感知，航测航线预先规划，无此决策）。

## 46. Task Family C: Aerial Perception Reliability, Landability, and Metric Terrain

> **本节于 2026-08-25 重写为航拍能力（C1–C4）。**
>
> 原内容（Occupancy / Flyable Volume / Route Feasibility / Minimum Clearance /
> Corridor Bottleneck / Dynamic Collision Risk / Thin-obstacle Avoidance /
> Next-best-view / Inspection-view Planning / Unknown-space Decision）针对前视导航数据，
> 在近垂直下视的航测数据上无法产生有效监督，故**不在当前实施范围**。
>
> **但它们仍是项目目标的一部分**（2026-08-25 用户补充：模型需要能力多样性），
> 已移入 §46.5 作为后续待办。原设计完整保留在 `DECISIONS.md` §18.2。

### 46.1 C1 感知可信度与失效归因

> **2026-08-25 第二次修订**：本节 `Deterministic basis` 列原先全部指向 LiDAR 残差，
> 违反铁律 14，已改为纯视觉的可复算测量（§40.5 机制 1、4）。

| Task | 3D target | Deterministic basis（纯视觉） |
|---|---|---|
| 深度可信度判定 | 逐区域 `reliable / unreliable` + 置信区间 | 多视重投影误差 + 前后向光流环路误差 + 估计器间分歧，三者超阈值 |
| 失效原因归因 | `water` / `reflection_or_transparency` / `low_depth_confidence` / `sky` / `texture_poor` | §14.5 各原因掩码 + 分割输出（观点，仅作筛选）+ **不同机制交叉指认**：单一机制不足以定原因 |
| 不确定性感知回答 | `answer` / `interval` / `unknown` / `request_view` | 该区域是否通过可信度门限 |
| **几何脆弱度**（新增） | 该区域几何在受控退化下的漂移量 | **扰动法**：调暗/模糊/加噪/抽视角后重新提取，测漂移（§40.5 机制 4） |
| 退化下的可信度对照 | 同问题在原始/退化输入下的答案与置信度变化 | **合成退化**；真实日/暮配对仅用于检验合成退化的真实性（§40.6） |

**这是本管线最不可替代的能力，且是纯视觉最契合的一类。** target 由**可复算的几何测量
程序化产生**，不依赖人工标注、不依赖 LiDAR。所有失效原因 MUST 分别保留，
不得合并为单一 invalid 概率（§14.5）。

### 46.2 C2 安全降落区评估

> **2026-08-25 修正**：原表把坡度/粗糙度的依据写为「LiDAR 平面拟合」。
> **坡度是角度、粗糙度可取比值，二者在均匀缩放下不变** —— 视觉点云在尺度未知时
> 依然给出正确的角度与比值。C2 的核心几何量因此**不需要任何传感器真值**。

| Task | 3D target | Deterministic basis | 尺度锚 |
|---|---|---|---|
| 表面坡度估计 | 坡度（度）+ 局部法向 | **视觉点云局部平面拟合**（角度无尺度） | 无需 |
| 粗糙度/平面度评估 | 残差 RMS **与局部尺寸之比**、起伏比值 | 到拟合平面的残差（取比值以消尺度） | 无需 |
| 可降落区分割 | `landable / unlandable / unknown` 区域 | 几何 + 语义 + 可信度**三者联合** | 无需 |
| 最大可降落连通面积 | 面积（m²）与其边界 | 满足坡度/粗糙度阈值的连通域 | **T3** |
| 相对面积比较 | 「哪个候选区更大」「大几倍」 | 同上，取比值 | 无需 |
| 动态占用判定 | 该区域当前是否被占用 | 重复观测的差分（需重复航次，非必需） | 无需 |
| 降落风险排序 | 候选区域排序 + 排除理由 | 语义风险等级 + 几何 + 可信度 | 无需 |

**硬性规则：**

1. **「平坦」不构成可降落。** 水面、车顶、人群上方均满足平面度。判定 MUST 联合语义。
2. **深度不可信区域 MUST NOT 判为可降落**（C1 与 C2 联动）。
3. 安全相关的坡度、面积、净空数值 MUST 由几何程序计算，**不得**由 VLM 估计（§14.15）。
4. 绝对面积（m²）无尺度锚时 MUST 降级为相对面积比较，**不得**输出伪米制值（铁律 9）。

### 46.3 C3 地形与高度推理（分档）

> **2026-08-25 修正**：原表依据全部写 LiDAR。按 §40.5 机制 2 与机制 5 拆为两档。
> 用户决定：**按尺度锚分档保留，默认走 GPS/EXIF**。

**C3-a：无尺度形态（默认，任何数据集可产）**

| Task | 3D target | Deterministic basis |
|---|---|---|
| 高低序数判定 | 「A 比 B 高」 | 视觉点云沿重力方向的序关系（单调变换下不变） |
| 高差比值 | 「A-B 高差是 C-D 的几倍」 | 高差之比（尺度消去） |
| 地形起伏排序 | 若干区域按起伏幅度排序 | 高程标准差之比 |
| 坡向与坡度 | 方位角 + 倾角 | 平面拟合法向（**角度无尺度**） |
| 共面性判定 | 「这几处是否在同一平面上」 | 平面拟合残差（仿射下保持） |

**C3-b：绝对米制形态（T3 及以上）**

| Task | 3D target | Deterministic basis | 尺度锚 |
|---|---|---|---|
| 两点高差 | 高差（米） | 点云沿重力方向的差值 × 尺度因子 | GPS/EXIF 相对高度 |
| 结构相对地面高度 | 高度（米）+ 地面参考面 | 局部地面拟合 + 结构顶面 | 同上 |
| 地形起伏幅度 | 区域内高程极差（米） | 高程统计 × 尺度因子 | 同上 |
| 地面采样距离推断 | GSD（米/像素） | 对地高度 + 内参 | 同上 |

**降级规则**：无锚数据集由 `metric_task_eligible` 自动关闭 C3-b，
**静默降级为 C3-a 并记录原因**，不得报错、不得伪造米制值。

**3D 必要性论证**：近垂直下视图像几乎不提供深度线索 —— 同色屋顶与地面外观相近。
这些量**没有外观对应物**，模型无法用外观捷径蒙对。**且 C3-a 保留了这一性质** ——
序数与比值同样看不出来，3D 必要性不因去掉米制而降低。

### 46.4 C4 成像退化鲁棒与跨时相变化

> **2026-08-25 修正**：核心机制由「配对拍摄」改为「合成退化」，
> 使本能力不再要求数据集具备重复航次（铁律 14）。

| Task | 3D target | Deterministic basis | 是否需重复航次 |
|---|---|---|---|
| 退化下的答案一致性（一阶） | 同问题在原始/退化输入下的答案与置信度 | **合成退化**：调暗/降对比/模糊/加噪/抽视角 | 否 |
| **二阶不确定性**（新增） | 「模型自报的把握在退化下是否仍可信」 | 置信度**判别力**在退化前后的变化（实测 AUC 0.865→0.670） | 否 |
| 表观差异归因 | `geometric_change` vs `illumination_only` | 几何测量无变化但外观差异显著 | 否（合成）/ 是（真实） |
| 真实三维变化检测 | 变化区域 + 变化类型（新增/移除/移动） | 跨航次点云差分 | **是** |
| 合成退化真实性校验 | 合成响应 vs 真实日/暮响应的一致性 | 见 §40.6 —— **这是验证项，不产训练数据** | 是 |

**关键判据**：外观变了但几何没变 → 是光照/成像差异，**不是**场景变化。
这正是「视觉系统不知道自己看不清」的直接检验。

**二阶任务为何重要**：一阶只要求模型在看不清时说「不确定」；
二阶要求模型知道**自己的不确定性估计本身也在退化**。实测已确认后者真实存在
（置信度不只是整体下移，是判别力坍缩），且它直接对应飞手诉求
「系统说它有把握，这个把握本身可信吗」。

### 46.5 后续目标：导航类能力（Task Family B backlog）

> **优先级低于 C1–C4，但不放弃**（2026-08-25 用户补充）。
> 理由：模型需要足够的能力**多样性（Diversity）**；这些能力虽不如 C1 novel，
> 却是无人机实用性的核心。

| 能力 | 阻塞原因 | 解锁条件 |
|---|---|---|
| 薄障碍（电线/缆索/细枝）检测与中心线 | 33 m 近垂直下视无有效监督 | 前视/侧视数据集 + §14.6 规则启用 |
| 前向避障与通道净空 | 相机看不到飞行方向前方 | 同上 |
| Occupancy / free / unknown、可飞行体积 | 需前视几何与航线上下文 | 同上 + §14.7 推导链启用 |
| 航迹可行性、瓶颈定位、最小净空 | 同上 | 同上 |
| 动态碰撞风险、TTC、扫掠体重叠 | 无前视，动态目标稀少且像素占比极小 | 前视数据集 + 动态目标丰富的场景 |
| Next-best-view、检查视角规划 | 航测航线预先规划，无主动视角决策 | 具备主动飞行决策的数据 |
| 任务分解与计划批判 | 步骤绑定 waypoint 与航迹约束 | 上述能力就绪后 |

**实施路径**：引入前视/侧视数据集（候选见 `DECISIONS.md` §19.5 的方案 B：
Mid-Air / FlyAwareV2 / UAVStereo，均需重新做许可与可行性核验）。
届时 §14.6（薄障碍证据规则）与 §14.7（可飞行空间推导链）**无需重写即可启用** ——
这正是当初保留而非删除它们的原因。

**在此之前**：UAVScenes 上**仍然不得**生成这些任务（铁律 5），
数据不支持这一事实不因优先级调整而改变。

### 46.6 专家模型的**提前准备**清单（不受数据集门禁限制）

> 与 §46.5 的关系：§46.5 列的是**能力**，受「有没有前视数据集」门禁；
> 本节列的是**提取工具**，**不受该门禁**（理由见 §40.1 的说明框）。

| 能力 | 需要的专家 | 状态 | 服务的 backlog 项 |
|---|---|---|---|
| **薄结构检测**（电线/缆索/细枝） | PowerLine-MTYOLO Nano | 🟡 **权重已下载，但需分叉 runtime**；许可 AGPL-3.0 待用户决策（M-011） | R-30、R-31 |
| **空中飞行器感知**（无人机/有人机/鸟） | —— | 🔴 **确无可用预训练专家**（HF/GitHub 均已查） | R-34、R-35 |
| 语义分割（stuff） | OneFormer ADE20K | ✅ 已部署验证（加载告警已证无害） | C2、C3、L1 实体 |
| 开放词汇检测 | Grounding DINO | ✅ 已部署验证 | grounding |
| 实例掩码与视频传播 | SAM 2.1 | ✅ 已部署验证 | 实例级实体 |
| 光流与动态证据 | SEA-RAFT | ⬜ 权重不在 HF | R-38 自洽测量、R-34 |

**检索面 MUST 包含 GitHub 与论文主页，不能只搜 HuggingFace。**
2026-08-25 实测教训：首轮只搜 HF，得出「薄结构没有可用专家」的结论；
实际上 PowerLine-MTYOLO **把 checkpoint 直接放在 GitHub 仓库根目录**。
**UAV / 遥感这类小众领域的模型大量只发在 GitHub**，只搜 HF 会系统性漏掉。

**准备工作 MUST 包含四项**，缺一不算「已准备」：

1. **许可核验** —— 代码与权重**分别**核验（同仓库不同权重许可可以不同，已踩过）；
2. **可获取性** —— 权重实际下载成功，不是「文档说有」；
3. **部署验证** —— 在本机环境跑通，且**验证输出真的对**
   （OneFormer 曾「能跑但疑似加载错误」，验了才知道无害）；
4. **输出契约实测** —— 实际给哪些字段，不能只看任务名
   （DA3Metric 有米制深度但 `conf`/`extrinsics`/`intrinsics` 全是 `None`）。

**第 3 项尤其容易被跳过。** 实测教训（2026-08-25）：PowerLine-MTYOLO 的权重
能下载、大小正常、sha256 可记，看起来「准备好了」——
但**用官方 ultralytics 加载直接抛 `AttributeError`**：
checkpoint 里 pickle 了分叉版才有的 `MultiModel` 类。
**「有 checkpoint」≠「能部署」**，必须真的把它加载起来跑一次才算数。

**MUST NOT 在准备阶段就放宽标准**：专家卡的 `deployment_status` 只有
`deployed_verified` 才算数，`blocked` / `deployed_with_warning` 都要写清原因。

#### 2026-08-25 调研结论：前两项**没有可直接使用的专家模型**

HuggingFace 上以 powerline / transmission line / cable / drone detection /
airborne object 等检索，命中的**全是零下载量的个人习作**；
检索 `ttpla` 命中的是同名但无关的 Stable Diffusion ControlNet。

**生态里现成的是数据集，不是专家**：

| 能力 | 可用数据集 | 规模 | 许可 |
|---|---|---|---|
| 薄结构 | **TTPLA** | 1100 张 3840×2160，8987 实例，COCO 多边形 | HF 镜像标 `other`，**待人工核验** |
| 空中目标 | **AOT**（Amazon Prime Air） | 4943 段序列、590 万帧、330 万标注，**含距离** | 待核验 |
| 空中目标 | **AOD4** | 22516 张，4 类 | 待核验（托管 Roboflow，非稳定依赖） |

**这改变了排期的性质**：「准备这两个专家」**不是「下载并测试」，而是「拿公开数据集微调一个检测器」** ——
工作量显著更大，估期时不能按「下个模型跑一跑」算。**MUST 在排期中如实反映。**

**一个值得注意的机会**：AOT 带**距离**标注，可能直接支撑 R-34 的 TTC 真值，
而不必依赖我们自己的深度估计。引入时应优先核验这一点。

详见 `registry/experts/thin_structure_detector.yaml` 与 `airborne_object_detector.yaml`。

## 47. Task Family D: Grounded 3D Language and Interaction

### 47.1 3D Grounding

Targets MAY be object IDs, point masks, OBBs, parts, centerlines, regions, routes, poses, or trajectories.

Required subtypes:

- object/part grounding；
- relational and observer-relative grounding；
- occluded-object grounding；
- **surface/region grounding**（可降落区、水面、特定坡度区域 —— 新增）。

> **2026-08-25 移除**：thin-obstacle grounding、route/waypoint/trajectory grounding。见 §40.1。

### 47.2 3D VQA

Required capability groups:

- metric geometry；
- **metric terrain**（高差、坡度、起伏 —— 见 §46.3）；
- situated relations；
- topology；
- visibility/occlusion；
- **perception reliability and failure attribution**（见 §46.1）；
- **landability**（见 §46.2）；
- **cross-temporal change**（见 §46.4）；
- viewpoint transformation；
- uncertainty and evidence sufficiency；
- spatial counterfactuals。

> **2026-08-25 移除**：temporal motion and TTC、route/clearance/risk。见 §40.1。

### 47.3 3D Caption

Caption targets SHOULD cover object、region、scene layout、visibility、**深度可信度**、
**可降落性**与**地形特征**描述。（2026-08-25：移除 trajectory 与 flight-corridor，见 §40.1。） Every caption MUST retain structured claims.

### 47.4 3D Dialogue

Dialogue SHOULD test cross-turn grounding、changing observer pose、metadata updates、
clarification under ambiguity、uncertain geometry、以及**可信度与可降落判断的修正**。
（2026-08-25：移除 route/risk revision，见 §40.1。）

### 47.5 3D Task Decomposition and Plan Critique

> ⏸️ **移出当前范围（2026-08-25）。** 其步骤绑定 waypoint、航迹约束与前置/完成条件，
> 依赖导航语义，近垂直下视航测数据无法支撑。见 §40.1。

Each step MUST bind action, target ID, goal pose/region, spatial constraints, preconditions, completion conditions, and evidence. Include plan verification, conflict detection, missing-step completion, and infeasibility explanation.

## 48. Task Family E: Metadata, Scene Graph, and Change Reasoning

| Task | Target |
|---|---|
| Metadata verification | identify conflicting field/source/reason |
| Metadata completion | missing relation, visibility, trajectory, or uncertainty field |
| 3D scene-graph query | executable graph query and result IDs |
| Scene-graph consistency | invalid or impossible node/edge set |
| 3D change reasoning | added/removed/moved/reshaped object and evidence |
| Expert disagreement diagnosis | likely failure source and review decision |
| Evidence selection | minimal fields/views required to support an answer |

VLM-generated scene-graph relations are proposals, not unquestioned truth.

## 49. Capability Coverage Matrix（2026-08-25 重定义）

Every release MUST report coverage by:

```text
perception                  原生 3D 感知（语义/实例/检测/表面解析）
metric_geometry             米制测量
metric_terrain              地形高差、坡度、起伏           ← 新增（C3）
perception_reliability      深度可信度判定                 ← 新增（C1）
failure_attribution         失效原因归因                   ← 新增（C1）
landability                 可降落性评估                   ← 新增（C2）
viewpoint_reasoning         观察者相对与视角变换
cross_view_identity         跨视角身份
visibility_occlusion        可见性与遮挡
temporal_change             跨时相变化                     ← 新增（C4）
illumination_robustness     光照鲁棒性                     ← 新增（C4）
uncertainty                 不确定性表达
grounded_language           语言与三维实体绑定
```

> **2026-08-25 移除**：`thin_structure`、`temporal_motion`、`occupancy_navigation`、
> `flight_safety`、`active_perception`、`planning_dialogue`。见 §40.1。

It MUST also report distributions across:

- real/simulated；
- metric / externally anchored / relative；
- 对地高度分段；
- **深度可信 / 不可信 / 未判定**（新增，C1 的直接产物）；
- **可降落 / 不可降落 / 未判定**（新增，C2）；
- 日间 / 傍晚航次（新增，C4）；
- static/dynamic；clear/occluded；
- 强监督 / 程序派生 / 过滤伪标签 / 弱标签；
- 地点类型：城镇 / 山谷 / 机场 / 岛屿水域。

## 50. Task Quality Gates

Before release, each task sample MUST pass:

1. scene and metadata gates G0–G2;
2. valid point-cloud/voxel/object/route target reference;
3. scale and coordinate eligibility;
4. unique answer or explicit ambiguity target;
5. deterministic checker or independent ground truth;
6. target-leakage test;
7. 3D-necessity test;
8. low-altitude tag validation where claimed;
9. evidence sufficiency and provenance completeness;
10. supervision-level policy;
11. negative/hard-case validation;
12. applicable adapter contract tests.

Dataset-level validation MUST include 2D-only, metadata-only, 2D+metadata, pointcloud-only where applicable, metadata masking/shuffling, and spatial counterfactuals.

## 51. Recommended Task Release Order（2026-08-25 重定义）

### Release A：可移植的基础监督

- 3D 语义/实例分割；
- 对象级 3D Grounding；
- metric 与 situated 3D VQA；
- 跨视角对应；
- 可见性/遮挡。

**作用**：验证点云与 metadata 的绑定接口是否成立。首批实施对象。

### Release B：航拍差异化能力（本项目的核心贡献）

按 §40.3 的优先级：

1. **C1 感知可信度与失效归因** —— 深度可信度判定、失效原因归因、几何脆弱度、不确定性感知回答；
2. **C2 安全降落区评估** —— 坡度/粗糙度/可降落分割/动态占用/风险排序（核心量无需尺度锚）；
3. **C3 地形与高度推理** —— C3-a 序数与比值（默认）；C3-b 绝对米制（T3 及以上）；
4. **C4 成像退化鲁棒** —— 合成退化下的一阶与二阶不确定性、表观差异归因。

**这一组是本项目不可替代之处 —— 且全部走纯视觉路径（铁律 14），
不要求数据集自带 LiDAR/RTK。**

### Release C：语言与长时程推理

- Grounded 3D Caption（含可信度与可降落性描述）；
- 位姿变化下的多轮对话；
- Scene Graph 查询与补全；
- 空间反事实推理。

**MUST** 只使用已通过确定性或独立验证的结构化 target 与 claims。

### Release D：验证与标定报告（**非训练数据**）

在一个 T4 数据集（本项目为 UAVScenes）上离线完成**一次**，产出**带误差棒的验证报告**：

- 纯视觉几何提取相对传感器真值的误差分布；
- 自报置信度 → `P(depth_error < threshold)` 的标定映射及其迁移不确定性；
- 合成退化与真实日/暮退化的响应一致性（C4 的合成路径是否可信）。

**这是本项目对外交付的核心之一** —— 它是「方法可移植」这一主张的证据（§40.6）。
**MUST NOT** 把本 Release 用到的传感器真值用于生成任何训练 target（铁律 14）。

### Release E：导航类能力（backlog，需前视/侧视数据集）

§46.5 列出的薄障碍、前向避障、occupancy/可飞行体积、航迹可行性、
动态碰撞风险、Next-best-view、任务分解与计划批判。

**解锁条件是 R-37（引入前视/侧视数据集）**，不是本项目内部的实现进度。
§14.6 与 §14.7 的规则已就绪，届时无需重写即可启用。

> **2026-08-25 移除**：原 Release B 的薄障碍中心线与净空、occupancy/free/unknown、
> 可飞行体积分割、航迹可行性与瓶颈定位、动态轨迹/TTC/扫掠体风险、Next-best-view 与检查覆盖；
> 原 Release C 的任务分解与计划批判（其步骤绑定 waypoint 与航迹约束）。
> 详见 §40.1。这些设计保留在 `DECISIONS.md` §18.2，**现登记为上面的 Release E**。

---

## 52. 任务价值论证与数据演进目标（2026-08-25 新增）

> **本节是本项目的首要交付物**（§1.1）。每个能力 MUST 回答五个问题：
>
> 1. **能力缺口** —— 现有训练数据缺的是什么能力？为何现有数据供不上？
> 2. **为何该任务能训到它** —— 任务形态与能力之间的因果，而非相关。
> 3. **当前上限** —— 我们这批数据在该任务上**能到什么程度、到不了什么程度**（诚实写明）。
> 4. **好数据的特征** —— 要把这类任务做好，数据须满足什么？**这是给后来者的优化目标。**
> 5. **衡量指标** —— 怎么判断新数据比我们的好。
> 6. **3D 增益**（2026-08-25 新增）—— 喂入 3D metadata 相对 2D-only 的实测提升，
>    带置信区间，并说明打乱/屏蔽后增益如何消失（§29）。
>    **这一项是铁律 5 的准入线，不是可选补充。**
>
> **缺此六项论证的任务不进 Release**（§1.1）。
>
> **第 6 项当前状态**：C1–C4 的 3D 增益**尚未实测** —— 需要可调用的 VLM（R-20，暂缓中）。
> 在拿到数字之前，任何任务 MUST 标注 `lift_unmeasured`，**不得进入正式 Release**。
> 这是当前最重要的未验证项，见 README 的 R-43。

### 52.0 通用判据：一个任务类型是否「值得做」

一个下游任务值得做，MUST 同时满足：

| 判据 | 含义 | 反例 |
|---|---|---|
| **能力真空** | 现有大规模训练数据**系统性地**供不上这个监督 | 「识别建筑物」—— 2D 数据遍地都是 |
| **3D 增益显著** | 喂入 3D metadata 后得分**实测**显著提升，且打乱 metadata 后增益消失（§29） | 「这是水面吗」—— 给不给点云都一样答得对 |
| **可判定** | 存在确定性 checker，不靠 LLM 打分 | 「描述这个场景」—— 无稳定真值 |
| **真实诉求** | 对应真实作业中的痛点，不是为难模型而设 | 「点云里第 731 个点的坐标」 |
| **可移植** | 不依赖某数据集特有的传感器（铁律 14） | 「LiDAR 残差是多少」 |

> **2026-08-25 修订**：第二条原为「**捷径不可解** —— 外观捷径给出错误答案」。
> 该判据过严且不可能达成：我们的 3D metadata 本身就是从 2D 提取的（铁律 5 修订说明），
> 信息论上不存在「2D 绝对答不出」的任务。
> 改为**实测增益** —— 口子放宽，但要求从「断言不可解」变成「拿出数字并排除伪增益」。

**「能力真空 + 3D 增益显著」是本项目的选题核心**：
模型在图像-答案对上会学到「外观→答案」的捷径 —— 不是因为三维线索不在图像里，
而是因为**训练过程从未奖励它去做三维计算**。
把最擅长三维提取的专家模型的输出显式喂进去，应当带来增益。
**增益的大小就是这个任务的价值度量**，而不是一个是非判断。

### 52.1 C1 感知可信度与失效归因

**能力缺口**：现有 VLM/3D 模型被训练成**永远给出一个答案**。
训练数据里几乎不存在「这里我看不清、且原因是 X」这种标注 ——
因为标注失效需要知道**真值和预测的差**，而常规标注流程只记录真值。
结果是模型在水面、反射面、无纹理区照样自信地报深度。**这是飞手的头号痛点。**

**为何该任务能训到它**：失效标注不来自人工判断，
而来自**几何自洽的可复算违反**（重投影/环路误差、估计器分歧、扰动漂移）。
这些量与「模型该不该自信」有直接因果：自洽违反大的地方，任何视觉方法都不可靠。

**当前上限（诚实）**：

- ✅ 能定位失效**区域**：水面 vs 陆面判别 AUC 0.865（正常照度）；
- ✅ 能产出**脆弱度**：扰动法已跑通（亮度 0.25× → AUC 掉到 0.670）；
- ⚠️ **失效原因的区分尚未验证**：只验证了水面，`texture_poor` / `reflection` 未测；
- ❌ **不能说「错了多少米」**：无真值。定量误差需 Release D 标定后才有意义；
- ❌ 低照度下原因归因基本失效（判别力已坍缩）。

**好数据的特征**（给后来者）：

1. **同场景的多次采集，成像条件受控变化**（光照、天气、曝光、运动模糊）——
   这是脆弱度标注的直接来源，比任何单次高质量采集都有用；
2. **含大面积「已知会失效」的地物**：水面、玻璃幕墙、湿沥青、雪地、均质屋顶。
   **失效样本是资产，不是噪声** —— 现有数据集普遍回避这类场景，正是缺口所在；
3. **至少有一个子集带传感器真值**，用于标定置信度（不必全量，见 §40.6）；
4. 逐像素或逐区域的**失效原因**标注，而非单一 valid/invalid 位（§14.5）。

**衡量指标**：失效区域检出的 AUC / AP；原因码的混淆矩阵；
**校准曲线的 ECE**；以及**在退化条件下上述指标的衰减幅度** ——
最后一项是本项目发现的关键维度，现有基准都不测。

**3D 增益（第 6 问，待测）**：预期最大 —— 2D VLM 完全没有「几何自洽违反」
这类信号的接口，它只能靠外观猜「这里像不像不可信」。
`lift_unmeasured`，需 R-20 解除暂缓后实测。

### 52.2 C2 安全降落区评估

**能力缺口**：「哪里能降落」需要**几何与语义的联合判断**，
而现有数据集要么只有语义分割（不知道坡度），要么只有几何（不知道那是人群还是草坪）。
更关键的是，**平坦 ≠ 可降落**这条判据在纯外观数据上无法学到：水面平、车顶平、人群上方也平。

**为何该任务能训到它**：判定 target 由「几何 + 语义 + 可信度」三者联合的程序产生，
**任一单模态都推不出答案**，因此不存在单模态捷径。

**当前上限（诚实）**：

- ✅ 坡度与平整度比值**无需尺度锚**即可算（角度在均匀缩放下不变）；
- ⚠️ 依赖视觉点云的局部平面拟合质量，而 VGGT-Ω 在弱纹理区的点云本就稀疏且噪声大 ——
  **恰恰是最需要判断可降落性的均质地面上，几何最不可靠**。这是本能力当前最大的软肋；
- ⚠️ 绝对面积（m²）需 T3 锚，精度未验证；
- ❌ 动态占用需重复航次，覆盖有限。

**好数据的特征**：

1. **真实降落场景的标注**（哪怕少量）—— 目前全靠几何阈值代理，没有人类判断做锚；
2. **弱纹理地面的高质量几何**：这是 C2 的瓶颈。立体、多基线、或主动传感都行；
3. **含负样本**：看起来平坦但不可降落的地方（水面、天窗、遮阳棚、人群）——
   **负样本的价值高于正样本**，因为捷径正是在这里出错；
4. 尺度锚（GPS/气压高度）以支持绝对面积。

**衡量指标**：可降落分割 IoU；**负样本上的假阳率**（首要指标 ——
把水面判成可降落是灾难性错误，把草坪判成不可降落只是保守）；坡度 MAE。

**3D 增益（第 6 问，待测）**：预期中等偏高 —— 语义部分 2D 本就能做，
**增益应主要来自坡度与平整度**。因此消融时 MUST 分别屏蔽语义字段与几何字段，
看增益是否确实来自几何那一半。`lift_unmeasured`。

### 52.3 C3 地形与高度推理

**能力缺口**：近垂直下视图像**几乎不提供深度线索**。
同色的屋顶与地面在 nadir 视角下外观相近 —— 这意味着**外观捷径必然给出错误答案**，
是 §52.0 判据里最干净的一类。而现有 3D 数据集以室内、街景、自动驾驶为主，
**近垂直下视的高度推理数据基本空白**。

**为何该任务能训到它**：答案与外观几乎无关，模型只能依赖三维结构。
序数与比值形态（C3-a）在深度的单调变换下不变，因此**即使我们的深度不准，序关系仍大概率正确**——
这正是"数据质量不高但任务仍成立"的典型例子。

**当前上限（诚实）**：

- ✅ C3-a（序数/比值）成立且对深度误差稳健；
- ⚠️ C3-b（绝对米制）依赖尺度锚。实测**不能**从 VGGT-Ω 自身恢复米制
  （锚定后 CV 仍 19.5%，见 `FINDINGS.md 附录 B`）；
- ❌ 米制精度**至今没有任何验证过的数字** —— 需 Release D。

**好数据的特征**：

1. **可靠的尺度锚**，且锚的不确定性被记录（不是只给一个数）；
2. **高度动态范围大的场景**：全平的农田产不出有区分度的题；
3. **多高度层的结构**：屋顶、平台、树冠、地面 —— 层次越多，序数题越有信息量；
4. **地面真高**（DTM/DSM）若有，能直接支撑「结构对地高度」这类最难的题。

**衡量指标**：序数准确率（C3-a）；米制 MAE 与相对误差（C3-b）；
**以及模型在「外观相同但高度不同」样本对上的准确率** —— 这是捷径检测的直接探针。

**3D 增益（第 6 问，待测）**：C3-a 预期高（nadir 下高度几乎无外观对应物）；
**C3-b 是本项目唯一预期「2D 原则上不可能」的一类** —— 尺度锚来自 EXIF/GPS，
信息不在像素里（§29.3）。`lift_unmeasured`。

### 52.4 C4 成像退化鲁棒与二阶不确定性

**能力缺口**：这是本项目认为**最被忽视**的一项。
现有基准测「模型在干净输入上多准」，几乎不测「模型的自我评估在退化下是否仍可信」。
而实测表明后者会**坍缩**：置信度不只是整体下移，是**判别力**从 AUC 0.865 掉到 0.670。
**模型在最该谨慎的时候反而变得自信**（水面落入高置信区的比例从 8.1% 涨到 19.1%）。

**为何该任务能训到它**：合成退化提供了**成对的反事实** ——
同一场景、同一几何、只有成像条件不同。答案的应然变化（几何不变、确定性下降）是可推导的，
因此 target 确定。

**当前上限（诚实）**：

- ✅ 合成退化路径任何数据集可跑，不需要重复航次；
- ✅ 二阶现象已实测确认存在；
- ⚠️ **合成退化是否像真实退化，尚未验证** —— 这正是 Release D 的一项；
- ⚠️ 亮度与对比度的贡献未分离（实测中二者同时变化）；
- ❌ 只测了光照。运动模糊、雨雾、过曝、压缩伪影均未测。

**好数据的特征**：

1. **同场景、同航线、跨成像条件的真实重复采集** ——
   用于校验合成退化的真实性，是这类研究的稀缺资源；
2. **退化条件被记录为元数据**（照度、曝光、快门、天气），而不是只留图像 ——
   没有条件标注就无法分档校准（§14.13）；
3. **覆盖多种退化类型**，不只是光照；
4. 退化程度**连续可变**，而非只有「白天/夜晚」两档 ——
   本项目实测发现 `_Evening` 航次内部就有 4 倍亮度梯度，连续变化才能画出衰减曲线。

**衡量指标**：一阶 —— 退化下的答案一致性与弃权率；
**二阶 —— 置信度判别力（AUC）随退化程度的衰减曲线，以及校准误差（ECE）的漂移**。
后者是本项目主张应当新增的评测维度。

**3D 增益（第 6 问，待测）**：这里的增益形态特殊 ——
不是「答得更准」，而是**「该改口时改口、该坚持时坚持」**。
消融的正确对照是：退化后 2D-only 模型的答案漂移幅度 vs 带 3D metadata 的漂移幅度。
**几何没变时答案不该变**，这正是 §0.4 判据 3 的可测形式。`lift_unmeasured`。

### 52.5 本项目留给后来者的四句话

1. **失效样本是资产。** 现有数据集回避水面、反射、弱纹理，
   而那正是可信度能力唯一的监督来源。
2. **序数与角度比米制便宜得多，且不损失价值。**
   在深度不准的现实下，先把无尺度的任务做扎实，比追求米制精度更划算。
3. **测「模型在干净输入上多准」是不够的，要测「它的自我评估在退化下是否还成立」。**
   这一维度现有基准普遍缺失，而它恰恰对应真实作业中最危险的失效模式。
4. **别去证明「2D 做不到」，去测「3D 帮了多少」。**
   当 3D metadata 本身就是从 2D 提取的时候，前者在信息论上不可能成立；
   后者是能拿出数字、能被复现、也能被后来者超越的判据。

---

# 附录：第三层 Agent / Skill 系统详细设计

> **第三层已于 2026-08-25 降级为「润色层」**（见 `DECISIONS.md` §19.4）：
> 先把一、二、四层主干搭通，Skill 是主干可运行后再提炼的东西。
> 本附录保留完整设计，届时直接启用。功能当前以普通函数实现，不封装 Skill。
>
> 2026-08-25 由 DESIGN.md（附录：第三层） 并入，正文未改动（仅修正若干陈旧能力表述）。


> ⏸️ **本层已于 2026-08-25 暂缓（[用户已确认]）。**
>
> 用户决定先完整搭通第一、二、四层的主干（数据输入 → 提取/生成/处理 → 下游任务输出），
> **第三层的 Skill 封装与统一门禁框架推迟**，待主干可运行后再回来审视哪里值得用 Skill 提炼。
>
> **但本文档的规则仍然有效** —— 其中定义的校验项、修复策略、泄漏检查等**功能**
> 会以普通代码形式实现在主干上，只是暂不封装为 Skill、暂不建立 Orchestrator 与 G1–G6 框架。
>
> 详见 `DECISIONS.md` §19.4 的功能/封装双重归属对照表。

> 状态：设计草案，不代表已经开始实现或运行服务器任务  
> 记录日期：2026-08-23（Asia/Shanghai）  
> 上游约束：以 `DECISIONS.md` 中标记为“用户已确认”的内容为准

## 1. 本阶段目标

当前阶段只完成本地控制面的总体设计、规则沉淀和接口定义，不下载大型数据集、不运行 VGGT-Ω、不调用 Qwen 批量生成数据，也不部署服务器 Pipeline。

最终执行环境在服务器。本地项目负责维护：

- Pipeline 的阶段定义和状态机；
- 3D metadata 与任务样本规范；
- Task Spec、Prompt Template 和输出 Schema；
- Agent 使用的 Skills；
- 校验器、质量门禁和监控指标定义；
- 版本、来源、运行配置和发布清单。

## 2. 不变的项目约束

以下规则继承自交接文档，不得由 Agent 或 Skill 擅自更改：

1. 点云主路径固定为 VGGT-Ω。
2. Qwen 接收 2D 图像/视频与结构化 3D metadata，不直接读取原始点云。
3. 任务必须真实依赖 3D 信息，不能退化为普通 2D QA 或 metadata 字段抄写。
4. 距离、角度、遮挡、相交、坡度、共面性等可确定计算的真值优先由几何程序产生。<br/>（2026-08-25：原列「净空、TTC」，属导航类能力，已移入 Release E backlog。）
5. LLM 不是几何真值的唯一来源，也不能同时自由生成 metadata、问题、答案并自行证明正确。
6. metric 与 relative scale 必须明确区分；不允许把伪深度或相对重建结果冒充米制真值。
7. 每项自动生成结果必须记录来源、模型版本、输入帧、坐标系、单位、置信度和运行版本。
8. 数据切分必须按场景、地域或完整轨迹进行，禁止逐帧随机切分造成泄漏。
9. 首版优先实现最小 L0/L1/L2 schema，不提前铺开完整 L3 导航和风险能力。
10. 正式放量前必须先跑通小样本闭环，并建立 2D-only、metadata-only、2D+metadata 对照。

## 3. 总体设计原则

### 3.1 Skill 与 Prompt 的职责不同

Skill 用于规定 Agent 如何决策、读取哪些规范、调用哪些校验器、在什么条件下继续或停止。Prompt Template 只是具体模型调用的一个版本化输入模板。

因此首版不为每种题型创建一个独立 Skill，而采用：

```text
少量流程型 Skill
    └── 读取可版本化 Task Spec
            └── 选择对应 Prompt Template
                    └── 绑定输入字段、隐藏字段、输出 Schema 和 Checker
```

新增任务通常只增加 Task Spec、模板和 checker，不应复制整个 Skill。

### 3.2 程序先于语言模型

能通过数据、几何或规则确定的内容，应先产生结构化事实和 target，再让模型完成语言表达、组合推理或候选方案生成。

推荐把任务分成三类：

| 类型 | 典型任务 | 真值来源 | 模型职责 |
|---|---|---|---|
| Program-first | Grounding、metric VQA、cross-view correspondence | 几何程序、匹配器、原生标注 | 问题自然化、指代理解、结构化回答 |
| Hybrid | Caption、Dialogue、Metadata Verification | 程序生成 claims/冲突，再由模型表达 | 组织语言、跨轮推理、解释 |
| Model-first constrained | *（当前无首批任务使用）* | 模型先生成候选，程序和规则验证 | 规划、解释、修复候选<br/>**2026-08-25：原列 Task Decomposition 与 Next-best-view，二者当前无数据支撑，已降级为后续目标（SPEC §46.5）** |

### 3.3 生成与评估解耦

- 确定性校验器优先于 LLM Judge。
- LLM Judge 只评估语义自然度、描述覆盖和难以程序化的歧义，不裁决几何真值。
- 尽量避免同一模型、同一上下文同时负责生成与唯一语义验收。
- 所有自动修复都必须保留原输出、错误列表、修复次数和最终状态。

## 4. Agent 系统结构

建议首版由一个 Orchestrator Agent 管理八类流程 Skill。

```text
Pipeline Orchestrator Agent
├── dataset-registry-manager
├── expert-registry-manager
├── scene-ingestion-validator
├── metadata-quality-gate
├── task-spec-designer
├── task-prompt-compiler
├── task-sample-auditor
└── dataset-quality-monitor
```

### 4.1 Pipeline Orchestrator Agent

职责：

- 根据场景状态选择下一阶段；
- 只向 Skill 提供当前阶段所需的最小上下文；
- 管理 artifact、版本、失败原因、重试次数和隔离队列；
- 执行质量门禁，不允许失败样本静默进入下一阶段；
- 汇总服务器运行结果，但不修改任务真值；
- 在超过重试上限、发现尺度冲突或关键来源缺失时停止并请求人工处理。

Orchestrator 不应：

- 自由改写 schema；
- 为了提高通过率而降低质量阈值；
- 自动把 relative 场景升级为 metric；
- 跳过失败阶段直接发布数据；
- 用 LLM 猜测缺失的相机、尺度或几何真值。

### 4.2 `dataset-registry-manager`

适用阶段：数据集调研、去重、验证和首批选择。

职责：

- 维护 Dataset Card、别名、版本和飞书只读快照；
- 核验官方来源、许可、文件清单、尺度来源和小样本验证状态；
- 阻止未完成许可或样本验证的数据集进入全量接入。

### 4.3 `expert-registry-manager`

适用阶段：专家模型被加入服务器配置之前。

职责：

- 分别记录代码许可、权重许可、API 条款和衍生数据限制；
- 记录输入输出、坐标约定、预处理变换、checkpoint hash 和运行环境；
- 区分研究推荐等级与实际部署授权；
- 维护专家运行频率、fallback 和服务器 profile；
- 未完成 UAV 小样本验证的模型不得标记为 production-ready。

当前语义链路候选为 Grounded-SAM-2、SAM 2.1、SEA-RAFT、OneFormer、CABiNet、Florence-2 和 DINOv2。几何专家优先顺序修订为 MoGe-3、DSINE、DA3-1.1；DA3-Streaming 仅用于长视频，CoTracker3/Trace Anything 用于轨迹和动态研究。WorldMirror 只允许推理/评估，不能生成 Qwen 训练 metadata。这些只是调研建议，不代表已获许可或已验证。

`expert-registry-manager` 还必须：

- 分别标记 `training_allowed`、`evaluation_only`、`quality_control_only`；
- 审计顶层仓库及传递依赖/权重许可；
- 记录模型谱系和共享偏差组，禁止把 MoGe/MetricAnything 或 VGGT/DA3 等相关模型当作完全独立投票；
- 阻止 WorldMirror 输出进入训练样本；
- 保存每个模型的图像变换、坐标约定、SE(3)/Sim(3)/scale-shift 对齐方式和 alignment version。

### 4.4 `scene-ingestion-validator`

适用阶段：数据集 adapter 输出后、VGGT-Ω 运行前。

检查：

- 图像/视频是否可读；
- 帧、时间戳、内参、外参和原生标注是否能对齐；
- 场景切分是否存在跨 split 泄漏；
- 数据来源、许可状态和 dataset version 是否记录；
- `depth_source`、`metric_scale` 与尺度锚点是否一致；
- 输入是否满足重建最小视角覆盖和重叠要求。

输出：`ingestion_report.json`，状态只能为 `pass`、`warn`、`quarantine` 或 `reject`。

### 4.5 `metadata-quality-gate`

适用阶段：VGGT-Ω、专家模型和 2D-to-3D fusion 完成后。

检查：

- scene/object/relation schema；
- 坐标系、单位和尺度状态；
- 相机、深度、点云和对象投影的一致性；
- 稳定 ID 的唯一性与引用完整性；
- OBB、centroid、centerline、track 的数值合法性；
- 置信度、support views、provenance 是否完整；
- 动态 ghost、薄结构缺失、低覆盖、异常深度和跨视角冲突；
- 派生字段能否从记录的上游字段重新计算。
- detector、mask、track、depth 和关联置信度是否被错误压成单一分数；
- 动态概率是否基于扣除相机自运动后的 residual flow；
- `sky`、`water`、`reflection_or_transparency`、`low_depth_confidence`、`reprojection_inconsistent`、`dynamic_geometry` 等 reason mask 是否分别保存；
- ~~薄障碍是否保存概率、骨架、边界置信度、多帧支持和 3D 拟合残差~~ —— **当前不适用**（SPEC §40.1）。
  等价的现行检查：**LiDAR 与视觉深度的残差及失效原因码是否可重算、是否分别保存**。
- metric、externally anchored、relative、affine-invariant、pseudo depth 是否被严格区分；
- metric 测试是否在 Sim(3) 对齐前报告原始尺度误差；
- 多专家结果是否先计算残差并校准，而不是直接平均或投票；
- WorldMirror conditioned/refiner 输出是否被错误当作独立验证。

输出：`metadata_validation_report.json` 和可供下游使用的 `metadata_snapshot_id`。失败版本不可原地覆盖，应产生新版本。

### 4.6 `task-spec-designer`

适用阶段：场景metadata通过门禁后、具体任务样本编译前。

职责：

- 将点云、相机、对象、关系、轨迹、occupancy和质量字段映射为Task Spec；
- 为每个任务定义能力标签、低空标签、监督等级、可见字段、隐藏target、3D目标锚点和checker；
- 保证任务具有3D必要性，避免仅靠单张2D图像或字段查找解决；
- 保证低空专项任务使用**下视几何、对地高度、深度可信度、可降落性属性、米制地形量或跨航次重复观测**；
  （2026-08-25：原文为「薄障碍、可飞行空间、航迹、动态风险或主动视角」，已按 SPEC §40 重定义。）
- 维护原生点云、Qwen 2D+metadata、多模态3D三类adapter；
- 输出能力覆盖矩阵，防止不同题型只是在重复测试同一能力。

### 4.7 `task-prompt-compiler`

适用阶段：把已通过 metadata 门禁的场景编译为模型调用包。

职责：

- 读取 Task Spec；
- 从场景 metadata 中裁剪任务局部子图；
- 应用 `metadata_input_fields` 与 `hidden_target_fields`；
- 调用 derivation program 得到 target 和 evidence；
- 选择相应 Prompt Template；
- 写入允许的输出类型、JSON Schema、拒答条件和精度要求；
- 生成正常提示词及结构化修复提示词；
- 在模型调用前进行目标泄漏检查。

输出为 `prompt_bundle.json`，而不是直接得到最终数据样本。

### 4.8 `task-sample-auditor`

适用阶段：模型返回后、样本进入数据集前。

检查：

- 输出是否满足 JSON Schema；
- ID、数值、单位和枚举是否合法；
- target 是否与 checker 重算结果一致；
- evidence 是否足以支持答案；
- 问题是否可解、是否存在多个同等答案；
- 输入中是否泄露 target 或派生答案；
- 是否存在纯 2D shortcut 或纯字段查找 shortcut；
- Caption claims 是否忠实、Dialogue 状态是否跨轮一致；
- 输出是否包含未被 metadata 支持的对象或关系；
- 任务难度、文本质量和表达多样性是否达到要求。

修复策略：

1. Schema 或格式错误：允许一次结构化 repair。
2. 表达问题但 target 正确：允许一次 constrained rewrite。
3. 几何真值、证据、尺度或歧义错误：禁止语言修复，返回上游重新编译或隔离。
4. 达到重试上限仍失败：`quarantine`，不得继续循环调用模型。

### 4.9 `dataset-quality-monitor`

适用阶段：批次生成期间和数据集候选发布前。

职责：

- 汇总每阶段通过率、失败类型和重试率；
- 监控类别、场景、任务、难度、尺度来源和真实/仿真的分布；
- 检查重复、近重复、模板坍缩和问答表达单一；
- 监控 checker agreement、目标泄漏率、歧义率和无依据内容率；
- 比较不同版本、模型和数据集的质量漂移；
- 执行 2D-only、metadata-only、2D+metadata、metadata shuffle 等依赖性测试；
- 生成 `quality_dashboard.json` 与 `release_manifest.json`。

监控 Skill 只能报告和阻断，不得自动改变 release threshold。

## 5. Task Spec 规范

每一种任务或子任务应有一个版本化 Task Spec。建议字段：

```yaml
task_id: 3d_vqa.metric.minimum_distance
version: 0.1.0
task_family: 3d_vqa
generation_mode: program_first

required_scene_capabilities:
  scale_status: metric
  geometry: [observer_position, centerline]

visual_input_policy:
  input_type: multi_view_image
  min_views: 2
  selection: support_and_context

metadata_input_fields:
  - observer.position
  - entities.object_id
  - entities.category
  - entities.geometry.centerline

hidden_target_fields:
  - derived.minimum_distance
  - target.object_id

derivation_program: minimum_point_to_polyline_distance
checker: check_minimum_distance_answer

prompt_template: 3d_vqa/metric_v1
output_schema: schemas/3d_vqa_metric_answer.schema.json

leakage_rules:
  forbidden_input_fields:
    - entities.distance_to_observer
    - derived.minimum_distance

quality_requirements:
  minimum_geometry_confidence: 0.80
  maximum_answer_count: 1
  numeric_tolerance_m: 0.10
```

Task Spec 必须明确：

- 任务为什么依赖 3D；
- 需要哪些场景能力；
- 哪些字段对模型可见；
- 哪些字段是隐藏真值；
- target 如何计算；
- 输出如何验证；
- 什么情况下拒绝生成该任务。

## 6. Prompt Bundle 规范

每次模型调用保存完整、可重放的 Prompt Bundle：

```json
{
  "prompt_bundle_id": "pb_...",
  "task_spec_id": "3d_vqa.metric.minimum_distance@0.1.0",
  "scene_id": "scene_000018",
  "metadata_snapshot_id": "meta_...",
  "model": {
    "provider": "pending",
    "name": "pending",
    "version": "pending",
    "parameters": {}
  },
  "visual_inputs": [],
  "system_prompt": "...",
  "task_prompt": "...",
  "metadata_context": {},
  "output_schema": {},
  "hidden_target_ref": "target_...",
  "checker": "check_minimum_distance_answer",
  "retry_policy": {
    "max_format_repairs": 1,
    "max_semantic_rewrites": 1
  }
}
```

提示词至少包含以下约束：

1. 任务身份与坐标系定义；
2. 可使用的视觉输入和 metadata 范围；
3. 不得虚构未提供的对象、关系、单位或尺度；
4. 证据不足、对象歧义或尺度不满足时的拒答格式；
5. 严格输出 Schema；
6. 数值精度、单位和 ID 格式；
7. 禁止输出隐藏推理过程，只输出要求的答案与可审计 evidence reference；
8. 不允许把 prompt 中的示例 ID 或示例数值复制为当前答案。

### 6.1 不同任务的提示词重点

#### 3D Grounding

- 只返回允许的 object/part/region/route/track ID；
- 候选集不得包含 target 标记；
- 关系表达必须相对指定坐标系或 observer pose；
- 多解时返回歧义状态，不强猜单一对象。

#### 3D VQA

- metric 题必须满足尺度要求；
- situated 题必须绑定观察者位姿和方向约定；
- 数值答案必须带单位和容差；
- target 应由程序计算，模型不负责创造真值。

#### 3D Caption

- 先提供程序生成的 claim set，再由模型组织语言；
- 最终同时保存自然语言和结构化 claims；
- 禁止加入 claim set 与视觉证据均不支持的事实。

#### 3D Task Decomposition

- 每一步绑定 action、target ID、goal region、约束、前置条件和完成条件；
- 模型生成候选计划后必须通过几何与规则验证；
- 不满足约束时允许返回不可行，而不是强行补全计划。

#### 3D Dialogue

- 显式传递 dialogue state、已绑定实体、当前 observer pose 和 metadata version；
- metadata 更新后必须能够修正旧答案；
- 指代不唯一时主动澄清，不得静默换绑对象。

#### 新增任务

Cross-view Correspondence、Metadata Verification、Viewpoint Transformation、可信度判定（C1）、可降落性（C2）等任务均应复用同一编译接口，通过 Task Spec 定义自己的输入掩码、真值程序和 checker。

## 7. 阶段门禁

建议使用硬门禁与软评分组合，不允许一个总分掩盖关键错误。

| Gate | 阶段 | 关键硬失败条件 |
|---|---|---|
| G0 | Dataset / expert registry and ingestion | 文件不可读、场景切分泄漏、数据或模型许可阻断、关键来源缺失 |
| G1 | Geometry and expert inference | 坐标系不明、尺度声称冲突、重建失败、预处理坐标变换缺失 |
| G2 | Metadata | ID 引用断裂、关键 provenance 缺失、数值非法、置信度或无效原因被错误合并 |
| G3 | Task design / compile | 3D必要性或低空特性不成立、target不可重算、输入泄漏target、任务不可解 |
| G4 | Model output | Schema 无法修复、引用不存在的实体 |
| G5 | Sample audit | checker 不一致、证据不足、多解未标记、3D 依赖不成立 |
| G6 | Dataset release | 泄漏率超阈值、重复率超阈值、对照实验不成立 |

统一状态：

- `pass`：可以进入下一阶段；
- `warn`：可以进入下一阶段，但必须记录警告并计入监控；
- `quarantine`：隔离，等待人工或上游重新处理；
- `reject`：当前配置下不可用。

## 8. 质量监控与评估

### 8.1 单样本质量维度

- schema validity；
- provenance completeness；
- geometry confidence；
- answer determinism；
- evidence sufficiency；
- target leakage；
- ambiguity；
- 3D necessity；
- visual/metadata consistency；
- language quality；
- uncertainty calibration。

硬失败项不参与加权平均。只有通过硬门禁的样本才可计算软质量分。

### 8.2 批次与数据集指标

至少监控：

- 每个 Gate 的通过率、隔离率和拒绝率；
- 模型输出 Schema 一次通过率；
- format repair 与 semantic rewrite 比例；
- deterministic checker agreement；
- unsupported claim rate；
- target leakage rate；
- ambiguous sample rate；
- exact/near duplicate rate；
- 类别、任务、难度、场景、尺度来源、真实/仿真分布；
- 相邻版本的数据分布漂移；
- 不同专家模型、数据集和重建配置的失败模式。
- mask AP、Boundary F-score 和薄结构连通率；
- HOTA、IDF1、ID switch 和跨视角关联质量；
- forward-backward flow error 与 ego-compensated dynamic IoU；
- 3D lifting point purity/completeness、重投影 IoU 和跨视角 3D IoU；
- 深度分歧、法向角误差和尺度漂移；
- ECE、Brier、NLL、AUSE、risk-coverage/AURC；
- 延迟、峰值显存、FPS、J/frame、临时磁盘、metadata bytes/frame 和视频分钟成本。
- perception、metric geometry、**metric terrain**、viewpoint、cross-view、visibility、
  **perception reliability**、**failure attribution**、**landability**、**temporal change**、
  **illumination robustness**、uncertainty、language 能力覆盖率；
  （2026-08-25：移除 thin structure、motion、navigation、safety、active perception、planning，见 SPEC §49。）
- pointcloud-native、Qwen 2D+metadata和multimodal-3D adapter的可用样本数；
- 强监督、程序派生、过滤伪标签、弱标签和语言生成的比例。

### 8.3 验证模型是否使用 3D Metadata

正式评测至少包含：

1. `2D-only`；
2. `metadata-only`；
3. `2D+metadata`；
4. metadata field masking；
5. metadata shuffle；
6. spatial counterfactual；
7. 遮挡或弱视觉证据子集。

只有当 `2D+metadata` 在真正依赖三维的任务上稳定优于 `2D-only`，且 metadata shuffle/counterfactual 会导致符合预期的性能变化，才能声称模型有效使用了 metadata。

## 9. Artifact 与可追溯性

服务器 Pipeline 的阶段产物建议统一为：

```text
run_manifest.json
scene_manifest.json
ingestion_report.json
geometry_manifest.json
metadata_snapshot.json
metadata_validation_report.json
task_spec.yaml
prompt_bundle.json
raw_model_output.json
validated_sample.json
quality_event.jsonl
quality_dashboard.json
release_manifest.json
```

每个 artifact 至少包含：

- artifact ID 与版本；
- parent artifact IDs；
- scene/dataset/split ID；
- 代码、模型、schema、task spec 和 prompt 版本；
- 创建时间与运行配置；
- 输入摘要或校验和；
- 状态、错误代码、警告和重试记录。

任何修复、重跑或重生成均创建新 artifact，不静默覆盖历史版本。

## 10. 本地控制面与服务器执行面

### 本地控制面

- 编写和审查 Skills；
- 维护 schema、Task Spec、Prompt Template、checker contract；
- 维护质量阈值和发布规则；
- 使用合成小样本做单元测试；
- 生成服务器可读取的版本化配置包。

### 服务器执行面

- 数据下载与缓存；
- VGGT-Ω 和专家模型推理；
- 2D-to-3D lifting/fusion；
- Qwen 或其他配置模型调用；
- 大规模 deterministic validation；
- 指标聚合、隔离队列和候选发布。

本地设计不得硬编码服务器路径、GPU 型号、模型密钥或单一调度系统。这些应由 server profile 注入。

## 11. 建议的后续目录结构

这里只记录建议，当前尚未创建：

```text
3D-data-Gen/
├── docs/
│   ├── architecture.md
│   └── quality-policy.md
├── agents/
│   └── pipeline-orchestrator/
├── skills/
│   ├── dataset-registry-manager/
│   ├── expert-registry-manager/
│   ├── scene-ingestion-validator/
│   ├── metadata-quality-gate/
│   ├── task-spec-designer/
│   ├── task-prompt-compiler/
│   ├── task-sample-auditor/
│   └── dataset-quality-monitor/
├── task_specs/
│   ├── grounding/
│   ├── vqa/
│   ├── caption/
│   ├── task_decomposition/
│   ├── dialogue/
│   └── new_tasks/
├── task_adapters/
│   ├── qwen_2d_metadata/
│   ├── pointcloud_native/
│   └── multimodal_3d/
├── prompt_templates/
├── schemas/
├── checkers/
├── configs/
└── tests/
```

## 12. 实现顺序建议

在用户确认实施后，按以下顺序推进：

1. 冻结 artifact ID、状态枚举和最小 schema。
2. 建立 dataset/expert registry，完成许可、checkpoint 和 I/O contract 门禁。
3. 定义 3D Grounding、metric/situated 3D VQA、Cross-view Correspondence 三个 Task Spec。
4. 实现 `task-prompt-compiler`，先只支持离线 prompt bundle 编译，不调用模型。
5. 实现确定性 checker 与 target leakage 检查。
6. 实现 `task-sample-auditor` 和有限修复策略。
7. 实现 metadata 与 ingestion 门禁，包括 residual flow 和 invalid-reason checks。
8. 最后实现 Orchestrator 状态机和 dataset-level monitor。
9. 用合成 scene package 完成本地测试，再迁移到服务器 UAV 小样本：至少 40–60 个短片段和 8–12 个长片段；如需完成完整语义专家评估，再扩展到 100–300 段。

该顺序优先验证“任务能否被正确编译和检查”，避免在几何模型尚未跑通前写出大量不可验证的提示词。

## 13. 用户决策状态

2026-08-24 已确定（详见 `DECISIONS.md` §19，机器可读形式见 SPEC §36）：

1. **首批真实数据集：UAVScenes 单个**；
2. **首版强制 metric**，relative / affine-invariant / pseudo 场景不具备任务资格；
3. **首批任务：3D Grounding（对象级）+ metric/situated 3D VQA + Cross-view Correspondence**；
4. **Qwen 部署暂缓** —— 首批只编译 prompt bundle 不调用模型，`task-prompt-compiler` 的离线编译能力因此成为当前最优先的 Skill；
5. **LLM Judge 首版不引入**，只用确定性 checker；
6. 质量阈值沿用文档建议值待校准；**首批样本 100% 人工复核**；
7. **不绑定调度框架**，使用脚本 + 文件状态机。

其中第 1–4 项为 **[用户已确认]**，不得擅自推翻；第 5–7 项为工作默认值，可带记录理由修订。

项目定位已于 2026-08-24 澄清（详见 `DECISIONS.md` §19.2）：本 Pipeline 产出**点云 + 下游任务标注**一对交付物；`3D-GRPO` 是下游训练框架（SFT + GRPO 训练点云理解模型），当前与数据生成解耦。

对 §4.6 `task-spec-designer` 的直接影响：其维护的三类 adapter 中，**`pointcloud_native` 已有明确消费方**，优先级不低于 `qwen_2d_metadata`。Task Spec 必须保证 target 可映射到点云几何锚点，而不是只服务 Qwen 的文本接口。
