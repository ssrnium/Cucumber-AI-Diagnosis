"""知识检索服务。

读取 data/disease_knowledge.json，按病害类别 + 症状关键词检索，返回带 source_id 的条目。

【pgvector 向量检索插入点】
后续可将知识条目 embedding 后存入 PostgreSQL(pgvector)，
在此处替换为向量近邻检索（语义召回），接口签名保持不变。
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings

ROOT_DIR = Path(__file__).resolve().parents[2]


@lru_cache
def load_knowledge() -> List[Dict]:
    path = Path(settings.KNOWLEDGE_PATH)
    if not path.is_absolute():
        path = ROOT_DIR / settings.KNOWLEDGE_PATH
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def search(disease_type: Optional[str] = None, keywords: Optional[List[str]] = None,
           limit: int = 5) -> List[Dict]:
    """按病害类别过滤，再按症状关键词命中数排序。"""
    entries = load_knowledge()
    if disease_type:
        matched = [e for e in entries if e.get("disease_type") == disease_type]
        # 无同类条目时退回全库，保证检索不空
        entries = matched or entries
    keywords = keywords or []
    if keywords:
        def score(entry: Dict) -> int:
            text = entry.get("title", "") + entry.get("content", "")
            return sum(1 for kw in keywords if kw and kw in text)

        entries = sorted(entries, key=score, reverse=True)
    return entries[:limit]


def get_by_source_id(source_id: str) -> Optional[Dict]:
    for entry in load_knowledge():
        if entry.get("source_id") == source_id:
            return entry
    return None
