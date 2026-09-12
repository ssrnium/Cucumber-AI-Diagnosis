"""检索兼容层（委托 knowledge_store）。

口径与论文一致：类别已知 → 显式映射唯一条目（确定性、可追溯），非向量检索。
保留旧接口（load_knowledge / search）供既有调用方与测试使用。
"""

from typing import Dict, List, Optional

from app.services.knowledge_store import K_STORE, ZH_TO_CLASS


def load_knowledge() -> List[Dict]:
    """扁平来源目录（source_id/title/content/level/category/disease_type）。"""
    return K_STORE.flat_catalog()


def search(disease_type: Optional[str] = None, keywords: Optional[List[str]] = None) -> List[Dict]:
    """按病害类别返回该条目引用的来源条目（keywords 参数保留兼容，不参与匹配）。"""
    cls = ZH_TO_CLASS.get(disease_type or "", disease_type or "")
    entry, source_ids, _ = K_STORE.lookup(cls)
    if not entry:
        return []
    sid_set = set(source_ids)
    return [e for e in K_STORE.flat_catalog() if e["source_id"] in sid_set]
