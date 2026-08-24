# 变更日志

> 记录本项目的每一次改动：用户新增的需求与决策、Agent 执行的实现与文档同步。
> 最新条目在最上方。**只追加，不改写历史条目**；若某条记录事后被证明有误，新增一条 `[修正]` 指向它，而不是删改原条目。
> 建立日期：2026-08-24

## 条目规范

每条记录必须包含：**类型标签**、**触发者**、**做了什么**、**涉及文件**、**为什么**。

| 标签 | 含义 |
|---|---|
| `[需求]` | 用户新增或变更需求 |
| `[决策]` | 用户拍板的技术/政策决策 |
| `[实现]` | Agent 的代码或数据改动 |
| `[文档]` | 文档同步（规则 1 的执行记录） |
| `[修正]` | 推翻或修正此前的判断、结论、记录 |
| `[运维]` | 环境、占卡、仓库、凭证等基础设施改动 |

触发者取值：`用户` / `Agent`。Agent 自发的改动也必须记录，不能只记用户要求的部分。

---

## 2026-08-24

### `[需求]` Blob 数据路径登记 — 用户

**要求**：项目推进中会涉及 blob 上的数据路径，提供过一次后不应再重复提供，需记录在 `MANUAL_INPUTS.md`。同时告知：`data/` 中各数据集的点云已由同事用 VGGT-Ω 转换完成，存放在 `Pointcloud-VQA/` 与 `PointCloud-grounding/`。

**改动**：`MANUAL_INPUTS.md` 新增 §3「数据路径登记（Blob）」，登记 D-001 / D-002 两条路径并附实测结构；§5 增加数据路径条目模板，要求**先实测再登记**；后续小节顺延编号。

**实测结果**：

- 这两个路径**不在 `/blob` 挂载点下**（该挂载是另一个 datastore），必须走 `python tools/blob_manager.py ls <路径>` 访问（支持 one-shot，无需进交互界面）。
- `Pointcloud-VQA/`：`AVImath/` `AirCopBench/` `Floodnet/` `LADI/` `UrbanVideoBench/` `pointcloud_train/` `shareGPT/`
- `PointCloud-grounding/`：`AAVG/` `DVGBench/` `benchmark/` `crop/` `nyp/` `refdrone/`
- 叶子层格式：逐图像一个 `.ply`，文件名即图像 ID，单文件约 2.0 MB，生成于 2026-06-24。

**附带结论**：这些点云对应的是飞书已有清单那批数据集，**不是** UAVScenes，因此不作为首批闭环输入。但它们是现成的 VGGT-Ω 产物，可用于在 Layer 2 开工前验证 VGGT-Ω 的实际输出格式与质量，无需自己先跑通推理。其归属取决于 `PROJECT_HANDOFF.md` §19.2 的未决问题。

**附带修正**：M-006（Blob 凭证）由「待提供」改为「已提供 —— 无需用户额外提供」，实测 `blob_manager` 可正常访问。

**涉及文件**：`docs/MANUAL_INPUTS.md`

---

### `[实现]` vertical slice 第 1–2 步：冻结契约 + UAVScenes adapter — Agent

对应 SPEC §34 vertical slice 第 1 步（冻结 ID、artifact 状态、最小 schema、错误码）与第 2 步（单数据集 adapter）。

**新增 `core/`（单一事实来源）**：

- `ids.py` —— SPEC §15 的 7 个 ID 命名空间、`<ns_NNN>` 格式、解析校验、不复用序号的 `IdMinter`
- `states.py` —— 12 个 pipeline 状态 + 2 个出口、4 种门禁状态、6 道门禁；`validate_transition` **强制要求门禁报告**，仅有状态标签会被拒（SPEC §31）
- `enums.py` —— 尺度/深度来源/深度类型/无效几何原因/监督等级；`supports_absolute_metric_target` 把铁律 8/9 变成可执行判断
- `errors.py` —— 57 个错误码，按 `<门禁>-<类别><NN>` 编码，分 hard / warn / stop 三级；hard 与 stop **永不允许推进**
- `artifact.py` —— 不可变 artifact 信封，`derive()` 自动串联血缘并分配新 ID，`write()` **拒绝覆盖已存在文件**（SPEC §30）

