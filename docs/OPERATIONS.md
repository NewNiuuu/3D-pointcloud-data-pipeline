# 运维与部署手册

> **面向 Agent 的操作参考。** 环境、模型部署、复现命令都在这里。
> 项目设计看 `DESIGN.md`；需要用户处理的事项看 `USER_ACTIONS.md`。
> 建立于 2026-08-25（由 OPERATIONS.md 与 OPERATIONS.md 合并）。

---

# 第一部分：VGGT-Ω 部署（点云主路径）


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

对本 Pipeline 的意义：`depth_conf` 是 G1/G2 门禁的输入，`extrinsics`/`intrinsics` 是投影、可见性、跨视角关联的前提。这些正是 blob 上现有 `.ply` 缺失的字段（见 `FINDINGS.md 附录 C`），也是本 Pipeline 必须保存完整输出而非只导出可视化点云的原因。

## 5. 当前阻塞

**权重需在 HF 申请访问**（`gated: manual`，自动流程审核，作者不参与）。已登记为 `USER_ACTIONS.md` M-007。

在获批之前可以做的：
- 已完成：环境部署、代码可运行性、输出契约、显存量级；
- 可继续：基于已确定的输出契约设计 L0 metadata schema 与 geometry manifest，无需真实权重。

不可做的：任何依赖真实重建结果的验证（尺度、动态拖影、薄结构、弱纹理、大场景漂移），这些仍是 SPEC §37 记录的经验性未知项。

---

# 第二部分：专家模型部署


> 契约：`DESIGN.md` §14（专家模型系统）、§23.2（`expert-registry-manager`）
> 逐模型详情见 `registry/experts/*.yaml`
> 实测日期：2026-08-24
> 环境：conda `nyp-3dpipe`（**禁止用共享 base**，见 `CLAUDE.md` 规则 3）

## 总览

| 模型 | 角色 | 许可 | 状态 | 实测峰值显存 |
|---|---|---|---|---:|
| **DA3-LARGE-1.1** | 深度/位姿/尺度第二意见 | Apache-2.0 | ✅ 已部署，真实推理通过 | 3.62 GB |
| **SAM 2.1 Base+** | mask 与视频跟踪 | Apache-2.0 | ✅ 已部署，单帧 mask 通过 | — |
| **Grounding DINO Base** | 开放词汇检测提议 | Apache-2.0 | ✅ 已部署，真实推理通过 | 2.01 GB |
| **DINOv2 Base** | 跨视角外观特征 | Apache-2.0 | ✅ 已部署，真实推理通过 | 0.37 GB |
| **OneFormer ADE20K** | 天空/水面/stuff 语义；**管线唯一的类别来源** | MIT | ✅ 已验证（加载告警证明无害） | 4.54 GB |
| **Florence-2 Large** | 属性/描述候选 | MIT | ❌ transformers 版本不兼容 | — |
| **MoGe-3 ViT-L** | **首选**独立几何交叉校验 | MIT | ✅ 已部署（独立环境 `nyp-moge`） | 2.87 GB |
| **DA3Metric-Large** | 单目 metric 深度 + sky 掩码 | Apache-2.0 | ✅ 已部署；**无 conf/相机参数** | 2.91 GB |
| **CoTracker3** | 点轨迹与可见性 | 非商用（待审全文） | ✅ 已部署 | 0.86 GB |
| **Grounded-SAM-2**（组合） | 开放词表实例分割 | Apache-2.0 | ✅ 串联跑通；**类别不可用，只出边界** | 2.37 GB |
| VGGT-Ω | **点云主路径** | FAIR NC | ✅ 权重已就位（M-007 已解决），真实场景多次跑通 | 6.53 GB |

许可全部核验完毕，**无一构成阻塞** —— 均与本项目的非商用学术定位相容。

> 这张表记的是**部署事实与复现细节**。要看「跑通到哪一步、接线了没有」的追踪视图，
> 去 `README.md` 的「🤖 已跑通的模型」表 —— 那份是给用户看的，两份必须同步改。

## 已部署且验证通过

全部在 UAVScenes AMtown01 的**真实图像**（2448×2048）上跑通，非合成输入。

**DA3-LARGE-1.1** —— 用户特别指定。SPEC §14.1 称其为 "DA3-1.1 Apache-compatible variant"，**核验属实**：代码与该权重均为 Apache-2.0（注意 `DA3NESTED-GIANT-LARGE` 是 cc-by-nc-4.0，不同变体许可不同）。

3 张图 @504 分辨率，前向 0.74 秒，峰值 3.62 GB。输出：

