# 3D 数据生成 Agent / Skill 系统设计

> ⏸️ **本层已于 2026-08-25 暂缓（[用户已确认]）。**
>
> 用户决定先完整搭通第一、二、四层的主干（数据输入 → 提取/生成/处理 → 下游任务输出），
> **第三层的 Skill 封装与统一门禁框架推迟**，待主干可运行后再回来审视哪里值得用 Skill 提炼。
>
> **但本文档的规则仍然有效** —— 其中定义的校验项、修复策略、泄漏检查等**功能**
> 会以普通代码形式实现在主干上，只是暂不封装为 Skill、暂不建立 Orchestrator 与 G1–G6 框架。
>
> 详见 `PROJECT_HANDOFF.md` §19.4 的功能/封装双重归属对照表。

> 状态：设计草案，不代表已经开始实现或运行服务器任务  
> 记录日期：2026-08-23（Asia/Shanghai）  
> 上游约束：以 `PROJECT_HANDOFF.md` 中标记为“用户已确认”的内容为准

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
4. 距离、角度、遮挡、相交、净空、TTC 等可确定计算的真值优先由几何程序产生。
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
| Model-first constrained | *（当前无首批任务使用）* | 模型先生成候选，程序和规则验证 | 规划、解释、修复候选<br/>**2026-08-25：原列 Task Decomposition 与 Next-best-view，二者已移出范围，见 SPEC §40.1** |

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

Cross-view Correspondence、Metadata Verification、Viewpoint Transformation、Next-best-view 等任务均应复用同一编译接口，通过 Task Spec 定义自己的输入掩码、真值程序和 checker。

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

2026-08-24 已确定（详见 `PROJECT_HANDOFF.md` §19，机器可读形式见 SPEC §36）：

1. **首批真实数据集：UAVScenes 单个**；
2. **首版强制 metric**，relative / affine-invariant / pseudo 场景不具备任务资格；
3. **首批任务：3D Grounding（对象级）+ metric/situated 3D VQA + Cross-view Correspondence**；
4. **Qwen 部署暂缓** —— 首批只编译 prompt bundle 不调用模型，`task-prompt-compiler` 的离线编译能力因此成为当前最优先的 Skill；
5. **LLM Judge 首版不引入**，只用确定性 checker；
6. 质量阈值沿用文档建议值待校准；**首批样本 100% 人工复核**；
7. **不绑定调度框架**，使用脚本 + 文件状态机。

其中第 1–4 项为 **[用户已确认]**，不得擅自推翻；第 5–7 项为工作默认值，可带记录理由修订。

项目定位已于 2026-08-24 澄清（详见 `PROJECT_HANDOFF.md` §19.2）：本 Pipeline 产出**点云 + 下游任务标注**一对交付物；`3D-GRPO` 是下游训练框架（SFT + GRPO 训练点云理解模型），当前与数据生成解耦。

对 §4.6 `task-spec-designer` 的直接影响：其维护的三类 adapter 中，**`pointcloud_native` 已有明确消费方**，优先级不低于 `qwen_2d_metadata`。Task Spec 必须保证 target 可映射到点云几何锚点，而不是只服务 Qwen 的文本接口。
