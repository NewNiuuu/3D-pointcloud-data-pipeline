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

## 2026-08-25

### `[实现]` `[修正]` 日/暮受控对照实测：置信度在暗光下判别力损失过半 — Agent

**做了什么**：完成用户要求的日间/傍晚配对实验（C4，同时服务 C1）。

**配对方法上纠了两次错**，两次都不是模型问题：

1. 按「基线最大」各取一段 → 选到了不同区域，判为"无重叠"；
2. 用两航次各自的 world 坐标算质心距离 → 再次判为"无重叠"。
   **每航次的 world 系原点在各自首帧，坐标不可跨航次比较。**
   换算到 RTK 绝对坐标后，两航次其实是同一条航线，逐点中位偏差 0.1 m、100% 落在 15 m 内。

**然后发现「傍晚」不等于「暗」**：RTK 配到 0.1 m 的那对（`GNSS01_0041`/`Evening_0001`）
跑出来是傍晚比日间**还亮 18.9%** —— `Evening_0001` 拍于 17:43，仍是黄金时刻。
扫描全航次亮度：17:43=0.354 → 17:57=0.270 → 18:01=0.220 → **18:04=0.0864**，
**航次内部 4 倍梯度**，只有 18:00 后的尾段真暗。

**最终成立的配对**：`GNSS01_0034`（15:2x，亮度 0.2845，基线 52.1 m）
vs `GNSS_Evening_0063`（18:0x，亮度 0.0712，基线 64.6 m），
RTK 质心距离 10.0 m，亮度比 0.25×。24 帧 @512。

**结果**：

| | 日间 | 暗傍晚 | 变化 |
|---|---:|---:|---:|
| 图像亮度 / 对比度 | 0.2785 / 0.2199 | 0.0725 / 0.0848 | −74.0% / −61.4% |
| `depth_conf` 中位 | 11.70 | 7.60 | −35.1% |
| 裸地 conf | 15.91 | 8.31 | −47.8% |
| 水面 conf | 9.43 | 7.42 | −21.4% |
| **AUC**（conf 区分水面/陆面） | **0.865** | **0.670** | 判别力损失过半 |
| 水面落入本场高置信区 | 8.1% | **19.1%** | 危险方向的错误翻倍 |
| 全场 conf 四分位距 | 6.91 | 1.86 | 分布被压扁 |

**结论**：模型确实"知道自己看不清"（中位降 35%，方向正确），
但掉幅不均匀 —— 日间高置信的裸地腰斩，本就低置信的水面已在地板上只掉两成，
所有类别向同一低值收敛。**置信度不只是偏移，是信息量变少了。**

**这推翻了 8-25 早前那条实测给出的实现路径之一**：
「按场景取分位数阈值」只能修正偏移，修不了判别力下降 ——
暗场景里 19.1% 的水面像素落进本场高置信区，分位数假定不成立。

**涉及文件**：
- `docs/C1_CONFIDENCE_ANALYSIS.md` — 新增 §7（配对方法与两次纠错）、§8（结果）、
  §9（判别力坍缩及其对 C1/C4 的含义）、§10 局限、§11 复现；§4 加入被限定的告警框
- `docs/CLAUDE_CODE_PROJECT_SPEC.md` §14.13 — 新增 MUST：校准以场景与成像条件为条件变量分档标定；
  低照度档位 MUST NOT 假定 conf 仍能区分失效原因
- `docs/CLAUDE_CODE_PROJECT_SPEC.md` §40.3 C1 / C4、§46.1 表 — 修正「`_Evening` 即受控对照」的说法，
  加入配对三项约束（RTK 质心距离 / 亮度比 / 基线）
- `docs/FINDINGS.md` — 新增两条（判别力坍缩、傍晚≠暗）；旧「场景相对」条加限定
- `README.md` — R-01 状态与进度表

**为什么**：C1 依赖的不是置信度绝对值，而是它区分可信/失效的能力。
这个能力在最需要它的条件下退化，是必须写进规格的约束，不是一个实验数字。
副产品：暗场景中「自信但不可信」的水面像素是 C4 的程序化负样本来源。

**遗留**：仍未与 LiDAR 逐点比对（M-008 未解）—— 本次证明的是「conf 区分类别的能力下降」，
未直接证明「暗光下深度误差变大」。未分离亮度与对比度各自的贡献。


### `[实现]` C1 监督信号实测验证：水面失效信号成立，但置信度是场景相对的 — Agent

**用户预设**：VGGT-Ω 的点云重建质量并不特别好。据此按「相对差异」而非「绝对值」判读。

**方法上的关键点：绕开了 M-008。** UAVScenes 的逐像素 2D 语义标注与深度图在同一像素空间，可直接按类别切分 `depth_conf`，不需要相机-LiDAR 外参。类别语义经 `_color` 版反查确认（**类别 4 = 水面**，浅蓝 173,216,230），没有猜。

**结果一：水面失效信号真实且干净**（HKisland01_0013，基线 46.6 m，24 帧）

| | 中位 conf | 落入低置信区 | 落入**高**置信区 |
|---|---:|---:|---:|
| 水面 | **7.21** | **76.0 %** | **0.0 %** |
| 植被 | 20.59 | 4.8 % | 49.3 % |

水面 P95（14.03）低于植被中位（20.59），两分布基本分离。**没有一个水面像素进入高置信区** —— 模型从不在水面上自信地给深度。C1 的监督信号成立，且不必依赖 LiDAR 残差就能定位失效区。

**结果二（对照组暴露的陷阱）：置信度是场景相对的**

AMtown02_0000（无水面，基线 38.3 m）的植被中位 conf 仅 **8.54**，而 HKisland 的植被是 **20.59** —— **同一语义类别跨场景差 2.4 倍**。全场中位 10.24 vs 15.11。

**因此全局置信度阈值不可用**：在 HKisland 上合理的阈值搬到 AMtown 会把近半数植被误判为不可信。这**实证确认了 SPEC §14.13**「原始置信度 MUST 校准为错误事件概率」—— 此前是设计原则，现在有了具体失效数字。已新增 R-20（置信度校准）到待办。

**与用户预设一致**：AMtown02 全场置信度中位仅 10.24、植被 39.9% 落在低置信区 —— 无水面的普通场景重建质量本身就参差。正因如此按绝对值判读会误导；而水面与植被的差距在这种背景噪声下**依然清晰可辨**，这才是信号真实的证据。

**过程中的两个教训**：

1. **HKisland01 前 32 帧相机只移动 0.29 m**（起飞悬停段），零基线无法重建。选片段必须按 `camera_translation_span_m` 筛，不能取前 N 帧；
2. **`PENDING_DELETIONS` X-002 第一次实际咬人** —— AMtown01_0000 的坏标注（adapter v0.1.0 的 `_id`/`_color` 混淆）导致通道数不一致直接报错，只能另建干净对照组。

**局限**：各一个场景；未与 LiDAR 逐点比对（只证明"模型认为水面不可信"，未证明"深度确实错"）；未覆盖 HKairport 与 `_Evening` 航次。

