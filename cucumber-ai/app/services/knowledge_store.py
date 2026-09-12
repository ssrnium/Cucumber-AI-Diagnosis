"""农业知识库（论文版嵌套结构）加载与检索。

数据来源：硕士论文 disease_knowledge.json（metadata.source_count=28，
4 个病害条目 DM/PM/ANT/GST + healthy_leaf，条目内 symptoms/conditions/
control/notes 四字段各带 sources 引用，全库共 28 个合法 source_id）。

检索口径与论文一致：类别已知 -> 显式映射唯一条目（确定性、可追溯），
不使用向量检索（论文 README §3 的结论）。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_KB_PATH = ROOT_DIR / "data" / "disease_knowledge.json"

CLASS_TO_KNOWLEDGE = {
    "Fresh_Leaf": "healthy_leaf",
    "Anthracnose": "ANT",
    "Downy_Mildew": "DM",
    "Gummy_Stem_Blight": "GST",
    "Powdery_Mildew": "PM",
}

CN_NAME = {
    "Fresh_Leaf": "健康黄瓜叶片",
    "Anthracnose": "黄瓜炭疽病",
    "Downy_Mildew": "黄瓜霜霉病",
    "Gummy_Stem_Blight": "黄瓜蔓枯病",
    "Powdery_Mildew": "黄瓜白粉病",
}

# 检测侧中文标签 -> 证据/检索用英文类别
ZH_TO_CLASS = {
    "健康叶": "Fresh_Leaf",
    "炭疽病": "Anthracnose",
    "霜霉病": "Downy_Mildew",
    "蔓枯病": "Gummy_Stem_Blight",
    "白粉病": "Powdery_Mildew",
}

# 扁平来源目录的产品侧分级（依据来源类型，标注于 content 中，非论文口径）
_LEVEL_BY_PREFIX = {
    "KB-BOOK": "A", "KB-JOUR": "A", "KB-SCIENCE": "A", "KB-NAU": "A",
    "KB-CAAS": "B", "KB-GB": "B",
}
_FIELD_CN = {"symptoms": "症状", "conditions": "发病条件", "control": "防治", "notes": "注意事项"}


class KnowledgeStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        kb_path = Path(path) if path else DEFAULT_KB_PATH
        self._kb = json.loads(kb_path.read_text(encoding="utf-8"))
        self._entries: Dict[str, Dict] = {d["disease_id"]: d for d in self._kb.get("diseases", [])}
        self._entries["healthy_leaf"] = self._kb.get("healthy_leaf", {})

    # ── 三级匹配（与论文 tools/knowledge_lookup.py 同口径）──
    def lookup(self, disease_class: str) -> Tuple[Optional[Dict], List[str], str]:
        """返回 (entry, source_ids, match_method)。全 miss 时 entry=None。"""
        if not disease_class:
            return None, [], "miss"
        # ① 显式映射
        kid = CLASS_TO_KNOWLEDGE.get(disease_class)
        if kid and kid in self._entries:
            entry = self._entries[kid]
            return entry, self.collect_source_ids(entry), "exact"
        # ② 归一化（空格转下划线 + 小写）比对 id/name_en/name_cn
        norm = disease_class.replace(" ", "_").lower()
        for entry in self._entries.values():
            names = {str(entry.get(k, "")).lower()
                     for k in ("disease_id", "name_en", "name_cn")}
            if norm in names:
                return entry, self.collect_source_ids(entry), "normalized"
        # ③ 模糊：子串互含
        for entry in self._entries.values():
            for k in ("name_en", "name_cn"):
                name = str(entry.get(k, ""))
                if name and (disease_class in name or name in disease_class):
                    return entry, self.collect_source_ids(entry), "fuzzy"
        return None, [], "miss"

    @staticmethod
    def collect_source_ids(entry: Dict) -> List[str]:
        sids = set()
        for field in ("symptoms", "conditions", "control", "notes"):
            v = entry.get(field, {})
            if isinstance(v, dict) and "sources" in v:
                sids.update(v["sources"])
        return sorted(sids)

    def all_source_ids(self) -> set:
        sids = set()
        for entry in self._entries.values():
            sids.update(self.collect_source_ids(entry))
        return sids

    def flat_catalog(self) -> List[Dict]:
        """从嵌套 KB 聚合扁平来源目录（供业务库来源追溯：每个 source_id
        对应引用它的病害字段与原文片段，内容为知识库原文、未创作）。"""
        catalog: Dict[str, Dict] = {}
        for entry in self._entries.values():
            name_cn = entry.get("name_cn", "")
            for field, field_cn in _FIELD_CN.items():
                v = entry.get(field, {})
                if not isinstance(v, dict):
                    continue
                text = self._field_text(field, v)
                for sid in v.get("sources", []):
                    item = catalog.setdefault(sid, {
                        "source_id": sid,
                        "disease_type": name_cn,
                        "title": "",
                        "content": "",
                        "level": _LEVEL_BY_PREFIX.get(sid.rsplit("-", 1)[0], "C"),
                        "category": field_cn,
                    })
                    item["title"] = f"{name_cn}·{field_cn}"
                    if text and text not in item["content"]:
                        item["content"] = (item["content"] + "；" + text).strip("；")
        return [catalog[sid] for sid in sorted(catalog)]

    @staticmethod
    def _field_text(field: str, v: Dict) -> str:
        if field == "symptoms":
            return v.get("typical") or v.get("leaf_upper") or ""
        if field == "conditions":
            parts = [f"温度{v['temperature']}" if v.get("temperature") else "",
                     f"湿度{v['humidity']}" if v.get("humidity") else "",
                     f"季节{v['season']}" if v.get("season") else ""]
            return "；".join(p for p in parts if p)
        if field == "control":
            parts = [v.get("agricultural", ""), v.get("chemical", ""), v.get("biological", "")]
            return "；".join(p for p in parts if p)
        return v.get("safety_interval", "") or ""


K_STORE = KnowledgeStore()