```
depth (N,H,W) float32     conf (N,H,W) float32
extrinsics (N,3,4)        intrinsics (N,3,3)
is_metric {}              scale_factor None       sky None
```

**关键判定：DA3-LARGE-1.1 输出的是 `relative` 深度**，不是 metric —— `is_metric` 为空、`scale_factor` 为 None、depth 落在 0.57~1.02。按铁律 8，**不得用它直接产出绝对米制目标**。若需 metric 第二意见，应改用 `DA3METRIC-LARGE`（同为 Apache-2.0，**已部署**，见下）。

**Grounding DINO** 在航拍图上检出 building / road 等。SPEC §14.1 的强制要求已记入专家卡：detector 的 box/class 置信度与 SAM 的 mask 置信度**必须分别保存**，且**不得把框内像素整体提升到 3D**。

## Grounded-SAM-2 串联（2026-08-25 补测）

Grounding DINO 与 SAM 2.1 串起来用，封装在 `pipeline/grounded_sam.py`。
**走 transformers 原生实现，不 clone 官方 repo** —— 后者要编译 CUDA 自定义算子 `_C`，
会把 numpy/torch 依赖再搅一遍（规则 3）。架构与权重一致，差别只在 runtime。

```bash
cd /home/aiscuser/nyp/3D-data-pipeline
/home/aiscuser/nyp/scripts/gpu_guard.sh release     # 规则 2：用卡前先腾卡

PY=/home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python
export HF_HOME=/home/aiscuser/nyp/model_cache HF_HUB_OFFLINE=1

# 1) 端到端冒烟（框→mask，4 项检查）
PYTHONNOUSERSITE=1 $PY scripts/smoke_grounded_sam.py --scenes 3 --frames 2

# 2) 负控标定（判别力）—— --isolated 逐条短语单送，排除长提示词串扰
PYTHONNOUSERSITE=1 $PY scripts/calibrate_grounded_sam.py --scenes 4 --frames 3
PYTHONNOUSERSITE=1 $PY scripts/calibrate_grounded_sam.py --scenes 4 --frames 3 --isolated

# 3) 与 OneFormer 融合（边界 + 类别）
PYTHONNOUSERSITE=1 $PY scripts/verify_instance_fusion.py --scenes 4 --frames 2

/home/aiscuser/nyp/scripts/gpu_guard.sh start       # 用完立刻挂回占卡
```

产物落在 `/home/aiscuser/nyp/metadata/_smoke_grounded_sam.json`、
`_calib_grounded_sam[_isolated].json`、`_fusion_check.json`。

实测：加载 7.1 s，峰值显存 **2.37 GB**（两个模型合计），每帧 0.5–1.2 s，
47 实例 / 6 帧，4 项检查全过。

**三个踩过的坑**：

1. **不要用 `post_process_grounded_object_detection` 取标签。**
   它走 `get_phrases_from_posmap`，把 query 上所有过阈值的 token 直接拼接，
   不管短语边界；12 条提示词同送时产出 `"a car a"` / `"a truck bus"` / `"a"`。
   改用短语 token span 归属（`phrase_token_spans`）。
   **务必保留一条「标签必须在提示词表内」的断言** —— 这类错不报错也不崩。
2. **「mask 必须完全在框内」是个错的检查。** SAM 的框提示是提示不是硬约束，
   框只框住部件时它会补全到整个物体（实测最多 1.178 倍框面积）。
   真正的坐标系错误会给出 ≈0 的重叠，而实测中位重叠 0.989。
   把溢出量记成 `mask_outside_box_ratio` 当分歧信号用，不要当失败。
3. **`Sam2Processor` 的框要三层嵌套**：`input_boxes=[[[x1,y1,x2,y2], ...]]`
   （batch → prompt → box）。少一层不报错，但结果全错。

## 有问题的两个

### OneFormer —— 可运行，但权重加载不完整

`transformers 5.15.1` 加载时报：

```
model.pixel_level_module.encoder.swin.layernorm.weight   MISSING
model.pixel_level_module.encoder.swin.layernorm.bias     MISSING
```

这两个参数**被随机初始化**了。模型能跑出 13 个类别的语义图，但输出可信度存疑 —— 一个随机初始化的 layernorm 会静默改变特征分布。

**在确定兼容的 transformers 版本或改用官方实现之前，不得启用。** 它的产出是 §14.5 要求的 sky/water 无效几何原因掩码，错误会直接污染 G2 门禁。

### Florence-2 —— 版本不兼容，未能运行

`Florence2LanguageConfig` 缺 `forced_bos_token_id`，其 `trust_remote_code` 实现是按旧版 transformers 写的。

