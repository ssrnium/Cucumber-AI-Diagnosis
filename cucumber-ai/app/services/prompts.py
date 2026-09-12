"""受控润色的 prompt 常量与任务包构建。

prompt 原文逐字保留自论文第六章（llm_client.py 与 build_kimi_polish_tasks.py）——
RULES 与 12 项校验一一对应，改一个字都可能改变口径。
"""

import json
from typing import Dict, List, Optional

SYSTEM_MSG = (
    "你是一个严格遵守指令的农业病害诊断报告润色器。你只能对给定事实字段做语言组织与表达优化，"
    "不得修改任何 protected_fields，不得添加知识库之外的信息，输出必须是合法 JSON。"
)

RULES = [
    "不得重新判断病害类别",
    "不得修改任何protected_fields",
    "不得添加知识库之外的症状、病原或防治建议",
    "不得将检测框扩写为模型未观察到的具体病斑特征",
    "低置信或类别冲突时必须保留不确定性表达",
    "只返回规定JSON，不返回Markdown",
]

PROTECTED = [
    "image_id", "suspected_disease_class", "prediction_confidence",
    "evidence_ids", "source_ids", "low_confidence_flag", "class_conflict_flag",
]
EDITABLE = ["diagnosis_summary", "knowledge_explanation", "management_suggestions", "uncertainty_note"]


def build_task(skeleton: Dict) -> Dict:
    return {
        "task_type": "controlled_report_polishing",
        "model_role": "报告语言润色器",
        "protected_fields": {k: skeleton[k] for k in PROTECTED},
        "editable_fields": {k: skeleton[k] for k in EDITABLE},
        "rules": RULES,
    }


def task_to_user_content(task: Dict, correction_errors: Optional[List[str]] = None) -> str:
    content = json.dumps(task, ensure_ascii=False, indent=2)
    if correction_errors:
        content += (
            "\n\n【上次输出未通过校验，请仅修正以下问题并重新输出完整内容】\n"
            + "\n".join(f"- {e}" for e in correction_errors)
        )
    return content