**涉及文件**：`docs/C1_CONFIDENCE_ANALYSIS.md`（新建）、`docs/FINDINGS.md`、`README.md`

---

### `[决策]` 备份改为手动触发，不常驻自动同步 — 用户

**用户决定**：全量备份一份即可，不需要每 30 分钟自动检查的常驻程序，后续需要时手动备份。

**已执行**：停掉守护进程（PID 317575）与它的两个 PID 文件；`scripts/blob_backup.sh` 保留，头部改为「默认手动使用」，日常入口是 `./blob_backup.sh once`，`start` 的常驻模式保留但不启用。

**顺带停掉了一个正在传垃圾的 azcopy**（PID 402103）。停守护时它那轮刚启动，正在上传 `.git/objects/pack/tmp_pack_XHzgph`（13 GiB，另一个 session 的 `git add -A` 正在实时写入的临时 pack）。这类文件 git 自己迟早会清掉，传上去就是**永久滞留**在共享容器里 —— 因为当前 token 没有删除权限。

**但有一个没拦住**：`tmp_pack_sBdTzc`（**6.80 GiB**，8-24 那次中断操作的遗留）已在首轮全量备份时上传，现在删不掉。已登记 X-007。

**据此新增排除规则**：`EXCLUDE_PATTERNS="tmp_pack_*;*.incomplete"`（用 `--exclude-pattern`，因为 `--exclude-path` 不支持通配符）。顺带把一直在报失败的 `.pt.incomplete` 半成品也排除了。

**为什么**：在一个**没有删除权限**的共享容器上，「误传」是不可逆的。排除规则的价值不只是省流量，更是防止不可逆的垃圾堆积。

**涉及文件**：`scripts/blob_backup.sh`、`docs/PENDING_DELETIONS.md`（X-007）、`README.md`（R-27 状态）

---

### `[决策]` `[修正]` 导航类能力保留为后续目标，非移出范围 — 用户

**用户补充**：细线检测、安全性检测这类能力相对 C1 确实没那么 novel，但**模型需要足够的能力多样性（Diversity）**。因此不是放弃，只是优先级放在 C1–C4 之后。

**我此前的措辞过强**：写成「**永久移出范围**」「不是暂缓而是**不做**」，尤其 Next Agent Instructions 第 6 条 —— 那是新接手者最先读的地方。已全部修正为「当前不实施，保留为后续目标」。

**不变的部分**：UAVScenes 上仍然不得生成这些任务 —— 数据不支持这一事实不因优先级调整而改变（铁律 5）。

**新增**：SPEC §46.5 backlog 表（逐项阻塞原因与解锁条件）、§51 Release D；README「📦 后续目标 backlog」区 R-30～R-37（R-37 引入前视数据集是解锁前置项）；PROJECT_HANDOFF §19.7。

当初**保留而非删除** §14.6/§14.7 的决定在此得到回报 —— 前视数据集到位后可直接启用。

---

### `[实现]` VGGT-Ω 权重验证 + 真实数据跑通 L2-S1 — Agent

**权重**：经魔搭 `facebook/VGGT-Omega`（官方命名空间、未 gating）获取，4,576,706,117 字节。载入验证 **1411 张量 / 1.1441 B 参数 / missing 0 / unexpected 0**。

此前我因 SDK 显示「3.34G」而怀疑真伪、收回了「大小吻合」的判断 —— 那是 GiB 单位显示，收回是多余的。

**权重许可补齐**：魔搭侧 `LICENSE.txt` 可直接读（HF 需授权），确认 **FAIR NC v1，与代码许可一致**。填上了专家卡 `weights: 未知` 的空缺 —— 按 §23.2 那本属硬失败。

**真实数据实测**（UAVScenes AMtown01，24 帧 @512）：前向 1.67 s，峰值 8.29 GB，占卡程序持续运行未中断（剩余 13.1 GB/卡）。

| 量 | 值 | 意义 |
|---|---|---|
| depth 中位 | 1.0228 | 归一化非米制，需按相机轨迹锚定 |
| 深度起伏比 | 1.654 | 高于 blob 语料的 1.13，但仍偏低（航拍固有） |
| depth_conf 中位 | 11.432（1.2–26.6） | G1/G2 门禁的输入 |
| **低置信度像素占比** | **21.7 %** | **C1 感知可信度的天然候选区域** |

最后一行有直接价值：C1 的失效区域候选不用另外构造，重建本身就标出了两成像素。

**仍未完成**：重建质量未与 LiDAR 逐点比对（需 M-008 外参）；水面/反射/无纹理面失效未专门测试（HKisland 约 40% 水面是天然测试集）。按 §23.2 不得标 production-ready。

**涉及文件**：`registry/experts/vggt_omega_1b_512.yaml`、`docs/FINDINGS.md`

---

### `[决策]` 标注格式契约定为 ShareGPT — 用户

3D-GRPO 目前仍很基础，**只确定了标注格式尽量满足 ShareGPT 格式**；3D-GRPO 与 SFT 都可依据数据的具体类型再做调整。

**含义**：下游训练框架的现状不构成对数据设计的约束。adapter 的目标是产出**规范的 ShareGPT 记录**并**把判分所需信息给全**，而非迁就某个框架的当前实现。已据此调整 `pointcloud_native` 的文档口径与 verification 字段（`reward_compatible_with_current_grpo` → `sharegpt_conformant` + `mcq_renderable`）。

**涉及文件**：`docs/PROJECT_HANDOFF.md` §19.6、`task_adapters/adapters.py`、`tests/test_task_adapters.py`

---

### `[实现]` R-11 Canonical Task Record + 三类 adapter — Agent

**`schemas/canonical_task_record.schema.json`**：与模型无关的最终产物形态。`task_spec_id` 强制带版本（无版本引用无法复现）；`target_geometry` 必填且 `anchor_kind` 已按 §40 移除 centerline/trajectory/route；`capability_tags` 枚举已移除 thin_structure 等 6 项。

**三路 adapter**：

| adapter | 关键约束 |
|---|---|
| `pointcloud_native` | 产出 **ShareGPT 格式**；字段对齐依据是**实测** `3D-GRPO/grpo/dataset.py`（读 `conversations` 的 human/gpt 两轮、`point_clouds[0]` 只取第一个、`<point_cloud>` 占位符） |
| `qwen_2d_metadata` | **铁律 3**：显式丢弃 `pointcloud_ref`，即使记录里有 |
| `multimodal_3d` | 信息最全，因而最易泄漏 |

**泄漏防护做成不可绕过的**：`render()` 是 final 语义，子类只实现 `_render()`，基类在其返回值上强制扫描。理由是这类 bug **不报错、不崩溃**，只会安静产出一批"模型能作弊的题"，直到有人发现指标好得可疑。

**调试过程中修正的三类假阳性**（都是我最初的规则设计有误）：

1. **`evidence.used_fields` 被当成泄漏原子** —— 但 program-first 任务里这些字段本就该可见，模型的任务正是组合它们推出答案。隐藏的只有 target。
2. **短枚举词误判** —— `left` / `water` 是合法词汇。改为只把实体 ID、数值、以及长度 ≥8 的特异短语作为原子。
3. **`target_type` 被当成答案** —— 它是答案的**类型标签**（"这是一道最近距离题"），与 `task_spec_id` 天然同名，纳入原子会让每条记录都误判。

