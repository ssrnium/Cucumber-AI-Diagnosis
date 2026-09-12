"""受控生成诊断报告骨架。

流程：LLM 生成 -> JSON Schema 校验 -> source_id 合法性校验
     -> 失败重试 2 次 -> 骨架降级回退（不用 LLM 也能出结构化报告）。

【agent_v1 LangGraph 工作流插入点】
后续将硕士论文中的 LangGraph 受控生成工作流（检索增强 -> 生成 -> 校验 ->
回检重写）迁移至此，替换 generate_report 内部实现，对外接口保持不变。
"""

import json
import logging
from typing import Dict, List, Optional

from pydantic import ValidationError

from app.schemas import Detection, DiagnoseRequest, DiagnosisReport
from app.services import llm, retriever

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 首次生成 + 重试 2 次


class ReportValidationError(Exception):
    """报告校验失败（JSON 非法 / Schema 不符 / source_id 越界）。"""


def _top_label(detections: List[Detection]) -> Optional[str]:
    if not detections:
        return None
    return max(detections, key=lambda d: d.confidence).label


def _top_confidence(detections: List[Detection]) -> float:
    if not detections:
        return 0.5
    return max(d.confidence for d in detections)


def _build_prompt(disease_type: str, confidence: float, symptoms: List[str],
                  entries: List[Dict]) -> str:
    evidence_lines = "\n".join(
        f"- [{e['source_id']}]（{e['level']}级/{e['category']}）{e['title']}：{e['content']}"
        for e in entries
    )
    return (
        f"疑似病害：{disease_type}\n"
        f"检测置信度：{confidence:.2f}\n"
        f"症状关键词：{'、'.join(symptoms) or '无'}\n\n"
        f"候选知识证据（只允许引用以下 source_id）：\n{evidence_lines}\n\n"
        "请输出 JSON，字段：disease_type, confidence, basis[], agronomy[], chemical[], "
        "safety[], source_ids[]。source_ids 只能取自上方候选证据编号。"
    )


def _parse_and_validate(raw: str, valid_source_ids: List[str]) -> DiagnosisReport:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportValidationError(f"LLM 输出不是合法 JSON: {exc}") from exc
    try:
        report = DiagnosisReport(**data)
    except (ValidationError, TypeError) as exc:
        raise ReportValidationError(f"报告不符合 JSON Schema: {exc}") from exc
    illegal = set(report.source_ids) - set(valid_source_ids)
    if illegal:
        raise ReportValidationError(f"source_id 越界引用: {sorted(illegal)}")
    return report


def _fallback_report(disease_type: str, confidence: float,
                     entries: List[Dict]) -> DiagnosisReport:
    """骨架降级回退：不依赖 LLM，直接由检索到的知识条目拼装结构化报告。"""
    basis, agronomy, chemical = [], [], []
    for entry in entries:
        line = f"{entry['title']}：{entry['content']}"
        category = entry.get("category", "症状")
        if category == "症状":
            basis.append(line)
        elif category == "药剂":
            chemical.append(line)
        else:
            agronomy.append(line)
    return DiagnosisReport(
        disease_type=disease_type,
        confidence=round(confidence, 4),
        basis=basis or [f"检测模型判定为{disease_type}，建议结合田间症状复核。"],
        agronomy=agronomy or ["加强田间巡查，及时隔离病株，控制棚内湿度。"],
        chemical=chemical or ["请在农技人员指导下选用登记药剂，严格按标签剂量使用。"],
        safety=["施药人员做好个人防护，遵守农药安全间隔期，避免高温时段施药。"],
        source_ids=[e["source_id"] for e in entries],
    )


def generate_report(request: DiagnoseRequest) -> DiagnosisReport:
    disease_type = _top_label(request.detections) or "健康叶"
    confidence = _top_confidence(request.detections)
    entries = retriever.search(disease_type=disease_type, keywords=request.symptoms)
    valid_source_ids = [e["source_id"] for e in entries]

    provider = llm.get_provider()
    prompt = _build_prompt(disease_type, confidence, request.symptoms, entries)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = provider.generate(prompt)
            report = _parse_and_validate(raw, valid_source_ids)
            report.confidence = round(confidence, 4)
            return report
        except ReportValidationError as exc:
            logger.warning("报告校验失败（第 %d 次）: %s", attempt, exc)
        except Exception as exc:  # noqa: BLE001  LLM 调用异常同样走重试/回退
            logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, exc)

    logger.info("LLM 生成多次失败，使用骨架降级回退报告")
    return _fallback_report(disease_type, confidence, entries)
