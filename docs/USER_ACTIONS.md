# 需要你处理的事项

> **这份文档只有两类内容：需要你提供的信息、需要你删除的文件。**
> 项目进度看 `../README.md`。
> 建立于 2026-08-25（由 USER_ACTIONS.md 与 USER_ACTIONS.md 合并）。

---

# 第一部分：需要你提供的信息


> 用途：登记项目推进过程中需要用户手动提供的信息（token、密钥、账号、链接、许可申请结果等）
> 阅读对象：用户与 Agent 共同维护
> 建立日期：2026-08-24

## 0. 安全红线

本项目已配置 GitHub remote 并公开推送：

```
origin    https://github.com/NewNiuuu/3D-pointcloud-data-pipeline.git
```

（外层 `nyp/` 仓库另有 remote `WoodSerenity/uavlm.git`，与本项目互不跟踪。）

**任何写进本文件的内容都可能被 commit 并 push 到 GitHub。**

因此：

- **真实的 token / API key / 密码 / SAS URL 一律不写进本文件。**
- 本文件只登记四件事：**需要什么、为什么需要、值放在哪里、是否已提供**。
- 真实值存放在 `secrets/.env.local`（该目录已配置为整体 git 忽略），或由用户直接 `export` 到环境变量。
- 若发现本文件里出现了疑似真实凭证，立即停下来告知用户，并按凭证轮换处理，不要只是删掉了事 —— 已进入 git 历史的密钥必须视为已泄露。

## 1. 使用方式

### Agent 侧

1. 推进过程中遇到需要人工提供的信息时，先在下方「待提供」表里新增一行。
2. **停下来告知用户**，说明卡在哪个环节、拿不到会导致什么。
3. **不要用占位符、假值或猜测的值继续往下跑**，也不要为了绕开而降低方案要求。
4. 用户提供后，把该行状态改为 `已提供`、填写更新时间，并**只记录变量名或存放位置，不回填真实值**，然后移入「已提供」归档表。

### 用户侧

两种给法，任选：

```bash
# 方式 A：写入 secrets/.env.local（推荐，重启后仍在）
mkdir -p /home/aiscuser/nyp/secrets
echo 'HF_TOKEN=实际的值' >> /home/aiscuser/nyp/secrets/.env.local

# 方式 B：临时导出到当前 shell
export HF_TOKEN=实际的值
```

也可以直接在对话里给出，Agent 负责写入 `secrets/.env.local` 并在本文件登记状态。

### 状态取值

| 状态 | 含义 |
|---|---|
| `待提供` | 已经需要，但还没拿到，相关工作被阻塞 |
| `已提供` | 已拿到并可用 |
| `不需要` | 评估后确认本阶段用不上 |
| `已失效` | 过期、被吊销或权限不足，需要重新提供 |

## 2. 待提供

