"""全量评测入口（2026-09-20 评测集扩充配套脚本）。

三段评测：
  1. 意图识别：eval_cases.json 全部 intent_cases → Accuracy / 每类 P/R/F1 / Macro-F1
  2. 对话质量：dialog_cases 经 AgentOrchestrator 真实生成回复（含 RAG 工具），
     LLM-as-Judge 六维打分（relevance/accuracy/completeness/helpfulness/
     diagnosis_accuracy/medication_safety）
  3. RAG 检索（离线）：rag_cases 直接对嵌入式 Chroma 知识库检索（不含查询改写/重排），
     统计 Recall@5 与 Top-1 source_id 命中率

回归对比：手动加载 docs/eval_run_20260914.json 作为历史基线（只读，不回写），
指标相对退化 >5% 时列入 regressions。

运行（在 cucumber-agent 目录，激活 .venv）：
  PYTHONUTF8=1 python echomind/evaluation/run_full_eval.py
  # 可选：--skip-dialog 只跑意图+RAG；--skip-rag；--out 指定输出路径
"""
import argparse
import asyncio
import json
import logging
import os
import pathlib
import sys
from dataclasses import asdict
from typing import Any, Dict, List

_ROOT = str(pathlib.Path(__file__).parent.parent.resolve())       # echomind/
_AGENT_ROOT = str(pathlib.Path(__file__).parent.parent.parent.resolve())  # cucumber-agent/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
# override=True：评测口径必须来自 cucumber-agent/.env，屏蔽宿主机全局 ANTHROPIC_* 环境变量
load_dotenv(dotenv_path=pathlib.Path(_AGENT_ROOT) / ".env", override=True)

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_full_eval")
logger.setLevel(logging.INFO)

CASES_PATH = pathlib.Path(__file__).parent / "eval_cases.json"
BASELINE_PATH = pathlib.Path(_AGENT_ROOT).parent / "docs" / "eval_run_20260914.json"
DEFAULT_OUT = pathlib.Path(_AGENT_ROOT).parent / "docs" / "eval_run_20260920.json"


def _load_cases() -> Dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _regression_check(current: Dict[str, float], baseline_path: pathlib.Path) -> List[str]:
    """与历史基线对比，退化超过 5% 的指标（与 evaluator._detect_regressions 同口径）。"""
    if not baseline_path.exists():
        return []
    try:
        prev = json.loads(baseline_path.read_text(encoding="utf-8")).get("avg_scores", {})
    except Exception as ex:
        return [f"基线读取失败: {ex}"]
    regressions = []
    for metric, value in current.items():
        if metric in prev and prev[metric] > 0:
            delta = (value - prev[metric]) / prev[metric]
            if delta < -0.05:
                regressions.append(
                    f"{metric}: {prev[metric]:.3f} → {value:.3f} (退化 {abs(delta):.1%})")
    return regressions


async def run_intent_and_dialog(cases: Dict[str, Any], skip_dialog: bool) -> Dict[str, Any]:
    from agents.agent_orchestrator import AgentOrchestrator
    from evaluation.evaluator import EndToEndEvaluator, IntentTestCase
    from mcp.knowledge_base import KnowledgeBase
    from mcp.tool_manager import MCPToolManager, Tool

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("未设置 ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic").strip()
    model = os.getenv("ANTHROPIC_MODEL", "deepseek-chat").strip()

    # 嵌入式 Chroma 知识库（28 条种子），作为 query_knowledge 共享工具接入编排器
    kb = KnowledgeBase(
        chroma_host=os.getenv("CHROMA_HOST", "localhost"),
        chroma_port=int(os.getenv("CHROMA_PORT", "8000") or 8000),
        chroma_path=os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma") or "./data/chroma",
    )
    logger.info("知识库片段数: %d", kb.doc_count)

    tool_manager = MCPToolManager(api_key=api_key, base_url=base_url, model=model)
    tool_manager.register(Tool(
        name="knowledge_search",
        description="搜索黄瓜病害知识库（基于 ChromaDB 向量检索，带 source_id 来源追溯）",
        handler=kb.search_handler,
        schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
            "required": ["query"],
        },
        cache_ttl=300.0,
        supports_rerank=True,
    ))

    orchestrator = AgentOrchestrator(
        api_key=api_key, base_url=base_url, model=model, rag_tool_manager=tool_manager)

    intent_cases = [
        IntentTestCase(message=c["message"], expected_intent=c["expected_intent"])
        for c in cases["intent_cases"]
    ]
    dialog_cases = None if skip_dialog else [
        {k: v for k, v in c.items() if k in ("question", "turns", "user_id", "conv_id")}
        for c in cases["dialog_cases"]
    ]

    # baseline_path 不传，避免回写覆盖历史记录；回归对比在本脚本手动完成
    evaluator = EndToEndEvaluator(
        orchestrator=orchestrator,
        recognizer=orchestrator._intent_recognizer,
        api_key=api_key, base_url=base_url, model=model,
        baseline_path=None,
    )
    report = await evaluator.run(intent_cases=intent_cases, dialog_cases=dialog_cases)
    return asdict(report)


