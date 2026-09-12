from fastapi import APIRouter, HTTPException

from app.schemas import Evidence
from app.services import retriever

router = APIRouter()


@router.get("/knowledge/{source_id}", response_model=Evidence)
def knowledge_detail(source_id: str) -> Evidence:
    """按 source_id 查询知识原文，用于诊断报告中的来源追溯展示。"""
    entry = retriever.get_by_source_id(source_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {source_id}")
    return Evidence(**entry)