**两处精确豁免**（不放行整棵子树）：

- ShareGPT 的 `gpt` 轮**就是标签**，模型生成时看不到它 —— 精确豁免 `conversations[1].value`；
- MCQ 的选项必然含正确答案（否则无解），故豁免 human 轮；但**问题文本单独校验**，不得指明哪个选项对。

**测试 31 项**，全库 **212 项通过**。

**涉及文件**：`schemas/canonical_task_record.schema.json`、`task_adapters/`（新建包）、`core/metadata.py`、`tests/test_task_adapters.py`（新建）

---

### `[运维]` 实测 azcopy 上传到已有目录的覆盖语义 — 用户提问触发

用户问：手动 `upload` 指定一个已存在的 blob 目录，会不会覆盖里面已有的文件。

**先厘清工具实际用的参数**：`blob_manager.cmd_upload` 用的是 `--overwrite ifSourceNewer`，**不是** azcopy 默认的 `true`。`scripts/blob_backup.sh` 同。

**实测三条结论**（探针目录 `_ovtest` / `_ovtest2`）：

| 情形 | 行为 |
|---|---|
| 同名文件、本地 mtime 更新 | 覆盖，无提示 |
| 同名文件、本地内容变了但 mtime 未推进 | **静默跳过**，远程保留旧内容 |
| 目标有、本地没有的文件 | **不删除**，原样保留 |

复现：改内容后 `touch -d 2020-01-01` → `Completed: 0`，远程仍是 v1；`touch` 回当前时间后再传 → `Completed: 1`，远程变 v2。另测得 blob 的 Last-Modified 是**秒级**粒度，本地比远程新 1 毫秒仍被判为不更新而跳过。

**影响**：上传是合并叠加而非镜像替换。想清掉远程旧文件必须显式 `rm`；而「用新版覆盖」可能因时间戳没推进而实际什么都没传（日志显示 Skipped，不报错）。**备份脚本同样漏掉 mtime 不推进的文件** —— 属已知限制，未改（改成按内容比对要全量读 58G，代价不成比例）。

**涉及文件**：`docs/FINDINGS.md` 新增条目；`docs/PENDING_DELETIONS.md` X-004 追加 `_ovtest`/`_ovtest2`。未改任何代码。

---

### `[运维]` `[修正]` 自动备份从未生效 —— 重建为独立脚本 `scripts/blob_backup.sh` — 用户 + Agent

**用户需求**：把 `/home/aiscuser/nyp` 的自动备份改到 blob_manager 启动目录下，目录名 `nyp_<MMDD>` 跟随当日日期，每 30 分钟检查并同步；**只维护一个目录**，日期变化时覆盖 + 改名，而不是每天新建。

**排查中发现的事实，推翻了需求前提**：

1. **备份从未成功过一次。** 8-23 建立至今 86 轮同步，`✓` 计数为 0，`output/liyan/nyp_0823/` 是空目录。原因是 `blob_manager.py` 把 SAS token **烤进**生成的 `.blob_backup.sh`，而当时用的是代码里 `DEFAULT_SAS_TOKEN`（`se=2026-04-05`，早已过期），每个文件都 403 `AuthenticationFailed`。日志照常滚动，失败不显眼。
2. **路径本来就是对的。** `base_prefix=output/liyan` 正是 blob_manager 启动后 `ls` 所在的目录，备份指向 `output/liyan/nyp_0823`。用户以为跑到了容器根目录，实际是**因为它从来没传上去过**。
3. **当前 token 权限 `sp=racwl` 没有 `d`。** 实测写入 ✓、服务端复制 ✓、`azcopy rm` ✗（403 `AuthorizationPermissionMismatch`）。而 Azure Blob 没有原生改名，改名 = 服务端复制 + 删源。

**`[决策]` 缺删除权限时不硬改名。** `/home/aiscuser/nyp` 有 58G。若跨天后照常改名，旧目录删不掉，会在**多人共用**的容器里每天多堆一份 58G 全量副本。故改为：探测到无删除权限就跳过改名、继续同步到旧日期目录并记 ⚠ 告警（数据不丢，只是目录名滞后）。补上 `sp=racwdl` 的 token 后无需改代码即自动恢复改名。已登记 M-009。

**`[决策]` 不修改 `blob_manager.py`。** 一度把上述逻辑实现进了它，用户指出该文件是多人公共的，已**完整还原**（1553 行，`_backup_generate_script` 回到原第 1225 行，无残留）。逻辑改为独立脚本，代价是 blob_manager 自带的 `backup` 子命令不再承载本项目备份。

**新增 `scripts/blob_backup.sh`**（沿用 `gpu_guard.sh` 的 start/stop/status/once 形态）：

- **token 每轮现读** `~/.blob_config.json`，不缓存不烤死 —— 直接消除上述第 1 条的故障模式；`status` 显示 token 剩余有效期与权限位；
- **`nyp_{date}` 模板 + 状态文件**记录上轮实际目录，跨天触发改名（服务端复制 `old/*` → `new`，再删源）；
- **删除权限用探针实测**（真传一个小 blob 再真删），不靠解析 `sp=` 字符串猜；
- **排除 `secrets;logs/blob_backup.log`**；
- **源路径加 `/*`**：azcopy 的目录拷贝会把源目录名多套一层，不加通配会落成 `nyp_0825/nyp/...`。实测通配**包含** `.git`、`.gitignore` 等隐藏项；
- **区分「部分成功」与「整轮失败」**：azcopy 对 `CompletedWithErrors` 也返回 1，传输途中被改写的文件属此类，混为一谈正是旧方案没能暴露问题的地方。

**`[决策]` 排除 `secrets/`（用户确认）。** blob 容器多人共用（同容器下有 `siqi`、`zzr`、`gradataset` 等他人目录），`secrets/.env.local` 传上去等同泄露。已验证远程 `nyp_0825/` 下无 `secrets`。

**实测结果**：首轮全量 5902/5904 成功、56 GiB、约 90 秒（峰值 14 Gbps）；增量轮 5920 跳过、6–17 个更新、6–8 秒。恒定 2 个失败为 `logs/thinking.log`（占卡程序实时追加）与 `model_cache/vggt_omega/*.pt.incomplete`（下载中的半成品），属传输中被改写，下轮自动重试。

**涉及文件**：新增 `scripts/blob_backup.sh`；`~/.blob_backup.json` 路径清空（避免 blob_manager 重新拉起旧机制）；`~/.blob_backup.pid` 由新脚本共同维护（让 blob_manager 启动时显示「备份运行中」并跳过询问）；`docs/MANUAL_INPUTS.md` 新增 M-009/M-010；`docs/PENDING_DELETIONS.md` 新增 X-004/X-005/X-006。

**为什么**：一个从未生效的备份比没有备份更危险 —— 它提供了虚假的安全感。

### `[实现]` R-10 冻结 L0/L1/L2 Metadata Schema — Agent