**新增 `schemas/normalized_scene.schema.json`**：SPEC §12 归一化场景契约的 JSON Schema，`additionalProperties: false`，强制 `unit` 只能是 `meter`/`unknown`、坐标系未知时必须显式写 `unknown`。

**新增 `adapters/uavscenes/`**：run 发现、split group 归并、按图像名连接位姿表、官方文件名解析图像-点云配对、定长窗口切分场景、可选落地帧文件。

**新增 `scripts/build_scenes.py`**：CLI，输出以 Artifact 信封写出。

**测试**：`tests/test_core_contracts.py` 35 项（全部针对铁律，不是"代码能跑"）、`tests/test_uavscenes_adapter.py` 21 项（**跑真实数据**，非合成 fixture）。共 56 项全过。

**实际产出**：`scenes/` 下 3 个 AMtown01 场景，各 50 帧、约 85 MB，缺位姿 0、缺点云 0。

**涉及文件**：`core/*`、`schemas/normalized_scene.schema.json`、`adapters/*`、`scripts/build_scenes.py`、`tests/*`

---

### `[修正]` 实测确定 T4x4 位姿方向与世界系尺度 — Agent

**背景**：`dataset_card.yaml` 中 `coordinate_system` 原为 `UNRESOLVED`。若猜错位姿方向，整条几何链路会静默出错。

**方法**：用 RTK 轨迹交叉验证两种假设。

**结论**：

1. **`T4x4` 是 `world_from_camera`**，平移列即相机中心。与 RTK 水平轨迹绝对相关 **0.9877**；`camera_from_world` 假设仅 **0.2155**。轨迹跨度亦逐项吻合（863.6/585.1 m vs RTK 863.0/584.1 m）。
2. **世界系为米制**。对 4 个地点做 Umeyama 相似变换，尺度因子 **0.9976 ~ 1.0022**，偏离 1.0 最大 **0.241%**。
3. 强制 `s=1` 后残差 RMS 0.44 ~ 1.89 m，来源是 RTK 天线与相机光心杆臂、RTK 噪声与时间同步 —— **不是尺度误差**，对物体间距离一类任务无影响。HKisland_GNSS01 残差偏高（1.89 m）值得留意。

**影响**：adapter 据此声明 `depth_type: externally_anchored`、`anchor_provenance_verified: true`；`domain_calibrated` 仍为 `false`（域校准尚未做，不得虚报）。

**涉及文件**：`adapters/uavscenes/adapter.py`、`registry/datasets/uavscenes/dataset_card.yaml`

---

### `[修正]` `--limit` 会多解出一个孤儿场景 — Agent

**问题**：`build_scenes.py` 在循环体内检查 `--limit` 后 `break`，但 `_build_scene` 在 `yield` **之前**就已解出帧文件。结果多构建一个场景、多解 85 MB 文件，且因 `break` 发生在写清单前，留下**没有 `scene_manifest.json` 的孤儿目录**。

**修复**：改用 `itertools.islice` 限流，生成器不再被多推进一次。已在干净输出目录验证：`--limit 2` 产出 2 个目录、均带清单。

**遗留**：首次运行产生的孤儿目录 `scenes/uavscenes_AMtown01_0003` 仍在磁盘上（删除操作未获授权），需人工清理。

**涉及文件**：`scripts/build_scenes.py`

---

### `[修正]` M-004 飞书导出降级为「按需触发」 — 用户提问触发

**用户提问**：不清楚 M-004 飞书导出是做什么的，此前只是把项目进展的飞书文档给过另一位 Agent。

