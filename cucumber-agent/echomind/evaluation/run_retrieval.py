"""RAG 检索改进对照实验脚本（2026-09-20）。

四版配置（同一冻结评测集 eval_cases.json，不改期望答案）：
  v1  基线：Chroma 内置 ONNX all-MiniLM-L6-v2（英文），裸向量检索
  v2  换 BAAI/bge-small-zh-v1.5 中文向量，新 collection 重建全部向量（不覆盖旧数据）
  v3  v2 + 查询侧别名归一化（病害俗称→学名、口语→知识类目）
  v4  v3 + 关键词混合检索（向量分与 KB 编号/病害名/类目命中共存取并集，确定性重排）

每版记录：Recall@1/3/5、MRR、Top-1 source_id 命中率、平均查询延迟、
冷启动时间、模型体积、内存粗估（RSS 增量）；并对安全类用例（用药注意/禁限用）
与安全间隔期规范单独统计子集指标，对域外对抗用例记录 Top-1 置信度。

防过拟合：--held-out 使用 eval_cases_heldout.json（23 条同义改写用例，
期望 source_id 继承原条目），只在最终版上跑一次，单独报告。

运行（在 cucumber-agent/echomind/ 目录，或设 PYTHONPATH=echomind）：
  PYTHONUTF8=1 python -m evaluation.run_retrieval --download-model   # 预下载 BGE 权重
  PYTHONUTF8=1 python -m evaluation.run_retrieval --version v1|v2|v3|v4
  PYTHONUTF8=1 python -m evaluation.run_retrieval --version v4 --held-out
输出：docs/rag_retrieval_<version>[_heldout]_20260920.json + .md 摘要
"""
import argparse
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

_ROOT = str(pathlib.Path(__file__).parent.parent.resolve())        # echomind/
_AGENT_ROOT = str(pathlib.Path(__file__).parent.parent.parent.resolve())  # cucumber-agent/
for p in (_ROOT, _AGENT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_retrieval")
logger.setLevel(logging.INFO)

EVAL_DIR = pathlib.Path(__file__).parent
DOCS_DIR = pathlib.Path(_AGENT_ROOT).parent / "docs"
# 评测专用 Chroma 持久化目录，与运行时 data/chroma 完全隔离
EVAL_CHROMA_DIR = pathlib.Path(_ROOT) / "data" / "chroma_eval"
BGE_MODEL_DIR = pathlib.Path(_ROOT) / "data" / "models" / "bge-small-zh-v1.5"

# 安全类用例口径：期望命中禁限用/安全间隔期/轮换规范或各病害"用药注意"条目
SAFETY_IDS = {
    "KB-SAFE-001", "KB-SAFE-002", "KB-SAFE-003",
    "KB-DM-005", "KB-PM-005", "KB-ANT-005", "KB-GST-005",
}

VERSIONS = {
    "v1": {"embedding_model": "default",            "alias_norm": False, "hybrid": False,
           "desc": "基线：Chroma 内置 all-MiniLM-L6-v2（英文）裸向量检索"},
    "v2": {"embedding_model": "bge-small-zh-v1.5",  "alias_norm": False, "hybrid": False,
           "desc": "bge-small-zh-v1.5 中文向量（新 collection 重建）"},
    "v3": {"embedding_model": "bge-small-zh-v1.5",  "alias_norm": True,  "hybrid": False,
           "desc": "v2 + 查询侧别名归一化"},
    "v4": {"embedding_model": "bge-small-zh-v1.5",  "alias_norm": True,  "hybrid": True,
           "desc": "v3 + 关键词混合检索（确定性重排）"},
}


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_AGENT_ROOT,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _dir_size_mb(path: pathlib.Path) -> Optional[float]:
    if not path.exists():
        return None
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1024 / 1024, 1)


def _rss_mb() -> Optional[float]:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        pass
    if sys.platform == "win32":
        # psutil 缺失时用 Windows API 兜底（WorkingSetSize ≈ RSS）
        try:
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD)] + [
                    (f"_{i}", ctypes.c_size_t) for i in range(8)] + [
                    ("WorkingSetSize", ctypes.c_size_t)]

            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / 1024 / 1024
        except Exception:
            return None
    return None


# 推理必需的最小权重文件集（ModelScope 仓库路径）
_BGE_FILES = [
    "config.json", "tokenizer.json", "tokenizer_config.json",
    "vocab.txt", "special_tokens_map.json", "model.safetensors",
]


def _model_size_mb(version: str) -> Optional[float]:
    """模型磁盘体积：v1 取 Chroma ONNX 缓存，v2+ 取本地 BGE 权重目录。"""
    if version == "v1":
        cache = pathlib.Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"
        return _dir_size_mb(cache)
    return _dir_size_mb(BGE_MODEL_DIR)