| # | 需要的信息 | 用途 / 触发环节 | 变量名或存放位置 | 状态 | 更新时间 | 备注 |
|---|---|---|---|---|---|---|
| M-009 | **带删除权限的 Azure SAS Token（`sp=racwdl`）** | `scripts/blob_backup.sh` 的日期改名：把 `nyp_<旧日期>` 改名为 `nyp_<今日>` = 服务端复制 + 删源，删源需要 `d` 权限 | `~/.blob_config.json` 的 `sas_token`（在 blob_manager 里用 `token` 命令更新） | **待提供（功能降级中，备份本身不受影响）** | 2026-08-25 | 当前 token 权限为 `racwl`，实测 `azcopy rm` 返回 403 `AuthorizationPermissionMismatch`。缺它的后果：跨天后目录名停在旧日期，脚本会记 ⚠ 并继续同步到旧目录，**数据不会丢**。之所以不硬改名，是因为旧目录删不掉的话每天会在共享容器多堆一份 58G 全量副本。补上后无需改代码，下一轮自动改名 |
| M-010 | **续期后的 SAS Token** | 同上，当前 token `se=2026-08-29T00:00:00Z` **将于 2026-08-29 过期** | 同上 | **待提供（8-29 前）** | 2026-08-25 | 过期后所有 azcopy 请求 403。**这正是 8-23 那次备份失败 86 轮却无人察觉的原因**（脚本里烤死了一个 2026-04-05 就过期的 token）。新脚本每轮现读配置，且 `blob_backup.sh status` 会显示剩余天数，但仍需人工续期 |
| M-011 | **AGPL-3.0 的使用决策**（PowerLine-MTYOLO / A-YOLOM 分叉 runtime） | 薄结构专家（R-30）唯一现成的权重是 AGPL-3.0。**强 copyleft + 网络条款** —— 用它产出数据、或接进对外服务的管线，法律影响需你判断 | 决策记入 `DECISIONS.md` | **待你决定** | 2026-08-25 | 不阻塞主干（R-30 本就在 backlog）。但**决定之前不接入**，免得事后要拆 |
| M-007 | VGGT-Ω 权重访问 | Layer 2 的 L2-S1 几何重建 | `model_cache/vggt_omega/` | **✅ 已解决** | 2026-08-25 | 经魔搭社区获取（用户同事提供线索）。`vggt_omega_1b_512.pt` 4.3 GB 已落地，加载验证 1411 张量 / 1.1441B 参数 / missing 0 / unexpected 0，并已在 UAVScenes 真实场景多次跑通推理。**不再是阻塞项** |
| M-008 | **UAVScenes `calibration_results.py`（相机-LiDAR 外参）** | **验证与标定用**（Release D）：测量纯视觉管线错多少、标定置信度到错误事件概率 | `data_raw/UAVScenes/` | **待提供（不阻塞主干）** | 2026-08-25 | **2026-08-25 第二次调整：从「阻塞中」降为「不阻塞」。** 按铁律 14（target 必须能从数据集自身视觉信息推出），LiDAR **不得**出现在生产路径上，只作一次性标尺。它现在卡的是《验证与标定报告》(Release D)，不卡数据生产。<br>历史：08-24 我曾以「尺度可由相机轨迹恢复」为由降级，该理由被实测推翻（锚定后 CV 仍 19.5%），08-25 上午重新升级为必需；同日下午用户确立铁律 14 后重新定位为验证项。只在 OneDrive/GDrive 完整版根目录 |
| M-002 | HuggingFace Token | 下载 gated **模型权重**（SAM 2.1、Grounding DINO、DINOv2、MoGe-3 等） | `HF_TOKEN` | 待提供 | 2026-08-24 | 部分 gated 仓库还需先在网页端接受协议。到 vertical slice 第 4–5 步才需要。**UAVScenes 数据集本身非 gated，不需要此项** |
| M-003 | Qwen / DashScope API Key | Layer 2 的 L2-S7 调用 Qwen 生成任务数据 | `DASHSCOPE_API_KEY` | **暂不需要** | 2026-08-24 | 2026-08-24 决策：Qwen 部署暂缓，首批只编译不调用（SPEC §34 第 1–10 步）。**到第 11 步前重新确认**部署方式与预算 |
| M-004 | 飞书数据集清单最新导出（**文本，非链接**） | **仅** Phase 2 扩充数据集时的去重基准 | `registry/feishu_snapshot/<date>.yaml` | **按需触发** | 2026-08-24 | 详见下方「M-004 说明」。当前不需要，不阻塞任何工作 |

### M-004 说明

**来源**：`DECISIONS.md` §3.2 / §10.1 与 SPEC §5 记载，前一位 Agent 读取过用户提供的飞书文档，从中提取项目已有数据集清单（FloodNet、Open3DVQA、TDBench、LADI-v2、AVI-Math、AirCopBench、SpatialSky、UrbanVideo-Bench、MM-UAVBench、MME-RealWorld、Geo3DVQA），并以此定义「22 个新增候选」= 不在该清单中的数据集。文档要求下一轮调研前重新读取最新内容（**只读，不得修改飞书**）。

**唯一用途**：下一轮数据集调研的去重基准。

**当前不需要的原因**：

