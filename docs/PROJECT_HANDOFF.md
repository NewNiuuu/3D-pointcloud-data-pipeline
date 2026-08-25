# PROJECT_HANDOFF

> ## ⚠️ 阅读本文前必读（2026-08-25）
>
> **本文档第 1–18 节是历史记录**，按「只追加不改写」原则保留原貌。
> 其中关于**低空差异化能力**的表述（薄障碍、可飞行空间、净空、航迹、TTC、
> Next-best-view、occupancy、free space、Task Decomposition 等）
> **已于 2026-08-25 整体作废** —— 它们基于尚未获得数据时的假设。
>
> UAVScenes 实测为**近垂直下视航测飞行**（俯角中位 87.6°，对地约 33 m），
> 相机看不到飞行方向前方，上述能力**无法产生有效监督**。
>
> **现行能力范围见 §19.5**，实施依据见 `CLAUDE_CODE_PROJECT_SPEC.md` §40。
>
> 具体受影响处：§5.3 的 `<route_002>` 命名空间（保留但当前未使用）、
> §5.4、§6.2 的专家分类、§8.1 的 Pipeline 草图、§8.2 的 L3 字段、
> §9.2 的部分新增任务、§18.2 第 4 条。

> 项目：低空无人机 2D 数据集到 3D 点云场景理解数据生成 Pipeline  
> 交接日期：2026-08-23（Asia/Shanghai）  
> 用途：让未参与此前对话的新 Codex Agent 仅凭本文即可继续调研、设计和实施。  
> 当前状态：完成第一轮低空数据集调研、已有方案草图审阅、3D metadata 与任务体系初步设计；尚未开始正式 Pipeline 代码实现。

## 0. 状态标记与阅读方法

本文严格区分三类信息：

- **[用户已确认]**：用户明确决定，后续不得擅自推翻或改写。
- **[设计建议]**：当前讨论形成的推荐方案，技术上较完整，但仍可根据实验调整。
- **[待验证]**：需要下载数据、运行模型、核对许可或做消融实验后才能确认。

后续 Agent 尤其要注意：用户已经明确要求不要质疑项目的出发点。可以指出具体工程风险、数据质量问题和实验缺口，但不要再次把工作重心转向“2D 转 3D 是否足够新颖”或否定该项目方向。

## 1. 项目最终目标

**[用户已确认]** 构建一个面向低空无人机/近地空中场景的 3D 点云场景理解大模型数据生成与评测体系：

1. 从低空无人机拍摄或其他近地空中视角的 2D 图像/视频数据集出发。
2. 使用 **VGGT-Ω** 将 2D 多视角图像或视频转化为点云。
3. 使用数据集原生标注及一组专家模型，从 2D 数据、相机信息和重建结果中提取具有 3D 属性的 metadata。
4. 将 2D 图像/视频与结构化 3D metadata 一起提供给 Qwen3.5 等多模态大模型；Qwen **不直接读取原始点云**。
5. 生成和评测真正依赖 3D 空间信息的任务，包括已有的 3D Grounding、3D VQA、3D Caption、3D Task Decomposition、3D Dialogue，以及后续新增任务。
6. 点云作为场景载体、3D 标注落点和最终评测依据；语言模型通过可读的 metadata 学习和使用三维空间知识。

最终目标不是普通的低空 2D VQA，也不是只生成可视化点云，而是建立：

```text
低空 2D 数据集
    ├── VGGT-Ω ──> Point Cloud
    ├── 原生标注/专家模型 ──> 3D Metadata
    └── 2D 视觉输入 + 3D Metadata ──> Qwen ──> 3D 理解任务数据
```

## 2. 问题背景与研究动机

### 2.1 数据稀缺

高质量、规模化、带丰富语言与三维标注的低空无人机点云数据较少。相比之下，低空无人机图像和视频数据更丰富，因此项目希望通过 2D 数据扩展 3D 点云理解训练数据。

### 2.2 不能把 2D 问题简单搬到点云上

用户要求最终配套点云的任务和标注必须体现 3D 特性。例如，仅问“图中有什么目标”仍是 2D 识别；需要引入距离、高度、朝向、遮挡、拓扑、轨迹、视角变化、空间可达性等三维属性。

### 2.3 Metadata 是点云与语言模型之间的桥梁

Qwen3.5 的标准接口读取文本、图像和视频，不直接消费 PLY/LAS 点云。因此需要把点云和专家模型中的三维信息转成：

- 带稳定对象 ID 的结构化 JSON；
- 局部 3D Scene Graph；
- 相机位姿、对象坐标、OBB、中心线、轨迹等数值信息；
- 必要时配套 Depth、Normal、BEV、Semantic-ID 等 2D 渲染；
- 可由程序核验的任务答案与证据。

## 3. 用户最初提出的需求

### 3.1 数据集调研

用户最初要求调研：

- 无人机拍摄或其他空中视角拍摄的数据集；
- 最好是多视角，单视角也可以；
- 能够通过重建、深度反投影或伪深度转换成 3D 点云场景；
- 排除高空卫星/传统遥感数据，因为距离过远、局部放大分辨率不足；
- 需要关注规模、实拍/仿真来源、深度、掩码、位姿、点云等可用于 3D 转换的信息。

### 3.2 与项目已有清单去重

用户提供了公共飞书项目文档：

- `https://fcnvs2rldyv1.feishu.cn/wiki/Oc5Owx8hoifPGikC5ZgcxRzGnDd`

早期要求是阅读其中已有数据集，与新调研结果去重并形成新表格。用户随后明确强调：

- **不要修改原飞书文档**；
- 飞书是团队公共文档；
- 应输出独立文档，不写回飞书。

### 3.3 Pipeline 草图完善

用户在以下 Obsidian 笔记中写了初步 TODO 和草图：

- `/Users/newniuuu/Documents/NiuuuNotes/🐮脑碎片🧩/低空大脑/Awesome3D-Data-gen-pipeline/8.20～.md`

笔记中的核心内容包括：

- TODO：调研 datasets、设计 Novel Pipeline、设计 Novel 下游任务；
- 初始数据集示例：UAVScenes；
- 3D 特征模型：Depth Anything 3、VGGT-Ω、混元世界模型；
- 飞行相关专家：细线障碍、空中目标、通用碰撞、视频跟踪与风险融合；
- 初始图中包含 `img`、`VGGT-Ω`、`DA-3`、`point cloud`、`3D-meta-data`、`Qwen3.5`、`Agent`、`2D-QA`、`3D-QA` 等节点。

该笔记只被只读查看，当前 Session **没有修改它**。

## 4. 讨论中逐步形成的最终任务定义

### 4.1 固定的数据流

**[用户已确认]**

- 点云生成器固定为 VGGT-Ω。
- 3D metadata 可以来自：
  - 数据集原生标注；
  - VGGT-Ω 的几何输出；
  - 2D/视频专家模型；
  - 将 2D mask、track 或属性提升并融合到 3D 后得到的结果；
  - 几何程序根据基础 metadata 计算的派生属性。
- Qwen 接收：2D 图像/视频 + 结构化 3D metadata。
- Qwen 不直接读取点云。
- 任务必须依赖 3D metadata，不能退化为普通 2D QA。

### 4.2 已知任务

**[用户已确认]** 当前至少考虑：

- 3D Grounding
- 3D VQA
- 3D Caption
- 3D Task Decomposition
- 3D Dialogue

### 4.3 后续设计任务

**[设计建议]** 需要围绕上述五类任务完成：

1. 明确每类任务读取哪些 metadata 原子。
2. 明确哪些字段对 Qwen 可见，哪些字段作为隐藏监督目标。
3. 设计稳定对象/部件/区域/轨迹 ID，使语言输出可映射回点云。
4. 给每个样本保存答案推导程序和使用过的 metadata 字段。
5. 增加新的、与“2D + 3D metadata”架构高度匹配的任务。

## 5. 已确认的关键结论