不建议为它单独降级主环境的 transformers —— 那会影响已验证通过的其他四个模型。合理做法是等官方适配，或为它单独建环境。它的角色（属性/描述候选）不在首批三个任务的关键路径上。

## MoGe-3 —— 曾因依赖冲突受阻，已用独立环境解决

冲突是真实的且不可调和：

| 包 | numpy 要求 |
|---|---|
| MoGe | `numpy>=2` |
| VGGT-Ω | `numpy<2` |
| DA3 | `numpy<2` |

外加需要 `flex-gemm`（指定 commit 的 CUDA 扩展）与 `utils3d_moge` 专用 fork。

**解决方案（用户已批准）：独立 conda 环境 `nyp-moge`，通过文件交换输出。** 这与它的角色天然相容 —— MoGe 是关键帧上的**离线**几何交叉校验，本就不需要与 VGGT-Ω 同进程。SPEC §14.12 要求的 SE(3)/Sim(3) 对齐与残差计算在主环境完成，输入是 MoGe 导出的深度/法向文件。

实测通过（峰值 2.87 GB）。输出：

```
points (H,W,3)   depth (H,W)   normal (H,W,3)   mask (H,W) bool   intrinsics (3,3) 归一化
```

`normal` 是**独立法向**，不是深度微分所得 —— 满足 SPEC §14.14「至少一路法向应来自独立法向估计器」的要求。

## 尺度：三个模型互不一致，且都对不上 LiDAR

同一帧 UAVScenes 图像：

| 来源 | 深度范围 |
|---|---|
| DA3-LARGE-1.1 | 0.572 – 1.015（归一化） |
| DA3Metric-Large | 6.970 – 23.782 m，中位 13.297 |
| MoGe-3 ViT-L | 16.744 – 22.959 m |
| **LiDAR 真值** | 31.09 – 38.02 m，中位 33.13（射线距离） |

这是 SPEC §14.13「多专家不得投票产生真值」的现实例证 —— 取平均或多数决只会得到一个同样错的数。

**但必须说明这个对比本身不严谨**：LiDAR 给的是射线距离，模型给的是垂直深度；两者传感器原点与视场均不同。严格验证需要相机-LiDAR 外参做投影，而 `calibration_results.py` **不在 interval=5 档案中**（只在完整版）。

因此：所有模型的 `domain_calibrated` 一律保持 `false`，在完成投影验证前**不得产出绝对米制目标**（SPEC §14.11）。

## 尚未部署

| 模型 | 角色 | 原因 |
|---|---|---|
| SEA-RAFT | 光流与动态证据 | 权重不在 HF，需从官方渠道单独获取 |
| CABiNet | UAV 障碍语义 | 同上 |
| DSINE | 独立法向 | SPEC §14.2 标注 license-gated，需先审查。**优先级已下降** —— MoGe-3 已提供独立法向 |
| PowerLine-MTYOLO | 电线专项 | 领域专项，非首批必需 |

## 环境事实（供复现）

```
conda env: nyp-3dpipe
HF_HOME:   /home/aiscuser/nyp/model_cache
调用:      PYTHONNOUSERSITE=1 /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python
```

已下载权重约 **13 GB**（DA3-Large-1.1 1.64 + DA3Metric-Large + MoGe 1.48 + SAM2.1 0.65 + GDINO 1.87 + DINOv2 0.69 + Florence-2 3.12 + OneFormer 1.83 + CoTracker3 0.10）。

两个 conda 环境：`nyp-3dpipe`（主，numpy<2）与 `nyp-moge`（MoGe 专用，numpy>=2）。

**安装过程中的两个反复踩到的坑**：

1. **numpy 会被反复拉到 2.x。** `imageio`、`plyfile`、`utils3d` 等都可能触发。每装一批依赖后必须重新 `pip install "numpy<2"` 并校验，否则 VGGT-Ω 与 DA3 会静默失效。
2. **DA3 的重依赖大多可跳过。** `xformers` 在 `swiglu_ffn.py` 里是 `try/except ImportError` 的可选加速路径，`open3d` 只在 `bench/`，`fastapi`/`uvicorn` 只在 web 服务。用 `--no-deps` 装本体再手工补必需项，可避开 xformers 换掉 torch 的风险。

## GPU 使用记录

全部推理在占卡程序**持续运行**的情况下完成（剩余约 13 GB/卡），未中断服务器保活，未执行 `gpu_guard.sh release`。最大单模型峰值 6.53 GB（VGGT-Ω 2 帧 @512）。
