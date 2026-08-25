#!/usr/bin/env python3
"""R-43：3D 增益（3D lift）实测 —— 铁律 5 的准入线。

`DESIGN.md` §29 规定：任务进 Release 的条件不是「2D 做不到」（信息论上不可能，
因为我们的 3D metadata 本就是从同一批 2D 图像提取的），而是

    lift = score(2D + metadata) − score(2D only)   显著 > 0
    且   打乱/屏蔽 metadata 后该增益**选择性消失**

三档 arm：

======  ==========================  ==================================
arm     模型看到的                    用途
======  ==========================  ==================================
``a``   图 + 问题 + 候选 ID           2D-only 基线
``b``   图 + 问题 + **真** metadata   实验组
``c``   图 + 问题 + **打乱** metadata  伪增益对照（§29.2）
======  ==========================  ==================================

**arm c 是关键**：只有 b 高于 a 无法区分真增益与「多给点 token 就涨分」。
若 c 与 b 相当，说明模型没在用 metadata 的内容，只是被格式/长度带高了。

打乱方式是**在候选之间轮换几何字段**，保持 JSON 结构、字段名、
数值分布完全一致 —— 只破坏「哪个几何属于哪个 ID」的对应关系。
这样长度效应与格式效应在 b/c 之间被抵消掉。
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checkers import task_checkers                                # noqa: E402
from task_adapters import get_adapter                             # noqa: E402

API = os.environ.get("QWEN_API_BASE", "http://localhost:8000/v1")
MODEL = os.environ.get("QWEN_MODEL", "Qwen/Qwen3.5-35B-A3B")

_SYSTEM = (
    "You are a UAV 3D scene understanding system. "
    "Answer strictly with a JSON object and nothing else. "
    "Coordinates, when provided, are in a right-handed camera-aligned world frame "
    "whose scale is arbitrary (relative units), with +Z pointing along the "
    "observer's viewing direction."
)


# ------------------------------------------------------------------ arms

def _strip_geometry(meta: dict[str, Any]) -> dict[str, Any]:
    """arm a：抹掉一切 3D 数值，但**保留候选 ID 与类别** —— 答案空间必须一致。

    若连 ID 都不给，模型无从作答，测到的就不是「3D 有没有用」而是
    「能不能猜出选项」，两者不是一回事。
    """
    out = copy.deepcopy(meta)
    out.pop("observer", None)
    for ent in out.get("entities") or []:
        ent.pop("geometry", None)
        ent.pop("visibility", None)
    return out


def _shuffle_geometry(meta: dict[str, Any], seed: str) -> dict[str, Any]:
    """arm c：在候选之间轮换几何，**结构与数值分布不变**，只打断 ID↔几何 的对应。"""
    out = copy.deepcopy(meta)
    ents = out.get("entities") or []
    geos = [e.get("geometry") for e in ents]
    if len(geos) > 1:
        rng = random.Random(seed)
        shift = rng.randrange(1, len(geos))          # 保证不是恒等置换
        for e, g in zip(ents, geos[shift:] + geos[:shift]):
            e["geometry"] = g
    return out


ARMS = {
    "a": ("2D-only", lambda m, s: _strip_geometry(m)),
    "b": ("2D+metadata", lambda m, s: m),
    "c": ("打乱 metadata", lambda m, s: _shuffle_geometry(m, s)),
}


# ------------------------------------------------------------------ 调用

def _answer_schema_hint(task_spec_id: str) -> str:
    if task_spec_id.startswith("3d_grounding"):
        return '{"object_id": "<obj_XXX>"}'
    if "observer_relative_direction" in task_spec_id:
        return '{"longitudinal": "front|behind", "lateral": "left|right|ambiguous"}'
    return "{}"


def ask(payload: dict[str, Any], meta: dict[str, Any], question: str,
        task_spec_id: str, timeout: int = 300) -> dict[str, Any] | None:
    parts: list[dict[str, Any]] = []
    for uri in payload.get("visual_inputs") or []:
        parts.append({"type": "image_url",
                      "image_url": {"url": "file://" + os.path.abspath(uri)}})
    text = (f"{question}\n\n"
            f"Scene metadata (JSON):\n{json.dumps(meta, ensure_ascii=False)}\n\n"
            f"Reply with exactly this JSON shape: {_answer_schema_hint(task_spec_id)}")
    parts.append({"type": "text", "text": text})

    body = {"model": MODEL,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": parts}],
            "temperature": 0.0, "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"{API}/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception as exc:                                      # noqa: BLE001
        print(f"      请求失败: {type(exc).__name__}: {str(exc)[:120]}")
        return None
    txt = (data["choices"][0]["message"].get("content") or "").strip()
    txt = txt.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        start, end = txt.find("{"), txt.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(txt[start:end + 1])
            except json.JSONDecodeError:
                pass
        print(f"      非 JSON 输出: {txt[:100]}")
        return None


# ------------------------------------------------------------------ 评分

_CHECKERS = {
    "3d_grounding.object": task_checkers.check_object_grounding_answer,
    "3d_vqa.situated.observer_relative_direction":
        task_checkers.check_observer_relative_direction_answer,
}


def _evidence_for(record: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """按各 checker 的契约构造 evidence。

    checker **独立重算** target，因此它要的是推导所需的原始量
    （候选集、观察者位姿、目标位置），而不是已经算好的答案。
    """
    spec_id = record["task_spec_id"].split("@")[0]
    tgt = record["hidden_target"]
    ev = record["evidence"]
    if spec_id == "3d_grounding.object":
        return {
            "target_object_id": tgt["object_id"],
            "candidate_ids": ev["used_entities"],
            "ambiguous": record.get("ambiguity", {}).get("is_ambiguous", False),
            "equivalent_answers": record.get("ambiguity", {}).get("equivalent_answers", []),
        }
    if spec_id == "3d_vqa.situated.observer_relative_direction":
        di = ev.get("derivation_inputs") or {}
        pos = next((e["geometry"]["centroid"] for e in (meta.get("entities") or [])
                    if e.get("object_id") == tgt.get("object_id")), None)
        return {
            "target_position": pos,
            "observer_position": di.get("observer_position"),
            "observer_forward": di.get("observer_forward"),
        }
    raise KeyError(spec_id)


def score(record: dict[str, Any], answer: dict[str, Any] | None,
          true_meta: dict[str, Any]) -> float:
    """用**确定性 checker** 判分，不采信样本里存的值（§27 G3）。

    注意传的是 ``true_meta`` —— 即便这一档给模型看的是打乱后的 metadata，
    **判分永远按真实几何**，否则 arm c 会被自己的错误 target 判成对的。
    """
    if answer is None:
        return 0.0
    spec_id = record["task_spec_id"].split("@")[0]
    fn = _CHECKERS.get(spec_id)
    if fn is None:
        raise KeyError(f"没有 {spec_id} 的 checker —— 判不了分的题不该参与评测")
    try:
        res = fn(answer, _evidence_for(record, true_meta))
    except Exception:                                             # noqa: BLE001
        return 0.0
    ok = getattr(res, "passed", None)
    if ok is None:
        ok = getattr(res, "correct", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("passed", res.get("correct"))
    return 1.0 if ok else 0.0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 区间 —— 小样本下比正态近似稳。§29.1 要求报区间而非点估计。"""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default="/home/aiscuser/nyp/metadata/compiled_records.json")
    ap.add_argument("--repeats", type=int, default=3,
                    help="每条样本每档重复次数（温度为 0，用于测稳定性而非采样）")
    ap.add_argument("--out", default="/home/aiscuser/nyp/metadata/lift_results.json")
    args = ap.parse_args()

    records = json.load(open(args.records))
    adapter = get_adapter("qwen_2d_metadata")
    results: list[dict[str, Any]] = []

    print(f"样本 {len(records)} 条 × 3 档 × {args.repeats} 次 = "
          f"{len(records) * 3 * args.repeats} 次调用\n")

    for i, rec in enumerate(records, 1):
        rendered = adapter.render(rec)
        payload = rendered.payload
        meta = payload.get("metadata_context") or {}
        question = rec["inputs"].get("question") or "Answer the task."
        spec_id = rec["task_spec_id"]
        print(f"[{i}/{len(records)}] {spec_id.split('@')[0]} | {rec['scene_id']}")
        if rec.get("ambiguity", {}).get("is_ambiguous"):
            print("      ⚠ 标记为歧义样本，仍计入但单独统计")

        for arm, (label, fn) in ARMS.items():
            hits = 0
            for r in range(args.repeats):
                view = fn(meta, f"{rec['sample_id']}:{r}")
                ans = ask(payload, view, question, spec_id)
                hits += score(rec, ans, meta)
            results.append({
                "sample_id": rec["sample_id"], "scene_id": rec["scene_id"],
                "task_spec_id": spec_id, "arm": arm, "arm_label": label,
                "hits": hits, "trials": args.repeats,
                "is_ambiguous": bool(rec.get("ambiguity", {}).get("is_ambiguous")),
            })
            print(f"      {arm} {label:16} {hits:.0f}/{args.repeats}")

    # ---- 汇总 ----
    print("\n" + "=" * 66)
    print("  3D 增益汇总（铁律 5 准入线）")
    print("=" * 66)
    by_arm: dict[str, list[float]] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append((r["hits"], r["trials"]))
    acc = {}
    for arm, (label, _) in ARMS.items():
        k = sum(h for h, _ in by_arm.get(arm, []))
        n = sum(t for _, t in by_arm.get(arm, []))
        lo, hi = wilson(int(k), n)
        acc[arm] = k / n if n else 0.0
        print(f"  {arm} {label:16} {k:.0f}/{n} = {acc[arm]:.3f}  "
              f"95%CI [{lo:.3f}, {hi:.3f}]")

    lift = acc.get("b", 0) - acc.get("a", 0)
    pseudo = acc.get("c", 0) - acc.get("a", 0)
    print(f"\n  lift  = b − a = {lift:+.3f}   ← 真增益候选")
    print(f"  伪增益 = c − a = {pseudo:+.3f}   ← 应当接近 0")
    print(f"  净增益 = b − c = {acc.get('b',0) - acc.get('c',0):+.3f}   "
          f"← 扣掉格式/长度效应后的增益")
    print("\n  " + ("⚠ 样本量太小，以上只能作为管线连通性验证，"
                    "不构成 §29.1 的准入判定" if len(records) < 30
                    else "可作为准入判定的初步依据"))
    json.dump({"per_sample": results, "accuracy": acc,
               "lift_b_minus_a": lift, "pseudo_c_minus_a": pseudo},
              open(args.out, "w"), ensure_ascii=False, indent=2)
    print(f"\n  明细 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