### 5.1 Qwen 的职责边界

**[用户已确认]** Qwen 负责理解 2D 输入和 3D metadata，并完成语言与结构化任务，不负责原始点云编码。

**[设计建议]** Qwen 最适合承担：

- 自然语言理解与指代消解；
- 组合多个三维事实进行推理；
- 将符号事实转为 Caption、Dialogue 或任务计划；
- 输出对象 ID、数值、空间关系、子任务图等结构化答案；
- 在证据不足时表达不确定性或请求补充视角。

### 5.2 3D Metadata 不应只是最终答案表

**[设计建议]** 如果问题问距离，输入中不能直接包含 `distance_to_target`；应提供对象坐标、中心线、相机位置等上游字段，把距离作为隐藏 target。否则任务会退化成 JSON 字段抽取。

每个任务样本建议显式保存：

```json
{
  "metadata_input_fields": [
    "observer.position",
    "entities.centerline"
  ],
  "hidden_target_fields": [
    "derived.minimum_distance"
  ],
  "derivation_program": "minimum_point_to_polyline_distance"
}
```

### 5.3 稳定 ID 是统一任务接口

> ⚠️ **本节含已作废的能力表述（2026-08-25）** —— 现行范围见 §19.5。原文保留作为历史。


**[设计建议]** 使用：

- `<obj_021>`：对象；
- `<part_006>`：对象部件；
- `<wire_004>`：细线实例；
- `<region_009>`：空间区域；
- `<route_002>`：候选航迹；
- `<track_011>`：时序轨迹；
- `<pose_007>`：相机/无人机位姿。

Qwen 输出这些 ID，系统再将 ID 映射回点云实例 mask、OBB、中心线或轨迹。

### 5.4 几何数值需要可验证

> ⚠️ **本节含已作废的能力表述（2026-08-25）** —— 现行范围见 §19.5。原文保留作为历史。


**[设计建议]** 距离、角度、方位、高度差、遮挡、净空、相交、TTC 等真值优先由几何程序计算；语言模型用于理解、组合和表达，不应成为唯一数值真值来源。

### 5.5 尺度必须显式管理

**[设计建议]** 每个场景记录：

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

如果缺少 RTK/GPS、LiDAR、已知基线、GCP 或其他尺度锚点，应标记为 `relative`，不要把相对深度冒充米制真值。

## 6. 技术路线选择及理由

### 6.1 VGGT-Ω 作为点云主路径

**[用户已确认]** 点云由 VGGT-Ω 生成。

截至调研日，官方实现可输出：

- camera pose encoding；
- camera extrinsics/intrinsics；
- depth；
- depth confidence；
- camera/register tokens；
- 通过深度和相机反投影得到的点云/GLB 可视化；
- 256 text-alignment checkpoint 可输出 text-alignment embedding。

官方资源：

- Repository: <https://github.com/facebookresearch/vggt-omega>
- Project: <https://vggt-omega.github.io/>
- Paper: <https://arxiv.org/abs/2605.15195>

**[待验证]** 需要在实际 UAV 数据上评估尺度、动态拖影、薄结构、电线、弱纹理和大场景分块重建。官方曾发布 benchmark contamination 提示，因此不要直接把论文 benchmark 数字当成本项目性能依据；这不影响把模型作为数据生成组件进行实测。

官方曾报告 A100 峰值显存约为：

| 帧数 | 1 | 10 | 25 | 50 | 100 | 200 | 300 | 400 | 500 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GB | 6.02 | 6.67 | 7.80 | 9.66 | 13.37 | 20.82 | 28.26 | 35.71 | 43.15 |

该表只应用于初步资源估算，正式工程需在目标硬件和目标分辨率上重新 profiling。

### 6.2 专家模型用于补充 Metadata

> ⚠️ **本节含已作废的能力表述（2026-08-25）** —— 现行范围见 §19.5。原文保留作为历史。


**[用户已确认]** 3D metadata 可以来自原数据集，也可以由专家模型从 2D 图像/视频提取。

**[设计建议]** 专家模型分为：

- 几何：Depth Anything 3、VGGT-Ω 输出、可选第二重建器；
- 通用语义：open-vocabulary detection、panoptic/instance segmentation；
- 视频：tracking、optical flow、dynamic mask；
- 专项：细线障碍、空中目标、建筑/杆塔/树木/车辆/人员；
- 3D 派生：2D-to-3D lifting、跨视角实例融合、OBB/centerline/track 计算；
- 功能和行动：free space、occupancy、visibility、route、TTC 等算法模块。

Depth Anything 3 适合作为深度补充或一致性检查，但最终固定架构中不替代 VGGT-Ω 的点云主路径：

- <https://github.com/ByteDance-Seed/Depth-Anything-3>

混元体系需要区分重建与生成：

- WorldMirror 可作为辅助几何输出或重建交叉检查：<https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror>
- HY-World 2.0 更偏生成、重建和模拟的综合世界模型：<https://github.com/Tencent-Hunyuan/HY-World-2.0>

**[待验证]** 是否实际接入 DA3 或 WorldMirror，取决于 VGGT-Ω 在 UAV 数据上的失败模式，不能在没有小样本实验前增加不必要的多模型复杂度。

### 6.3 Qwen 使用结构化 metadata

**[用户已确认]** Qwen 只接收 2D 数据和专家生成的 3D metadata，不直接读取点云。

截至调研日，Qwen3.5 标准服务支持 text/image/video 输入、text 输出和 structured output：

- <https://help.aliyun.com/zh/model-studio/qwen3-5-plus>
- <https://help.aliyun.com/zh/model-studio/vision-model/>

因此推荐输入不是原始 PLY，而是：

- 选取的 RGB 视角或视频片段；
- 任务相关的局部 metadata 子图；
- 相机/观察者位姿；
- 对象、部件、区域和轨迹表；
- 可选 Depth/Normal/BEV/Instance-ID 渲染；
- 明确的坐标系、单位、来源和置信度。

## 7. 讨论过但已否决或不再采用的方案

### 7.1 直接写入公共飞书

**已否决。** 用户明确要求不要修改公共飞书。所有结果应以独立文件或对话内容交付。

### 7.2 未授权修改现有 Obsidian 项目笔记

**未执行。** `8.20～.md` 只读查看，没有被改动。当前研究项目配置还要求：只有当前任务出现精确同步口令 `确认并同步` 才能向配置的 Obsidian 输出目录写入；且配置只允许写入 `文献调研办公室`，并不包含该项目笔记路径。

### 7.3 让 Qwen 直接读取点云

**已否决。** 用户明确固定为 Qwen 读取 2D + 3D metadata；点云由 VGGT-Ω 生成并作为场景/评测载体。

### 7.4 由多个模型竞争生成主点云

**不再采用。** 最终口径固定为 VGGT-Ω 生成点云。DA3、WorldMirror 等只能作为专家、补充或质量校验候选，不得把架构重新描述为多个点云主干并列。

### 7.5 把高空遥感数据纳入主数据池

**已否决。** 用户明确排除卫星/高空遥感数据；近地空中视角和低空仿真可以保留。

### 7.6 继续质疑项目出发点或以新颖性否定路线

**已否决。** 此前讨论曾强调通用“2D→3D→QA”存在 prior art；用户随后明确要求不要质疑项目出发点。后续只需在既定架构下改进 metadata、任务和实验设计。可以记录相关工作用于任务设计和引用，但不要再次把它作为否定项目的论点。

### 7.7 让同一模型自由生成 metadata、问题和答案

**[设计上不推荐]** 这会造成循环自证和不可验证的语言真值。推荐使用专家/几何程序产生 metadata 和 target，再让 Qwen进行任务理解、组合、表达或自然化。

## 8. 当前确定的系统与数据架构

### 8.1 推荐 Pipeline

> ⚠️ **本节含已作废的能力表述（2026-08-25）** —— 现行范围见 §19.5。原文保留作为历史。