数据框架的核心缺口。此前 SPEC §16 只有文字描述，`schemas/` 里只有归一化场景契约。

**新增 4 个 schema（版本 `0.1.0`）**：`l0_geometry`、`l1_entities`、`l2_relations`、`metadata_snapshot`。全部 `additionalProperties: false` —— 打错字的字段名必须报错而非被静默忽略。

**相对 SPEC §16 文字描述的两处实质设计变化**：

1. **新增 `surface` 实体类型**。SPEC 原 L1 只有 object/part/region/route/track，但 **C2 可降落性与 C3 地形推理的锚点是平面/表面**，不是对象。surface 携带 plane 参数、slope_deg、aspect_deg、roughness_m、area_m2、largest_inscribed_circle_m（比面积更贴近「能否放下一台无人机」）。
2. **L2 每条关系强制携带 `derivation.program` 与 `inputs`**，且 `inputs` 必须逐字段列出。没有它，§23.4 的「派生字段可重算」检查根本无从执行。

**按 §40 新能力范围的调整**：L2 关系类型移除 route_clearance / time_to_collision / reachability / swept_volume_overlap；新增 slope_difference_deg / surface_height_above_m；region 新增 `purpose` 字段区分 depth_reliability / landing_candidate / terrain_patch / change_region。

**`core/metadata.py`** 强制 9 项 JSON Schema 表达不了的跨层不变量：

- 跨层引用完整性、ID 唯一性与格式；
- **米制资格必须可重推** —— `metric_task_eligible` 不能手工填，必须与 `derive_metric_eligibility()` 的结果一致（铁律 8/9）；
- 派生程序必须已注册；
- 无效原因掩码未被合并（§14.5）；
- 置信度分量未被压成单一分数（§14.8）；
- **primary 深度制品必须是 VGGT-Ω 且只能有一份**（铁律 1/4）；
- 层引用必须带内容摘要（快照不可变性的技术保证）。

**metadata_snapshot 的设计要点**：下游唯一该引用的是 `snapshot_id`，不是散落的层文件路径 —— 否则无法保证任务编译时读到的是同一份一致的 metadata。`capabilities` 把资格判定固化进 metadata，Task Spec 的 `required_scene_capabilities` 直接比对；每个为 false 的资格位 MUST 在 `reasons` 给出理由，避免场景被静默丢弃。`l3_capability` 为显式 null 而非省略 —— 「确认没有」与「遗漏」是两回事。

**测试 39 项**：合法 fixture 必须通过（保证 schema 不是紧到没法用，且 fixture 本身是 schema 的可执行文档），每个不变量用故意构造的坏数据验证会被拦下。全库 180 项通过。

**涉及文件**：`schemas/l0_geometry.schema.json`、`l1_entities`、`l2_relations`、`metadata_snapshot`（新建）、`core/metadata.py`（新建）、`core/__init__.py`、`tests/test_metadata_schemas.py`（新建）、SPEC §16

---

### `[决策]` `[修正]` 低空差异化能力范围重定义（方案 A） — 用户

**背景**：用户提供无人机飞手痛点调研（大疆社区 / Reddit / MavicPilots），要求结合手上实际材料设计下游任务，并明确表示不必被调研报告的优先级牵着走。

**决定性实测**：UAVScenes 相机**近垂直下视，俯角中位 87.6°（范围 84.6–88.8°），对地约 33 m** —— 航测飞行，相机永远看不到飞行方向前方。

**移出范围**：薄障碍、前向避障、通道净空、可飞行体积、航迹可行性与瓶颈、TTC 与动态碰撞风险、Next-best-view 与主动感知、检查视角规划、有人机/鸟类避让、任务分解与计划批判。理由：强行生成会产出「形似导航训练数据、实则无有效监督」的样本，训练出虚假能力，违反铁律 5。

**新能力范围（按优先级）**：C1 感知可信度与失效归因 → C2 安全降落区评估 → C3 米制地形与高度推理 → C4 跨时相变化与光照鲁棒。

排序依据不是「无人机需要什么能力」，而是「哪些能力的监督信号极难获得，而本数据集恰好能可靠产出」—— 三种难获取形态（与外观矛盾的答案、外观相同但答案不同、无外观对应物的数值）本数据集均可大规模产出。

**文档修订（用户特别要求仔细，避免旧内容误导后续执行）**：

- 用 grep 全量检索 10 类导航术语，建立完整改动清单；
- 策略是**整节重写 + 对被废止内容打显式标记**，而非零散词替换（后者易留残余且前后矛盾）；
- SPEC 升至 v0.3.0，顶部加不可错过的重定义横幅；重写 §1/§13/§14.15/§16/§20.3/§23.4/§28.2/§34/§40/§41/§43/§44/§45/§46/§47/§49/§51；§14.6/§14.7 打「当前不适用」标记但保留规则本身；
- **最危险的一处**：§41 Canonical Task Record 的示例原为 `uav.route.minimum_clearance` —— 那是「最终输出长什么样」的范例，照着写会直接跑偏。已换成 C1 感知可信度的示例；
- README 第四层整体重写；PROJECT_HANDOFF 加顶部横幅 + 5 个历史章节就地标记 + §19.5 决策记录 + Next Agent Instructions 修正；AGENT_SKILL_SYSTEM_DESIGN §4.6 与覆盖率列表；
- **Task Spec 的事实错误**：metric 任务原声称「候选实体包含电线、杆塔等细长障碍」与数据事实不符，已改正；另两个 Spec 移除 `aerial_active_view` 信号；
- 迭代验证：裸露旧内容从 23 处 → 5 → 2 → 0（SPEC）；全库从 18 → 13 → 6 → 2（余 2 处：一处被章节标记覆盖，一处为过去时历史陈述）。

**未采纳的方案 B**：保留导航能力并引入前视/侧视数据集。用户选择 A 先行；B 作为后续扩展，届时 §14.6/§14.7 规则可直接启用，无需重写。

**涉及文件**：`docs/CLAUDE_CODE_PROJECT_SPEC.md`、`README.md`、`docs/PROJECT_HANDOFF.md`、`docs/AGENT_SKILL_SYSTEM_DESIGN.md`、`task_specs/*`（3 个）

---

### `[决策]` 第三层降为润色层，优先搭通一/二/四层主干 — 用户

**决策**：先完整搭通「数据输入 → 中间的提取/生成/处理 → 下游任务输出」这条主干（第一、二、四层），**第三层的 Skill 封装与统一门禁框架暂缓**。

**理由**：Skill 本质是**润色性质**的 —— 包装可复用的提示词与核验方法，应当在已有完整链路可供审视之后，再判断哪里值得优化、哪里值得新增 Skill 实现的能力。主干未通就先造 Skill，等于对着不存在的流程写规则。

**关键区分（写入 `PROJECT_HANDOFF.md` §19.4 对照表）**：第三层多数条目具有**双重身份** —— *功能*在主干数据流上，*Skill 封装*才属于第三层。

