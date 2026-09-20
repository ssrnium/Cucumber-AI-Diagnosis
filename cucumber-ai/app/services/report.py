"""受控生成诊断报告（论文 agent_v1 工作流迁移版）。

六步流水线（与论文 graph/workflow.py 同语义）：

    证据构建(rule A / 双 flag) → 知识检索(类别显式映射) → 确定性骨架
    → LLM 受控润色 → 12 项校验 → 通过即交付
    校验失败且未满 2 次 → 携带错误列表纠错重润（仅 1 次）
    再失败或 LLM 异常 → 确定性骨架回退（必然合规 —— "交付率 100%"的机制）

对外的 DiagnosisReport 为平台七段式（由论文 11 字段报告映射而来），
口径关键的骨架模板、PROTECTED 原则、12 项校验、prompt 原文均逐字保留。
"""

import hashlib
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from app.schemas import Detection, DiagnoseRequest, DiagnosisReport
from app.services import llm, prompts, skeleton, validators
from app.services.knowledge_store import CN_NAME, K_STORE, ZH_TO_CLASS

logger = logging.getLogger(__name__)

LOW_CONF_THRESHOLD = 0.75  # 论文口径（detect_one.py:21）


# ── ① 证据构建（rule A：最高置信框定图像级类别）──
def _symptom_class_conflicts(clues: List[str], suspected_class: str) -> List[str]:
    """症状线索中显式提及的病害名与模型类别不一致时，返回提及的病害名列表。

    仅匹配知识库已登记的病害别名（如"白粉病"），普通症状词（"黄斑""白粉"）不算类别主张。
    """
    conflicts: List[str] = []
    for clue in clues:
        for zh_name, cls in ZH_TO_CLASS.items():
            if zh_name in clue and cls != suspected_class and zh_name not in conflicts:
                conflicts.append(zh_name)
    return conflicts


def build_evidence(request: DiagnoseRequest) -> Dict:
    detections: List[Detection] = request.detections
    digest = hashlib.sha256(
        json.dumps([d.model_dump() for d in detections], sort_keys=True).encode()
    ).hexdigest()[:8]
    image_id = f"api-{digest}"

    if not detections:
        return {
            "image_id": image_id,
            "suspected_disease_class": None,
            "prediction_confidence": None,
            "detection_count": 0,
            "regions": [],
            "low_confidence_flag": False,
            "class_conflict_flag": False,
            "symptom_clues": list(request.symptoms),
            "symptom_conflicts": [],
        }

    regions = [
        {
            "region_id": f"{image_id}_region_{j}",
            "class_id": j,
            "class_name": d.label,
            "confidence": round(d.confidence, 6),
            "bbox_xyxy": [round(d.x1, 2), round(d.y1, 2), round(d.x2, 2), round(d.y2, 2)],
        }
        for j, d in enumerate(detections)
    ]
    top = max(detections, key=lambda d: d.confidence)
    cls_en = ZH_TO_CLASS.get(top.label, top.label)
    return {
        "image_id": image_id,
        "suspected_disease_class": cls_en,
        "prediction_confidence": round(top.confidence, 6),
        "detection_count": len(detections),
        "regions": regions,
        "low_confidence_flag": top.confidence < LOW_CONF_THRESHOLD,
        "class_conflict_flag": len({d.label for d in detections}) > 1,
        "symptom_clues": list(request.symptoms),
        "symptom_conflicts": _symptom_class_conflicts(request.symptoms, cls_en),
    }


