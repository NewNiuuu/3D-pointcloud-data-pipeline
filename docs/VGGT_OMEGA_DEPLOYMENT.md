# VGGT-Ω 部署记录

> 对象：`VGGT-Ω`，本项目**固定的点云主路径**（SPEC 铁律 1，不得替换）
> 实测日期：2026-08-24
> 状态：**代码已部署可运行；权重受限未获取**

## 1. 可获取性核验

| 项 | 结果 |
|---|---|
| GitHub | <https://github.com/facebookresearch/vggt-omega> HTTP 200，CVPR 2026 Oral |
| commit | `282ec70363edeff59424bf43731658092fba3d37`（2026-08-24 浅克隆） |
| 论文 | <https://arxiv.org/abs/2605.15195> |
| 权重 | <https://huggingface.co/facebook/VGGT-Omega> —— **`gated: manual`，需申请** |
| 权重文件 | `vggt_omega_1b_512.pt`、`vggt_omega_1b_256_text.pt` |

SPEC §38 记录的三个 URL **全部有效**，与 2026-08-23 的调研快照一致。

## 2. 许可（G0 / expert-registry-manager 要求分别记录）

| 层 | 许可 | 关键约束 |
|---|---|---|
| 代码 | **FAIR Noncommercial Research License v1** | 仅限 Noncommercial Research Uses |
| 权重 | **未知** —— `LICENSE.txt` 需登录 HF 且获批后才可见 | 未审查，按 §23.2 属硬失败，获批前不得标记 production-ready |

代码许可的关键条款：

> "You will not use the Research Materials **or any outputs or results** of the Research Materials
> in connection with any commercial uses or for any uses other than Noncommercial Research Uses"

两点判断：

1. **输出受非商用限制**，但**没有**"禁止用输出改进其他 AI 模型"的条款。这与 WorldMirror 不同（后者正因该条款被 SPEC §14.14 限制为仅推理/评估）。因此 **VGGT-Ω 的输出可以进入训练 metadata**，前提是整体保持非商用研究用途。
2. 与已确认的 UAVScenes / MARS-LVIG（CC BY-NC-SA 4.0）立场一致，无新增冲突。

### 待法务复核的开放问题

CC BY-NC-SA 4.0 的 ShareAlike 要求衍生作品沿用该许可；FAIR NC 要求衍生作品"subject to the terms of this Agreement"。**两个 ShareAlike 式条款是否可同时满足，不确定。** 这不影响研究使用（两者都允许），但可能影响**公开发布**衍生数据集的许可声明方式。列为 G6 发布门禁的开放项，非当前阻塞。

## 3. 部署

### 环境（项目专属，禁止用共享 base）

```bash
conda env: nyp-3dpipe
python:    /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python
```

依赖：`torch==2.8.0+cu126`、`torchvision==0.23.0+cu126`、`numpy<2`、`einops`、`safetensors`、`opencv-python-headless<5`。

`PYTHONNOUSERSITE=1` **必须显式设置**（直接调 python 二进制时 `conda env config vars` 不生效）：
`~/.local/lib/python3.10/site-packages` 下有 35 个包会渗进任何 python3.10。

### 两点实测结论

1. **核心包不需要 `cv2`。** `requirements.txt` 列了 `opencv-python`，但 `cv2` 只出现在 `visual_util.py`（gradio demo 的可视化辅助）。核心 `vggt_omega/` 只依赖 torch / torchvision / numpy / PIL 与标准库。
2. **`numpy<2` 是硬约束。** opencv-python-headless 5.x 会强制拉起 numpy≥2，必须钉在 4.x。

### 安装

```bash
git clone --depth 1 https://github.com/facebookresearch/vggt-omega.git third_party/vggt-omega
PYTHONNOUSERSITE=1 $PY -m pip install -e third_party/vggt-omega
```

## 4. 输出契约（实测，非文档转述）

以随机权重跑通前向（数值无意义，key / 形状 / dtype 为真）：

```
输入 images: (B, S, 3, H, W)     S = 帧数

camera_and_register_tokens   (B, S, 17, 2048)      float32
pose_enc                     (B, S, 9)             float32
depth                        (B, S, H, W, 1)       float32
depth_conf                   (B, S, H, W)          float32
images                       (B, S, 3, H, W)       float32   预处理后的输入回传

encoding_to_camera(pose_enc, image_size_hw) ->
extrinsics                   (B, S, 3, 4)          float32
intrinsics                   (B, S, 3, 3)          float32
```

模型规模 **1.144 B 参数**（fp32 权重约 4.58 GB），子模块 `aggregator` / `camera_head` / `dense_head`。

`load_and_preprocess_images(image_path_list, mode='balanced', image_resolution=512, patch_size=16)`。

### 显存实测

| 配置 | 峰值已分配 | 官方参考 |
|---|---:|---|
| 2 帧 @512，fp32 | **6.53 GB** | 1 帧 6.02 GB / 10 帧 6.67 GB |

实测与官方量级一致。在占卡程序仍占用 27 GB/卡的情况下（剩余 12.62 GB）跑通，未中断服务器保活。

### 与 SPEC 的对照

SPEC §13 声称 VGGT-Ω 可输出 camera pose encoding、extrinsics/intrinsics、depth、depth confidence、camera/register tokens —— **实测全部属实**。

对本 Pipeline 的意义：`depth_conf` 是 G1/G2 门禁的输入，`extrinsics`/`intrinsics` 是投影、可见性、跨视角关联的前提。这些正是 blob 上现有 `.ply` 缺失的字段（见 `BASELINE_POINTCLOUD_ANALYSIS.md`），也是本 Pipeline 必须保存完整输出而非只导出可视化点云的原因。

## 5. 当前阻塞

**权重需在 HF 申请访问**（`gated: manual`，自动流程审核，作者不参与）。已登记为 `MANUAL_INPUTS.md` M-007。

在获批之前可以做的：
- 已完成：环境部署、代码可运行性、输出契约、显存量级；
- 可继续：基于已确定的输出契约设计 L0 metadata schema 与 geometry manifest，无需真实权重。

不可做的：任何依赖真实重建结果的验证（尺度、动态拖影、薄结构、弱纹理、大场景漂移），这些仍是 SPEC §37 记录的经验性未知项。