- 保留并以**普通代码**实现：L2-S6 任务编译、接入校验、样本校验、metadata 质量与 provenance；
- 暂缓：Orchestrator 执行器、G1–G6 统一门禁框架、8 个 Skill 的封装、两个 registry-manager。

即**保留必要的校验动作，暂不建立统一的 Skill 与门禁框架**。

**由此暴露的主干真实缺口**（重排后的当前重点）：

1. **L0/L1/L2 Metadata Schema 尚未冻结** —— SPEC §16 只有文字描述，`schemas/` 里只有归一化场景契约，对象/关系/场景包的 JSON Schema 全缺。**这是数据框架的核心缺口，后面所有东西都插在它上面。**
2. **Canonical Task Record 未实现** —— SPEC §41 有契约无代码，它定义最终输出长什么样。
3. **三类 adapter 未实现** —— `pointcloud_native` 是 3D-GRPO 的直接消费接口。
4. L2-S3 提升融合、L2-S4 派生、L2-S6 编译均无实现。

**README 追踪表已重排**：待办分「主干（当前重点）」与「次要」；第三层三项移入暂缓并标注原因。

**涉及文件**：`PROJECT_HANDOFF.md` §19.4、`README.md`、`docs/AGENT_SKILL_SYSTEM_DESIGN.md`（加暂缓横幅）

---

### `[运维]` `CLAUDE.md` 移入仓库进行版本管理 — 用户

**要求**：`nyp/` 下所有内容应归属 NewNiuuu；`CLAUDE.md` 移到 `3D-data-pipeline/` 一起做 git 版本管理。

**处理**：移入仓库，并在 `nyp/CLAUDE.md` 留符号链接指向它 —— 兼顾版本管理与 session 启动时的自动加载（子目录中的 CLAUDE.md 不会被自动加载）。

**涉及文件**：`CLAUDE.md`（移入仓库）、`nyp/CLAUDE.md`（符号链接）

---

### `[需求]` README 改为用户的进度追踪入口 — 用户

**要求**：README 是用户持续追踪项目用的文档。每次改动记进 CHANGELOG 即可，不要堆进 README；README 需要一张**进度/待办表**，涵盖用户提出的、商讨确定的、以及 Agent 认为该做的需求，与实际完成情况对照。

**改动**：README 顶部新增「📋 进度追踪表」，41 行需求按状态分四组 —— 🔴受阻 / 🟡待办 / ⏸️暂缓 / ✅已完成，每行带编号（`R-nn`）、来源标记（用户 / 商讨 / 建议）、以及所属架构层或产出。待办项按建议优先级排序，受阻项写明阻塞编号与影响面。

同时更新过期的头部说明（原写「架构设计完成，尚未在服务器实现」「信息核验截止 2026-08-23」），并把追踪表提到全文最前。

**`CLAUDE.md` 新增规则**：README 的读者是用户、职责是追踪「还有什么要做、做到哪了」；每次交付必须更新进度表；但改动细节一律进 CHANGELOG，不得堆进 README。

**涉及文件**：`README.md`、`CLAUDE.md`

---

### `[修正]` 尺度恢复的精度结论被系统扫描推翻 — Agent

**用户要求**：把基线阈值定准。

**结果：阈值定不出来，而且此前两条结论都被推翻。**

**做了什么**：固定评估帧，用包含该帧的不同窗口分别重建并锚定尺度，看米制深度是否收敛。

**发现 1 —— 参考值本身不稳**：48 帧 stride1 得 31.54 m，48 帧 stride3 得 45.63 m，**两个长基线配置相差 45%**。没有稳定参考，"误差"无从谈起。

**发现 2 —— 帧数是独立于基线的因素**：k=6 到 k=32 之间基线锁定在 3.39 m 不变，误差却从 4.5% 降到 0.3%。我此前把两者混为一谈。

**发现 3 —— 根因在重建而非尺度**：同一评估帧在 6 种配置下，未缩放 depth 的 CV 为 21.0%，反解尺度 CV 为 41.8%，**两者乘积（锚定后米制深度）CV 仍达 19.5%**。若锚定有效，乘积 CV 应远小于两因子。实测 19.5% ≈ 21.0%，说明**尺度锚定几乎没起作用**。

根因：DA3 对同一帧的深度预测会随窗口内其他帧改变（参考视图选择、上下文不同），这不是全局缩放差异，**一个标量补不回来**。数学前提「重建内部单位全局一致」在 DA3 上不成立。

**被推翻的两条结论**：

1. 08-24 报「相对深度锚定后误差 0.5%」—— 是特定窗口与 LiDAR 中位数的偶然吻合，不可复现；
2. 08-24 报「基线 ≥2.0 m 即可作为米制任务阈值」—— 无实证支持。

**数学关系本身仍然成立**（相似变换只有 1 个标量影响米制量），受影响的是可达精度：**上限由重建稳定性决定（约 20% CV），而非尺度拟合精度**。因此换更好的尺度锚点没用，得先解决重建稳定性。

**M-008 重新升级为阻塞项**。我 08-24 将其降级的理由（"尺度可由相机轨迹恢复，不需要标定文件"）已被推翻。没有独立真值就无法给出任何精度数字。

**代码修正**：三个 Task Spec 的 `camera_baseline_m_at_least: 2.0` 由充分条件降为**必要不充分条件**（仅排除明显退化轨迹），新增 `domain_calibrated: true` 作为唯一充分条件，并新增 `reject_if.reconstruction_scale_unstable`。141 项测试全过。

**方法论教训**：连续两次得出被下一实验推翻的结论，共同原因是**用被测系统自身作参考**。自洽检验只能证伪不能证实 —— 几个配置互相吻合可能只是共享同一偏差。**凡是要给出精度数字，必须有独立于被测系统的真值来源。**

**适用范围**：本结论针对 **DA3**，不能外推到 VGGT-Ω（点云主路径，权重待批）。VGGT-Ω 是多视角联合重建，稳定性可能更好，但必须实测。

**涉及文件**：`docs/SCALE_RECOVERY_ANALYSIS.md`（新增「重大修正」节）、`docs/FINDINGS.md`、`docs/MANUAL_INPUTS.md`、`task_specs/*`（3 个）

---

## 2026-08-24

### `[运维]` 修正 git 提交作者 — 用户

**问题**：这台机器是组里共用的，git 全局身份是 `woods <woodserenity@sjtu.edu.cn>`，导致 9 个提交全部错误归属，无法按批次追踪。

**修复**：`git filter-branch` 改写全部 9 个提交的 author/committer 为 `NewNiuuu <LazyNiuuuu@outlook.com>`，并在**仓库级**（非全局）固化该身份，避免再受共用机器的全局配置影响。强推覆盖远程。

**安全性**：改写前后 HEAD 树对象哈希一致（`2ec9c517…`），**文件内容零改动，只改元数据**。原始提交保留在 `refs/original/`。

**提醒**：GitHub 靠邮箱关联账号，该邮箱需在 GitHub 账号中验证过才会显示头像与贡献图。

**涉及文件**：git 历史（内容未变）、仓库级 git config

---

### `[实现]` 尺度恢复分析：不用 metric 模型也能拿到米制深度 — 用户提问触发

