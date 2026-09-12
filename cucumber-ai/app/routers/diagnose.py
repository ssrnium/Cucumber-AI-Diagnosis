from fastapi import APIRouter

from app.schemas import DiagnoseRequest, DiagnosisReport
from app.services import report

router = APIRouter()


@router.post("/diagnose", response_model=DiagnosisReport)
def diagnose(request: DiagnoseRequest) -> DiagnosisReport:
    """证据 -> 检索 -> 受控生成 -> 诊断报告（含来源追溯 source_ids）。"""
    return report.generate_report(request)
