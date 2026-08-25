# 项目规则

本文件是每个 session 自动加载的项目级规则。以下规则由用户确立，不得擅自更改或放宽。
## 规则 1：设计改动必须立即同步到文档

本项目（`3D-data-pipeline/`）的设计以文档为准。**任何对设计的改动，必须在同一次交付里同步写入文档**，不允许"代码先改，文档回头补"。

### 文档职责与同步映射

| 文档 | 阅读对象 | 什么改动必须同步进来 |
|---|---|---|
| `3D-data-pipeline/README.md` | **用户（项目追踪入口）** | **进度追踪表**：需求增删与状态变化、阻塞项、四层进度。**不写具体改动** —— 那是 CHANGELOG 的事 |
| `3D-data-pipeline/docs/CLAUDE_CODE_PROJECT_SPEC.md` | Agent（实施主规格） | 架构铁律、四层结构、各类 contract/schema、Task Spec 字段、门禁 G0–G6、artifact 血缘、状态机、UNRESOLVED 项的解决 |
| `3D-data-pipeline/docs/AGENT_SKILL_SYSTEM_DESIGN.md` | Agent/开发者 | Skill 职责、检查项、修复策略、Prompt Bundle 规范、实现顺序 |
| `3D-data-pipeline/docs/PROJECT_HANDOFF.md` | 人类与 Agent | 新的用户决策、被否决的方案、调研依据、约束来源。**追加历史，不改写既有的「[用户已确认]」条目** |
| `3D-data-pipeline/docs/MANUAL_INPUTS.md` | 用户与 Agent | 需要用户手动提供的信息（token、凭证、许可申请、飞书只读导出）。**只登记「需要什么/值放在哪/是否已提供」，真实值一律不写进来** |
| `3D-data-pipeline/docs/CHANGELOG.md` | 用户与 Agent | **每一次改动的流水账**：用户新增需求与决策、Agent 的实现与文档同步、事实修正。只追加不改写 |
| `3D-data-pipeline/docs/PENDING_DELETIONS.md` | 用户 | 应删除但**不由 Agent 执行**的内容清单 + 删除命令。用户定期批量处理 |
| `3D-data-pipeline/docs/FINDINGS.md` | **人类** | 调研发现的**简明摘要**：结论一句话 + 为什么重要 + 详情去哪看。不放实现细节 |

### README 是用户的追踪工具，不是记录本

`README.md` 的读者是用户，用途是回答**「还有什么要做、做到哪了」**。

**每次交付必须更新 README 的进度追踪表**：

- 产生新需求（无论来自用户、商讨还是自己判断该做）→ 加一行，标明来源与所属架构层；
- 需求状态变化 → 改状态，完成的补产出、受阻的补阻塞原因；
- 阻塞项解除或新增。

**但不要把改动细节写进 README。** 「改了哪个文件、修了什么 bug、实测了什么数字」
一律进 `docs/CHANGELOG.md`。README 堆满流水账就失去追踪价值了。

### 调研结果必须双份记录

任何调研性质的产出（模型评估、许可核验、数据实测、可行性验证）都要记两处：

1. **详细文档** —— 完整数据、复现命令、原始输出（如 `EXPERT_DEPLOYMENT.md`、`BASELINE_POINTCLOUD_ANALYSIS.md`）；
2. **`docs/FINDINGS.md`** —— **面向人类的简明摘要**，每条只写：结论一句话、为什么重要、详情链接。

FINDINGS 的写法要求：**结论先行，不铺陈过程**；说清"这件事影响了什么决定"；
被推翻的结论也要留下并注明，不要只留正确的那版。**不要把实现细节、代码、完整表格搬进来** —— 那是详细文档的职责。

### 变更日志是强制动作

**每次交付都必须在 `docs/CHANGELOG.md` 追加条目**，与代码/文档改动同一次完成，不允许攒着回头补。

- 记录范围包括**用户新增的需求与决策**，以及 **Agent 自发的改动** —— 不是只记用户要求的部分。
- 每条含：类型标签（`[需求]`/`[决策]`/`[实现]`/`[文档]`/`[修正]`/`[运维]`）、触发者、做了什么、涉及文件、为什么。
- 最新条目在最上方。**历史条目只追加不改写**；此前的判断被推翻时，新增 `[修正]` 条目指向它并说明原因，而不是删改原记录。
- 纯粹的探索、读文件、失败的尝试不必逐条记录；但**改变了项目状态或结论的事情必须记**，包括被证明错误的判断。

### 人工输入的处理方式

遇到需要用户手动提供的信息时：在 `MANUAL_INPUTS.md` 的「待提供」表新增一行 → 停下来告知用户 →
**不得用占位符、假值或猜测值继续推进**，也不得为绕开而降低方案要求。
真实值写入 `secrets/.env.local`（该目录已整体 git 忽略），文档里只记变量名。
注意本仓库有 GitHub remote（`origin` → `WoodSerenity/uavlm.git`），凭证一旦进入 git 历史即视为泄露。

### 不执行删除

**Agent 不删除文件。** 发现应清理的内容（bug 残留、废弃产物、重复文件）时：
追加一条到 `docs/PENDING_DELETIONS.md`，写清路径、体积、原因、删除命令，**然后继续推进项目，不因此停下来请示**。

例外 —— 以下情况必须当场请示，不能只记清单，因为可能丢失真实成果：
未提交的代码/文档/实验结果、用户提供的原始数据、删除范围可能超预期（通配符/递归删父目录）、
无法确定是否还有其他引用。