def download_bge_model() -> None:
    """
    预下载 BGE 权重：优先 modelscope pip 包，缺失/失败时直连 ModelScope CDN
    （实测 CDN 约 11MB/s，远快于本机到 PyPI 的链路），最后回退 HF 镜像。网络抖动重试。
    """
    if BGE_MODEL_DIR.exists() and all((BGE_MODEL_DIR / f).exists() for f in _BGE_FILES):
        logger.info("BGE 权重已存在: %s", BGE_MODEL_DIR)
        return
    BGE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope import snapshot_download
        for attempt in range(3):
            try:
                p = snapshot_download("BAAI/bge-small-zh-v1.5",
                                      local_dir=str(BGE_MODEL_DIR))
                logger.info("ModelScope 下载完成: %s", p)
                return
            except Exception as ex:
                logger.warning("ModelScope 第 %d 次下载失败: %s", attempt + 1, ex)
                time.sleep(3)
    except ImportError:
        logger.info("modelscope 包不可用，改走 CDN 直连")
    # CDN 直连（requests 流式下载）
    import requests
    for f in _BGE_FILES:
        dest = BGE_MODEL_DIR / f
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = f"https://modelscope.cn/models/BAAI/bge-small-zh-v1.5/resolve/master/{f}"
        for attempt in range(3):
            try:
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            fh.write(chunk)
                logger.info("CDN 下载完成: %s (%d bytes)", f, dest.stat().st_size)
                break
            except Exception as ex:
                logger.warning("CDN 第 %d 次下载 %s 失败: %s", attempt + 1, f, ex)
                time.sleep(3)
        else:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"BGE 权重文件下载失败: {f}")