def run_rag_recall(cases: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    """离线 RAG 检索评测：直接用 KnowledgeBase.search（不含查询改写/LLM 重排）。"""
    from mcp.knowledge_base import KnowledgeBase

    kb = KnowledgeBase(
        chroma_host=os.getenv("CHROMA_HOST", "localhost"),
        chroma_port=int(os.getenv("CHROMA_PORT", "8000") or 8000),
        chroma_path=os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma") or "./data/chroma",
    )
    details: List[Dict[str, Any]] = []
    answerable_hit5 = answerable_top1 = answerable_n = 0
    for c in cases["rag_cases"]:
        results = kb.search(c["query"], top_k=top_k)
        got_ids = [r.get("source_id", "") for r in results]
        expected = c.get("expected_source_ids", [])
        hit5 = bool(set(got_ids) & set(expected)) if expected else None
        top1 = got_ids[0] if got_ids else ""
        top1_hit = (top1 in expected) if expected else None
        if expected:
            answerable_n += 1
            answerable_hit5 += int(bool(hit5))
            answerable_top1 += int(bool(top1_hit))
        details.append({
            "query": c["query"],
            "tag": c.get("tag", ""),
            "expected_source_ids": expected,
            "top_k_source_ids": got_ids,
            "top1_score": results[0]["score"] if results else None,
            "recall_hit": hit5,
            "top1_hit": top1_hit,
        })
    return {
        "top_k": top_k,
        "doc_count": kb.doc_count,
        "answerable_total": answerable_n,
        "recall_at_5": round(answerable_hit5 / answerable_n, 4) if answerable_n else None,
        "top1_source_accuracy": round(answerable_top1 / answerable_n, 4) if answerable_n else None,
        "adversarial": [d for d in details if not d["expected_source_ids"]],
        "details": details,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dialog", action="store_true")
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--skip-intent", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    cases = _load_cases()
    output: Dict[str, Any] = {
        "eval_meta": {
            "cases_file": str(CASES_PATH),
            "cases_version": cases["meta"]["version"],
            "intent_cases": len(cases["intent_cases"]),
            "dialog_cases": 0 if args.skip_dialog else len(cases["dialog_cases"]),
            "rag_cases": 0 if args.skip_rag else len(cases["rag_cases"]),
            "model": os.getenv("ANTHROPIC_MODEL", "deepseek-chat"),
            "base_url": os.getenv("ANTHROPIC_BASE_URL", ""),
            "baseline": str(BASELINE_PATH),
        }
    }

    if not args.skip_intent:
        logger.info("=== 意图识别 + 对话质量评测开始 ===")
        report = await run_intent_and_dialog(cases, skip_dialog=args.skip_dialog)
        output["agent_eval"] = report
        output["agent_eval"]["regressions_vs_20260914"] = _regression_check(
            report.get("avg_scores", {}), BASELINE_PATH)
        intent_result = next((r for r in report["results"] if r["test_id"] == "intent_recognition"), None)
        if intent_result:
            logger.info("意图识别: %s", intent_result["detail"])
        logger.info("对话质量 avg_scores: %s", report.get("avg_scores"))

    if not args.skip_rag:
        logger.info("=== RAG Recall@5 离线评测开始 ===")
        rag = await asyncio.to_thread(run_rag_recall, cases)
        output["rag_eval"] = rag
        logger.info("RAG Recall@%d: %s  Top-1 命中: %s",
                    rag["top_k"], rag["recall_at_5"], rag["top1_source_accuracy"])

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("结果已写入: %s", out_path)

    # 控制台摘要（供报告引用）
    print("\n========== 评测摘要 ==========")
    print(json.dumps(output.get("eval_meta", {}), ensure_ascii=False, indent=2))
    if "agent_eval" in output:
        ae = output["agent_eval"]
        print("avg_scores:", json.dumps(ae.get("avg_scores", {}), ensure_ascii=False))
        print("pass_rate:", ae.get("pass_rate"), " total:", ae.get("total"), " passed:", ae.get("passed"))
        ir = next((r for r in ae["results"] if r["test_id"] == "intent_recognition"), None)
        if ir:
            print("intent:", ir["detail"])
        print("regressions_vs_20260914:", ae.get("regressions_vs_20260914"))
        print("recommendations:", json.dumps(ae.get("recommendations", []), ensure_ascii=False))
    if "rag_eval" in output:
        rag = output["rag_eval"]
        print(f"RAG: doc_count={rag['doc_count']} answerable={rag['answerable_total']} "
              f"Recall@{rag['top_k']}={rag['recall_at_5']} top1_acc={rag['top1_source_accuracy']}")


if __name__ == "__main__":
    asyncio.run(main())