def _parse_json(raw: str) -> Tuple[Optional[Dict], Optional[str]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error:{exc}"


def _map_to_report(pol: Dict, entry: Optional[Dict], status: str) -> DiagnosisReport:
    cls = pol["suspected_disease_class"]
    name_cn = (entry or {}).get("name_cn") or CN_NAME.get(cls, cls)
    summary = pol.get("diagnosis_summary", "")
    explanation = pol.get("knowledge_explanation", "")
    basis = [t for t in [summary] + [l.strip() for l in explanation.split("\n")] if t]

    suggestions = pol.get("management_suggestions", []) or []
    agronomy = [s for s in suggestions if s.startswith(("农业防治", "生物防治"))]
    chemical = [s for s in suggestions if s.startswith("化学防治")]

    safety: List[str] = []
    notes = (entry or {}).get("notes", {})
    if isinstance(notes, dict) and notes.get("safety_interval"):
        safety.append(f"安全间隔期与注意事项：{notes['safety_interval']}")
    uncertainty = pol.get("uncertainty_note", "") or ""
    if uncertainty.strip():
        safety.append(uncertainty)

    diagnosis_status = (
        "UNCERTAIN"
        if pol.get("low_confidence_flag") or pol.get("class_conflict_flag")
        else "DIAGNOSED"
    )
    return DiagnosisReport(
        disease_type=name_cn,
        confidence=round(float(pol["prediction_confidence"]), 4),
        basis=basis,
        agronomy=agronomy,
        chemical=chemical,
        safety=safety,
        source_ids=pol.get("source_ids", []),
        uncertainty_note=uncertainty or None,
        report_status=status,
        diagnosis_status=diagnosis_status,
        requires_review=diagnosis_status == "UNCERTAIN",
    )


INCONCLUSIVE_NOTE = "未检出可信病斑，当前结果不足以判断叶片是否健康"


def _inconclusive_report(request: DiagnoseRequest) -> DiagnosisReport:
    """无检测框：信息不足，不映射为"健康叶"（无信息 ≠ 健康），不走 LLM 流水线。"""
    basis = [INCONCLUSIVE_NOTE]
    if request.symptoms:
        basis.append(
            "用户补充的症状线索：" + "、".join(request.symptoms)
            + "（症状线索仅作辅助参考，需结合人工复核确认）"
        )
    return DiagnosisReport(
        disease_type=None,
        confidence=None,
        basis=basis,
        agronomy=[],
        chemical=[],
        safety=[INCONCLUSIVE_NOTE, "建议补拍更清晰的叶片特写后重新诊断，或提交专家复核。"],
        source_ids=[],
        uncertainty_note=INCONCLUSIVE_NOTE,
        report_status="inconclusive",
        diagnosis_status="INCONCLUSIVE",
        requires_review=True,
    )


def generate_report(request: DiagnoseRequest) -> DiagnosisReport:
    # ① 证据 → ② 检索 → ③ 骨架
    evidence = build_evidence(request)
    if not request.detections:
        logger.info("无检测框（image_id=%s），按 INCONCLUSIVE 语义直接返回", evidence["image_id"])
        return _inconclusive_report(request)
    entry, _, match_method = K_STORE.lookup(evidence["suspected_disease_class"])
    if entry is None:
        logger.warning("知识库未命中类别 %s（match_method=%s），骨架走空条目分支",
                       evidence["suspected_disease_class"], match_method)
    sk = skeleton.build_skeleton(evidence, entry or {})

    # ④ LLM 受控润色 → ⑤ 12 项校验（首润 + 仅 1 次纠错重润，与论文 attempt<2 同义）
    provider = llm.get_provider()
    task = prompts.build_task(sk)
    errors: List[str] = []
    polished: Optional[Dict] = None

    for attempt in (1, 2):
        try:
            raw = provider.polish(task, correction_errors=errors or None)
        except Exception as exc:  # noqa: BLE001  节点失败 → 骨架回退（论文 failed→fallback_persist）
            logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, exc)
            break
        pol, parse_err = _parse_json(raw)
        if parse_err:
            logger.warning("LLM 输出 JSON 解析失败（第 %d 次）: %s", attempt, parse_err)
            errors = [parse_err]
            continue
        errs = validators.check_one(sk, pol, K_STORE.all_source_ids())
        if not errs:
            polished = pol
            logger.info("报告润色通过（第 %d 次, match_method=%s）", attempt, match_method)
            break
        errors = errs
        logger.warning("报告校验失败（第 %d 次）: %s", attempt, errs[:4])

    # ⑥ 交付 / 骨架回退
    if polished is None:
        logger.info("使用确定性骨架回退（fallback_to_skeleton）")
        polished = sk
        status = "fallback_to_skeleton"
    else:
        status = "polished"
    return _map_to_report(polished, entry, status)
