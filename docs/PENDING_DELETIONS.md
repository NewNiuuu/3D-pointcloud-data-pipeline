# 待删除清单

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
| — | — | — | 暂无 |

## 条目模板

```
| X-0XX | `<绝对路径>` | <体积> | <为什么该删；如果是 bug 残留，指明是哪个 bug、是否已修> | <日期> |
```

配套在「删除命令」区给出可直接粘贴的命令，**并尽量带一个防误删的前置检查**（如上例先验证清单不存在）。