**澄清**：M-004 源自 `PROJECT_HANDOFF.md` §3.2 / §10.1 与 SPEC §5 —— 前一位 Agent 用该飞书文档提取项目已有数据集清单，据此定义「22 个新增候选」= 不在清单中的数据集。其**唯一用途是下一轮数据集调研的去重基准**。

**修正**：此前将其表述为「当前唯一待办的用户提供项」，措辞使其显得像一件用户需要立即处理的事。实际当前**不需要**：首批数据集已定且过 G0、去重只在 Phase 2 才有价值、本机 `data/` 已有该清单中 9 个数据集的实物。状态由「待提供」改为「**按需触发**」。

**附带结论**：需要时应**导出为文本粘贴**而非提供链接 —— 飞书 wiki 需登录态，无头环境无法访问（同 SharePoint 403 情形）。

**当前状态**：**没有阻塞首批闭环的用户提供项。**

**涉及文件**：`docs/MANUAL_INPUTS.md`

---

### `[需求]` 建立变更日志 — 用户

**要求**：项目规模较大，需要一个日志文档记录每一次改动，包括用户新增的需求和 Agent 进行的改动。

**改动**：新建本文件 `docs/CHANGELOG.md`，补录当日全部历史；将「每次改动必须记入 CHANGELOG」写入 `CLAUDE.md` 规则 1；在 `README.md` 与 `CLAUDE.md` 的文档映射表中登记本文件。

**涉及文件**：`docs/CHANGELOG.md`（新建）、`CLAUDE.md`、`README.md`

---

### `[实现]` `[文档]` UAVScenes 通过 G0 门禁，建立 Layer 1 数据集注册表 — Agent

**改动**：

- 自 HuggingFace 镜像 `sijieaaa/UAVScenes` 下载 interval=5 全量 35 GB 至 `data_raw/UAVScenes`（非 gated，无需 token）。
- 新建 `registry/datasets/uavscenes/`：`dataset_card.yaml`（SPEC §7 契约 + 帧级数据契约 + 7 项风险）、`license_review.yaml`（G0 = `pass_with_constraints`）、`file_inventory.json`（4 档案 sha256、逐 run 计数、split group 划分）。
- 新建 `.gitignore` 排除 `data_raw/`、`*.zip`、`*.ply` —— 数据受 NC-SA 约束，不得随代码再分发。

**核验到的关键事实**（不解压，经 zip 中央目录与抽样解析）：

- 20 个 run 归属 **4 个 split group**（AMtown / AMvalley / HKairport / HKisland）；HKairport 与 HKisland 各含 base / `_GNSS` / `_GNSS_Evening` 变体，同 location 全部 run 必须绑定同一 split。
- 每 run 带 `rtk_positions_raw.csv`，**RTK 尺度锚点确认存在**，满足强制 metric 政策。
- `sampleinfos_interpolated.json` 覆盖 interval=1 全部帧，**位姿密度为已发布图像的 5 倍**。
- 图像 2448×2048；LiDAR 为逐帧 ASCII XYZ，无 intensity/ring/time；图像-点云配对官方已完成。

**涉及文件**：`registry/datasets/uavscenes/*`（新建）、`.gitignore`（新建）、`docs/PROJECT_HANDOFF.md` §19.3、`README.md`、`docs/MANUAL_INPUTS.md`

---

### `[修正]` M-005a 被误判为硬阻塞项 — Agent

**原判断**（同日稍早）：「UAVScenes 需许可申请，是唯一硬阻塞项，等待周期不可控，建议尽早提交申请」。

**修正**：**不成立**。UAVScenes 提供开放的 HuggingFace 镜像，非 gated、非 private，无需任何凭证即可下载。

**原因**：该判断基于「多数 UAV 数据集需要申请表或机构邮箱」的一般规律外推，未先核实这一个数据集的实际获取方式。

**影响**：M-005a 由「待提供（硬阻塞）」改为「已提供（无需凭证）」；当前唯一待办的用户提供项变为 M-004（飞书导出），且不阻塞首批闭环。