**用户提问**：不同深度输出形式之间有没有数学转换关系？若有，是否就不必非要拿到 metric 数据？

**结论：有，且我们手上就有锚点。**

多视角重建差一个 7 自由度相似变换，但**只有其中 1 个标量（尺度）影响米制量** —— 旋转平移不改变任何两点间距离。UAVScenes 每 run 带 RTK 且相机轨迹已验证为米制，故 `s = |真实相机位移| / |重建相机位移|`，用 Umeyama 求解。**这一步不需要相机-LiDAR 外参**（两边都是相机位置）。

**实测**（DA3-LARGE-1.1 相对深度 × 反解尺度 vs LiDAR 真值中位）：

| 场景 | 相机轨迹行程 | 反解尺度 | 对齐残差 | 误差 |
|---|---:|---:|---:|---:|
| AMtown01_0000 | 3.70 m | 37.52 | 0.141 m | **0.5 %** |
| AMtown01_0001 | 13.67 m | 76.23 | 0.202 m | **5.0 %** |
| AMtown01_0002 | **0.15 m** | 22.35 | **0.026 m** | **77.3 %** |

**两个关键发现**：

1. **基线不足则灾难性失效**。第三行相机几乎未移动，轨迹退化，尺度自由度未被约束。
2. **低对齐残差不代表尺度可信**。第三行残差是三者中最小的（0.026 m），误差却达 77%。退化轨迹本就容易拟合得好。判据必须是**基线长度与轨迹构型**，不是残差。

**落到代码**：三个 Task Spec 的 `eligibility` 新增 `camera_baseline_m_at_least: 2.0` 与 `reject_if.scale_recovery_degenerate`，并在注释中写明「判据不是对齐残差」。24 项 Task Spec 测试仍全过。

**M-008 降级**：原判断「没有标定文件就无法解锁绝对米制任务」**不成立**，改为按需触发。它仍有价值 —— 逐像素比对可区分「尺度对但形状错」与「整体偏差」，这也是 AMtown01_0001 那 5.0% 误差待查清的手段。

**局限**：LiDAR 对比不严格（射线距离 vs 垂直深度），绝对误差是量级参考；仅测 DA3 一个模型、AMtown01 一个 run；2.0 m 阈值是保守取值而非实测拐点，需系统扫描确定。

**涉及文件**：`docs/SCALE_RECOVERY_ANALYSIS.md`（新建）、`docs/FINDINGS.md`、`docs/MANUAL_INPUTS.md`、`task_specs/*`（3 个）

---

### `[需求]` 调研结果需另记一份面向人类的简明文档 — 用户

**要求**：调研性质的产出也要记录到类似 README 的人类可读文档中，简明易懂；并再次强调文档必须及时更新。

**改动**：新建 `docs/FINDINGS.md` —— 每条只写「结论一句话 + 为什么重要 + 详情去哪看」，不放实现细节。`CLAUDE.md` 规则 1 新增「调研结果必须双份记录」：详细文档记数据与复现命令，FINDINGS 记结论与影响。

**顺带修正**：`CLAUDE.md` 的章节结构此前被我插乱（规则 3 插进了规则 1 中间，导致「变更日志」「人工输入」等规则 1 的小节跑到规则 3 底下，规则 2 排到最后）。已重排为规则 1 → 2 → 3，各自小节归位。

**涉及文件**：`docs/FINDINGS.md`（新建）、`CLAUDE.md`、`README.md`

---

### `[实现]` 补装 MoGe-3、DA3Metric-Large、CoTracker3 — Agent

**MoGe-3（用户批准独立环境）**：新建 conda env `nyp-moge`（numpy>=2），`flex-gemm` 有预编译 wheel 无需自行编译。真实图像推理通过，峰值 2.87 GB。输出 `points`/`depth`/`normal`/`mask`/`intrinsics`，其中 **`normal` 是独立法向而非深度微分所得**，满足 SPEC §14.14 要求 —— 这使 DSINE 的优先级下降。

**DA3Metric-Large**（Apache-2.0）：峰值 2.91 GB，depth 6.97–23.78 m。**但 `conf`、`extrinsics`、`intrinsics` 全为 `None`** —— 只输出 depth 与 sky 掩码。这意味着它**过不了需要置信度的 G1/G2 门禁**，只能作单目尺度先验与 sky 掩码来源，不能参与位姿交叉校验。

**CoTracker3 Offline**：tracks `(B,T,N,2)` + visibility `(B,T,N)`，峰值 0.86 GB，8 帧可见率 0.971。GitHub API 报 `NOASSERTION`，许可全文尚未人工审查，已记入卡片阻塞项。

**尺度对比（重要）**：同一帧上 DA3-Large-1.1 给 0.57–1.02（归一化）、DA3Metric-Large 给 6.97–23.78 m、MoGe-3 给 16.74–22.96 m，而 LiDAR 真值射线距离中位 33.13 m —— **三者互不一致且都对不上**。这是 SPEC §14.13「多专家不得投票产生真值」的现实例证。

**但该对比不严谨**：射线距离 vs 垂直深度、传感器原点与视场均不同。严格验证需相机-LiDAR 外参投影，而 `calibration_results.py` **不在 interval=5 档案中**。因此所有模型 `domain_calibrated` 保持 `false`，绝对米制目标暂不解锁。已登记 **M-008** 索取该标定文件。

**涉及文件**：`registry/experts/`（moge 更新至 v0.2.0，新增 da3_metric_large、cotracker3_offline，共 9 张卡）、`docs/EXPERT_DEPLOYMENT.md`、`docs/FINDINGS.md`、`docs/MANUAL_INPUTS.md`

---

### `[实现]` 专家模型许可核验与部署 — Agent

用户要求部署文档中提到的专家模型（特别指定 DA3）。按 SPEC §23.2，**候选等级不等于使用许可**，先逐个核验代码/权重许可再部署。

**许可核验结果 —— 全部可用，无一构成阻塞**：DA3 代码与 `DA3-LARGE-1.1`/`DA3-BASE`/`DA3METRIC-LARGE` 均 Apache-2.0（**SPEC §14.1 所称 "DA3-1.1 Apache-compatible variant" 核验属实**；但 `DA3NESTED-GIANT-LARGE` 是 cc-by-nc-4.0，同项目不同变体许可不同）；SAM 2.1 / Grounding DINO / DINOv2 为 Apache-2.0；OneFormer / Florence-2 / MoGe-3 为 MIT。

**已部署并在真实 UAVScenes 图像上验证通过**（非合成输入）：

| 模型 | 峰值显存 | 实测输出 |
|---|---:|---|
| DA3-LARGE-1.1 | 3.62 GB | 3 图 @504 前向 0.74s |
| Grounding DINO Base | 2.01 GB | 检出 building/road 等 4 框 |
| DINOv2 Base | 0.37 GB | CLS embedding (1,768) |
| SAM 2.1 Base+ | — | mask (1,3,2048,2448)，iou 0.843 |

