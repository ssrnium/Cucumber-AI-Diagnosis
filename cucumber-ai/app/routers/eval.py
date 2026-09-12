"""评测入口骨架。

对内置样本集跑完整诊断链路，统计：
- parse_rate          报告可解析率（LLM 输出 -> 合法 JSON Schema）
- citation_valid_rate 引用合法率（source_ids 全部落在知识库内）

【小红书 Agent 项目评测/监控机制插入点】
后续接入真实评测样本集（图片 + 标注）与线上监控指标上报，
本接口保持返回指标 JSON 的形态不变。
"""

from typing import Dict, List

from fastapi import APIRouter

from app.schemas import Detection, DiagnoseRequest
from app.services import report, retriever

router = APIRouter()

# 骨架评测样本集：后续替换为真实标注样本
SAMPLES: List[Dict] = [
    {
        "name": "sample-downy-mildew",
        "detections": [Detection(x1=10, y1=10, x2=90, y2=90, confidence=0.9, label="霜霉病")],
        "symptoms": ["多角形病斑", "霉层"],
    },
    {
        "name": "sample-anthracnose",
        "detections": [Detection(x1=50, y1=60, x2=150, y2=160, confidence=0.8, label="炭疽病")],
        "symptoms": ["褐色病斑", "黄色晕圈"],
    },
    {
        "name": "sample-healthy",
        "detections": [],
        "symptoms": [],
    },
]


@router.post("/eval/run")
def eval_run() -> Dict:
    valid_ids = {e["source_id"] for e in retriever.load_knowledge()}
    details = []
    parsed = 0
    cited_valid = 0
    for sample in SAMPLES:
        request = DiagnoseRequest(detections=sample["detections"], symptoms=sample["symptoms"])
        try:
            result = report.generate_report(request)
            parse_ok = True
            citation_ok = set(result.source_ids).issubset(valid_ids)
            parsed += 1
            cited_valid += 1 if citation_ok else 0
            details.append({
                "name": sample["name"],
                "parse_ok": parse_ok,
                "citation_ok": citation_ok,
                "disease_type": result.disease_type,
                "source_ids": result.source_ids,
            })
        except Exception as exc:  # noqa: BLE001
            details.append({"name": sample["name"], "parse_ok": False, "error": str(exc)})
    total = len(SAMPLES)
    return {
        "total": total,
        "parse_rate": round(parsed / total, 4) if total else 0.0,
        "citation_valid_rate": round(cited_valid / total, 4) if total else 0.0,
        "details": details,
        "note": "骨架评测：接入真实标注样本集后替换 SAMPLES，并补充 mAP / 人工一致率等指标。",
    }