1. 首批数据集已定为 UAVScenes 单个并完成 G0，不依赖去重；
2. 去重只在 Phase 2 扩充数据集时才有价值；
3. 本机 `data/` 下已有 FloodNet、LADI、AirCopBench、UrbanVideoBench、nuScenes、AVIMath、RefDrone、AAVG、DVG 实物，快照的主要信息已可直接观察。

**需要时的正确交付方式**：**导出为文本粘贴**，而非提供链接 —— 飞书 wiki 需登录态，无头环境无法访问（同 SharePoint 403 的情形）。

### 优先级说明

- **当前无阻塞主干的人工输入项。** M-008（相机-LiDAR 外参）仍待提供，
  但 2026-08-25 已按铁律 14 降为**非阻塞** —— 它只影响 Release D 的验证报告，
  数据生产走纯视觉路径，可继续推进。
- M-007 已通过魔搭渠道解决（权重下载中），见「已提供」表说明。
  （M-008 曾于 08-24 被我错误降级，08-25 已恢复 —— 见 CHANGELOG 的 `[修正]` 条）
- M-007 详情：没有 VGGT-Ω 权重就无法做几何重建，Layer 2 的 L2-S1 之后全部停在这里。
- 其余：M-002 到 vertical slice 第 4–5 步才触发，M-003 到第 11 步，M-004 到 Phase 2。
- M-005a、M-001、M-006 已解决，见「已提供」表。
- 数据在 blob 上的位置登记在 §3，提供过一次即永久记录。

## 3. 数据路径登记（Blob）

用户提供过一次的数据位置**永久记录在此**，不需要重复提供。新增路径时追加一行，并尽量记录实测到的目录结构与文件格式，避免下次还要重新探。

### 访问方式

Blob **不能**通过 `/blob` 挂载点访问这些路径（该挂载是另一个 datastore）。统一走 `blob_manager`：

```bash
cd /home/aiscuser
python tools/blob_manager.py ls <路径>          # 列目录（one-shot，不进交互）
python tools/blob_manager.py download <路径>    # 下载
bash /home/aiscuser/nyp/blob_manager.sh         # 交互式界面
```

凭证（SAS URL / Token）由 `blob_manager` 自行管理，**不在本文件记录**。若报 token 过期，用 `python tools/blob_manager.py token` 更新。

### 已登记路径

| # | 路径 | 内容 | 生成方式 | 实测结构 | 记录时间 |
|---|---|---|---|---|---|
| D-001 | `Pointcloud-VQA/` | `data/` 中 VQA 类数据集的点云 | 同事用 **VGGT-Ω** 从 2D 转换 | 子目录：`AVImath/` `AirCopBench/` `Floodnet/` `LADI/` `UrbanVideoBench/` `pointcloud_train/` `shareGPT/`，另有 `avi-math_10k_ans.json`(4.6MB)。再下一层为 `train/` 等 split | 2026-08-24 |
| D-002 | `PointCloud-grounding/` | `data/` 中 grounding 类数据集的点云 | 同事用 **VGGT-Ω** 从 2D 转换 | 子目录：`AAVG/` `DVGBench/` `benchmark/` `crop/` `nyp/` `refdrone/` | 2026-08-24 |

**实测文件格式**（以 `Pointcloud-VQA/Floodnet/train/` 为例）：逐图像一个 `.ply`，文件名即图像 ID（如 `10165.ply`），单文件约 2.0 MB，生成时间 2026-06-24。

### 与本 Pipeline 的关系（2026-08-24 已澄清）

这两个路径下的点云对应 `data/` 中的数据集（FloodNet、LADI、AirCopBench、UrbanVideoBench、AVIMath、RefDrone、AAVG、DVG），**不是** UAVScenes。

用户口径（详见 `DECISIONS.md` §19.2）：

- 它们是本 Pipeline "2D → 点云"这一步在那批数据集上的**最终点云结果**；
- 同时**也可以**作为生成下游任务标注的中间产物，**是否纳入取决于后续任务设计**，当前不预先锁定；
- 与首批 UAVScenes 闭环并行，不互相阻塞。

