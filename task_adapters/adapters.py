"""三类 adapter：把 Canonical Task Record 投影为各模型的输入格式。

契约来源：SPEC §39/§41。泄漏防护见 :mod:`task_adapters.base`。
"""

from __future__ import annotations

from typing import Any

from .base import AdapterError, RenderedSample, TaskAdapter

__all__ = [
    "PointcloudNativeAdapter",
    "Qwen2DMetadataAdapter",
    "Multimodal3DAdapter",
    "ADAPTER_REGISTRY",
    "get_adapter",
]

POINT_CLOUD_PLACEHOLDER = "<point_cloud>"


class PointcloudNativeAdapter(TaskAdapter):
    """原生点云模型 adapter —— 产出 **ShareGPT 格式**。

    ## 契约是 ShareGPT，不是某个具体训练框架

    用户 2026-08-25 明确：标注格式**尽量满足 ShareGPT 格式**；
    3D-GRPO 与 SFT 都会**依据数据的具体类型再做调整**。

    因此本 adapter 的目标是产出规范的 ShareGPT 记录：

    ```json
    {"conversations": [{"from": "human", "value": "..."},
                       {"from": "gpt",   "value": "..."}]}
    ```

    再加上点云模型需要的 ``point_clouds`` 字段与占位符约定。

    ## 与 3D-GRPO 现状的对照（实测，供参考而非约束）

    读 `3D-GRPO/grpo/dataset.py` 确认其当前读取：``conversations`` 的
    human/gpt 两轮、``point_clouds[0]``（只取第一个）、human 文本中的
    ``<point_cloud>`` 占位符会被替换成模型的 point-token 三连。
    本 adapter 的产出与之逐字段对齐，因此**开箱即可被消费**。

    其 `reward.py` 目前只支持单选字母的精确匹配。本项目的 target 有实体 ID、
    米制数值、方位枚举与布尔，多数不是单选字母。这**不构成阻塞** ——
    训练框架会按数据类型调整。本 adapter 做的是把信息给足：

    - 任务能渲染为单选时（Task Spec 提供 ``choices``）就渲染为 MCQ，
      现有 reward 直接可用；
    - 否则保持自由作答，并在 ``verification`` 中带上 checker 名与容差，
      供按数据类型扩展后的 reward 做确定性判分。
    """

    name = "pointcloud_native"

    def _render(self, record: dict[str, Any]) -> RenderedSample:
        pcd = self._require(record, "inputs.pointcloud_ref")
        question = record.get("inputs", {}).get("question")
        if not question:
            raise AdapterError(
                f"样本 {record.get('sample_id')} 缺少 inputs.question，"
                "原生点云 adapter 无法构造对话")

        choices = record.get("inputs", {}).get("choices")
        human = question if POINT_CLOUD_PLACEHOLDER in question \
            else f"{POINT_CLOUD_PLACEHOLDER}\n{question}"

        answer_key = None
        if choices:
            rendered = "\n".join(f"{c['key']}. {c['text']}" for c in choices)
            human = f"{human}\n{rendered}"
            answer_key = self._answer_choice_key(record, choices)
            if answer_key is None:
                raise AdapterError(
                    f"样本 {record.get('sample_id')} 提供了 choices，"
                    "但隐藏目标不匹配任何选项 —— 这会产生无解题")

        payload = {
            "id": record["sample_id"],
            "data_source": record.get("scene_id"),
            "question_type": record["task_spec_id"],
            "point_clouds": [pcd],
            "conversations": [
                {"from": "human", "value": human},
                # gpt 轮承载答案。3D-GRPO 用它作为 GT，模型训练时不会看到。
                {"from": "gpt", "value": answer_key if answer_key
                 else self._freeform_answer(record)},
            ],
        }

        verification = self._verification_block(record)
        verification["answer_mode"] = "multiple_choice" if choices else "free_form"
        verification["sharegpt_conformant"] = True
        verification["mcq_renderable"] = bool(choices)
        if not choices:
            verification["reward_note"] = (
                "本样本为自由作答（答案非单选字母）。训练侧应按 checker 与容差"
                "做确定性判分 —— 判分所需信息已在 verification 中给全。")
        # gpt 轮是 GT 标签，训练时模型看不到它 —— 精确豁免这一条路径。
        label_paths = ["conversations[1].value"]
        if choices:
            # MCQ 的选项被渲染进 human 轮，正确答案文本必然出现在其中 ——
            # 这是单选题的定义，不是泄漏。但代价是 human 轮整体失去扫描保护，
            # 因此改由 _assert_question_clean 单独校验问题本身。
            self._assert_question_clean(record, question)
            label_paths.append("conversations[0].value")
        return RenderedSample(self.name, record["sample_id"], payload, verification,
                              label_paths=tuple(label_paths))

    @staticmethod
    def _assert_question_clean(record: dict[str, Any], question: str) -> None:
        """MCQ 下单独校验**问题本身**不泄漏答案。

        选项列表必然含正确答案（否则无解），故 human 轮整体豁免扫描。
        但问题文本仍**不得**指明哪个选项是对的 —— 这里补上那道检查。
        """
        from .base import LeakageError, scan_for_leakage

        findings = scan_for_leakage({"question": question},
                                    record.get("hidden_target") or {},
                                    record.get("evidence"))
        if findings:
            raise LeakageError(
                f"样本 {record.get('sample_id')} 的问题文本泄漏了答案", findings)

    @staticmethod
    def _answer_choice_key(record: dict[str, Any], choices: list[dict]) -> str | None:
        """找出隐藏目标对应的选项键。"""
        target = record.get("hidden_target") or {}
        wanted = {str(v) for v in target.values() if isinstance(v, (str, bool))}
        for c in choices:
            if c["text"] in wanted or str(c["text"]).lower() in {w.lower() for w in wanted}:
                return c["key"]
        return None

    @staticmethod
    def _freeform_answer(record: dict[str, Any]) -> str:
        """自由作答的 GT 文本。

        由 hidden_target 渲染，**只出现在 gpt 轮**（GT），不进 human 轮。
        """
        target = record.get("hidden_target") or {}
        parts = [f"{k}={v}" for k, v in target.items() if k != "target_type"]
        return "; ".join(parts) if parts else str(target.get("target_type", ""))


