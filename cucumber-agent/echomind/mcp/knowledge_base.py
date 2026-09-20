"""
RAG 知识库 —— 基于 ChromaDB 的真实检索实现。

功能：
  1. 文档导入：将文本切片后存入 ChromaDB（自动生成 Embedding）
  2. 语义检索：根据 query 从知识库中检索最相关的文档片段
  3. 与 MCP 工具框架集成：作为 knowledge_search 工具的真实 handler

ChromaDB 在这里的角色：
  - memory/ 中用于存储对话记忆（情景记忆 + 用户画像）
  - 这里用于存储知识库文档（RAG 检索）
  两者是不同的 collection，互不干扰。
"""
import asyncio
import hashlib
import json
import logging
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)

# ── 检索增强配置（V2/V3/V4，详见 docs/评测报告_RAG对照实验_20260920.md）──────────
#
# KB_EMBEDDING_MODEL:
#   "default"            → Chroma 内置 ONNX all-MiniLM-L6-v2（英文，V1 基线）
#   "bge-small-zh-v1.5"  → 中文 BGE 向量（V2），使用独立 collection，不覆盖旧数据
# KB_ALIAS_NORM=1 → V3：查询侧别名归一化（病害俗称→学名、口语→知识类目）
# KB_HYBRID=1     → V4：向量分 + KB 编号/病害名/类目关键词命中的确定性混合重排
#
# 三项均有 __init__ 参数可显式覆盖（评测脚本用），环境变量仅作缺省。

# 病害别名表：左为知识库 disease_type 学名，右为田间俗称/口语叫法（真实农学别名，
# 非针对评测集调参）：流胶病/蔓割病是蔓枯病俗称，跑马干是霜霉病俗称，白毛病是白粉病俗称。
DISEASE_ALIASES: Dict[str, List[str]] = {
    "黄瓜霜霉病": ["霜霉病", "霜霉", "跑马干"],
    "黄瓜白粉病": ["白粉病", "白粉", "白毛病", "白毛"],
    "黄瓜炭疽病": ["炭疽病", "炭疽"],
    "黄瓜蔓枯病": ["蔓枯病", "蔓枯", "蔓割病", "流胶病", "流胶"],
    "健康叶片":   ["健康叶片", "健康黄瓜", "正常叶片", "健康的黄瓜叶"],
}

# 知识类目别名表：左为知识条目标题中的类目词，右为用户口语表达。
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "症状识别": ["症状识别", "症状", "表现", "特征", "长什么样", "什么样", "什么状态", "什么毛病", "怎么回事", "识别"],
    "发病条件": ["发病条件", "发病规律", "发生条件", "温湿度", "条件下", "什么环境", "诱发", "流行"],
    "农业防治": ["农业防治", "生物防治", "栽培", "预防", "防控", "管理手段", "不打农药", "不用农药", "通风"],
    "化学防治": ["化学防治", "药剂", "杀菌剂", "打药", "喷药", "哪些药", "用什么药"],
    "用药注意": ["用药注意", "注意事项", "留意", "讲究", "抗药性", "抗性", "轮换", "间隔期"],
}

_KB_ID_RE = re.compile(r"KB-[A-Z]+-\d{3}")


def match_canonical_terms(query: str) -> Dict[str, List[str]]:
    """扫描查询中命中的病害学名与知识类目（长别名优先，避免“霜霉”抢先于“霜霉病”）。"""
    diseases: List[str] = []
    for canonical, aliases in DISEASE_ALIASES.items():
        if any(a in query for a in sorted(aliases, key=len, reverse=True)):
            diseases.append(canonical)
    categories: List[str] = []
    for canonical, aliases in CATEGORY_ALIASES.items():
        if any(a in query for a in sorted(aliases, key=len, reverse=True)):
            categories.append(canonical)
    return {"diseases": diseases, "categories": categories,
            "kb_ids": _KB_ID_RE.findall(query)}


def normalize_query(query: str) -> str:
    """V3 别名归一化：保留原文，追加命中的病害学名与类目词，约束向量检索语义。"""
    matched = match_canonical_terms(query)
    extra = matched["diseases"] + matched["categories"]
    if not extra:
        return query
    return f"{query} {' '.join(extra)}"