**当前可立即兑现的价值**：它们是现成的 VGGT-Ω 产物，可用于在 Layer 2 开工前核验 VGGT-Ω 的实际输出格式与质量，无需先跑通推理 —— 这是目前 Layer 2 最大的未知项（VGGT-Ω 尚未安装、可获取性未验证）。

## 4. 已提供

| # | 信息 | 变量名或存放位置 | 提供时间 | 备注 |
|---|---|---|---|---|
| M-005a | UAVScenes 数据获取 | `/home/aiscuser/nyp/data_raw/UAVScenes` | 2026-08-24 | **无需凭证**。原判断"需许可申请、是唯一硬阻塞项"不成立：官方 HF 镜像 `sijieaaa/UAVScenes` 非 gated、非 private，已下载 35 GB（interval=5）。用户提供的 SharePoint 链接为浏览器登录态 URL，服务器返回 403，未采用。许可为 CC BY-NC-SA 4.0，见 `registry/datasets/uavscenes/license_review.yaml` |
| M-001 | GitHub Token（classic PAT） | `secrets/.env.local`（权限 600，已 gitignore） | 2026-08-24 | 已用于推送 `3D-data-pipeline/` 至 `NewNiuuu/3D-pointcloud-data-pipeline`。**⚠️ 该 token 曾出现在对话记录中，已建议用户 revoke 并改用仅授权该仓库的 fine-grained PAT** |
| M-006 | Blob 访问凭证 | 由 `tools/blob_manager.py` 自行管理 | 2026-08-24 | **无需用户额外提供**。实测 `python tools/blob_manager.py ls` 可正常列目录。注意源码内有默认 SAS token，其 `se=` 到期日已过但实际访问仍成功，说明另有生效配置；token 失效时用 `blob_manager.py token` 更新。`/blob` 挂载点是另一个 datastore，**不含** D-001/D-002 |

## 5. 条目模板

新增条目时复制以下行：

```
| M-0XX | <需要什么> | <用在哪个 Layer / 哪个阶段，拿不到会阻塞什么> | <变量名或文件路径> | 待提供 | — | <申请方式、权限范围、有效期等> |
```

数据集类条目建议额外记录：

```yaml
dataset_id: <数据集 id>
申请方式: 网页表单 / 邮件 / 直接下载
需要机构邮箱: yes | no
许可类型: <license identifier>
商业训练是否允许: yes | no | unknown
衍生点云是否可再分发: yes | no | unknown
申请提交时间: <date>
获批时间: <date>
```

后三项与 `dataset_card.yaml` 的 `license` 字段必须保持一致。

### 数据路径条目（§3）

用户给出 blob 路径后，Agent 应**先实测一次目录结构再登记**，不要只抄路径：

```
| D-0XX | `<路径>` | <内容是什么> | <谁用什么工具生成> | <实测的子目录与文件格式> | <日期> |
```

登记时必须实际跑一次 `python tools/blob_manager.py ls <路径>` 确认可访问，并记录到叶子层的文件命名与体积。**路径写错或结构猜错的代价是下次重新探一遍**，登记的意义就在于此。

## 6. 与其他文档的边界

- **本文件只管「需要用户手动提供的外部信息」。**
- 需要用户做**技术决策**的未决项（首批数据集、是否强制 metric scale、首批任务、Qwen 部署方式、质量阈值等）**不放这里**，它们在 `DESIGN.md` §36 `Unresolved Decisions` 和 `README.md` 的「实施边界」中维护。
- 一条信息若既涉及决策又涉及凭证（例如 M-003：先决定用 API 还是本地权重，再决定要不要 key），在两处各记一条并互相引用。

---

# 第二部分：待删除清单（Agent 不执行删除）


> 用途：记录项目推进过程中产生的、应当删除但**不由 Agent 执行删除**的内容。
> 由用户定期查看并手动执行。
> 建立日期：2026-08-24

## 规则

**Agent 不执行删除操作。** 发现应删除的内容时，追加一条到下方表格，写清路径、体积、为什么该删、删除命令，然后继续推进项目，不因此停下来请示。

用户确认删除后，把该条移入「已删除」区并标注日期 —— 保留记录而不是抹掉，便于事后核对误删。