**涉及文件**：`docs/MANUAL_INPUTS.md`、`docs/PROJECT_HANDOFF.md` §19.3

---

### `[决策]` 接受 CC BY-NC-SA 4.0 学术用途约束 — 用户

**背景**：UAVScenes 与其上游 MARS-LVIG 均为 CC BY-NC-SA 4.0，仅限学术用途。按 SPEC §35，「许可条件阻碍预期用途」是必须停下来请示的情况。

**决策**：接受 NC-SA 约束，按学术研究推进。

**由此产生的强制义务**：

- 本项目生成的 3D metadata、衍生点云与任务标注按**演绎作品**处理，发布时采用 CC BY-NC-SA 4.0；
- 署名 MARS-LVIG 与 UAVScenes；
- 训练所得权重不得商业发布；
- 未来引入许可不兼容的数据集时必须分区发布，不得合并为单一 SA 作品（G6 复核）。

**注意**：HuggingFace 仓库元数据标签为 `cc-by-sa-4.0`，**遗漏 NonCommercial**。以 GitHub LICENSE 为准。

**涉及文件**：`registry/datasets/uavscenes/license_review.yaml`、`docs/PROJECT_HANDOFF.md` §19.3、`README.md`

---

### `[需求]` `[运维]` 同步 3D-data-pipeline 至独立 GitHub 仓库 — 用户

**要求**：将 `3D-data-pipeline/` 推送到 `https://github.com/NewNiuuu/3D-pointcloud-data-pipeline`。

**改动**：在 `3D-data-pipeline/` 内 `git init`（独立于外层 `nyp/` 的 `WoodSerenity/uavlm` 仓库，外层本就未跟踪它），提交并推送。

**安全处理**：推送前扫描真实凭证 0 命中（先前 4 处命中系 `task-spec`/`risk-aware` 被 `sk-` 模式误匹配）；使用临时 credential helper，**未将 token 写入 remote URL 或 `.git/config`**；token 存入 `secrets/.env.local`（权限 600，已 gitignore）。

**遗留风险**：用户提供的是 `ghp_` 开头的 classic PAT，作用域通常为整个账号，且已出现在对话记录中。**已建议 revoke 并改用仅授权该仓库的 fine-grained PAT。**

**涉及文件**：`.git/`（新建）、`docs/MANUAL_INPUTS.md` M-001

---

### `[决策]` `[文档]` 四项实施边界决策 — 用户

按 SPEC §35 要求，实施前澄清四项阻塞决策：

| 项 | 决定 |
|---|---|
| 首批数据集 | **UAVScenes 单个** |
| 是否强制 metric scale | **强制**；relative / affine-invariant / pseudo 不具备任务资格 |
| 首批任务 | **3D Grounding（对象级）+ metric/situated 3D VQA + Cross-view Correspondence** |
| Qwen 部署 | **暂缓**；首批只编译 prompt bundle 不调用模型（vertical slice 第 1–10 步） |

同时确立工作默认值（`[设计建议]` 级别，可带理由修订）：最终交付物暂定 pipeline 工具链 + 小规模 benchmark；首版不引入 LLM Judge；首批样本 100% 人工复核；不绑定调度框架；质量阈值沿用文档建议值。

**文档同步（规则 1）**：SPEC §36 四项 `UNRESOLVED` → 已解决值 + provenance，§8 数据集选择，§34 vertical slice；PROJECT_HANDOFF 新增 §19（含 §19.1 环境现实约束、§19.2 未决项）；README「开始实现前需要确定」→「实施边界（已确定）」+ 进度表；AGENT_SKILL_SYSTEM_DESIGN §13「尚待用户决定」→「用户决策状态」。

**涉及文件**：`docs/CLAUDE_CODE_PROJECT_SPEC.md`、`docs/PROJECT_HANDOFF.md`、`README.md`、`docs/AGENT_SKILL_SYSTEM_DESIGN.md`

---

### `[实现]` 环境现实约束核实 — Agent

