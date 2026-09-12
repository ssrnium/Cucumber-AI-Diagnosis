"""确定性事实报告骨架构建（程序生成，不调用任何大模型）。

逐行移植自论文第六章 build_report_skeletons.py —— 骨架是"交付率 100%"
与 uncertainty_note 校验的口径基础，模板文字不得改动。
"""

import time
from typing import Dict, List

from app.services.knowledge_store import CN_NAME, K_STORE


def build_skeleton(ev: Dict, entry: Dict) -> Dict:
    cls = ev["suspected_disease_class"]
    conf = ev["prediction_confidence"]
    low = ev["low_confidence_flag"]
    conflict = ev["class_conflict_flag"]
    name_cn = entry.get("name_cn", CN_NAME.get(cls, cls)) if entry else CN_NAME.get(cls, cls)

    # diagnosis_summary（程序模板，事实型）
    if cls == "Fresh_Leaf":
        summary = f"检测模型预测该叶片为{name_cn}（置信度 {conf:.4f}）。"
    else:
        summary = f"检测模型预测该叶片疑似{name_cn}（置信度 {conf:.4f}）。"

    # knowledge_explanation（知识库原文摘编，不创作）
    sym = entry.get("symptoms", {}) if entry else {}
    cond = entry.get("conditions", {}) if entry else {}
    parts = []
    typical = sym.get("typical") or sym.get("leaf_upper") or ""
    if typical:
        parts.append(f"知识库记载的典型症状：{typical}")
    cond_bits = [f"温度 {cond.get('temperature')}" if cond.get("temperature") else "",
                 f"湿度 {cond.get('humidity')}" if cond.get("humidity") else "",
                 f"季节 {cond.get('season')}" if cond.get("season") else ""]
    cond_text = "；".join(b for b in cond_bits if b)
    if cond_text:
        parts.append(f"适宜发病条件：{cond_text}。")
    explanation = "\n".join(parts) if parts else "知识库未登记该类别详细说明。"

    # management_suggestions（逐条复制知识库防治条目）
    control = entry.get("control", {}) if entry else {}
    suggestions: List[str] = []
    for key, label in (("agricultural", "农业防治"), ("chemical", "化学防治"), ("biological", "生物防治")):
        text = control.get(key, "")
        if text:
            if key == "chemical" and control.get("disclaimer"):
                text = f"{text}（{control['disclaimer']}）"
            suggestions.append(f"{label}：{text}")

    # uncertainty_note（程序规则生成）
    notes = []
    if low:
        notes.append(f"本图最高检测置信度为 {conf:.4f}，低于 0.75，诊断结论置信度有限，建议人工复核。")
    if conflict:
        notes.append("本图存在多个类别的检测框，类别归属存在冲突，建议人工复核。")
    uncertainty = "".join(notes)

    return {
        "image_id": ev["image_id"],
        "suspected_disease_class": cls,
        "prediction_confidence": conf,
        "evidence_ids": [r["region_id"] for r in ev["regions"]],
        "source_ids": K_STORE.collect_source_ids(entry) if entry else [],
        "low_confidence_flag": low,
        "class_conflict_flag": conflict,
        "diagnosis_summary": summary,
        "knowledge_explanation": explanation,
        "management_suggestions": suggestions,
        "uncertainty_note": uncertainty,
        "knowledge_id": (entry or {}).get("disease_id", "healthy"),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generator": "skeleton.py (deterministic, no LLM)",
    }