**例外**：以下情况仍必须**当场请示**，不得只记在这里 —— 因为它们不是"清理垃圾"，而是有可能丢失真实工作成果：

- 删除对象包含未提交的代码、文档或实验结果；
- 删除对象是用户提供的原始数据；
- 删除范围可能超出预期（通配符、递归删父目录）；
- 无法确定该对象是否还有其他引用。

## 待删除

| # | 路径 | 体积 | 原因 | 记录时间 |
|---|---|---:|---|---|
| X-007 | Blob 远程：`output/liyan/nyp_0825/.git/objects/pack/tmp_pack_sBdTzc` | **6.80 GiB** | **被误备份的 git 废弃临时 pack**。2026-08-24 16:35 一次中断的 git 操作留下的临时文件，首轮全量备份时被一并上传。git 自己迟早会清掉本地那份，blob 上这份则会永久滞留。**当前 token 无 `d` 权限，Agent 删不掉**（同 M-009）。教训已记入 FINDINGS：备份排除项该把 `.git/objects/pack/tmp_pack_*` 纳进去 | 2026-08-25 |
| X-004 | Blob 远程：`output/liyan/_perm_probe/`<br>`output/liyan/_perm_probe2/`<br>`output/liyan/_perm_probe3/`<br>`output/liyan/_srctest/`<br>`output/liyan/_rntest_0825/`<br>`output/liyan/_ovtest/`<br>`output/liyan/_ovtest2/`<br>`output/liyan/.perm_probe` | < 1 KB | **备份改造与覆盖语义验证时的探针残留**。用于验证 SAS token 的写入/服务端复制/删除权限、azcopy 目录改名与通配上传的真实语义，以及 `--overwrite ifSourceNewer` 的实际行为。结论已记入 CHANGELOG 与 FINDINGS，目录本身无用。**当前 token 权限 `racwl` 缺 `d`，Agent 删不掉**，需用带删除权限的 token 清理（同 M-009） | 2026-08-25 |
| X-005 | Blob 远程：`output/liyan/nyp_0823/` | 0 B | **空目录**。8-23 配置的备份从未成功上传过一个字节（token 过期，86 轮全 403），只留下一个空目录名。已由 `nyp_0825` 取代 | 2026-08-25 |
| X-006 | `/home/aiscuser/.blob_backup.sh`<br>`/home/aiscuser/.blob_backup.log`<br>`/home/aiscuser/.blob_backup.log.failed_0823-0825.bak` | ~30 KB | **blob_manager 旧备份机制的残留**。备份已迁到 `nyp/scripts/blob_backup.sh`，`.blob_backup.json` 的路径已清空。`.log.failed_*.bak` 是那 86 轮失败日志的存档，**确认过失败原因后再删**（保留一阵有助于复盘）。注意 `.blob_backup.pid` 仍在用（见脚本里的 COMPAT_PID_FILE），**不要删** | 2026-08-25 |
| X-001 | `/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003` | ~88 MB | **孤儿场景目录**。`build_scenes.py` 的 `--limit` 曾在 `yield` 之后才 `break`，而帧文件在 `yield` 之前就已解出，导致多解一个场景且未写 `scene_manifest.json`。该 bug 已用 `itertools.islice` 修复（见 CHANGELOG `[修正]`），此目录是修复前的残留，无清单、不被任何流程引用 | 2026-08-24 |
| X-002 | `/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0000`<br>`/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0001`<br>`/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0002` | ~257 MB | **标注文件约半数错误**。adapter v0.1.0 用后缀匹配定位标注，而两个标注档案各含 `*_id`（类别 ID）与 `*_color`（RGB 可视化）两份**同名**平行数据，遍历无序 `set` 导致随机命中其一。已在 v0.2.0 改为显式路径并加 5 项测试锁死。这三个场景的 `labels_cam/` 与 `labels_lidar/` 内容不可信，**清单本身正确但标注文件需重新生成** | 2026-08-24 |
| X-003 | `/home/aiscuser/nyp/.venv` | ~60 MB | **废弃的 venv**。最初用 `python -m venv --system-site-packages` 建的项目环境，用户随后要求改用 conda。已被 `nyp-3dpipe` conda 环境完全取代，无任何脚本或文档引用它 | 2026-08-24 |

