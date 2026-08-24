# 专家模型部署状态

> 契约：`CLAUDE_CODE_PROJECT_SPEC.md` §14（专家模型系统）、§23.2（`expert-registry-manager`）
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
| **OneFormer ADE20K** | 天空/水面/stuff 语义 | MIT | ⚠️ 可运行但权重加载异常 | 4.54 GB |
| **Florence-2 Large** | 属性/描述候选 | MIT | ❌ transformers 版本不兼容 | — |
| **MoGe-3 ViT-L** | **首选**独立几何交叉校验 | MIT | ❌ 依赖冲突，需独立环境 | — |
| VGGT-Ω | **点云主路径** | FAIR NC | 代码就绪，**权重待批**（M-007） | 6.53 GB |

许可全部核验完毕，**无一构成阻塞** —— 均与本项目的非商用学术定位相容。

## 已部署且验证通过

全部在 UAVScenes AMtown01 的**真实图像**（2448×2048）上跑通，非合成输入。

**DA3-LARGE-1.1** —— 用户特别指定。SPEC §14.1 称其为 "DA3-1.1 Apache-compatible variant"，**核验属实**：代码与该权重均为 Apache-2.0（注意 `DA3NESTED-GIANT-LARGE` 是 cc-by-nc-4.0，不同变体许可不同）。

3 张图 @504 分辨率，前向 0.74 秒，峰值 3.62 GB。输出：

```
depth (N,H,W) float32     conf (N,H,W) float32
extrinsics (N,3,4)        intrinsics (N,3,3)
is_metric {}              scale_factor None       sky None
```

**关键判定：DA3-LARGE-1.1 输出的是 `relative` 深度**，不是 metric —— `is_metric` 为空、`scale_factor` 为 None、depth 落在 0.57~1.02。按铁律 8，**不得用它直接产出绝对米制目标**。若需 metric 第二意见，应改用 `DA3METRIC-LARGE`（同为 Apache-2.0，尚未部署）。

**Grounding DINO** 在航拍图上检出 building / road 等。SPEC §14.1 的强制要求已记入专家卡：detector 的 box/class 置信度与 SAM 的 mask 置信度**必须分别保存**，且**不得把框内像素整体提升到 3D**。

## 有问题的三个

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

### MoGe-3 —— 硬依赖冲突，必须独立环境

这是几何专家接入顺序里的**首选**（SPEC §34 `primary_geometry_cross_check`），但存在不可调和的冲突：

| 包 | numpy 要求 |
|---|---|
| MoGe | `numpy>=2` |
| VGGT-Ω | `numpy<2` |
| DA3 | `numpy<2` |

外加需要 `flex-gemm`（指定 commit 的 CUDA 扩展）与 `utils3d_moge` 专用 fork（不是 PyPI 上的 `utils3d`）。

**解决方案：为 MoGe 建独立 conda 环境，通过文件交换输出。** 这与它的角色天然相容 —— MoGe 是关键帧上的**离线**几何交叉校验，本就不需要与 VGGT-Ω 同进程。SPEC §14.12 要求的 SE(3)/Sim(3) 对齐与残差计算在主环境完成，输入是 MoGe 导出的深度/法向文件。

许可方面无障碍：MIT，SPEC §14.2 要求的 "after weight-license confirmation" 已完成。

## 尚未部署

| 模型 | 角色 | 原因 |
|---|---|---|
| SEA-RAFT | 光流与动态证据 | 权重不在 HF，需从官方渠道单独获取 |
| CABiNet | UAV 障碍语义 | 同上 |
| DSINE | 独立法向 | SPEC §14.2 标注为 license-gated，需先审查 |
| CoTracker3 | 点轨迹与可见性 | 非商用许可 —— 与本项目定位相容，可部署 |
| PowerLine-MTYOLO | 电线专项 | 领域专项，非首批必需 |
| DA3METRIC-LARGE | metric 深度第二意见 | Apache-2.0，建议补充部署 |

## 环境事实（供复现）

```
conda env: nyp-3dpipe
HF_HOME:   /home/aiscuser/nyp/model_cache
调用:      PYTHONNOUSERSITE=1 /home/aiscuser/miniconda3/envs/nyp-3dpipe/bin/python
```

已下载权重约 **11.2 GB**（DA3 1.64 + MoGe 1.48 + SAM2.1 0.65 + GDINO 1.87 + DINOv2 0.69 + Florence-2 3.12 + OneFormer 1.83）。

**安装过程中的两个反复踩到的坑**：

1. **numpy 会被反复拉到 2.x。** `imageio`、`plyfile`、`utils3d` 等都可能触发。每装一批依赖后必须重新 `pip install "numpy<2"` 并校验，否则 VGGT-Ω 与 DA3 会静默失效。
2. **DA3 的重依赖大多可跳过。** `xformers` 在 `swiglu_ffn.py` 里是 `try/except ImportError` 的可选加速路径，`open3d` 只在 `bench/`，`fastapi`/`uvicorn` 只在 web 服务。用 `--no-deps` 装本体再手工补必需项，可避开 xformers 换掉 torch 的风险。

## GPU 使用记录

全部推理在占卡程序**持续运行**的情况下完成（剩余约 13 GB/卡），未中断服务器保活，未执行 `gpu_guard.sh release`。最大单模型峰值 6.53 GB（VGGT-Ω 2 帧 @512）。