**发现**（影响首批范围的判断）：

- 本地 `data/` 下 9 个目录**只有 QA 标注 JSON，无任何图像/视频/点云**，且均属飞书已有清单，服务于同级 `3D-GRPO` 项目，不能作为本 Pipeline 的重建输入。
- 22 个新增候选当时一个都未落盘。
- VGGT-Ω 未安装。作为固定的点云主路径，其可获取性必须在 Layer 2 开工前核验；若不可用须停下来重新讨论，不得静默替换（受 §7.4 约束）。
- 磁盘可用 5.2T；`/blob` 挂载点显示 0 字节，可写性待确认。

**涉及文件**：`docs/PROJECT_HANDOFF.md` §19.1、`README.md`

---

### `[需求]` `[实现]` 建立人工输入登记簿 — 用户

**要求**：在 `docs/` 下增加一个文档，存储项目进行过程中需要用户手动提供的信息（GitHub token、HuggingFace token 等）。

**设计取舍**：因仓库连接 GitHub remote，**未做成直接粘贴 token 的地方**，而是拆为两层 —— 文档登记「需要什么、为什么、值放在哪、是否已提供」，真实值存入 `secrets/.env.local`。`secrets/.gitignore` 用 `*` + `!.gitignore` 使该目录整体自我屏蔽，不受根 `.gitignore` 增删影响。已实测验证屏蔽生效。

**涉及文件**：`docs/MANUAL_INPUTS.md`（新建）、`secrets/.gitignore`（新建）、`README.md` 文档入口表、`CLAUDE.md`

---

### `[需求]` `[运维]` 显卡监听守护程序 — 用户

**要求**：每 20 分钟检查显卡是否空闲，空闲则拉起占卡程序 `thinking.py`。

**实现**：`scripts/gpu_guard.sh`，`setsid nohup` 后台运行（独立于 Claude Code session），三分支判断 —— 占卡程序存活则不动；显卡被其他进程占用则不介入；显卡真空闲且占卡程序不在则拉起并在 60 秒后验证。命令：`start` / `stop` / `status` / `once` / `release`。日志 `logs/gpu_guard.log`，自动轮转。

**实测发现并修复的两个问题**：

1. **解释器错误**：直接 `python /blob/thinking.py` 失败 —— 默认 PATH 指向 `miniconda3`，其中无 torch。必须用 `/opt/conda/envs/ptca/bin/python`（torch 2.8.0+cu126，8 卡可见）。已在脚本中写死。
2. **`pkill -f` 自杀**：`pkill -f "python .*/blob/thinking.py"` 会匹配到执行该命令的 shell 自身（命令行含该模式串）并将其杀死。脚本内部调用不受影响（脚本 cmdline 不含该串），但该坑已写入 `CLAUDE.md`。

**验证**：实际停掉占卡程序后测试自动拉起成功，显卡空窗约 2 分钟。

**涉及文件**：`scripts/gpu_guard.sh`（新建，位于外层 `nyp/`）、`CLAUDE.md`

---

### `[需求]` 确立两条项目规则 — 用户

1. **设计改动必须立即同步到文档** —— 不允许「代码先改，文档回头补」。
2. **占卡程序必须保持挂载** —— 服务器连续 2 小时未使用显卡将被释放；用卡时可停，用完必须立刻挂回。

**实现**：写入 `CLAUDE.md`（每 session 自动加载），含文档职责映射表与占卡操作协议。

**涉及文件**：`CLAUDE.md`（新建，位于外层 `nyp/`）

---

### `[实现]` 项目文档通读 — Agent

阅读 `README.md`、`CLAUDE_CODE_PROJECT_SPEC.md`、`PROJECT_HANDOFF.md`、`AGENT_SKILL_SYSTEM_DESIGN.md`，确认项目为低空无人机 2D→3D 数据生成与评测体系，四层架构，五条不可动摇的架构铁律，当时状态为「设计完成、零代码」。