### 执行要求

- 改动涉及多份文档时，**全部一起改**；README 与 SPEC 出现口径冲突时停下来报告，不要自行选一个。
- 解决任何一个 `UNRESOLVED` 项，必须同时更新 SPEC §36 的清单和 README 的「开始实现前需要确定」。
- 文档里的状态标记体系要保留：`[用户已确认]` / `[设计建议]` / `[待验证]`，以及 `MUST` / `MUST NOT` / `SHOULD` / `MAY` / `UNRESOLVED`。
- 不修改飞书公共文档，不修改用户的 Obsidian 笔记。

## 规则 2：占卡程序必须保持挂载

**服务器连续 2 小时未使用显卡就会被释放。** 占卡程序是保命机制。

### 现状

```
占卡程序：/blob/thinking.py     （root 所有，只读使用，不要改它）
守护脚本：/home/aiscuser/nyp/scripts/gpu_guard.sh
日志目录：/home/aiscuser/nyp/logs/
```

`thinking.py` 的行为：先轮询等待 8 卡各自空闲 ≥30GB → 再用 resnet101 + DataParallel
吃满全部 8 卡（每卡约 27GB）跑无限前向循环。

**必须用 `/opt/conda/envs/ptca/bin/python` 启动**，默认 PATH 上的 miniconda3 python 没有 torch。

### 守护脚本（首选方式）

`gpu_guard.sh` 每 20 分钟检查一次：占卡程序活着 → 不动；显卡被别的进程占用 → 不介入；
显卡真空闲且占卡程序不在 → 自动拉起。

```bash
scripts/gpu_guard.sh start      # 后台启动守护（默认 1200 秒一轮）
scripts/gpu_guard.sh status     # 查看守护 / 占卡程序 / 显卡状态
scripts/gpu_guard.sh once       # 立即检查一轮，不进入循环
scripts/gpu_guard.sh release    # 停掉占卡程序腾出显卡（会一并停掉守护）
scripts/gpu_guard.sh stop       # 只停守护，不影响占卡程序
```

### 操作协议

**需要用显卡前：**

```bash
scripts/gpu_guard.sh release    # 停守护 + 停占卡，并打印显存状态
```

**自己的 GPU 任务结束后，立刻：**

```bash
scripts/gpu_guard.sh start      # 重新挂上守护，它会自动拉起占卡程序
scripts/gpu_guard.sh status     # 验证确实占上了
```

### 关键注意事项

1. **守护是兜底，不是免责。** 它最长有 20 分钟盲区，且只在显卡完全空闲时才动作。
   用完卡仍然要主动 `start`，不要指望它替你收尾。
2. **不要在自己的 GPU 任务还在跑的时候启动 `thinking.py`。** 它的门槛是"8 卡各自空闲 ≥30GB"：
   - 若自己的任务占显存大 → 它一直空转轮询，卡没被占上，2 小时倒计时照常走；
   - 若自己的任务只占几 GB → 它会立刻抢占全部 8 卡各 27GB，**大概率把自己的任务 OOM 掉**。

   `gpu_guard.sh` 已用「无其他计算进程 + 每卡空闲 ≥30GB」双重条件规避了这一点，
   但手动启动时必须自己注意。
3. **不要手写 `pkill -f` 匹配 `thinking.py`。** `pkill -f` 匹配完整命令行，
   会把执行这条命令的 shell 自身一起杀掉（已踩过）。用 `gpu_guard.sh release`，
   或先 `pgrep` 拿到 PID 再精确 `kill`。
4. 状态一律用 `gpu_guard.sh status` 或 `nvidia-smi` 确认，不要凭记忆假设占卡程序还活着。

### 无关进程（不要误杀）

```
python /opt/portable_jupyter/bin/jupyter-lab   —— Jupyter 服务
python aml_code_runner.py                      —— 平台任务运行器
python tools/blob_manager.py                   —— blob 存储管理
```

## 规则 3：不碰共享环境，用项目专属 conda 环境

**禁止向 `/opt/conda/envs/ptca`（共享 base 环境）安装、升级或卸载任何包。**
它是多人共用的，一次 `pip install` 就可能连带升级 numpy 之类的底层依赖，破坏别人的工作。

### 项目环境

```
conda env: nyp-3dpipe
python:    /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python
```

调用方式（二选一）：

```bash
conda activate nyp-3dpipe                     # 交互式，env config vars 自动生效
PYTHONNOUSERSITE=1 /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python ...   # 直接调二进制
```

### `PYTHONNOUSERSITE=1` 不是可选项

`~/.local/lib/python3.10/site-packages` 下有 35 个包（wandb、webdataset、ftfy…），
**会渗进任何 python3.10，包括 conda 环境**。已用 `conda env config vars set` 绑定到该 env，
但**直接调用 python 二进制时不会生效**，必须显式带上该变量，否则隔离是假的。

验证隔离是否生效：

```bash
PYTHONNOUSERSITE=1 $PY -c "import sys; print([p for p in sys.path if 'nyp-3dpipe' not in p] or '无泄漏')"
```

### 如果不小心动了共享环境

立刻还原，不要拖到"回头再说"：记下改动的包与原版本，`pip install 包==原版本` 回滚，
再用 `pip check` 确认无残留冲突，最后在 CHANGELOG 记一条 `[修正]`。
