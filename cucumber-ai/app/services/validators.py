"""润色结果事实一致性校验器（正式版 12 项核查）。

逐行移植自论文第六章 validate_kimi_polish.py —— "幻觉率 0.22%"的口径
完全由这些规则定义，任何改动都会改变口径，不得修改。
"""

import re
from typing import Dict, Iterable, List, Set

PROTECTED = [
    "image_id", "suspected_disease_class", "prediction_confidence",
    "evidence_ids", "source_ids", "low_confidence_flag", "class_conflict_flag",
]
EDITABLE = ["diagnosis_summary", "knowledge_explanation", "management_suggestions", "uncertainty_note"]
VISUAL_CLAIM = re.compile(r"可见|观察到|图像显示|图中可见|照片显示|显示出.*病斑|发现.*病斑")
PATH_LEAK = re.compile(r"\.jpe?g|\.png|[A-Za-z]:\\|images/|train/|val/|test/")
MD_WRAP = re.compile(r"```|^#+\s")


def ngrams(text, n=3):
    if not text or len(text) < n:
        return set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def editable_texts(report: Dict) -> List[str]:
    out = [report.get("diagnosis_summary", ""), report.get("knowledge_explanation", ""),
           report.get("uncertainty_note", "")]
    out += [s for s in report.get("management_suggestions", []) if isinstance(s, str)]
    return [t for t in out if t]


def check_one(sk: Dict, pol: Dict, knowledge_sids: Set[str],
              mapping_names: Iterable[str] = ()) -> List[str]:
    """返回错误列表，空列表即通过。mapping_names 为原始文件名泄漏黑名单（本平台无映射表，传空）。"""
    errors = []
    # 1 JSON 可解析（调用方保证）2 必填字段完整
    for k in PROTECTED + EDITABLE:
        if k not in pol:
            errors.append(f"missing_field:{k}")
    # 3 protected 逐项相等（含 4 evidence_ids 不增不减、5 跨图引用）
    for k in PROTECTED:
        if sk.get(k) != pol.get(k):
            errors.append(f"protected_field_changed:{k}")
    if not isinstance(pol.get("management_suggestions"), list):
        errors.append("management_suggestions_not_list")
    # 5 source_ids 全部存在于知识库
    for sid in pol.get("source_ids", []):
        if sid not in knowledge_sids:
            errors.append(f"unknown_source_id:{sid}")
    # 6 低置信保留不确定性说明
    if sk.get("low_confidence_flag") and not pol.get("uncertainty_note", "").strip():
        errors.append("low_confidence_note_missing")
    # 7 冲突样本保留类别冲突提示
    if sk.get("class_conflict_flag") and "冲突" not in pol.get("uncertainty_note", ""):
        errors.append("conflict_note_missing")
    # 8 Fresh Leaf 不得生成病害防治建议
    if sk.get("suspected_disease_class") == "Fresh_Leaf":
        sk_text = " ".join(editable_texts(sk))
        for s in pol.get("management_suggestions", []):
            for kw in ("喷雾", "药剂", "农药"):
                if kw in s and kw not in sk_text:
                    errors.append(f"fresh_leaf_disease_control:{kw}")
    # 9 内容支撑：可编辑文本每句须有骨架 3-gram 支撑
    sup = set()
    for t in editable_texts(sk):
        sup |= ngrams(t, 3)
    if sup:
        for t in editable_texts(pol):
            segs = [s for s in re.split(r"[。\n]", t) if len(s) >= 6]
            for s in segs:
                if not (ngrams(s, 3) & sup):
                    errors.append(f"unsupported_segment:{s[:20]}")
                    break
    # 10 不得将整叶框扩写为病斑级视觉观察（检查 diagnosis_summary 与 uncertainty_note）
    for t in (pol.get("diagnosis_summary", ""), pol.get("uncertainty_note", "")):
        if VISUAL_CLAIM.search(t):
            errors.append("visual_overclaim_in_summary")
    # 11 不出现原始文件名或路径
    for t in editable_texts(pol):
        if PATH_LEAK.search(t):
            errors.append("path_or_filename_leak")
            break
        for name in mapping_names:
            if name and name in t:
                errors.append(f"original_filename_leak:{name}")
                break
    # 12 无 Markdown 包裹
    for t in editable_texts(pol):
        if MD_WRAP.search(t):
            errors.append("markdown_wrapper_found")
            break
    return errors