def run_version(version: str, cases_path: pathlib.Path, top_k: int = 5) -> Dict[str, Any]:
    """跑一版配置，返回完整指标与逐条明细。"""
    import chromadb
    from mcp.knowledge_base import KnowledgeBase

    cfg = VERSIONS[version]
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    rag_cases = cases["rag_cases"]

    rss_before = _rss_mb()
    t0 = time.perf_counter()
    client = chromadb.PersistentClient(
        path=str(EVAL_CHROMA_DIR),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    kb = KnowledgeBase(
        client=client,
        embedding_model=cfg["embedding_model"],
        alias_norm=cfg["alias_norm"],
        hybrid=cfg["hybrid"],
        collection_name=f"kb_eval_{version}",
    )
    cold_start_s = round(time.perf_counter() - t0, 2)
    rss_after = _rss_mb()

    details: List[Dict[str, Any]] = []
    latencies: List[float] = []
    ranks: List[Optional[int]] = []
    hits = {1: 0, 3: 0, 5: 0}
    top1_hits = 0
    answerable_n = 0
    safety_stats = {"n": 0, "hit5": 0, "top1": 0}
    adv_top1_scores: List[float] = []

    for i, c in enumerate(rag_cases):
        expected = c.get("expected_source_ids", [])
        tq = time.perf_counter()
        results = kb.search(c["query"], top_k=top_k)
        latencies.append((time.perf_counter() - tq) * 1000)
        got_ids = [r.get("source_id", "") for r in results]

        if not expected:
            # 域外对抗用例：不进分母，只记录 Top-1 置信度（越低说明越好区分）
            if results:
                adv_top1_scores.append(results[0]["score"])
            details.append({
                "query": c["query"], "tag": c.get("tag", ""),
                "expected_source_ids": [], "top_k_source_ids": got_ids,
                "top1_score": results[0]["score"] if results else None,
                "first_relevant_rank": None,
            })
            continue

        answerable_n += 1
        rank = next((idx + 1 for idx, sid in enumerate(got_ids) if sid in expected), None)
        ranks.append(rank)
        for k in hits:
            if rank is not None and rank <= k:
                hits[k] += 1
        top1_hit = bool(got_ids and got_ids[0] in expected)
        top1_hits += int(top1_hit)
        if set(expected) & SAFETY_IDS:
            safety_stats["n"] += 1
            safety_stats["hit5"] += int(rank is not None and rank <= 5)
            safety_stats["top1"] += int(top1_hit)
        details.append({
            "query": c["query"], "tag": c.get("tag", ""),
            "expected_source_ids": expected,
            "top_k_source_ids": got_ids,
            "top1_score": results[0]["score"] if results else None,
            "first_relevant_rank": rank,
            "top1_hit": top1_hit,
            "safety_related": bool(set(expected) & SAFETY_IDS),
        })

    mrr = (sum(1.0 / r for r in ranks if r) / answerable_n) if answerable_n else None
    # 延迟：去掉首条（含向量索引热身），取其余均值
    warm_lat = latencies[1:] if len(latencies) > 1 else latencies
    metrics = {
        "answerable_total": answerable_n,
        "recall_at_1": round(hits[1] / answerable_n, 4) if answerable_n else None,
        "recall_at_3": round(hits[3] / answerable_n, 4) if answerable_n else None,
        "recall_at_5": round(hits[5] / answerable_n, 4) if answerable_n else None,
        "mrr": round(mrr, 4) if mrr is not None else None,
        "top1_source_accuracy": round(top1_hits / answerable_n, 4) if answerable_n else None,
        "avg_query_latency_ms": round(sum(warm_lat) / len(warm_lat), 1) if warm_lat else None,
        "cold_start_s": cold_start_s,
        "model_size_mb": _model_size_mb(version),
        "memory_rss_delta_mb": (round(rss_after - rss_before, 1)
                                if rss_before is not None and rss_after is not None else None),
        "safety_subset": {
            "n": safety_stats["n"],
            "recall_at_5": round(safety_stats["hit5"] / safety_stats["n"], 4) if safety_stats["n"] else None,
            "top1_source_accuracy": round(safety_stats["top1"] / safety_stats["n"], 4) if safety_stats["n"] else None,
        },
        "adversarial_top1_score_avg": (round(sum(adv_top1_scores) / len(adv_top1_scores), 4)
                                       if adv_top1_scores else None),
    }
    return {
        "eval_meta": {
            "version": version,
            "version_desc": cfg["desc"],
            "config": cfg,
            "git_commit": _git_commit(),
            "embedding_model": ("chroma-onnx-all-MiniLM-L6-v2" if version == "v1"
                                else "BAAI/bge-small-zh-v1.5 (cpu, local cache)"),
            "cases_file": str(cases_path),
            "cases_version": cases["meta"]["version"],
            "cases_split": cases["meta"].get("split", "dev"),
            "rag_cases_total": len(rag_cases),
            "answerable_denominator": answerable_n,
            "adversarial_excluded": len(rag_cases) - answerable_n,
            "date": "2026-09-20",
        },
        "metrics": metrics,
        "details": details,
    }


def render_markdown(result: Dict[str, Any]) -> str:
    meta, m = result["eval_meta"], result["metrics"]
    lines = [
        f"# RAG 检索对照实验 {meta['version'].upper()} 运行摘要",
        "",
        f"- 配置：{meta['version_desc']}",
        f"- embedding：{meta['embedding_model']}",
        f"- git commit：{meta['git_commit']}",
        f"- 用例集：{pathlib.Path(meta['cases_file']).name}（{meta['cases_split']}，version {meta['cases_version']}）",
        f"- 用例数：{meta['rag_cases_total']}（可答进分母 {meta['answerable_denominator']}，"
        f"域外对抗不进分母 {meta['adversarial_excluded']}）",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| Recall@1 | {m['recall_at_1']} |",
        f"| Recall@3 | {m['recall_at_3']} |",
        f"| Recall@5 | {m['recall_at_5']} |",
        f"| MRR | {m['mrr']} |",
        f"| Top-1 source_id 命中率 | {m['top1_source_accuracy']} |",
        f"| 平均查询延迟 (ms) | {m['avg_query_latency_ms']} |",
        f"| 冷启动 (s) | {m['cold_start_s']} |",
        f"| 模型体积 (MB) | {m['model_size_mb']} |",
        f"| 内存 RSS 增量 (MB) | {m['memory_rss_delta_mb']} |",
        f"| 安全类子集 n={m['safety_subset']['n']} Recall@5 | {m['safety_subset']['recall_at_5']} |",
        f"| 安全类子集 Top-1 | {m['safety_subset']['top1_source_accuracy']} |",
        f"| 域外对抗 Top-1 平均置信度 | {m['adversarial_top1_score_avg']} |",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=list(VERSIONS), default="v4")
    parser.add_argument("--held-out", action="store_true",
                        help="使用 held-out 同义改写集（只在最终版跑一次）")
    parser.add_argument("--cases", default="",
                        help="自定义用例文件（默认 eval_cases.json / eval_cases_heldout.json）")
    parser.add_argument("--download-model", action="store_true",
                        help="只预下载 BGE 权重后退出")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if args.download_model:
        download_bge_model()
        return

    if args.version != "v1":
        download_bge_model()

    if args.cases:
        cases_path = pathlib.Path(args.cases)
    elif args.held_out:
        cases_path = EVAL_DIR / "eval_cases_heldout.json"
    else:
        cases_path = EVAL_DIR / "eval_cases.json"

    result = run_version(args.version, cases_path)

    suffix = f"{args.version}{'_heldout' if args.held_out else ''}_20260920"
    out_json = pathlib.Path(args.out) if args.out else DOCS_DIR / f"rag_retrieval_{suffix}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(render_markdown(result), encoding="utf-8")

    m = result["metrics"]
    print(f"\n===== {args.version.upper()}"
          f"{' (held-out)' if args.held_out else ''} =====")
    print(f"分母: {result['eval_meta']['answerable_denominator']}  "
          f"R@1={m['recall_at_1']} R@3={m['recall_at_3']} R@5={m['recall_at_5']}  "
          f"MRR={m['mrr']} Top1={m['top1_source_accuracy']}")
    print(f"延迟={m['avg_query_latency_ms']}ms 冷启动={m['cold_start_s']}s "
          f"模型={m['model_size_mb']}MB RSS增量={m['memory_rss_delta_mb']}MB")
    print(f"安全类: {m['safety_subset']}  对抗Top1置信: {m['adversarial_top1_score_avg']}")
    print(f"输出: {out_json} / {out_md}")


if __name__ == "__main__":
    main()
