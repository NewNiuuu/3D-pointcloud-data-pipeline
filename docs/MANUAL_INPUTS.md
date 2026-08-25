# 人工输入登记簿

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
| M-007 | **VGGT-Ω 权重访问申请** | Layer 2 的 L2-S1 几何重建 —— 点云主路径，**当前唯一阻塞项** | HF 账号申请 + `HF_TOKEN` | **待提供（阻塞中）** | 2026-08-24 | <https://huggingface.co/facebook/VGGT-Omega> 为 `gated: manual`，需用你的 HF 账号提交访问申请（自动流程审核，作者不参与）。获批后权重 `LICENSE.txt` 才可见，需补做权重许可审查。代码已部署可运行，输出契约已实测，见 `VGGT_OMEGA_DEPLOYMENT.md` |
| M-008 | **UAVScenes `calibration_results.py`（相机-LiDAR 外参）** | 用独立真值逐像素验证深度 —— 自洽检验已被证明不足以判定精度 | `data_raw/UAVScenes/` | **待提供（阻塞中）** | 2026-08-25 | **重新升级为必需**。我曾于 2026-08-24 将其降级，理由是「尺度可由相机轨迹恢复」，该理由已被系统扫描推翻（锚定后米制深度 CV 仍达 19.5%）。没有独立真值就无法给出任何精度数字，`domain_calibrated` 无法置位，绝对米制任务无法解锁。只在 OneDrive/GDrive 完整版根目录 |
| M-002 | HuggingFace Token | 下载 gated **模型权重**（SAM 2.1、Grounding DINO、DINOv2、MoGe-3 等） | `HF_TOKEN` | 待提供 | 2026-08-24 | 部分 gated 仓库还需先在网页端接受协议。到 vertical slice 第 4–5 步才需要。**UAVScenes 数据集本身非 gated，不需要此项** |
| M-003 | Qwen / DashScope API Key | Layer 2 的 L2-S7 调用 Qwen 生成任务数据 | `DASHSCOPE_API_KEY` | **暂不需要** | 2026-08-24 | 2026-08-24 决策：Qwen 部署暂缓，首批只编译不调用（SPEC §34 第 1–10 步）。**到第 11 步前重新确认**部署方式与预算 |
| M-004 | 飞书数据集清单最新导出（**文本，非链接**） | **仅** Phase 2 扩充数据集时的去重基准 | `registry/feishu_snapshot/<date>.yaml` | **按需触发** | 2026-08-24 | 详见下方「M-004 说明」。当前不需要，不阻塞任何工作 |

### M-004 说明

**来源**：`PROJECT_HANDOFF.md` §3.2 / §10.1 与 SPEC §5 记载，前一位 Agent 读取过用户提供的飞书文档，从中提取项目已有数据集清单（FloodNet、Open3DVQA、TDBench、LADI-v2、AVI-Math、AirCopBench、SpatialSky、UrbanVideo-Bench、MM-UAVBench、MME-RealWorld、Geo3DVQA），并以此定义「22 个新增候选」= 不在该清单中的数据集。文档要求下一轮调研前重新读取最新内容（**只读，不得修改飞书**）。

**唯一用途**：下一轮数据集调研的去重基准。

**当前不需要的原因**：

1. 首批数据集已定为 UAVScenes 单个并完成 G0，不依赖去重；
2. 去重只在 Phase 2 扩充数据集时才有价值；
3. 本机 `data/` 下已有 FloodNet、LADI、AirCopBench、UrbanVideoBench、nuScenes、AVIMath、RefDrone、AAVG、DVG 实物，快照的主要信息已可直接观察。

**需要时的正确交付方式**：**导出为文本粘贴**，而非提供链接 —— 飞书 wiki 需登录态，无头环境无法访问（同 SharePoint 403 的情形）。

### 优先级说明

- **M-007 与 M-008 均为阻塞项**：前者卡住几何重建，后者卡住米制精度验证。
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

用户口径（详见 `PROJECT_HANDOFF.md` §19.2）：

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
- 需要用户做**技术决策**的未决项（首批数据集、是否强制 metric scale、首批任务、Qwen 部署方式、质量阈值等）**不放这里**，它们在 `CLAUDE_CODE_PROJECT_SPEC.md` §36 `Unresolved Decisions` 和 `README.md` 的「实施边界」中维护。
- 一条信息若既涉及决策又涉及凭证（例如 M-003：先决定用 API 还是本地权重，再决定要不要 key），在两处各记一条并互相引用。