以下为**[设计建议]**，与用户固定架构兼容：

```text
0. Dataset Adapter / Scene Slicing
   └── 原始图像/视频、原生标注、相机/传感器信息

1. Geometry Reconstruction
   └── VGGT-Ω：camera、depth、depth confidence、point cloud

2. 2D Expert Perception
   └── detection、mask、tracking、thin obstacle、aerial target、flow

3. 2D-to-3D Lifting and Fusion
   └── 3D instance、OBB、centerline、visibility、track、scene graph

4. Metadata Derivation
   └── distance、height、orientation、occlusion、topology、motion、risk

5. Quality and Provenance
   └── source、model version、confidence、support views、scale status

6. Task Compiler
   └── field masking、question generation、target calculation、checker

7. Qwen Input Adapter
   └── 2D views/video + task-local 3D metadata

8. Task Dataset
   └── Grounding / VQA / Caption / Task Decomposition / Dialogue / new tasks
```

### 8.2 Metadata 分层

**[设计建议]**

#### L0：原始几何

- camera intrinsics/extrinsics；
- camera pose；
- depth/depth confidence；
- XYZ/RGB point；
- normal；
- coordinate frame、unit、scale source；
- reprojection error、coverage、density。

#### L1：3D 实体

- object/part/region/route/track ID；
- category、attributes；
- centroid、AABB、OBB、size、orientation；
- instance mask；
- visible views、occlusion ratio；
- static/dynamic；
- wire centerline/endpoints/radius；
- planes/surfaces。

#### L2：3D 关系

- distance、height difference、azimuth、elevation；
- front/back/left/right/above/below；
- near/intersect/contain/support/connect/hang；
- occludes/visible-from；
- cross-view correspondence；
- topology/connectivity；
- observer-relative relations。

#### L3：时间、功能和行动

> ⚠️ **本节含已作废的能力表述（2026-08-25）** —— 现行范围见 §19.5。原文保留作为历史。


- 3D trajectory、velocity、acceleration；
- TTC；
- occupancy/free space；
- visibility coverage；
- reachability；
- candidate route、minimum clearance；
- next-best-view；
- scene change；
- task precondition/completion condition。

### 8.3 推荐场景包目录

**[设计建议]**