**关键判定**：DA3-LARGE-1.1 输出的是 **`relative` 深度**（`is_metric` 为空、`scale_factor` 为 None、depth 落在 0.57~1.02），按铁律 8 不得直接产出绝对米制目标。需 metric 第二意见应改用 `DA3METRIC-LARGE`（同 Apache-2.0，未部署）。

**三个有问题的**：

1. **OneFormer** —— 可运行但 `swin.layernorm.weight/bias` 在 transformers 5.15.1 下报 `MISSING` 并被随机初始化，输出可信度存疑。它产出的是 §14.5 的 sky/water 无效几何掩码，错误会直接污染 G2，**确定兼容版本前不得启用**。
2. **Florence-2** —— `Florence2LanguageConfig` 缺 `forced_bos_token_id`，其 remote code 按旧版 transformers 编写。不为它降级主环境（会影响已验证的其他四个模型）。
3. **MoGe-3** —— 几何专家接入顺序的**首选**，但存在硬冲突：MoGe 要 `numpy>=2`，VGGT-Ω 与 DA3 要 `numpy<2`；另需 `flex-gemm` CUDA 扩展与 `utils3d_moge` 专用 fork。**解决方案：独立 conda 环境 + 文件交换**，这与它"关键帧离线交叉校验"的角色天然相容。

**新增** `registry/experts/` 7 张专家卡（SPEC §23.2 要求的分层许可、I/O 契约、实测数据、UAV 验证状态、阻塞项），以及 `docs/EXPERT_DEPLOYMENT.md` 总览。

**两个安装陷阱已记录**：numpy 会被 imageio/plyfile/utils3d 反复拉到 2.x，每批依赖装完必须重新钉住并校验；DA3 的 xformers/open3d/fastapi 均可跳过（分别是可选加速路径、bench、web 服务），用 `--no-deps` 装本体可避开 xformers 换掉 torch。

**GPU**：全部推理在占卡程序持续运行下完成（剩余约 13 GB/卡），未中断保活。

**涉及文件**：`registry/experts/*.yaml`（新建 7 个）、`docs/EXPERT_DEPLOYMENT.md`（新建）

---

### `[需求]` `[修正]` 改用项目专属 conda 环境，不碰共享 base — 用户

**要求**：使用模型相关依赖时不要动共享 base 环境，为本项目建隔离环境。随后进一步要求用 **conda** 而非 venv。

**我的错误**：安装 VGGT-Ω 依赖时直接装进了共享的 `/opt/conda/envs/ptca`。`opencv-python-headless 5.0` 把 numpy 从 1.24.4 拉到 2.2.6，**同时违反了 VGGT-Ω 的 `numpy<2` 与 scipy 1.10.1 的约束**。

**已还原**：numpy 回退 1.24.4，卸载 opencv-python-headless / einops / safetensors，`pip check` 确认 "No broken requirements found"，共享环境回到我动手前的状态。

**新环境**：conda env `nyp-3dpipe`（python 3.10.20），独立安装 torch 2.8.0+cu126、torchvision 0.23.0+cu126、numpy<2、einops、safetensors、opencv-python-headless<5、pyyaml、jsonschema、pytest。141 项项目测试在新环境全过。

**发现的隔离漏洞**：`~/.local/lib/python3.10/site-packages` 下有 35 个包（wandb、webdataset、ftfy…）**会渗进任何 python3.10，包括 conda 环境**。已用 `conda env config vars set PYTHONNOUSERSITE=1` 绑定，但**直接调用 python 二进制时该配置不生效**，必须显式带变量，否则隔离是假的。

**新增规则 3**（`CLAUDE.md`）：禁止向共享 base 安装/升级/卸载任何包；给出项目环境调用方式、`PYTHONNOUSERSITE` 的必要性与验证命令、以及误动共享环境后的还原流程。

**涉及文件**：`CLAUDE.md`、`docs/PENDING_DELETIONS.md`（X-003 废弃 venv）

---

### `[实现]` VGGT-Ω 部署与输出契约实测 — Agent

**可获取性**：SPEC §38 记录的三个 URL 全部有效。代码 clone 成功（commit `282ec70`），**权重 `gated: manual` 需申请**。

**许可**（G0 分层记录）：

- 代码 **FAIR Noncommercial Research License v1**；
- 关键条款"outputs or results 亦限于 Noncommercial Research Uses"，但**没有**"禁止用输出改进其他 AI 模型"的条款 —— 与 WorldMirror 不同，因此 **VGGT-Ω 输出可进入训练 metadata**；
- 权重许可**未知**（需获批后才可见），按 §23.2 属硬失败，获批前不得标记 production-ready；
- 开放问题：CC BY-NC-SA 4.0 的 ShareAlike 与 FAIR NC 的衍生条款能否同时满足，不确定。不影响研究使用，列为 G6 发布门禁的开放项。

**实测输出契约**（随机权重前向，key/形状/dtype 为真）：

```
pose_enc     (B,S,9)        depth       (B,S,H,W,1)    depth_conf  (B,S,H,W)
camera_and_register_tokens  (B,S,17,2048)
encoding_to_camera -> extrinsics (B,S,3,4)   intrinsics (B,S,3,3)
```

模型 1.144 B 参数（fp32 约 4.58 GB）。**2 帧 @512 峰值 6.53 GB**，与官方参考（1 帧 6.02 GB）量级一致。SPEC §13 声称的输出能力**全部属实**。

**两点部署实测**：核心包**不需要 `cv2`**（只有 gradio demo 的 `visual_util.py` 用）；`numpy<2` 是硬约束，opencv 5.x 会破坏它。

**GPU 使用**：在占卡程序仍占 27 GB/卡（剩余 12.62 GB）的情况下跑通，未中断服务器保活，无需 release。

**当前阻塞**：权重需申请，登记为 M-007。

**涉及文件**：`docs/VGGT_OMEGA_DEPLOYMENT.md`（新建）、`docs/MANUAL_INPUTS.md`、`third_party/vggt-omega`（未纳入 git）

---

### `[实现]` 现有 VGGT-Ω 点云语料分析 — Agent

下载 blob `Pointcloud-VQA/Floodnet/train/` 的 3 个 `.ply` 实测。三条结论：

1. **格式**：binary PLY，逐点仅 `xyz + rgba`。**无法向、无置信度、无相机参数、无 provenance** —— 是可视化交付形态，不是 VGGT-Ω 完整输出。本 Pipeline 的 metadata 层无法直接消费：缺置信度过不了 G1/G2，缺相机参数做不了投影与跨视角关联。
2. **尺度是 relative 而非 metric**：到原点距离中位数 ≈ 1.00，整个航拍场景跨度不足 1 单位。按铁律 8/9 禁止用于绝对米制目标。深度起伏小（`z_max/z_min ≈ 1.13`），这是航拍近垂直视角的固有特性，也意味着可供 3D 任务利用的深度信息有限。
3. **组织与任务形态**：全部 9 个数据集约 38 万样本，每样本恰好 1 个 `.ply`（逐图像单视角反投影，非多视角融合）；题型为 `Condition_Recognition` / `Yes_No` / `Counting` / `Quality Assessment`，即**把 2D 识别题搬到点云上**，属 SPEC 铁律 5 与 HANDOFF §2.2 明确排除的形态。

