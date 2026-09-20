# Prompts 登记册

本目录是平台所有 LLM Prompt 的**登记册（registry）**，只做登记与版本管理，**不重构代码**——
所有 prompt 当前硬编码在源码中（cucumber-ai / cucumber-agent），此处逐个登记其用途、模型参数、
代码位置与关联评测结果，便于：

1. **变更留痕**：修改任何 prompt 时，同步更新对应 yaml 的 `version` 与 `changelog`；
2. **评测联动**：prompt 变更后重跑关联评测（见每个 yaml 的 `eval_link`），防止回归；
3. **口径统一**：报告润色 prompt 与 12 项校验一一对应（幻觉率 0.22% 的口径基础），逐字改动都会改变口径。

## 登记清单

| 文件 | Prompt | 所在服务 | 代码位置 |
| --- | --- | --- | --- |
| [cucumber-ai-report-polish-system.yaml](cucumber-ai-report-polish-system.yaml) | 受控润色 system 指令 | cucumber-ai | `app/services/prompts.py` |
| [cucumber-ai-report-polish-rules.yaml](cucumber-ai-report-polish-rules.yaml) | 受控润色规则与任务包（RULES + build_task） | cucumber-ai | `app/services/prompts.py` |
| [agent-intent-recognition.yaml](agent-intent-recognition.yaml) | 三路融合意图识别 LLM 路 prompt | cucumber-agent | `echomind/core/intent_recognizer.py` |
| [agent-llm-judge.yaml](agent-llm-judge.yaml) | LLM-as-Judge 六维评分 prompt | cucumber-agent | `echomind/evaluation/evaluator.py` |
| [agent-diagnosis-system.yaml](agent-diagnosis-system.yaml) | 诊断分诊 Agent system prompt | cucumber-agent | `echomind/agents/agent_orchestrator.py` |
| [agent-prevention-system.yaml](agent-prevention-system.yaml) | 防治知识 Agent system prompt | cucumber-agent | `echomind/agents/agent_orchestrator.py` |
| [agent-medication-system.yaml](agent-medication-system.yaml) | 用药安全 Agent system prompt | cucumber-agent | `echomind/agents/agent_orchestrator.py` |
| [agent-escalation-system.yaml](agent-escalation-system.yaml) | 人工升级 Agent system prompt | cucumber-agent | `echomind/agents/agent_orchestrator.py` |
| [agent-response-composer.yaml](agent-response-composer.yaml) | 多 Agent 结果合并 Composer prompt | cucumber-agent | `echomind/agents/agent_orchestrator.py` |
| [tool-query-rewrite.yaml](tool-query-rewrite.yaml) | RAG 查询改写 prompt | cucumber-agent | `echomind/mcp/tool_manager.py` |
| [tool-rerank.yaml](tool-rerank.yaml) | RAG 结果重排 prompt | cucumber-agent | `echomind/mcp/tool_manager.py` |
| [memory-profile-summary.yaml](memory-profile-summary.yaml) | 记忆画像提炼 / 对话摘要 prompts | cucumber-agent | `echomind/memory/conversation_memory.py` |

## 版本约定

- `version` 采用 `v<主>.<次>` + 日期；任何**语义级**改动升主版本并记录 changelog，标点/措辞微调升次版本；
- `eval_link` 指向该 prompt 变更后必须重跑的评测（如意图 prompt → `docs/评测报告_20260920.md` 意图指标）；
- 报告润色两个 prompt 源自论文第六章，**原文逐字保留**，如需修改须同步重测 12 项校验通过率口径。