class Qwen2DMetadataAdapter(TaskAdapter):
    """Qwen adapter：2D 图像/视频 + 任务局部 3D metadata。

    **铁律 3：Qwen MUST NOT 消费原始点云。** 因此本 adapter 显式**丢弃**
    ``inputs.pointcloud_ref``，即使记录里有它。这不是疏忽，是架构约束。
    """

    name = "qwen_2d_metadata"

    def _render(self, record: dict[str, Any]) -> RenderedSample:
        inputs = record.get("inputs") or {}
        visual = inputs.get("visual_inputs") or []
        if not visual:
            raise AdapterError(
                f"样本 {record.get('sample_id')} 没有 visual_inputs，"
                "Qwen adapter 需要至少一个视觉输入")
        question = inputs.get("question")
        if not question:
            raise AdapterError(f"样本 {record.get('sample_id')} 缺少 inputs.question")

        payload = {
            "sample_id": record["sample_id"],
            "task_spec_id": record["task_spec_id"],
            "visual_inputs": list(visual),
            # 铁律 3：不投影 pointcloud_ref
            "metadata_context": inputs.get("visible_metadata") or {},
            "metadata_fields": list(inputs.get("visible_metadata_fields") or []),
            "observer_pose_id": inputs.get("observer_pose_id"),
            "question": question,
        }
        if inputs.get("choices"):
            payload["choices"] = inputs["choices"]

        verification = self._verification_block(record)
        verification["pointcloud_withheld"] = True
        verification["pointcloud_withheld_reason"] = (
            "铁律 3：Qwen 在本架构中不直接读取点云")
        return RenderedSample(self.name, record["sample_id"], payload, verification)


class Multimodal3DAdapter(TaskAdapter):
    """多模态 3D adapter：点云 + 图像 + 相机 + metadata 全都给。

    信息最全的一路。正因如此，**它最容易泄漏** —— metadata 里多带一个字段
    就可能把答案送出去。基类的泄漏扫描对它尤其重要。
    """

    name = "multimodal_3d"

    def _render(self, record: dict[str, Any]) -> RenderedSample:
        inputs = record.get("inputs") or {}
        pcd = self._require(record, "inputs.pointcloud_ref")
        question = inputs.get("question")
        if not question:
            raise AdapterError(f"样本 {record.get('sample_id')} 缺少 inputs.question")

        payload = {
            "sample_id": record["sample_id"],
            "task_spec_id": record["task_spec_id"],
            "pointcloud_ref": pcd,
            "visual_inputs": list(inputs.get("visual_inputs") or []),
            "camera_refs": list(inputs.get("camera_refs") or []),
            "observer_pose_id": inputs.get("observer_pose_id"),
            "metadata_context": inputs.get("visible_metadata") or {},
            "metadata_fields": list(inputs.get("visible_metadata_fields") or []),
            "question": question,
        }
        if inputs.get("choices"):
            payload["choices"] = inputs["choices"]
        return RenderedSample(self.name, record["sample_id"], payload,
                              self._verification_block(record))


ADAPTER_REGISTRY: dict[str, TaskAdapter] = {
    a.name: a for a in (
        PointcloudNativeAdapter(), Qwen2DMetadataAdapter(), Multimodal3DAdapter())
}


def get_adapter(name: str) -> TaskAdapter:
    """按名取 adapter。未注册的名字必须报错，不得静默跳过。"""
    if name not in ADAPTER_REGISTRY:
        raise AdapterError(
            f"未注册的 adapter {name!r}；已注册：{sorted(ADAPTER_REGISTRY)}")
    return ADAPTER_REGISTRY[name]