这不是对既有工作的否定，而是明确了本 Pipeline 要补的差距：**点云要带尺度、置信度与 provenance，任务要真正依赖三维**。UAVScenes 的多视角 + RTK 正好提供这两样。

**新增风险**：航拍深度起伏小，需在 Task Spec 的 `eligibility` 中加入深度起伏下限，优先选取有高差的场景。

**涉及文件**：`docs/BASELINE_POINTCLOUD_ANALYSIS.md`（新建）

---

### `[实现]` vertical slice 第 7–8 步：确定性几何 + checker + 三类 Task Spec — Agent

**新增 `geometry/primitives.py`**（17 个纯函数，SPEC §14.15 / 铁律 7）：点到线段/折线距离、多折线取最近、点集间最小距离、相机中心与光轴、世界系↔相机系、投影、观察者相对方位、方位角/俯仰角、高度差、质心、AABB、PCA-OBB、视锥测试、可见比例。

设计纪律：纯函数无 I/O（checker 才能独立重算）、单位显式、**退化情形抛 `GeometryError` 而不返回近似值** —— 一个在退化输入上给出貌似合理数值的几何函数会静默污染整个数据集。

**新增 `checkers/task_checkers.py`**（4 个 checker）：三条纪律 —— checker **独立重算 target，不采信样本里存的值**；容差随版本冻结；不做语义宽容。

**新增 `core/task_spec.py`**：Task Spec 加载器，在编译任何样本**之前**静态拦截违规，含铁律 6 的机器可判定形式（含父路径泄漏检测）、checker 注册检查、铁律 8 的尺度资格检查、3D 必要性与低空特性的论证非空检查。

**新增 4 个 Task Spec**（覆盖用户确认的 3 个任务族）：

| Spec | 族 | 推导程序 | checker |
|---|---|---|---|
| `3d_grounding.object` | grounding | `select_referent_by_spatial_predicate` | `check_object_grounding_answer` |
| `3d_vqa.metric.minimum_distance` | vqa | `minimum_point_to_polyline_distance` | `check_minimum_distance_answer` |
| `3d_vqa.situated.observer_relative_direction` | vqa | `observer_relative_direction` | `check_observer_relative_direction_answer` |
| `cross_view_correspondence.object` | cross_view | `link_observations_via_lifted_point_support` | `check_cross_view_correspondence_answer` |

**新增 4 个答案输出 schema**（`schemas/answers/`），均 `additionalProperties: false`，ID 用正则锁死 `<ns_NNN>` 格式，数值答案强制显式 `unit`。

**两处把"数据实测结果"写进阈值论证**（而非拍脑袋取值）：

- metric 距离容差 0.10 m —— UAVScenes 相对尺度精度优于 0.25%，40 m 距离上约 0.1 m，容差与数据精度相当；
- situated 左右死区 ±10° —— 绝对配准残差 0.44~1.89 m，20 m 距离上对应 1.3~5.4° 角度不确定度，10° 留有余量。

**测试**：141 项全过。其中 `test_task_specs.py` 用**故意构造的违规 Spec** 验证校验器确实会拦（12 项）—— 一个从不失败的校验器等于没有校验。

**涉及文件**：`geometry/*`、`checkers/*`、`core/task_spec.py`、`task_specs/*`、`schemas/answers/*`、`tests/test_geometry_and_checkers.py`、`tests/test_task_specs.py`

---

### `[修正]` adapter 标注定位在 `*_id` 与 `*_color` 间随机命中 — Agent

**问题**：两个标注档案各含 `*_id`（类别 ID）与 `*_color`（RGB 可视化）两个平行目录，**文件名完全相同**（各 2589 个）。adapter v0.1.0 的 `_label_member` 用后缀匹配遍历无序 `set`，随机命中其一 —— 已落地场景中约半数帧的标签是 RGB 三元组而非类别 ID。

**初次判断有误**：我最初把这看成"数据集内部标注编码不一致"。实际是我的 adapter 把两个平行目录混为一谈，数据集本身是一致的。

**修复**：改为拼接确定路径 + 存在性校验，语义真值一律取 `*_id`；adapter 版本 0.1.0 → 0.2.0；新增 5 项测试锁死（含"标签行数必须等于点云行数"与"未知 stem 必须返回 None 而非模糊匹配"）。

**副作用**：标注查找从扫描全部成员变为 O(1)，adapter 测试从 21 秒降至 3.7 秒。

**遗留**：已落地的 3 个场景标注不可信，记入 `PENDING_DELETIONS.md` X-002。

**涉及文件**：`adapters/uavscenes/adapter.py`、`tests/test_uavscenes_adapter.py`、`docs/PENDING_DELETIONS.md`

---

### `[需求]` 建立待删除清单，Agent 不再执行删除 — 用户

**要求**：新开一个文档存放待删除内容与删除命令；Agent 正常推进时不管删除，积攒后由用户手动查看处理。

**改动**：新建 `docs/PENDING_DELETIONS.md`；`CLAUDE.md` 增加「不执行删除」条款。删除命令带防误删前置检查。

**保留的例外**（仍需当场请示，因为可能丢失真实成果）：未提交的代码/文档/实验结果、用户提供的原始数据、删除范围可能超预期（通配符/递归删父目录）、无法确定是否还有其他引用。

**涉及文件**：`docs/PENDING_DELETIONS.md`（新建）、`CLAUDE.md`

---

### `[决策]` 项目定位与 3D-GRPO 关系澄清 — 用户

**澄清内容**：

1. **本 Pipeline 的最终产物是一对交付物**：2D 数据集对应的**点云** + 该点云对应的**下游任务标注**。只生成点云不算完成。
2. **Blob 上的点云**（D-001/D-002）是同事已用 VGGT-Ω 转出的**最终点云结果**，即"2D → 点云"这一步在 `data/` 那批数据集上已完成。同时它们**也可以**作为生成下游标注的中间产物，**是否纳入取决于后续任务设计**，当前不预先锁定。
3. **`3D-GRPO` 是下游训练框架**，不属于数据生成：用产出的点云 + 任务标注先做 SFT，再用 GRPO 训练自有点云理解模型。**当前与数据生成解耦**，无需为其调整排期；它目前只是初步框架，待新类型数据产出后再改。

**对架构的影响**：SPEC §39/§41 三类 adapter 中，`pointcloud_native` 有了明确消费方（3D-GRPO），优先级**不低于** `qwen_2d_metadata`。Task Spec 必须保证 target 可映射到点云几何锚点，而非只服务 Qwen 的文本接口。这不改变铁律 2/3 —— Qwen 在本架构中仍只读 2D + metadata。

**关闭的未决项**：`PROJECT_HANDOFF.md` §19.2 由「尚未确认」改为「已澄清」，并标记为 `[用户已确认]`。

**涉及文件**：`docs/PROJECT_HANDOFF.md` §19.2、`README.md`、`docs/AGENT_SKILL_SYSTEM_DESIGN.md` §13、`docs/MANUAL_INPUTS.md` §3

---

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
