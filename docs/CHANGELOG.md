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
