# cucumber-agent — 黄瓜病害智能体编排服务

> 基于 EchoMind（https://github.com/Biscuit-AI531/EchoMind）领域二开。
> 母版是客服场景的多 Agent 编排运行时；本服务将其改造为黄瓜病害诊断平台的对话式智能体层：
> 意图识别（这是什么病 / 怎么治 / 药怎么用 / 转人工）→ 四角色 Agent 编排 → 工具调平台 API → 带来源追溯的回答。

## ⚠️ 运行前提

**`/chat`、`/eval/run` 等 LLM 链路必须配置 `ANTHROPIC_API_KEY`，否则服务在启动阶段即退出。**

走 Anthropic 兼容协议，默认对接 DeepSeek：

```bash
# cucumber-agent/.env（已被根 .gitignore 排除，严禁提交）
ANTHROPIC_API_KEY=sk-...            # 必填
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic   # 默认值，可省略
ANTHROPIC_MODEL=deepseek-flash      # 默认值，可省略
```

## 四角色 Agent

| AgentType | 职责 | 领域工具 |
| --- | --- | --- |
| diagnosis | 前台分诊 + 图片诊断引导 + 报告解读 | diagnose_image / query_diagnosis_records / 分诊工具 |
| prevention | 防治知识 RAG 问答（回答必引 source_id） | query_knowledge（共享） |
| medication | 用药建议（安全间隔期 + 禁忌 + 禁限用农药边界） | query_knowledge / check_medication_safety |
| escalation | 人工升级（不调 LLM，结构化交接单 + 创建专家复核反馈） | create_diagnosis_feedback |

## 平台集成

- 工具层 HTTP 调用：`diagnose_image` → cucumber-ai `:8000`（/detect → /diagnose）；
  `query_diagnosis_records` / `create_diagnosis_feedback` → cucumber-admin `:8080`（svc-agent 服务账号，JWT 过期自动重新登录）。
- 知识库：`echomind/data/cucumber_knowledge.json` 28 条黄瓜病害知识种子
  （源自论文第六章 disease_knowledge.json 同构数据，含 source_id/level/disease_type/category 元数据），
  启动时自动导入 ChromaDB。
- `user_id` 透传：cucumber-admin `/api/v1/agent/chat` 把登录用户 ID 作为 user_id 传入，记忆/画像按用户隔离。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| ANTHROPIC_API_KEY | （无，必填） | LLM Key |
| ANTHROPIC_BASE_URL | https://api.deepseek.com/anthropic | Anthropic 兼容端点 |
| ANTHROPIC_MODEL | deepseek-flash | 模型名 |
| REDIS_URL | redis://redis:6379/0 | 工作记忆 |
| CHROMA_HOST / CHROMA_PORT | chromadb / 8000 | 知识库与情景记忆（不可用时自动降级本地模式） |
| CUCUMBER_ADMIN_URL | http://localhost:8080 | 业务后端 |
| CUCUMBER_AI_URL | http://localhost:8000 | AI 服务 |
| AGENT_SERVICE_USERNAME / AGENT_SERVICE_PASSWORD | svc-agent / （无） | admin 服务账号；未配置时记录查询/反馈工具降级 |
| API_PORT | 8002 | 服务端口 |

## 本地运行

```bash
cd cucumber-agent
python -m venv .venv && .venv/Scripts/pip install -r echomind/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 配好 .env 后：
cd echomind && ../.venv/Scripts/python -m uvicorn api.main:app --port 8002
```

接口文档：http://localhost:8002/docs 。无 Redis/ChromaDB 时组件自动降级（内存/本地模式），链路不断。

## 测试

```bash
cd cucumber-agent/echomind
PYTHONUTF8=1 ../.venv/Scripts/python -m pytest tests/ -q   # 13 passed
```

## 安全边界

本服务无鉴权，**严禁直接对公网暴露**；一律经 cucumber-admin `/api/v1/agent/*`（JWT 鉴权 + 审计落库）代理访问。
