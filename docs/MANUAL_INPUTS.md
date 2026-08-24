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
| M-004 | 飞书数据集清单最新只读导出 | Layer 1 重新核对去重，更新 `feishu_snapshot` | `registry/feishu_snapshot/<date>.yaml` | 待提供 | 2026-08-24 | **只读**。文档 `Oc5Owx8hoifPGikC5ZgcxRzGnDd` 需登录，Agent 无法直接访问；不得修改飞书原文档。**当前唯一待办的用户提供项** |
| M-002 | HuggingFace Token | 下载 gated **模型权重**（SAM 2.1、Grounding DINO、DINOv2、MoGe-3 等） | `HF_TOKEN` | 待提供 | 2026-08-24 | 部分 gated 仓库还需先在网页端接受协议。到 vertical slice 第 4–5 步才需要。**UAVScenes 数据集本身非 gated，不需要此项** |
| M-006 | Azure Blob SAS / 存储凭证 | `blob_manager.py` 读写 blob 存储 | 由 `blob_manager` 自身管理 | 待提供 | 2026-08-24 | `/blob` 挂载点当前显示 0 字节，可写性待确认。若现有配置已可用则改为「不需要」 |
| M-003 | Qwen / DashScope API Key | Layer 2 的 L2-S7 调用 Qwen 生成任务数据 | `DASHSCOPE_API_KEY` | **暂不需要** | 2026-08-24 | 2026-08-24 决策：Qwen 部署暂缓，首批只编译不调用（SPEC §34 第 1–10 步）。**到第 11 步前重新确认**部署方式与预算 |

### 优先级说明

- **M-004 是当前唯一待办的用户提供项，且不阻塞首批闭环** —— Layer 1 已有 UAVScenes 可开工。
- M-005a 与 M-001 已解决，见「已提供」表。

## 3. 已提供

| # | 信息 | 变量名或存放位置 | 提供时间 | 备注 |
|---|---|---|---|---|
| M-005a | UAVScenes 数据获取 | `/home/aiscuser/nyp/data_raw/UAVScenes` | 2026-08-24 | **无需凭证**。原判断"需许可申请、是唯一硬阻塞项"不成立：官方 HF 镜像 `sijieaaa/UAVScenes` 非 gated、非 private，已下载 35 GB（interval=5）。用户提供的 SharePoint 链接为浏览器登录态 URL，服务器返回 403，未采用。许可为 CC BY-NC-SA 4.0，见 `registry/datasets/uavscenes/license_review.yaml` |
| M-001 | GitHub Token（classic PAT） | `secrets/.env.local`（权限 600，已 gitignore） | 2026-08-24 | 已用于推送 `3D-data-pipeline/` 至 `NewNiuuu/3D-pointcloud-data-pipeline`。**⚠️ 该 token 曾出现在对话记录中，已建议用户 revoke 并改用仅授权该仓库的 fine-grained PAT** |

## 4. 条目模板

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

## 5. 与其他文档的边界

- **本文件只管「需要用户手动提供的外部信息」。**
- 需要用户做**技术决策**的未决项（首批数据集、是否强制 metric scale、首批任务、Qwen 部署方式、质量阈值等）**不放这里**，它们在 `CLAUDE_CODE_PROJECT_SPEC.md` §36 `Unresolved Decisions` 和 `README.md` 的「实施边界」中维护。
- 一条信息若既涉及决策又涉及凭证（例如 M-003：先决定用 API 还是本地权重，再决定要不要 key），在两处各记一条并互相引用。