def hybrid_rerank(
    query: str,
    vector_items: List[Dict[str, Any]],
    corpus: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    V4 确定性混合重排：向量候选与关键词命中候选取并集，按 向量分+关键词加成 重排。

    加成规则（确定性，不引入 reranker 模型）：
      - 查询显式提到 KB 编号且条目命中：+0.60
      - 查询命中病害学名/俗称，条目标题或 disease_type 含该学名：+0.25
      - 查询命中知识类目，条目标题含该类目词：+0.10
    关键词独有候选基础分 0，仅靠加成进入候选集；同分时按 (source_id, chunk) 字典序保证可复现。
    """
    matched = match_canonical_terms(query)
    diseases, categories, kb_ids = matched["diseases"], matched["categories"], matched["kb_ids"]
    if not diseases and not categories and not kb_ids:
        return vector_items[:top_k]

    def bonus(item: Dict[str, Any]) -> float:
        b = 0.0
        if item.get("source_id", "") in kb_ids:
            b += 0.60
        text = f"{item.get('title', '')} {item.get('disease_type', '')}"
        if any(d in text for d in diseases):
            b += 0.25
        if any(c in item.get("title", "") for c in categories):
            b += 0.10
        return b

    merged: Dict[tuple, Dict[str, Any]] = {}
    for it in vector_items:
        key = (it.get("source_id", ""), it.get("chunk", 0))
        merged[key] = dict(it, final_score=round(it.get("score", 0.0) + bonus(it), 4))
    for doc in corpus:
        b = bonus(doc)
        if b <= 0:
            continue
        key = (doc.get("source_id", ""), doc.get("chunk", 0))
        if key not in merged:
            merged[key] = dict(doc, score=0.0, final_score=round(b, 4))

    ranked = sorted(
        merged.values(),
        key=lambda x: (-x["final_score"], x.get("source_id", ""), x.get("chunk", 0)),
    )
    for it in ranked:
        it["score"] = it.pop("final_score")
    return ranked[:top_k]


def load_bge_embedding_fn(model_path: Optional[str] = None):
    """
    加载 BAAI/bge-small-zh-v1.5（CPU）为 Chroma embedding function。

    模型默认取自本地缓存 echomind/data/models/bge-small-zh-v1.5
    （权重经 ModelScope CDN 预下载，见 evaluation/run_retrieval.py --download-model），
    可用 KB_BGE_MODEL_PATH 覆盖；找不到本地权重时回退按模型名在线加载。
    推理后端优先 sentence-transformers，缺失时用 transformers 等价实现
    （BertModel + CLS pooling + L2 归一化，与官方用法一致）。
    """
    default_dir = pathlib.Path(__file__).parent.parent / "data" / "models" / "bge-small-zh-v1.5"
    path = model_path or os.getenv("KB_BGE_MODEL_PATH", "")
    if not path:
        path = str(default_dir) if default_dir.exists() else "BAAI/bge-small-zh-v1.5"

    encode = None
    try:
        from sentence_transformers import SentenceTransformer
        _st = SentenceTransformer(path, device="cpu")
        dim = _st.get_sentence_embedding_dimension()

        def encode(texts: List[str]) -> List[List[float]]:
            return _st.encode(list(texts), normalize_embeddings=True).tolist()
        backend = "sentence-transformers"
    except ImportError:
        import torch
        from transformers import AutoModel, AutoTokenizer
        _tok = AutoTokenizer.from_pretrained(path)
        _model = AutoModel.from_pretrained(path)
        _model.eval()
        dim = _model.config.hidden_size

        def encode(texts: List[str]) -> List[List[float]]:
            batch = _tok(list(texts), padding=True, truncation=True,
                         max_length=512, return_tensors="pt")
            with torch.no_grad():
                out = _model(**batch)
            vecs = out.last_hidden_state[:, 0]  # CLS pooling（bge-zh-v1.5 官方口径）
            vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)
            return vecs.tolist()
        backend = "transformers(cls-pooling)"
    logger.info(f"BGE 中文 embedding 已加载: {path} (dim={dim}, backend={backend})")

    class BGEZhEmbeddingFunction:
        """chromadb 0.5 EmbeddingFunction 协议：__call__(input) -> embeddings。"""

        def name(self) -> str:
            return "bge-small-zh-v1.5"

        def __call__(self, input: List[str]) -> List[List[float]]:
            return encode(input)

    return BGEZhEmbeddingFunction()


def _bge_available() -> bool:
    """本地 BGE 权重与推理后端是否就绪（决定运行时缺省是否启用 V4 口径）。"""
    default_dir = pathlib.Path(__file__).parent.parent / "data" / "models" / "bge-small-zh-v1.5"
    if not (default_dir.exists() and (default_dir / "model.safetensors").exists()):
        return False
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


class KnowledgeBase:
    """
    基于 ChromaDB 的 RAG 知识库。

    ChromaDB 内置了 Embedding 模型（all-MiniLM-L6-v2），
    调用 add() 时自动生成向量，query() 时自动做语义匹配。
    不需要额外调用 Anthropic Embeddings API。
    """

    COLLECTION_NAME = "knowledge_base"
    COLLECTION_NAME_BGE = "knowledge_base_bge_zh"

    def __init__(
        self,
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        chroma_path: str = "./data/chroma",
        client: Optional[Any] = None,
        embedding_model: Optional[str] = None,
        alias_norm: Optional[bool] = None,
        hybrid: Optional[bool] = None,
        collection_name: Optional[str] = None,
    ):
        # 检索版本配置：显式参数 > 环境变量 > 缺省。
        # 缺省（2026-09-20 对照实验结论，见 docs/评测报告_RAG对照实验_20260920.md）：
        # 本地 BGE 权重与后端就绪时启用 V4（bge + 别名归一化 + 关键词混合），
        # 否则回退 V1 基线（Chroma 默认英文 embedding，行为与旧版一致）。
        self._embedding_model = (
            embedding_model or os.getenv("KB_EMBEDDING_MODEL", "")
        ).strip()
        if not self._embedding_model:
            self._embedding_model = "bge-small-zh-v1.5" if _bge_available() else "default"
        _is_bge = self._embedding_model == "bge-small-zh-v1.5"
        self._alias_norm = (
            alias_norm if alias_norm is not None
            else os.getenv("KB_ALIAS_NORM", "1" if _is_bge else "0") == "1"
        )
        self._hybrid = (
            hybrid if hybrid is not None
            else os.getenv("KB_HYBRID", "1" if _is_bge else "0") == "1"
        )
        self._embedding_fn = None
        if self._embedding_model == "bge-small-zh-v1.5":
            self._embedding_fn = load_bge_embedding_fn()

        if client is not None:
            # 测试注入（如 chromadb.EphemeralClient），跳过服务端/本地自动选择
            self._client = client
        else:
            # 优先连接独立 ChromaDB 服务（服务端内置 embedding 模型，客户端无需下载）
            try:
                # HttpClient 默认也会初始化 ChromaDB telemetry；显式关闭避免 posthog 兼容性错误日志。
                self._client = chromadb.HttpClient(
                    host=chroma_host,
                    port=chroma_port,
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )
                self._client.heartbeat()
                logger.info(f"知识库 ChromaDB 已连接: {chroma_host}:{chroma_port}")
            except Exception:
                logger.info(f"知识库 ChromaDB 服务不可用，使用本地模式: {chroma_path}")
                self._client = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )

        # BGE 版本使用独立 collection（cosine 空间），不覆盖旧的默认 embedding 数据
        if collection_name:
            coll_name = collection_name
        elif self._embedding_fn is not None:
            coll_name = self.COLLECTION_NAME_BGE
        else:
            coll_name = self.COLLECTION_NAME
        coll_metadata = {"description": "黄瓜病害 RAG 知识库（带 source_id 来源追溯）"}
        kwargs: Dict[str, Any] = {}
        if self._embedding_fn is not None:
            coll_metadata["hnsw:space"] = "cosine"
            kwargs["embedding_function"] = self._embedding_fn
        self._collection = self._client.get_or_create_collection(
            name=coll_name,
            metadata=coll_metadata,
            **kwargs,
        )

        # 如果知识库为空，导入默认文档
        if self._collection.count() == 0:
            self._load_default_docs()

        # V4 混合检索用的全量语料缓存（28 条种子量级，初始化时一次读取）
        self._corpus: List[Dict[str, Any]] = []
        if self._hybrid:
            self._corpus = self._fetch_corpus()

    # ── 文档管理 ──────────────────────────────────────────────────────────────

    def add_documents(self, documents: List[Dict[str, str]]) -> int:
        """
        批量导入文档到知识库。

        documents 格式: [{"title": "...", "content": "...",
                          "source_id": "...", "disease_type": "...", "level": "...", "category": "..."}]
        长文档会自动切片（每片 500 字）。source_id 等元数据随切片透传，用于来源追溯。
        """
        ids, docs, metas = [], [], []

        for doc in documents:
            title   = doc.get("title", "")
            content = doc.get("content", "")
            chunks  = self._chunk_text(content, chunk_size=500)

            for i, chunk in enumerate(chunks):
                doc_id = hashlib.md5(f"{title}_{i}_{chunk[:50]}".encode()).hexdigest()
                ids.append(doc_id)
                docs.append(chunk)
                metas.append({
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source_id": str(doc.get("source_id", "") or ""),
                    "disease_type": str(doc.get("disease_type", "") or ""),
                    "level": str(doc.get("level", "") or ""),
                    "category": str(doc.get("category", "") or ""),
                })

        if ids:
            # ChromaDB 会自动生成 Embedding
            self._collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info(f"知识库导入 {len(ids)} 个文档片段")
            if getattr(self, "_hybrid", False):
                self._corpus = self._fetch_corpus()

        return len(ids)

    async def add_documents_async(self, documents: List[Dict[str, str]]) -> int:
        """异步导入文档；ChromaDB 客户端为同步实现，因此放入线程池执行。"""
        return await asyncio.to_thread(self.add_documents, documents)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        语义检索：根据 query 返回最相关的文档片段。

        检索口径由配置决定（接口不变）：
          V1 基线：ChromaDB 自动转向量，余弦相似度匹配；
          V3：查询先经别名归一化再检索；
          V4：在 V3 基础上向量分与关键词命中取并集做确定性重排。
        """
        norm_query = normalize_query(query) if self._alias_norm else query
        fetch_k = top_k * 3 if self._hybrid else top_k
        results = self._collection.query(
            query_texts=[norm_query],
            n_results=fetch_k,
        )

        items = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                items.append({
                    "title":    meta.get("title", ""),
                    "content":  doc,
                    "score":    round(1.0 - dist, 4),  # ChromaDB 返回距离，转为相似度
                    "chunk":    meta.get("chunk_index", 0),
                    "source_id": meta.get("source_id", ""),
                    "disease_type": meta.get("disease_type", ""),
                    "level":    meta.get("level", ""),
                    "category": meta.get("category", ""),
                })

        if self._hybrid:
            items = hybrid_rerank(query, items, self._corpus, top_k)
        return items

    async def search_async(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """异步检索；ChromaDB 客户端为同步实现，因此放入线程池执行。"""
        return await asyncio.to_thread(self.search, query, top_k)

    @property
    def doc_count(self) -> int:
        return self._collection.count()

    async def doc_count_async(self) -> int:
        """异步获取文档片段数量。"""
        return await asyncio.to_thread(self._collection.count)

    # ── MCP 工具 handler ─────────────────────────────────────────────────────

    async def search_handler(self, params: Dict[str, Any], context: Any) -> List[Dict]:
        """
        作为 MCP 工具的 handler 注册。

        MCPToolManager.register(Tool(
            name="knowledge_search",
            handler=kb.search_handler,
            ...
        ))
        """
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        return await self.search_async(query, top_k=top_k)

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _fetch_corpus(self) -> List[Dict[str, Any]]:
        """读取全量条目（V4 关键词混合检索的候选来源）。"""
        got = self._collection.get(include=["documents", "metadatas"])
        corpus = []
        for doc, meta in zip(got.get("documents") or [], got.get("metadatas") or []):
            corpus.append({
                "title": meta.get("title", ""),
                "content": doc,
                "score": 0.0,
                "chunk": meta.get("chunk_index", 0),
                "source_id": meta.get("source_id", ""),
                "disease_type": meta.get("disease_type", ""),
                "level": meta.get("level", ""),
                "category": meta.get("category", ""),
            })
        return corpus

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """将长文本按 chunk_size 切片，保留语义完整性（按句号/换行切分）。"""
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        chunks = []
        current = ""
        # 按句子切分
        sentences = text.replace("\n", "。").split("。")
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) + 1 > chunk_size:
                if current:
                    chunks.append(current)
                current = sent
            else:
                current = f"{current}。{sent}" if current else sent

        if current:
            chunks.append(current)

        return chunks

    def _load_default_docs(self) -> None:
        """导入黄瓜病害知识种子（28 条，源自论文第六章 disease_knowledge.json 同构数据）。"""
        seed_path = pathlib.Path(__file__).parent.parent / "data" / "cucumber_knowledge.json"
        try:
            docs = json.loads(seed_path.read_text(encoding="utf-8"))
            if not isinstance(docs, list) or not docs:
                raise ValueError("知识种子文件为空或格式错误")
        except Exception as ex:
            logger.warning(f"黄瓜知识种子加载失败（{seed_path}）: {ex}")
            return
        self.add_documents(docs)
        logger.info(f"已导入黄瓜病害知识种子: {len(docs)} 条（5 病害类别 + 通用用药安全）")
