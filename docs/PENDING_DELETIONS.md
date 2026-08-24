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
| X-001 | `/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003` | ~88 MB | **孤儿场景目录**。`build_scenes.py` 的 `--limit` 曾在 `yield` 之后才 `break`，而帧文件在 `yield` 之前就已解出，导致多解一个场景且未写 `scene_manifest.json`。该 bug 已用 `itertools.islice` 修复（见 CHANGELOG `[修正]`），此目录是修复前的残留，无清单、不被任何流程引用 | 2026-08-24 |
| X-002 | `/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0000`<br>`/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0001`<br>`/home/aiscuser/nyp/scenes/uavscenes_AMtown01_0002` | ~257 MB | **标注文件约半数错误**。adapter v0.1.0 用后缀匹配定位标注，而两个标注档案各含 `*_id`（类别 ID）与 `*_color`（RGB 可视化）两份**同名**平行数据，遍历无序 `set` 导致随机命中其一。已在 v0.2.0 改为显式路径并加 5 项测试锁死。这三个场景的 `labels_cam/` 与 `labels_lidar/` 内容不可信，**清单本身正确但标注文件需重新生成** | 2026-08-24 |

**X-002 删除后的重建命令**（删除后需重跑，否则 `scenes/` 为空）：

```bash
cd /home/aiscuser/nyp/3D-data-pipeline
/opt/conda/envs/ptca/bin/python scripts/build_scenes.py --run interval5_AMtown01 --limit 3
```

### 删除命令

```bash
# X-001 孤儿场景目录
# 建议先确认它确实没有清单（有清单说明是正常场景，不该删）：
ls /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003/scene_manifest.json 2>/dev/null \
  && echo "⚠️ 有清单，不要删！" \
  || rm -rf /home/aiscuser/nyp/scenes/uavscenes_AMtown01_0003
```

一次性清理全部待删除项（**执行前请先逐条核对上表**）：

```bash
# 目前只有 X-001，随清单增长再补充
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