```text
scene_000018/
├── scene.ply
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

### 8.4 推荐对象格式

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

### 8.5 推荐任务样本格式

```json
{
  "task_type": "3d_vqa.metric_reasoning",
  "visual_inputs": ["view_003.jpg", "view_007.jpg"],
  "metadata_inputs": {
    "observer": {},
    "entities": [],
    "geometry_primitives": {}
  },
  "question": "哪根电线距离无人机最近？",
  "target": {
    "object_id": "<wire_004>",
    "distance_m": 6.3
  },
  "evidence": {
    "used_entities": ["<wire_004>", "<wire_007>"],
    "used_fields": ["observer.position", "entities.centerline"],
    "derivation_program": "minimum_point_to_polyline_distance"
  },
  "quality": {
    "answer_confidence": 0.88,
    "geometry_confidence": 0.84
  }
}
```

## 9. 任务体系设计

### 9.1 现有任务如何使用 Metadata

#### 3D Grounding

推荐子任务：

- object grounding；
- multi-object grounding；
- part grounding；
- relational grounding；
- observer-relative grounding；
- occluded-object grounding；
- trajectory/route grounding。

输入可包含 2D views、候选实体表、位置/大小/可见性/关系等，但不得暴露 target ID。输出为对象、部件、区域、中心线或轨迹的稳定 ID，系统再映射回点云。

#### 3D VQA

推荐类别：

- metric：距离、尺寸、高度、角度；
- situated：从当前无人机位姿出发的左右前后；
- topology：连接、包含、区域连通；
- visibility：遮挡、可见视角、观察完整度；
- temporal：运动、变化、轨迹、TTC；
- counterfactual：修改位置、朝向、尺度或对象后重新判断。

#### 3D Caption

推荐层级：

- object caption；
- part caption；
- region caption；
- scene layout caption；
- trajectory caption；
- visibility-aware caption；
- risk-aware caption。

Caption 除自然语言外应保存结构化 claims，便于检查描述是否忠实覆盖 metadata。

#### 3D Task Decomposition

每个步骤绑定：

- action；
- target ID；
- 3D goal region/waypoint；
- spatial constraints；
- precondition；
- completion condition；
- evidence。

除生成计划外，还可做 plan verification、约束冲突检测和缺失步骤补全。

#### 3D Dialogue

推荐对话类型：

- 跨轮对象指代；
- 观察者位姿变化；
- 多相似目标时主动澄清；
- metadata/轨迹更新后的答案修正；
- 证据不足时不确定性表达；
- 多视角和时间记忆。

### 9.2 推荐新增任务

> ⚠️ **部分条目当前无数据支撑，已降级为后续目标**：Next-best-view Prediction、Route/Plan Critique。见 §19.7。
> 现行能力范围见 §19.5。其余条目（Cross-view Correspondence、Metadata Verification/Completion、
> Viewpoint Transformation、Scene Graph Query、Geometry-aware Retrieval、3D Change Reasoning、
> Spatial Counterfactual、Uncertainty-aware Reasoning、Grounded Measurement Dialogue）仍然有效。

以下为**[设计建议]**，尚未确定实现优先级：

1. **Cross-view 3D Correspondence**：判断不同视角的 2D 实例是否对应同一 3D 实体。
2. **3D Metadata Verification**：找出与图像、其他 metadata 或物理约束冲突的 metadata。
3. **3D Metadata Completion**：补全缺失空间关系、对象属性、遮挡或轨迹片段。
4. **Viewpoint Transformation**：在不同无人机位置和朝向之间转换相对空间关系。
5. **Next-best-view Prediction**：根据目标、遮挡、视锥和候选位姿选择下一观察位置。
6. **3D Scene Graph Query**：把自然语言转成可执行的三维图查询条件。
7. **Geometry-aware Retrieval**：根据空间布局检索场景、区域、对象组或轨迹片段。
8. **3D Change Reasoning**：识别并解释同一地点跨时间的三维变化。
9. **Spatial Counterfactual Simulation**：修改位置、朝向、尺寸或障碍后重新推理。
10. **Uncertainty-aware 3D Reasoning**：依据来源和置信度决定回答、区间估计、拒答或请求补观测。
11. **Route/Plan Critique**：识别计划中违反几何、可见性或任务约束的步骤。
12. **Grounded Measurement Dialogue**：在多轮对话中同时保持对象/部件 grounding 和 metric quantity。

建议第一批新增任务优先考虑：Cross-view Correspondence、Metadata Verification、Viewpoint Transformation、Uncertainty-aware Reasoning、Next-best-view、Scene Graph Query。

## 10. 已调研数据集与去重结果

### 10.1 已有飞书清单快照

早期独立调研文档记录的飞书已有数据集为：

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

这只是 2026-08-23 的快照；继续工作前应重新读取最新飞书内容，但仍然只读。

### 10.2 已整理的 22 个新增候选

独立交付物：

- `deliverables/低空无人机_新增3D可转化数据集清单_2026-08-23.docx`

当时与上述飞书清单逐项去重，记录为新增候选：

| 等级 | 数据集 | 来源 | 核心 3D 条件 |
|---|---|---|---|
| S | UAVScenes | 实拍 | RGB + Livox 点云、6DoF 位姿、标定、语义点云/网格 |
| S | Dronescapes | 实拍 | 视频、SfM 位姿/内参、度量深度、法向、语义子集 |
| S | H3D / Hessigheim 3D | 实拍 | 高密度机载 LiDAR、RGB、标注点云、纹理网格、多时相 |
| S | SkyLume | 实拍 | 五向相机、RTK 重复飞行、COLMAP 位姿、网格/LiDAR 深度、法向 |
| S | UAVStereo | 实拍+仿真 | 立体 RGB、PFM 视差、网格/LiDAR 几何 |
| S | UrbanScene3D | 实拍+仿真 | LiDAR、纹理网格、多套影像/位姿、仿真深度/框/分割 |
| S | ClaraVid | 仿真 | 度量深度、语义/实例/动态 mask、相机参数、场景点云 |
| A | NTU VIRAL | 实拍 | 双相机、双 3D LiDAR、IMU、UWB、Leica 真值、标定 |
| A | MUN-FRL | 实拍 | 单目 RGB、3D LiDAR、IMU、RTK-GNSS、标定 |
| A | MARS-LVIG | 实拍 | RGB、Livox、IMU、GNSS、RTK 和 DJI L1 地图真值 |
| A | Mid-Air | 仿真 | 深度、法向、语义、视差、遮挡 mask、位姿、IMU/GPS |
| A | UAV3D | 仿真 | 多机多视角 RGB、像素语义、3D box |
| A | U2UData+ | 仿真 | 多机 RGB + LiDAR、3D box/track、协同感知 |
| A | IllumUAV-Sim | 仿真 | 对齐昼夜 RGB、深度、法向、相机参数 |
| B | UAPD / DAPM | 仿真 | RGB、深度、随机高度/姿态/FOV |
| B | UAVPairs | 实拍 | 高重叠多视角图像、SfM 匹配关系 |
| B | UAVID3D | 实拍 | RGB + 热红外、高重叠环绕影像、GPS |
| B | Ready for 3D Reconstruction | 实拍 | GCP/checkpoint、2D 对应、MVS 子集、TLS 点云 |
| B | FlyAwareV2 | 实拍+仿真 | RGB、深度、语义 mask；实拍深度含单目伪深度 |
| B | LAMBDA | 仿真 | RGB、LiDAR、4D radar、CSI、depth、IMU、多机 |
| C | UAVid | 实拍 | 4K 视频、8 类语义；几何和位姿较弱 |
| C | VisDrone | 实拍 | 大规模检测/跟踪框；无深度和位姿 |

首批可行性冲刺曾建议：

- UAVScenes：真实语义点云；
- Dronescapes：真实视频 + 位姿/度量深度；
- H3D：高密度 LiDAR 语义；
- ClaraVid：完整仿真标签；
- UAVStereo：立体深度。

SkyLume 和 UrbanScene3D 体量较大，建议第二阶段再处理。

**[待验证]** 这些候选尚未全部实际下载；许可、文件完整性、官方链接、别名和镜像需要正式入库前复核。不能仅根据论文或项目页假定可用于商业训练、权重发布或衍生点云再分发。

## 11. 重要模型、论文、仓库和资源

### 11.1 直接工程组件

- VGGT-Ω：<https://github.com/facebookresearch/vggt-omega>
- Depth Anything 3：<https://github.com/ByteDance-Seed/Depth-Anything-3>
- Hunyuan WorldMirror：<https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror>
- HY-World 2.0：<https://github.com/Tencent-Hunyuan/HY-World-2.0>
- Qwen3.5 官方说明：<https://help.aliyun.com/zh/model-studio/qwen3-5-plus>

### 11.2 Metadata 与任务设计相关工作

- SceneVerse++：2D 视频提升到结构化 3D supervision 的参考实现，<https://sv-pp.github.io/>
- SceneVerse：scene graph 到多类 3D-language 数据的参考，<https://scene-verse.github.io/>
- ConceptGraphs：2D foundation model 结果融合为 open-vocabulary 3D scene graph，<https://concept-graphs.github.io/>
- SpatialRGPT：scene graph/depth 支撑空间推理，<https://arxiv.org/abs/2406.01584>
- LLaVA-3D：2D patch 与 3D position embedding 结合的参考，<https://arxiv.org/abs/2409.18125>
- Grounded 3D-LLM：referent token 和 grounded dialogue 的参考，<https://arxiv.org/abs/2405.10370>
- MM-Spatial：metric size/distance、空间关系和 3D grounding，<https://arxiv.org/abs/2503.13111>
- ASHiTA：scene-grounded hierarchical task decomposition，<https://openaccess.thecvf.com/content/CVPR2025/html/Chang_ASHiTA_Automatic_Scene-grounded_HIerarchical_Task_Analysis_CVPR_2025_paper.html>
- DAAAM：4D scene graph、时空 QA 和长期记忆，<https://openaccess.thecvf.com/content/CVPR2026/html/Gorlo_Describe_Anything_Anywhere_At_Any_Moment_CVPR_2026_paper.html>
- Descrip3D：对象级关系描述支持 grounding/caption/QA，<https://openaccess.thecvf.com/content/WACV2026/html/Xue_Descrip3D_Enhancing_Large_Language_Model-based_3D_Scene_Understanding_with_Object-Level_WACV_2026_paper.html>
- Ground3D-LMM：grounded measurement 和 metric-aware 3D dialogue，<https://arxiv.org/abs/2607.05493>
- SpatialThinker：scene graph 与 spatial reward 的参考，<https://arxiv.org/abs/2511.07403>
- PointLLM-R：3D reasoning supervision 的参考；本项目不采用其“模型直接读点云”接口，<https://arxiv.org/abs/2605.22013>

### 11.3 专项专家

> ⚠️ **薄障碍专项模型（EDFNet / PowerLine-MTYOLO / TTPLA-YOLACT）当前不适用**
> —— 近垂直下视数据无薄障碍监督（§19.5）。保留待引入前视数据集。


- 笔记中的 `ETFNet` 应更正为 **EDFNet**：Early Fusion of Edge and Depth for Thin-Obstacle Segmentation in UAV Navigation，<https://arxiv.org/abs/2604.09694>
- EDFNet/细线检测只能作为候选专家输出，超细结构仍需多视角、几何一致性和置信度检查。
- 笔记提到小型无人机检测 SPAE-YOLOv8；尚未完成官方实现、数据许可和真实泛化能力核验。

## 12. 重要参数、配置和目录

### 12.1 当前项目根目录

```text
/Users/newniuuu/develop/project_space/Research-Assistants/Domain-researcher
```

### 12.2 当前关键文件

```text
AGENTS.md
research-config.toml
.agents/skills/research-emerging-domain/
deliverables/低空无人机_新增3D可转化数据集清单_2026-08-23.docx
PROJECT_HANDOFF.md
```

### 12.3 用户现有项目笔记

```text
/Users/newniuuu/Documents/NiuuuNotes/🐮脑碎片🧩/低空大脑/Awesome3D-Data-gen-pipeline/8.20～.md
```

关联草图：

```text
/Users/newniuuu/Documents/NiuuuNotes/🐮脑碎片🧩/draw/pipeline design.md
```

二者当前均不得擅自修改。

### 12.4 Obsidian 同步配置

- 精确同步口令：`确认并同步`
- 配置允许的输出目录：Obsidian vault 下的 `文献调研办公室`
- 不得写入其他 Obsidian 目录。
- 不得删除或移动已有 Obsidian 文件。
- 不得下载 PDF，除非用户另行明确授权。

### 12.5 统一几何来源枚举

建议保留：

```text
direct_lidar
stereo
sfm_mvs
rendered_depth
pseudo_depth
```

每个场景或帧记录 `depth_source` 和 `metric_scale`，不同来源不能混成同一种真值口径。

### 12.6 数据切分原则

**[设计建议]**

- 按地理场景、区域、完整飞行或轨迹切分；
- 同地点重复航线和相邻帧必须绑定在同一 split；
- 禁止逐帧随机切分造成泄漏；
- 真实与仿真结果分别报告；
- 保留跨数据集 zero-shot test；
- 高质量人工复核测试子集与大规模自动训练集分离。

## 13. 当前已完成的工作

1. 阅读并只读核对了用户提供的公共飞书数据集清单快照。
2. 调研并整理了 22 个未出现在当时飞书清单中的低空/近地空中数据集候选。
3. 生成独立 DOCX：
   - `deliverables/低空无人机_新增3D可转化数据集清单_2026-08-23.docx`
4. 只读检查了用户的 `8.20～.md` Pipeline 草图及关联 Excalidraw 文本元素。
5. 核验了 VGGT-Ω、DA3、WorldMirror、Qwen3.5 等主要组件的官方资料。
6. 形成了 L0–L3 的 3D metadata 分层方案。
7. 形成了面向 Qwen 的 scene package、对象 schema 和任务 JSONL 初稿。
8. 重构了 3D Grounding、VQA、Caption、Task Decomposition、Dialogue 如何使用 metadata。
9. 提出了 Cross-view Correspondence、Metadata Verification、Metadata Completion、Viewpoint Transformation、Next-best-view、Scene Graph Query、Counterfactual Reasoning 等新增任务。
10. 明确记录了不修改飞书、不擅自改 Obsidian 笔记、Qwen 不直接读点云等边界。

## 14. 尚未完成的工作

### 14.1 数据集层

- 重新读取最新飞书清单并复核去重结果；
- 为 22 个候选建立机器可读 dataset card；
- 核对每个数据集最新链接、许可、文件列表、校验和和版本；
- 对首批候选各下载 1–3 个小样本；
- 实际验证图像、位姿、内参、尺度、时间戳和标注可用性；
- 最终确定第一阶段数据集，不要默认沿用早期建议。

### 14.2 VGGT-Ω 几何层

- 建立标准输入 adapter；
- 在 UAVScenes/Dronescapes 等样本上跑通；
- 评估深度、位姿、点云完整度和尺度；
- 检查动态拖影、薄线丢失、天空、玻璃/水面、重复纹理和大尺度场景漂移；
- 决定关键帧采样、场景分块、融合和下采样策略；
- 为点云生成 provenance 和 confidence。

### 14.3 专家模型层

> ⚠️ **薄障碍专项模型（EDFNet / PowerLine-MTYOLO / TTPLA-YOLACT）当前不适用**
> —— 近垂直下视数据无薄障碍监督（§19.5）。保留待引入前视数据集。


- 已完成官方资料层面的专家模型调研和首版组合建议，下一步需要完成许可证审查、checkpoint 获取和 UAV 小样本实测；
- 语义/实例首版候选：Grounded-SAM-2、SAM 2.1、SEA-RAFT、OneFormer、CABiNet、Florence-2、DINOv2；
- 几何专家优先顺序已修订为 MoGe-3、DSINE、DA3-1.1；DA3-Streaming 仅用于长视频，CoTracker3/Trace Anything 用于轨迹和动态研究；
- 验证 Grounded-SAM-2/SAM 2.1 的 mask、track 和跨视角身份稳定性；
- 验证 SEA-RAFT residual flow，而不是直接把光流幅值当作动态物体；
- 核验 PowerLine-MTYOLO、EDFNet、TTPLA-YOLACT 等薄障碍专项模型的许可和真实 UAV 能力；
- 设计 mask/track 到 3D 的投影和跨视角实例融合；
- 建立专家冲突融合和置信度校准。
- WorldMirror 仅允许作为推理/评估或受控 refiner，不能把其输出用于 Qwen/VLM 训练 metadata。

### 14.4 Metadata 层

- 冻结 JSON schema；
- 定义坐标系和单位规范；
- 实现对象、部件、区域、轨迹的稳定 ID；
- 实现 distance、angle、visibility、occlusion、topology 等派生程序；
- 决定哪些 metadata 是首版必需，避免一开始实现所有 L3 属性。

### 14.5 任务层

- 为五类已有任务编写正式 task spec；
- 确定首批新增任务优先级；
- 为每类任务定义 metadata input mask 和 hidden target；
- 实现 deterministic checker；
- 定义训练/验证/人工审核格式；
- 防止目标泄漏和纯 2D shortcut。

### 14.6 实验与评测

- 建立 2D-only、2D+metadata、metadata-only 等对照；
- 定义几何和语言的联合指标；
- 进行 scene-level split 和跨数据集评测；
- 评估 metadata 噪声、缺失和错误对任务性能的影响；
- 验证 Qwen 是否真的使用 metadata，而不是只依赖图像或语言先验。

## 15. 当前不确定问题与风险

### 15.1 用户尚需决定的问题

1. 第一阶段优先做哪一个数据集或哪两个互补数据集。
2. 首版重点任务：五类传统任务全覆盖，还是先做 2–3 个代表任务。
3. 是否要求 metric scale；若要求，数据集筛选将明显收紧。
4. Qwen 具体使用 API 版本、开源权重或云端模型。
5. 最终点云理解模型是否另有原生点云 encoder；目前只确认 Qwen 不读点云。
6. 最终成果更偏数据集、benchmark、训练模型还是完整 Pipeline 工具链。

### 15.2 工程风险

- VGGT-Ω 在低空大场景、快速运动和薄线上的实际表现未验证。
- 单目或重建深度可能只有相对尺度。
- 动态物体跨视角融合会形成 ghost points。
- 2D mask 的小误差在深度边界处会被放大成 3D 标签污染。
- 电线、绳索、细枝可能在点云中缺失，单一专家输出不能视为可靠真值。
- 任务若直接暴露派生字段，会退化成 metadata lookup。
- Qwen 可能只依赖 2D 图像，忽略 metadata，需要构造反事实和遮挡样本进行验证。
- 仿真和真实数据存在明显域差异。
- 数据许可可能限制商业训练、衍生点云或模型权重发布。
- 大规模多视角重建、渲染和 Qwen 数据生成成本尚未测算。

### 15.3 研究与证据边界

外部资料检索截止为 2026-08-23。多数核心模型和任务论文已通过官方仓库、项目页、arXiv 或 CVF 页面核验，但 22 个数据集没有全部下载验证，不能承诺零遗漏或所有字段当前仍有效。

## 16. 下一阶段建议执行顺序

### Phase 1：冻结最小可行范围

1. 与用户确认 1–2 个数据集。
2. 确认是否强制 metric scale。
3. 选择两个基础任务：建议 3D Grounding + 3D VQA。
4. 选择一个新增任务：建议 Cross-view Correspondence 或 Metadata Verification。
5. 冻结最小 L0/L1/L2 schema，不先实现完整 L3。

### Phase 2：跑通单场景闭环

1. Dataset adapter。
2. VGGT-Ω 重建点云。
3. 一个通用实例分割/跟踪专家。
4. 2D mask 提升到 3D。
5. 生成稳定 object ID 和 OBB/centroid/visibility。
6. 生成少量 task JSONL。
7. Qwen 输入 2D views + metadata 并输出结构化答案。
8. 程序检查答案并映射回点云。

### Phase 3：建立质量和对照实验

1. 记录 provenance、confidence 和 scale status。
2. 比较 2D-only、metadata-only、2D+metadata。
3. 增加 metadata shuffle、field masking 和 counterfactual 测试。
4. 检查 Qwen 是否真正利用三维字段。

### Phase 4：扩展任务和专家

1. Caption、Dialogue、Task Decomposition。
2. 细线、空中目标和动态轨迹专家。
3. Viewpoint Transformation、Uncertainty-aware Reasoning。
   （2026-08-25：移除 Next-best-view，属主动感知，见 §19.5。）
4. 多数据集和仿真—真实泛化。

### Phase 5：规模化和 Benchmark

1. 批处理、缓存、失败重试和版本管理。
2. 大规模 task compilation。
3. 人工复核 Gold test set。
4. 场景级 split 和跨数据集测试。
5. 发布前许可和衍生数据审查。

## 17. 新 Agent 必须遵守的约束和原则

1. 不要质疑或否定用户的项目出发点；围绕既定架构解决技术问题。
2. 固定口径：点云由 VGGT-Ω 生成；Qwen 读取 2D + 3D metadata，不直接读点云。
3. 任务必须体现 3D 信息，避免退化成普通 2D QA 或 metadata 字段抄写。
4. 清楚区分用户决定、设计建议和待验证假设。
5. 不修改公共飞书文档。
6. 不擅自修改用户现有 Obsidian 笔记。
7. 技术调研必须使用 `research-emerging-domain` skill，并实时联网核验外部事实。
8. 普通调研不得修改 `AGENTS.md`、`research-config.toml`、`.agents/skills/`、`tests/` 或依赖文件。
9. 没有精确同步口令 `确认并同步`，不得写入配置的 Obsidian 输出目录；即使授权也不得写出允许目录。
10. 不下载 PDF，除非用户明确授权。
11. 数据集信息必须区分实拍/仿真、原生深度/重建深度/伪深度、metric/relative scale。
12. 所有自动生成 metadata 应保留来源、模型版本、输入帧、置信度和单位。
13. 涉及许可、公开下载、模型版本或 API 能力时重新联网核验，不沿用旧快照。
14. 实施前优先做小样本闭环，不直接全量下载或大规模生成。

## 18. 后续设计更新：专家模型与质量规则

2026-08-23 收到一份基于官方论文、仓库、项目页和 checkpoint/model card 的 2D/几何专家调研报告。报告未下载权重，也未进行本地 UAV 实测。

已经同步到主规格和 README 的结论：

1. 首版建议采用 Grounded-SAM-2 + SAM 2.1 + SEA-RAFT + OneFormer/CABiNet + DA3/Metric3Dv2，并使用 Florence-2 和 DINOv2 补充属性与跨视角 embedding。
2. detector box 只能用于候选和提示，不能把 box 内所有像素直接提升到 3D。
3. 动态区域必须使用 `observed flow - VGGT static flow` 的残差证据，不能直接使用光流幅值。
4. 无效几何必须分别保留 sky、water、reflection/transparency、low-depth-confidence、reprojection-inconsistent、dynamic-geometry 等 reason masks。
5. 可飞行空间必须在 3D occupancy/free-space 中结合无人机尺寸、安全裕量和不确定性计算。
6. 薄障碍只能作为软证据，必须保存概率、骨架、边界置信度、多帧支持和 3D 线拟合残差。
7. 新增 `expert-registry-manager` Skill，负责代码/权重/API 许可、checkpoint、I/O、坐标约定、运行频率和 UAV 验证状态。
8. SAM 3、SegFormer、DSINE、UFM、DAM、EDFNet、PBSeg 等存在不同程度的许可或缺少明确许可问题，未审查前不得启用。

更新后的设计入口：

- `README.md`：人类可读总览；
- `CLAUDE_CODE_PROJECT_SPEC.md`：服务器实施主规格；
- `AGENT_SKILL_SYSTEM_DESIGN.md`：Agent/Skill 详细设计。

### 18.1 第二轮几何专家调研修订

同日完成第二轮几何/3D metadata 专家调研，仍只核验官方资料，未下载权重、未做 UAV 实测。它没有推翻第一轮语义专家链路，而是补充并修正了独立几何专家支路：

1. 最优先验证的几何第三通道改为 MoGe-3，而非直接把 DA3/Metric3Dv2 作为首选。
2. DSINE用于独立 normal/uncertainty；DA3-1.1用于 depth/pose/sky/scale cross-check；DA3-Streaming仅在长视频需求下启用。
3. CoTracker3提供2D tracks/visibility，Trace Anything提供稠密3D轨迹候选；二者当前权重许可限制进入商业训练流水线。
4. WorldMirror许可证禁止用输出改进其他 AI 模型，因此只能用于推理/评估，不能进入Qwen训练metadata。
5. 深度必须标记为 metric、externally anchored、relative、affine-invariant或pseudo；“模型声称metric”不等于UAV域尺度可靠。
6. 多专家不得投票生成真值。需要先做SE(3)/Sim(3)/scale-shift对齐，再计算深度、法向、相机、重投影和track residual，并校准为错误概率。
7. 必须防止循环验证：使用VGGT-Ω prior运行的WorldMirror只能叫refiner；MoGe/MetricAnything及VGGT/DA3等相关模型不得计为完全独立证据。
8. 第一版occupancy/free-space/visibility/clearance/TTC仍由VGGT-Ω→TSDF/voxel/ESDF/raycast及确定性运动程序计算。
9. 小样本建议至少覆盖40–60个短片段和8–12个长片段；完整语义专家比较可扩展至100–300段。

### 18.2 第四层：下游任务与能力补全

> ⚠️ **本节第 4 条已于 2026-08-25 作废** —— 「低空差异化能力重点是薄障碍、开放空域
> free/unknown/occupied、飞行净空、route、TTC、动态风险、Next-best-view」基于
> 尚未获得数据时的假设。实测证明数据集不支持这些能力。**现行定义见 §19.5**。
> 本节保留作为历史记录与未来引入前视数据集时的参考。

用户明确要求把下游任务设计从metadata Pipeline和Skill系统中独立出来，成为第四个架构层。该层的目标不是只生成Qwen问答，而是生成可复用于Qwen、原生点云模型和多模态3D模型的统一任务标注。

关键决策：

1. Canonical Task Record必须保留`pointcloud_ref`、3D target geometry、visual inputs、visible metadata、hidden target、evidence、checker、supervision level和adapter列表。
2. 每个任务必须映射到点索引/点mask、OBB、中心线、体素、相机位姿、轨迹、路线或确定性空间关系。
3. 任务体系分为五组：原生3D感知；空间与视角推理；低空飞行/安全/主动感知；Grounded 3D语言与规划；metadata/scene graph/change reasoning。
4. 低空差异化能力重点是薄障碍、开放空域free/unknown/occupied、飞行净空、route、TTC、动态风险、Next-best-view和unknown-space-aware decision。
5. 新增`task-spec-designer` Skill，负责3D必要性、低空特异性、监督等级、能力覆盖和多模型adapter设计；`task-prompt-compiler`继续负责实例化和提示词编译。
6. 当前共设计8个Skill，尚未创建实际Skill目录。
7. Task Release顺序：先做可移植基础监督，再做低空专项能力，最后扩展语言、对话、规划和长期推理。

## 19. 2026-08-24 实施边界决策

用户在实施启动前确认了 `CLAUDE_CODE_PROJECT_SPEC.md` §35 要求先行澄清的四项阻塞决策。以下四条为 **[用户已确认]**，后续 Agent 不得擅自推翻：

1. **首批数据集：UAVScenes 单个。** 真实多视角、含 Livox 点云与 6DoF 位姿，作为唯一 Phase 1 数据集。其余候选（含 Dronescapes、H3D、ClaraVid）留待后续阶段，不得视为已选定。
2. **首版强制 metric scale。** 只接受具备外部尺度锚点（LiDAR/RTK/GCP）的场景；`relative`、`affine_invariant`、`pseudo` 深度的场景在首版不具备任务资格，无论其数据集等级。
3. **首批任务三类：** `3d_grounding.object`、`3d_vqa.metric_or_situated`、`cross_view_correspondence`。第三项选择 Cross-view Correspondence 而非 Metadata Verification，因其 3D 必要性更强。
4. **Qwen 部署暂缓决定。** 首批工作按 SPEC §34 vertical slice 第 1–10 步推进，**只编译 prompt bundle、跑泄漏检查和 checker 复现验证，不调用任何模型**。第 11 步之前重新确认部署方式与预算。

同时确立的工作默认值（**[设计建议]** 级别，非用户确认的不变量，可带记录理由修订）：

- 最终交付物暂定 pipeline 工具链 + 小规模 benchmark；
- 首版不引入 LLM Judge，只用确定性 checker；
- 首批样本 100% 人工复核；
- 不绑定调度框架，使用脚本 + 文件状态机；
- 质量阈值沿用文档建议值，待有真实数据后校准。

### 19.1 环境现实约束（2026-08-24 核实）

实施环境已从交接文档记录的 macOS 本地目录迁移至 Linux 服务器 `/home/aiscuser/nyp`，8×A100-40GB。核实结果：

- 本地 `data/` 目录下 9 个数据集**只有 QA 标注 JSON，不含任何图像、视频或点云**，且均属飞书已有清单（FloodNet、LADI、AirCopBench、UrbanVideoBench、nuScenes、AVIMath、RefDrone、AAVG、DVG），服务于同级的 `3D-GRPO` 项目，**不能用于本 Pipeline 的重建输入**。
- 22 个新增候选**一个都未落盘**。因此 Layer 1 的真实起点是许可申请与小样本下载，UAVScenes 的获取是首个关键路径。
- VGGT-Ω 未安装。作为固定的点云主路径，其可获取性与可用性必须在 Layer 2 开工前核验；若不可用，须停下来重新讨论而非静默替换（受 §7.4 约束）。
- 磁盘可用约 5.2T；`/blob` 挂载点当前显示 0 字节，可写性待确认。
- 本仓库配置了 GitHub remote `origin → WoodSerenity/uavlm.git`，凭证管理规则见 `MANUAL_INPUTS.md`。

### 19.2 项目定位与 3D-GRPO 的关系（2026-08-24 已澄清）

**[用户已确认]**

**本 Pipeline 的最终产物**：2D 数据集对应的**点云**，以及该点云对应的**下游任务标注**。两者是一对交付物，缺一不可 —— 只生成点云不算完成。

**Blob 上的点云的定位**（`Pointcloud-VQA/`、`PointCloud-grounding/`，见 `MANUAL_INPUTS.md` §3）：

- 它们是同事已用 VGGT-Ω 从 `data/` 各 2D 数据集转出的**最终点云结果**，即本 Pipeline"2D → 点云"这一步在那批数据集上**已经完成**；
- 同时，由于下游任务标注必须与点云绑定，这批点云**也可以**作为生成下游标注的中间产物；
- 究竟是否纳入本轮标注生成，**取决于后续任务设计**，当前不预先锁定。

**3D-GRPO 的定位**：

- 它是本 Pipeline **下游的训练框架**，不是数据生成的一部分；
- 用途：拿本 Pipeline 产出的点云 + 下游任务标注，先做 SFT，再用 GRPO 训练自有的**点云理解模型**；
- **当前与数据生成工作解耦**，无需为其调整 Pipeline 排期；
- 它目前只是初步框架，待新类型数据产出后再相应修改。

**对架构的影响**：SPEC §39/§41 定义的三类 adapter 中，`pointcloud_native`（原生点云模型 adapter）是 3D-GRPO 的直接消费接口，因此其优先级**不低于** `qwen_2d_metadata`。Canonical Task Record 必须保留 `pointcloud_ref` 与 3D target geometry（SPEC §41 已有此要求），这一条从"为将来预留"变为"已有明确消费方"。

注意这不改变铁律 2/3：Qwen 在本架构中仍然只读 2D + metadata，不直接读点云。点云面向的是 3D-GRPO 那条原生点云路线。

### 19.5 低空差异化能力范围重定义（2026-08-25）

**[用户已确认]**

**背景**：用户提供了一份基于大疆社区、Reddit r/drones/r/dji、MavicPilots 的无人机飞手
痛点调研，并要求结合手上实际材料设计下游任务，明确表示不必被该报告的优先级牵着走。

**实测发现（决定性）**：UAVScenes 相机**近垂直下视，俯角中位 87.6°（范围 84.6–88.8°），
对地约 33 m**。这是航测/测绘飞行，**相机永远看不到飞行方向前方**。

**因此当前实施范围不含的能力**（§18.2 与 §9.2 的相应设计**保留为后续目标**）：

薄障碍避让、前向避障、通道净空、可飞行体积、航迹可行性与瓶颈、TTC 与动态碰撞风险、
Next-best-view 与主动感知、检查视角规划、有人机/鸟类避让、任务分解与计划批判。

**理由**：强行生成会产出「形似导航训练数据、实则无有效监督」的样本，训练出虚假能力，
违反铁律 5。

**新的能力范围（方案 A —— 围绕数据实际支持重新定义）**，按优先级：

| 优先级 | 能力 | 依据 |
|---|---|---|
| C1 | 感知可信度与失效归因 | LiDAR 与视觉深度残差可程序化产出失效标注；HKisland 约 40% 水面、HKairport 约 52% 均质硬化面为天然大样本；`*_Evening` 与日间航次同地点同航线，构成受控成像退化对照 |
| C2 | 安全降落区评估 | 垂直下视正是评估降落区的视角；坡度/粗糙度由 LiDAR 确定性计算，表面类型有人工标注，动态占用有重复航次 |
| C3 | 米制地形与高度推理 | Nadir 图像几乎不提供深度线索，这类数值无外观对应物，3D 必要性最强 |
| C4 | 跨时相变化与光照鲁棒 | `*_Evening` 配对，几何真值相同，可区分真实三维变化与表观差异 |

**排序依据**：不是「无人机需要什么能力」，而是「哪些能力的监督信号极难获得，
而本数据集恰好能可靠产出」。三种难获取的监督形态 —— 与外观矛盾的答案、外观相同但答案不同、
无外观对应物的数值 —— 本数据集均可大规模产出。

**曾考虑但未采纳的方案 B**：保留导航能力并引入前视/侧视数据集（Mid-Air / FlyAwareV2 / UAVStereo）。
用户选择方案 A 先行，理由是先用现有材料跑通完整链路；方案 B 作为后续扩展，届时
SPEC §14.6/§14.7 的规则可直接启用，无需重写。

**已同步修订**：SPEC §1/§13/§14.15/§16/§20.3/§23.4/§28.2/§34/§40/§41/§43/§44/§45/§46/§47/§49/§51、
README 第四层与固定原则、AGENT_SKILL_SYSTEM_DESIGN §4.6、三个 Task Spec 的
`low_altitude_specificity`（其中 metric 任务原声称「候选实体包含电线、杆塔」为**事实错误**，已改正）。

### 19.6 标注格式契约：ShareGPT（2026-08-25）

**[用户已确认]**

标注格式**尽量满足 ShareGPT 格式**：

```json
{"conversations": [{"from": "human", "value": "..."},
                   {"from": "gpt",   "value": "..."}]}