**X-002 删除后的重建命令**（删除后需重跑，否则 `scenes/` 为空）：

```bash
cd /home/aiscuser/nyp/3D-data-pipeline
PYTHONNOUSERSITE=1 /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python \
    scripts/build_scenes.py --run interval5_AMtown01 --limit 3
```

### 删除命令

```bash
# X-004 / X-005 Blob 远程残留
# 前提：先把 ~/.blob_config.json 里的 token 换成带 d 权限的（sp=racwdl），否则必然 403。
# 可先验证权限：能删掉探针文件说明权限到位。
TOKEN=$(grep -oP '"sas_token"\s*:\s*"\K[^"]+' ~/.blob_config.json)
R="https://yifanyang.blob.core.windows.net/yifanyang/output/liyan"
for d in _perm_probe _perm_probe2 _perm_probe3 _srctest _rntest_0825 _ovtest _ovtest2 nyp_0823; do
    azcopy rm --recursive "${R}/${d}?${TOKEN}"
done
azcopy rm "${R}/.perm_probe?${TOKEN}"

# X-007 被误备份的 git 废弃临时 pack（6.8 GiB）
azcopy rm "${R}/nyp_0825/.git/objects/pack/tmp_pack_sBdTzc?${TOKEN}"

# X-006 旧备份机制残留（.blob_backup.pid 仍在用，不在此列）
rm -f /home/aiscuser/.blob_backup.sh /home/aiscuser/.blob_backup.log
# 失败日志存档：确认过 8-23 那次失败原因后再删
rm -f /home/aiscuser/.blob_backup.log.failed_0823-0825.bak
```

```bash
# X-001 孤儿场景目录
# 建议先确认它确实没有清单（有清单说明是正常场景，不该删）：
ls /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003/scene_manifest.json 2>/dev/null \
  && echo "⚠️ 有清单，不要删！" \
  || rm -rf /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003
```

```bash
# X-003 废弃 venv：先确认 conda 环境可用，再删
PYTHONNOUSERSITE=1 /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python -c "import torch, vggt_omega; print('conda 环境正常')" \
  && rm -rf /home/aiscuser/nyp/.venv
```

```bash
# X-004 孤儿场景（12 个）：先确认确实无清单，再删
cd /home/aiscuser/nyp/scenes
for d in uavscenes_HKisland01_00{01,02,03,04,05,06,07,08,09,10,11,12}; do
  [ -f "$d/scene_manifest.json" ] && echo "⚠️ $d 有清单，跳过" || rm -rf "$d"
done
```

一次性清理全部待删除项（**执行前请先逐条核对上表**）：

```bash
rm -rf /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003 \
       /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0000 \
       /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0001 \
       /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0002 \
       /home/aiscuser/nyp/.venv
# 删完 X-002 后记得按上面的重建命令重跑 3 个场景
```

## 已删除

| # | 路径 | 删除时间 | 备注 |
|---|---|---|---|
| X-001 | `scenes/uavscenes_AMtown01_0003` | 2026-08-25 | 用户手动执行，带前置检查 |
| X-002 | `scenes/uavscenes_AMtown01_0000/0001/0002` | 2026-08-25 | 坏标注残留。**删除前曾实际造成故障** —— C1 实验想用它做对照组时，`_id`/`_color` 混淆导致通道数不一致直接报错，只得另建 AMtown02_0000 |
| X-003 | `/home/aiscuser/nyp/.venv` | 2026-08-25 | 废弃 venv，已被 conda `nyp-3dpipe` 取代 |

## 条目模板

```
| X-0XX | `<绝对路径>` | <体积> | <为什么该删；如果是 bug 残留，指明是哪个 bug、是否已修> | <日期> |
```

配套在「删除命令」区给出可直接粘贴的命令，**并尽量带一个防误删的前置检查**（如上例先验证清单不存在）。