```

**3D-GRPO 与 SFT 都会依据数据的具体类型再做调整** —— 因此下游训练框架的现状
（如现行 reward 只支持单选字母匹配）**不构成对数据设计的约束**。

对本 Pipeline 的含义：`pointcloud_native` adapter 的产出目标是**规范的 ShareGPT 记录**，
而非迁就某个框架的当前实现。adapter 的职责是**把判分所需信息给全**
（checker 名、容差、hidden_target），训练侧据此按数据类型实现 reward。

### 19.7 导航类能力保留为后续目标（2026-08-25 补充）

**[用户已确认]**

对 §19.5 的补充修正。用户重新考虑后指出：细线检测、安全性检测这类能力
**相对 C1 确实没那么 novel，但模型需要足够的能力多样性（Diversity）**
（该要求此前已在文档中提出）。

**因此 §19.5 中「移出范围」的措辞过强，应修正为**：

- 这些能力**不在当前实施范围**（UAVScenes 数据确实不支持，这一点不变）；
- 但**保留为后续目标**，进入待办 backlog（SPEC §46.5 / Release D）；
- **当前阶段全力攻坚 C1–C4**，Task Family B 的优先级放在其后。

**不变的部分**：在 UAVScenes 上**仍然不得**生成这些任务 ——
数据不支持这一事实不因优先级调整而改变（铁律 5）。
解锁条件是引入前视/侧视数据集（原方案 B）。

**已同步修订**：SPEC §40.1 的重定义横幅、§1 输出族、§20.3、§34、§41、§46（新增
§46.5 backlog 表）、§51（新增 Release D）；`AGENT_SKILL_SYSTEM_DESIGN.md` §3.2；
本文 §9.2 与 Next Agent Instructions 第 6 条。

### 19.4 层级推进顺序调整：第三层降为润色层（2026-08-25）

**[用户已确认]**

**决策**：先完整搭通第一、二、四层，即「数据输入 → 中间的提取/生成/处理 → 下游任务输出」这条主干；**第三层（Skill 与质量监管体系）暂缓**。

**理由（用户原话意）**：第三层是用 Skill 去包装可复用的提示词与核验方法，它本质上是**润色性质**的 —— 应当在已有完整链路可供审视之后，再去判断「哪里可以优化」「哪里值得新增一个用 Skill 实现的能力」。在主干尚未打通时先造 Skill，等于对着不存在的流程写规则。

**这不是取消第三层**，而是调整顺序：先有可运行的链路，再用 Skill 去提炼其中重复出现的决策与校验。

**执行上的关键区分**：

第三层的很多条目具有**双重身份** —— 其*功能*在主干数据流上，其*Skill 封装*才属于第三层。处理原则：

| 条目 | 功能归属 | 现在做什么 |
|---|---|---|
| `task-prompt-compiler` | **L2-S6 任务编译**，主干必需 | **实现为普通代码**，不封装为 Skill |
| `scene-ingestion-validator` | L2-S0 后的接入校验 | 实现为普通校验函数，不封装为 Skill |
| `task-sample-auditor` | L2-S8 样本校验 | 同上 |
| `metadata-quality-gate` | L2-S5 质量与 provenance | 同上 |
| Orchestrator Agent | 第三层调度 | **暂缓** |
| G1–G6 门禁框架 | 第三层监管 | **暂缓**（单点校验仍做，但不建统一门禁框架） |
| `dataset-registry-manager` / `expert-registry-manager` | 第三层注册管理 | **暂缓**（注册表本身已存在于 `registry/`，够用） |

即：**保留必要的校验动作，暂不建立统一的 Skill 与门禁框架。**

**受影响的既有设计**：`AGENT_SKILL_SYSTEM_DESIGN.md` §12 的实现顺序（第 4 步 task-prompt-compiler、第 6 步 auditor、第 7 步门禁、第 8 步 Orchestrator）中，涉及 Skill 封装与门禁框架的部分推迟；涉及功能实现的部分保留。

**调整后的主干缺口**（这才是当前应推进的）：

1. **Metadata schema 尚未冻结** —— SPEC §16 的 L0/L1/L2 只有文字描述，`schemas/` 里只有归一化场景契约。这是数据框架的核心缺口。
2. **Canonical Task Record 未实现** —— SPEC §41 定义了契约，无代码。
3. **三类 adapter 未实现** —— 其中 `pointcloud_native` 是 3D-GRPO 的直接消费接口。
4. **L2-S3 提升融合、L2-S4 派生、L2-S6 编译** 均无实现。

### 19.3 UAVScenes 获取与许可决策（2026-08-24）

数据已获取，Layer 1 的 G0 门禁通过（`registry/datasets/uavscenes/`）。

**获取路径修正**：原判断"UAVScenes 需许可申请、是唯一硬阻塞项"**不成立**。官方提供 HuggingFace 镜像 `sijieaaa/UAVScenes`，非 gated、非 private，**无需任何 token**，已下载 35 GB（interval=5）。用户提供的 SharePoint 链接为浏览器登录态 URL，服务器访问返回 403，未采用。

**[用户已确认] 许可政策**：UAVScenes 与其上游 MARS-LVIG 均为 **CC BY-NC-SA 4.0，仅限学术用途**。用户决定接受该约束，按学术研究推进。由此产生的强制义务：

- 本项目生成的 3D metadata、衍生点云与任务标注按**演绎作品**处理，发布时采用 CC BY-NC-SA 4.0；
- 署名 MARS-LVIG 与 UAVScenes；
- 训练所得权重不得商业发布；
- 未来若引入许可不兼容的数据集，必须分区发布，不得合并为单一 SA 作品（G6 复核）。

注意：HuggingFace 仓库元数据标签为 `cc-by-sa-4.0`，**遗漏了 NonCommercial**。以 GitHub LICENSE 文件为准，不得以 HF 标签作为商用依据。

**核验到的数据事实**（详见 `registry/datasets/uavscenes/dataset_card.yaml`）：

- 20 个 run，归属 **4 个 split group**：AMtown、AMvalley、HKairport、HKisland。HKairport 与 HKisland 各含 base / `_GNSS` / `_GNSS_Evening` 变体，**同 location 的全部 run 必须绑定同一 split**。
- 每个 run 含 `rtk_positions_raw.csv`（lat/lon/alt + UTM），**RTK 尺度锚点确认存在**，满足首版强制 metric 政策。
- 图像 2448×2048，`sampleinfos_interpolated.json` 提供 `T4x4` 位姿与 `P3x3` 内参；**位姿覆盖 interval=1 全部帧，密度是已发布图像的 5 倍**。
- LiDAR 为逐帧 ASCII XYZ 文本，无 intensity/ring/time；图像-点云配对已由官方完成（文件名含双时间戳）。
- interval=5 实际含 24126 帧；官方称的 120k 标注对对应 interval=1。

**新增风险**（已录入 dataset card）：R-001 降采样影响帧间重叠与重建质量；R-005 仅 4 个独立切分单元、泛化评测统计效力有限；R-006 ASCII 点云解析开销大；R-007 畸变系数抽样全为 0，含义待全量核验。

## Next Agent Instructions

> ⚠️ **先读 §19.4（第三层暂缓）与 §19.5（能力范围重定义）** —— 它们推翻了本文
> 第 1–18 节中关于低空差异化能力与推进顺序的多项表述。

接手后按以下顺序开始：

1. 阅读本文件，然后完整阅读项目根目录的 `AGENTS.md`。
2. 如果用户继续要求技术调研、论文、数据集、模型或最新进展，先完整读取并使用：
   - `.agents/skills/research-emerging-domain/SKILL.md`
   - 该 skill 指向的必要 protocol/reference。
3. 只读检查：
   - `deliverables/低空无人机_新增3D可转化数据集清单_2026-08-23.docx`
   - 用户笔记 `/Users/newniuuu/Documents/NiuuuNotes/🐮脑碎片🧩/低空大脑/Awesome3D-Data-gen-pipeline/8.20～.md`
4. 在开始实现前先向用户确认三个最小边界：首批数据集、是否要求 metric scale、首批任务类型。
5. 如果用户没有指定，建议用一个真实多视角数据集跑通最小闭环，并先实现：
   - VGGT-Ω 点云；
   - object-level metadata；
   - 3D Grounding；
   - Metric/Situated 3D VQA；
   - Cross-view Correspondence 或 Metadata Verification。
6. 第一版 schema 只保留必要 L0/L1/L2 字段。**导航、TTC、可飞行空间、航迹类功能
   当前不实施**（近垂直下视数据不支持，见 §19.5），但**保留为后续目标**
   （SPEC §46.5，需引入前视数据集）。L3 层的现行内容是可信度、可降落性、
   地形量与跨时相变化（SPEC §16）。
7. 每个任务必须具有 `metadata_input_fields`、`hidden_target_fields`、`evidence` 和 `derivation_program/checker`。
8. 首次实验必须包含 2D-only 与 2D+metadata 对照，验证 metadata 是否产生真实增益。
9. 不要擅自：
   - 修改飞书；
   - 修改用户 Obsidian 笔记；
   - 改项目治理文件；
   - 下载全部大型数据集；
   - 把 DA3/WorldMirror 改成点云主路径；
   - 让 Qwen 直接读取点云；
   - 把未验证伪深度当作 metric ground truth。
10. 每次交付都注明：事实核验截止时间、已验证范围、仍未验证的许可/数据/模型风险。
