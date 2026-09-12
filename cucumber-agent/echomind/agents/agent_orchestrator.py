"""
亮点：多 Agent 路由与编排（黄瓜病害智能诊断平台领域版）

核心问题：多 Agent 情况下如何做 Routing？

路由策略（三层决策）：
  1. 意图路由 —— 根据 IntentCategory 直接映射到专属 Agent
  2. 性能路由 —— 同类 Agent 有多个时，选成功率最高、延迟最低的
  3. 降级路由 —— 专属 Agent 不可用时，自动降级到 DiagnosisAgent（前台分诊）

并行协作：
  - 复杂问题（如"诊断病害 + 用药建议"）可同时派发给多个 Agent
  - 结果由 Orchestrator 合并后返回

升级机制：
  - Agent 置信度低于阈值或命中灾情紧急词 → 自动升级到人工（专家复核）
"""
import asyncio
import inspect
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from anthropic import AsyncAnthropic

from agents.tools import (
    AgentToolSpec,
    build_shared_rag_tools,
    diagnosis_tools,
    escalation_tools,
    medication_tools,
    triage_tools,
)
from core.intent_recognizer import IntentCategory, IntentRecognizer, UrgencyLevel
from core.llm_utils import extract_text_content

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class AgentType(Enum):
    DIAGNOSIS  = "diagnosis"   # 病害诊断（前台分诊 + 图片诊断引导与报告解读）
    PREVENTION = "prevention"  # 防治知识问答（RAG，引用 source_id）
    MEDICATION = "medication"  # 用药建议（安全间隔期 + 禁忌 + 禁限用边界）
    ESCALATION = "escalation"  # 人工升级与专家复核交接


@dataclass(frozen=True)
class AgentProfile:

    role: str
    mission: str
    workflow: Tuple[str, ...]
    input_contract: Tuple[str, ...]
    output_contract: Tuple[str, ...]
    handoff_conditions: Tuple[str, ...] = ()
    tool_scope: Tuple[str, ...] = ()
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 1024


def _env_float(name: str, default: float) -> float:
    """读取可选浮点配置；错误配置不应阻塞服务启动。"""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("忽略非法浮点配置 %s=%r", name, os.getenv(name))
        return default


def _env_int(name: str, default: int) -> int:
    """读取可选整数配置；错误配置不应阻塞服务启动。"""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("忽略非法整数配置 %s=%r", name, os.getenv(name))
        return default


@dataclass
class AgentStats:
    """Agent 运行时统计，供 Monitor 和路由决策使用。"""
    total:     int   = 0
    success:   int   = 0
    total_ms:  float = 0.0
    monitor_penalty: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success / self.total if self.total else 1.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.total if self.total else 0.0

    def routing_score(self) -> float:
        """路由评分：成功率高、延迟低的 Agent 得分高。"""
        latency_score = 1.0 / (1.0 + self.avg_ms / 1000)
        base_score = self.success_rate * 0.7 + latency_score * 0.3
        return base_score * max(0.0, 1.0 - self.monitor_penalty)


@dataclass
class AgentResponse:
    agent_type:  AgentType
    content:     str
    success:     bool
    confidence:  float = 1.0
    latency_ms:  float = 0.0
    escalate:    bool  = False   # 是否需要升级
    tools_used:  List[str] = field(default_factory=list)
    tool_traces: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Request:
    message:     str
    user_id:     str
    conv_id:     str
    context:     str = ""        # 来自 MemoryManager 的格式化上下文
    history:     Optional[List[Dict[str, str]]] = None  # 对话历史，传给意图识别
    entities:    Dict[str, List[str]] = field(default_factory=dict)
    intent:      Optional[IntentCategory] = None
    intent_group: Optional[str] = None
    urgency:     Optional[UrgencyLevel]   = None
    intent_confidence: float = 1.0
    image_url:   Optional[str] = None   # 用户随消息上传的叶片图片地址
    record_id:   Optional[int] = None   # 用户正在讨论的诊断记录 ID
    request_id:  str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class OrchestratorResult:
    request_id:  str
    response:    str
    agent_type:  AgentType
    intent:      Optional[IntentCategory]
    escalated:   bool  = False
    latency_ms:  float = 0.0
    agent_types: List[AgentType] = field(default_factory=list)
    primary_agent: Optional[AgentType] = None
    supporting_agents: List[AgentType] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    tool_traces: List[Dict[str, Any]] = field(default_factory=list)
    routing_reason: str = ""
    routing_confidence: float = 0.0


@dataclass
class RoutingDecision:
    """一次请求的结构化路由决策。"""
    primary_agent: AgentType
    supporting_agents: List[AgentType] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0

    @property
    def agent_types(self) -> List[AgentType]:
        return [self.primary_agent] + self.supporting_agents

    @property
    def multi_agent(self) -> bool:
        return bool(self.supporting_agents)


# ── 基础 Agent ────────────────────────────────────────────────────────────────

class BaseAgent:
    """所有 Agent 的基类，封装 LLM 调用、角色契约和统计。"""

    agent_type: AgentType
    system_prompt: str
    profile: AgentProfile

    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        skill_manager: Optional[Any] = None,
        profile: Optional[AgentProfile] = None,
    ):
        self._client = client
        self.profile = profile or self.profile
        self._model  = self.profile.model or model
        self._skill_manager = skill_manager
        self.stats   = AgentStats()
        self._last_tools_used: List[str] = []
        self._last_tool_traces: List[Dict[str, Any]] = []
        self._shared_tools: Dict[str, AgentToolSpec] = {}
        self._domain_tools: Dict[str, AgentToolSpec] = {}

    def get_tools(self) -> Dict[str, AgentToolSpec]:
        """返回该角色真实可调用的工具白名单（共享 RAG + 角色领域工具）。"""
        tools = dict(self._shared_tools)
        tools.update(self._domain_tools)
        return tools

    def set_shared_tools(self, tools: Optional[Dict[str, AgentToolSpec]]) -> None:
        self._shared_tools = dict(tools or {})

    def set_domain_tools(self, tools: Optional[Dict[str, AgentToolSpec]]) -> None:
        self._domain_tools = dict(tools or {})

    async def handle(self, req: Request) -> AgentResponse:
        t0 = time.monotonic()
        self.stats.total += 1
        self._last_tools_used = []
        self._last_tool_traces = []
        try:
            content = await self._call_llm(req)
            ms = (time.monotonic() - t0) * 1000
            self.stats.success += 1
            self.stats.total_ms += ms
            escalate = self._needs_escalation(content)
            return AgentResponse(
                agent_type=self.agent_type,
                content=content,
                success=True,
                latency_ms=ms,
                escalate=escalate,
                tools_used=list(self._last_tools_used),
                tool_traces=list(self._last_tool_traces),
            )
        except Exception as ex:
            ms = (time.monotonic() - t0) * 1000
            self.stats.total_ms += ms
            logger.error(f"{self.agent_type.value} 处理失败: {ex}")
            return AgentResponse(
                agent_type=self.agent_type,
                content="抱歉，处理您的请求时出现问题，请稍后重试；如病情紧急可直接申请转人工专家。",
                success=False,
                latency_ms=ms,
                tool_traces=list(self._last_tool_traces),
            )

    async def _call_llm(self, req: Request) -> str:
        def _clean(s: str) -> str:
            return s.encode("utf-8", errors="ignore").decode("utf-8")

        messages = []
        if req.context:
            messages.append({"role": "user", "content": f"[背景信息]\n{_clean(req.context)}"})
            messages.append({"role": "assistant", "content": "好的，我已了解背景信息。"})
        if req.entities:
            entities_text = json.dumps(req.entities, ensure_ascii=False)
            messages.append({"role": "user", "content": f"[结构化实体]\n{_clean(entities_text)}"})
            messages.append({"role": "assistant", "content": "好的，我会结合这些结构化实体处理。"})
        role_packet = self._build_role_packet(req)
        if role_packet:
            messages.append({"role": "user", "content": f"[角色输入契约]\n{_clean(role_packet)}"})
            messages.append({"role": "assistant", "content": "好的，我会按照该角色的输入和输出契约处理。"})
        messages.append({"role": "user", "content": _clean(req.message)})

        tools = self.get_tools()
        tools_used: List[str] = []
        tool_traces: List[Dict[str, Any]] = []
        for _ in range(3):
            request_kwargs: Dict[str, Any] = {
                "model": self._model,
                "max_tokens": self.profile.max_tokens,
                "temperature": self.profile.temperature,
                "system": self._build_system_prompt(req),
                "messages": messages,
            }
            if tools:
                request_kwargs["tools"] = [
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "input_schema": spec.input_schema,
                    }
                    for spec in tools.values()
                ]
            resp = await self._client.messages.create(**request_kwargs)
            tool_uses = [block for block in (resp.content or []) if self._block_type(block) == "tool_use"]
            if not tool_uses:
                self._last_tools_used = tools_used
                return extract_text_content(resp.content)

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in tool_uses:
                name = self._block_value(block, "name")
                tool_use_id = self._block_value(block, "id")
                args = self._block_value(block, "input") or {}
                spec = tools.get(name)
                tool_t0 = time.monotonic()
                call_success = True
                result_success: Optional[bool] = None
                error_text = ""
                if spec is None:
                    call_success = False
                    result: Any = {"success": False, "error": f"工具不在 {self.agent_type.value} Agent 白名单中"}
                    error_text = result["error"]
                else:
                    try:
                        self._validate_tool_input(spec, args)
                        result = spec.handler(req, args)
                        if inspect.isawaitable(result):
                            result = await result
                        tools_used.append(name)
                        if isinstance(result, dict) and "success" in result:
                            result_success = bool(result.get("success"))
                    except Exception as ex:
                        call_success = False
                        logger.warning("Agent 工具 %s 执行失败: %s", name, ex)
                        error_text = str(ex)
                        result = {"success": False, "error": error_text}
                tool_latency_ms = (time.monotonic() - tool_t0) * 1000
                if not error_text and isinstance(result, dict):
                    error_text = str(result.get("error", "") or "")
                tool_traces.append(
                    {
                        "agent_type": self.agent_type.value,
                        "tool_name": name,
                        "tool_use_id": tool_use_id,
                        "input": dict(args),
                        "success": call_success,
                        "result_success": result_success,
                        "latency_ms": round(tool_latency_ms, 1),
                        "cached": bool(result.get("cached")) if isinstance(result, dict) else False,
                        "reranked": bool(result.get("reranked")) if isinstance(result, dict) else False,
                        "error": error_text,
                    }
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": tool_results})

        self._last_tools_used = tools_used
        self._last_tool_traces = tool_traces
        raise RuntimeError(f"{self.agent_type.value} 工具调用超过最大轮数")

    @staticmethod
    def _block_type(block: Any) -> Optional[str]:
        if isinstance(block, dict):
            return block.get("type")
        return getattr(block, "type", None)

    @staticmethod
    def _block_value(block: Any, key: str) -> Any:
        if isinstance(block, dict):
            return block.get(key)
        return getattr(block, key, None)

    @staticmethod
    def _validate_tool_input(spec: AgentToolSpec, args: Any) -> None:
        if not isinstance(args, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        schema = spec.input_schema
        for field_name in schema.get("required", []):
            if field_name not in args:
                raise ValueError(f"缺少必需参数: {field_name}")
        properties = schema.get("properties", {})
        unknown = set(args) - set(properties)
        if unknown and schema.get("additionalProperties") is False:
            raise ValueError(f"不允许的工具参数: {', '.join(sorted(unknown))}")
        type_map = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list}
        for key, value in args.items():
            expected = properties.get(key, {}).get("type")
            if expected in type_map and not isinstance(value, type_map[expected]):
                raise ValueError(f"参数 {key} 类型错误，期望 {expected}")

    def _build_system_prompt(self, req: Request) -> str:
        """把角色契约和动态 Skills 拼入 system prompt。"""
        profile_prompt = (
            f"\n\n[角色契约]\n"
            f"角色：{self.profile.role}\n"
            f"职责：{self.profile.mission}\n"
            f"处理流程：{' -> '.join(self.profile.workflow)}\n"
            f"可用输入：{'；'.join(self.profile.input_contract)}\n"
            f"输出要求：{'；'.join(self.profile.output_contract)}\n"
            f"升级条件：{'；'.join(self.profile.handoff_conditions) or '无，按平台通用规则处理'}\n"
            f"允许的数据/工具范围：{'、'.join(self.profile.tool_scope) or '仅使用当前请求上下文'}\n"
            "不要声称执行了未提供的诊断、查询或反馈创建操作；缺少证据时明确说明需要核验。"
        )
        base_prompt = f"{self.system_prompt}{profile_prompt}"
        if self._skill_manager is None:
            return base_prompt
        skill_prompt = self._skill_manager.prompt_for(req.message, self.agent_type.value)
        if not skill_prompt:
            return base_prompt
        return f"{base_prompt}\n\n[动态 Skills]\n{skill_prompt}"

    def _build_role_packet(self, req: Request) -> str:
        """给子 Agent 的确定性输入包；子类可补充领域字段。"""
        packet = {
            "agent_type": self.agent_type.value,
            "intent": req.intent.value if req.intent else None,
            "intent_group": req.intent_group,
            "urgency": req.urgency.name if req.urgency else None,
            "intent_confidence": round(req.intent_confidence, 4),
            "available_entities": req.entities or {},
            "image_url": req.image_url,
            "record_id": req.record_id,
        }
        return json.dumps(packet, ensure_ascii=False)

    def _needs_escalation(self, content: str) -> bool:
        """检测 Agent 是否建议升级（简单关键词检测）。"""
        keywords = ["转人工", "人工专家", "专家复核", "escalate", "specialist", "无法处理"]
        return any(kw in content for kw in keywords)


class DiagnosisAgent(BaseAgent):
    """病害诊断 Agent：平台前台分诊 + 图片诊断引导与报告解读。"""

    agent_type    = AgentType.DIAGNOSIS
    profile = AgentProfile(
        role="黄瓜病害诊断分诊与报告解读",
        mission="接待种植户咨询，引导上传叶片照片，调用诊断工具获取检测与受控报告，并用通俗语言解读诊断结论。",
        workflow=("确认症状或图片", "引导补充必要信息（部位/天数/照片）", "调用诊断工具", "解读报告与来源", "给出下一步建议"),
        input_contract=("症状描述", "叶片图片地址", "诊断记录 ID", "结构化实体（病害/部位/天数）", "对话历史", "知识库上下文"),
        output_contract=("先回应核心问题", "信息不足时只询问必要字段", "解读报告时保留 source_id 来源编号", "明确下一步与能力边界"),
        handoff_conditions=("用户明确要求人工或专家复核", "灾情紧急（绝收/大面积蔓延）", "诊断结果置信度低或用户质疑诊断"),
        tool_scope=("query_knowledge", "diagnose_image", "query_diagnosis_records", "inspect_request_context", "suggest_required_fields"),
        temperature=0.3,
        max_tokens=1600,
    )
    system_prompt = (
        "你是黄瓜病害智能诊断平台的诊断助手。友好、简洁地回答种植户问题。"
        "用户描述症状时，优先引导其上传清晰的叶片照片以获得准确诊断；"
        "拿到诊断报告后，用通俗语言解读结论、依据和防治要点，并保留来源编号。"
        "如果问题超出诊断范围（纯防治知识或用药细节），明确说明并建议由对应专业服务接续。"
    )

    def _build_role_packet(self, req: Request) -> str:
        packet = json.loads(super()._build_role_packet(req))
        packet["triage_targets"] = ["prevention", "medication", "escalation"]
        packet["response_mode"] = "answer_or_clarify"
        packet["image_available"] = bool(req.image_url)
        packet["diagnosis_fields"] = {
            "disease_hints": req.entities.get("disease", []),
            "plant_part": req.entities.get("plant_part", []),
            "onset_days": req.entities.get("onset_days", []),
            "missing_hint": "无图片时应引导用户上传叶片正面清晰照片",
        }
        return json.dumps(packet, ensure_ascii=False)


class PreventionAgent(BaseAgent):
    """防治知识 Agent：RAG 知识库问答，回答必须引用 source_id。"""

    agent_type    = AgentType.PREVENTION
    profile = AgentProfile(
        role="黄瓜病害防治知识问答",
        mission="基于平台知识库回答病害预防、发病条件、农业/生物/化学防治方法，所有结论必须可追溯。",
        workflow=("明确病害与问题", "检索知识库", "组织带来源的回答", "提示知识边界"),
        input_contract=("病害名称", "症状或栽培场景描述", "知识库检索结果（带 source_id）"),
        output_contract=("回答中引用的每条知识标注 [source_id]", "知识库未覆盖的内容明确说明", "不编造未检索到的防治方法"),
        handoff_conditions=("用户质疑知识准确性要求人工确认", "涉及具体田块灾情处置决策"),
        tool_scope=("query_knowledge",),
        temperature=0.1,
        max_tokens=1600,
    )
    system_prompt = (
        "你是黄瓜病害防治知识专家。回答必须基于知识库检索结果，"
        "每条引用都要标注来源编号（如 [KB-DM-001]）；检索不到的内容明确告知用户，不要凭印象编造。"
        "涉及具体用药剂量时，引导用户确认药剂标签或转用药建议。"
    )

    def _build_role_packet(self, req: Request) -> str:
        packet = json.loads(super()._build_role_packet(req))
        packet["citation_rule"] = "回答中引用的每条知识必须标注其 source_id"
        packet["disease_hints"] = req.entities.get("disease", [])
        return json.dumps(packet, ensure_ascii=False)


class MedicationAgent(BaseAgent):
    """用药建议 Agent：药剂查询 + 安全间隔期 + 禁忌 + 禁限用农药合规边界。"""

    agent_type    = AgentType.MEDICATION
    profile = AgentProfile(
        role="黄瓜病害用药安全建议",
        mission="围绕已确诊病害给出合规的用药方向建议，强制核对安全间隔期与禁限用边界，不出具处方。",
        workflow=("确认病害与药剂", "合规检查（禁限用/采收期）", "给出药剂类别与轮换建议", "强调标签与植保部门边界"),
        input_contract=("病害名称", "拟用药剂", "距采收天数", "知识库检索结果（带 source_id）", "用药安全检查结果"),
        output_contract=("先给合规结论", "安全间隔期与轮换用药提醒", "禁限用农药明确拒绝", "具体剂量以标签为准的声明"),
        handoff_conditions=("用户坚持使用禁限用农药", "病害未确诊就要求开药", "灾情需要植保部门现场处置"),
        tool_scope=("query_knowledge", "check_medication_safety"),
        temperature=0.0,
        max_tokens=1600,
    )
    system_prompt = (
        "你是农药安全使用顾问。只推荐在黄瓜上有登记的杀菌剂类别，"
        "必须提醒安全间隔期和轮换用药；对禁限用农药（如甲胺磷、氧乐果等）明确拒绝并说明法规边界。"
        "具体药剂品种、剂型、剂量以农药登记标签和当地植保部门指导为准，你不替代处方。"
    )

    def _build_role_packet(self, req: Request) -> str:
        packet = json.loads(super()._build_role_packet(req))
        packet["medication_fields"] = {
            "disease_hints": req.entities.get("disease", []),
            "pesticide_hints": req.entities.get("pesticide", []),
            "compliance_boundary": "禁限用农药一律拒绝；具体剂量以登记标签为准",
        }
        return json.dumps(packet, ensure_ascii=False)


class EscalationAgent(BaseAgent):
    """人工升级节点（专家复核交接）。

    升级不是一个普通问答 Prompt：它生成标准化的交接信息并停止普通
    Agent 继续编造答案。当请求关联了诊断记录（record_id）时，确定性地
    调用 create_diagnosis_feedback 创建专家复核反馈（不经 LLM）。
    """

    agent_type = AgentType.ESCALATION
    profile = AgentProfile(
        role="人工升级与专家复核交接",
        mission="确认升级原因，整理已知上下文，关联诊断记录创建专家复核反馈，告知用户下一步。",
        workflow=("确认升级原因", "整理已知信息", "关联诊断记录创建复核反馈", "生成交接摘要"),
        input_contract=("用户消息", "意图", "紧急度", "结构化实体", "诊断记录 ID", "对话背景"),
        output_contract=("升级原因", "已知信息摘要", "复核反馈创建结果", "保守的后续说明"),
        handoff_conditions=("用户明确要求人工或专家复核", "灾情紧急或诊断存疑"),
        tool_scope=("create_diagnosis_feedback",),
        temperature=0.0,
        max_tokens=500,
    )
    system_prompt = "你负责黄瓜诊断平台的人工升级交接，不要继续模拟已完成的诊断或复核操作。"

    async def handle(self, req: Request) -> AgentResponse:
        t0 = time.monotonic()
        self.stats.total += 1
        intent = req.intent.value if req.intent else "unknown"
        urgency = req.urgency.name if req.urgency else "UNKNOWN"
        entities = json.dumps(req.entities or {}, ensure_ascii=False)
        tools_used: List[str] = []
        tool_traces: List[Dict[str, Any]] = []

        feedback_note = "本次升级未关联诊断记录，专家将依据会话记录复核。"
        if req.record_id:
            spec = self.get_tools().get("create_diagnosis_feedback")
            if spec is not None:
                args = {
                    "record_id": req.record_id,
                    "comment": f"[人工升级交接] 意图={intent} 紧急度={urgency}；用户补充：{req.message[:200]}",
                }
                tool_t0 = time.monotonic()
                try:
                    result = spec.handler(req, args)
                    if inspect.isawaitable(result):
                        result = await result
                    tools_used.append("create_diagnosis_feedback")
                    ok = bool(result.get("success"))
                    feedback_note = (
                        f"已针对诊断记录 #{req.record_id} 创建专家复核反馈（状态：待复核）。"
                        if ok else
                        f"复核反馈创建失败（{result.get('error', '未知原因')}），已保留交接摘要，专家可从反馈列表跟进。"
                    )
                    tool_traces.append({
                        "agent_type": self.agent_type.value,
                        "tool_name": "create_diagnosis_feedback",
                        "input": args,
                        "success": ok,
                        "latency_ms": round((time.monotonic() - tool_t0) * 1000, 1),
                        "error": str(result.get("error", "") or ""),
                    })
                except Exception as ex:
                    logger.warning("升级交接创建反馈失败: %s", ex)
                    feedback_note = "复核反馈创建异常，已保留交接摘要，专家可从反馈列表跟进。"
                    tool_traces.append({
                        "agent_type": self.agent_type.value,
                        "tool_name": "create_diagnosis_feedback",
                        "input": args,
                        "success": False,
                        "latency_ms": round((time.monotonic() - tool_t0) * 1000, 1),
                        "error": str(ex),
                    })

        content = (
            "我已将这个问题升级为人工专家复核处理。\n\n"
            f"升级原因：意图={intent}，紧急度={urgency}\n"
            f"已记录信息：{entities}\n"
            f"{feedback_note}\n"
            "请保留病叶照片和田间发生情况记录；农技专家复核后会通过诊断反馈给出结论。"
        )
        ms = (time.monotonic() - t0) * 1000
        self.stats.success += 1
        self.stats.total_ms += ms
        return AgentResponse(
            agent_type=self.agent_type,
            content=content,
            success=True,
            latency_ms=ms,
            escalate=True,
            tools_used=tools_used,
            tool_traces=tool_traces,
        )


class ResponseComposer:
    """多 Agent 汇总节点，统一主次、去重和输出边界。"""

    def __init__(self, client: AsyncAnthropic, model: str, skill_manager: Optional[Any] = None):
        self._client = client
        self._model = model
        self._skill_manager = skill_manager

    async def compose(self, req: Request, responses: List[AgentResponse]) -> str:
        successful = [response for response in responses if response.success and response.content.strip()]
        if not successful:
            return "抱歉，所有 Agent 均处理失败。"
        if len(successful) == 1:
            return successful[0].content

        evidence = "\n\n".join(
            f"[{response.agent_type.value} Agent 输出]\n{response.content}"
            for response in successful
        )
        prompt = (
            "你是黄瓜病害智能诊断平台的 Response Composer，负责把多个专业 Agent 的结果合并成一条最终回复。\n"
            "要求：以主 Agent 的结论为主，按用户问题优先级组织内容；去掉重复和冲突表述；"
            "不能补造诊断结果、药剂剂量、后台查询结果；保留知识来源编号（source_id）与用药安全提示；"
            "如果结论冲突，明确说明需要核验。只输出给用户看的中文回复，不要提及 Agent。\n\n"
            f"主 Agent：{successful[0].agent_type.value}\n"
            f"用户问题：{req.message}\n"
            f"候选结果：\n{evidence}"
        )
        if self._skill_manager is not None:
            skill = self._skill_manager.prompt_for(req.message, "diagnosis")
            if skill:
                prompt += f"\n\n[平台输出边界]\n{skill}"
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=_env_int("ECHOMIND_COMPOSER_MAX_TOKENS", 1600),
                temperature=_env_float("ECHOMIND_COMPOSER_TEMPERATURE", 0.1),
                messages=[{"role": "user", "content": prompt}],
            )
            content = extract_text_content(response.content).strip()
            if content:
                return content
        except Exception as ex:
            logger.warning("Response Composer 失败，使用确定性合并: %s", ex)

        # 汇总节点不可用时保留主次标签，避免丢失某个专业 Agent 的结论。
        return "\n\n".join(
            f"{response.content}" if index == 0 else f"补充说明：\n{response.content}"
            for index, response in enumerate(successful)
        )


# ── 编排器 ────────────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    多 Agent 编排器。

    路由逻辑（三层）：
      1. 意图 → Agent 类型映射
      2. 同类多实例时按 routing_score() 选最优
      3. 专属 Agent 失败时降级到 DiagnosisAgent
    """

    # 意图 → Agent 类型的静态映射（路由表）
    _INTENT_ROUTING: Dict[IntentCategory, AgentType] = {
        IntentCategory.DISEASE_DIAGNOSIS: AgentType.DIAGNOSIS,
        IntentCategory.PREVENTION_QA:     AgentType.PREVENTION,
        IntentCategory.MEDICATION_ADVICE: AgentType.MEDICATION,
        IntentCategory.HUMAN_HANDOFF:     AgentType.ESCALATION,
        # greeting / other → DIAGNOSIS（前台分诊，默认）
    }

    def __init__(
        self,
        api_key:  str,
        base_url: Optional[str] = None,
        model:    str = "claude-3-5-sonnet-20241022",
        skill_manager: Optional[Any] = None,
        rag_tool_manager: Optional[Any] = None,
    ):
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncAnthropic(**kwargs)

        self._intent_recognizer = IntentRecognizer(api_key=api_key, base_url=base_url, model=model)
        self._skill_manager = skill_manager
        self._composer = ResponseComposer(client, model, skill_manager)
        self._shared_tools: Dict[str, AgentToolSpec] = {}
        self._recent_tool_traces = deque(maxlen=_env_int("ECHOMIND_TOOL_TRACE_MAX", 200))

        # Agent 池：每种类型可有多个实例（水平扩展）
        self._pool: Dict[AgentType, List[BaseAgent]] = {
            AgentType.DIAGNOSIS: [self._make_agent(DiagnosisAgent, client, model, skill_manager)],
            AgentType.PREVENTION: [self._make_agent(PreventionAgent, client, model, skill_manager)],
            AgentType.MEDICATION: [self._make_agent(MedicationAgent, client, model, skill_manager)],
            AgentType.ESCALATION: [self._make_agent(EscalationAgent, client, model, skill_manager)],
        }
        self.set_shared_tools(build_shared_rag_tools(rag_tool_manager))
        self.set_domain_tools(rag_tool_manager)

    @staticmethod
    def _make_agent(
        agent_cls: type[BaseAgent],
        client: AsyncAnthropic,
        default_model: str,
        skill_manager: Optional[Any],
    ) -> BaseAgent:
        """按角色创建 Agent，并允许用环境变量覆盖该角色的模型。

        可使用更强模型，前台分诊可使用更快模型，升级节点本身不需要调用 LLM。
        """
        profile = agent_cls.profile
        env_name = f"ECHOMIND_{agent_cls.agent_type.value.upper()}_MODEL"
        model = os.getenv(env_name, "").strip() or profile.model
        configured_profile = replace(profile, model=model) if model else profile
        return agent_cls(client, default_model, skill_manager, profile=configured_profile)

    def set_skill_manager(self, skill_manager: Optional[Any]) -> None:
        """更新 SkillManager 引用，供运行时重载或测试替换使用。"""
        self._skill_manager = skill_manager
        self._composer._skill_manager = skill_manager
        for agents in self._pool.values():
            for agent in agents:
                agent._skill_manager = skill_manager

    def set_shared_tools(self, tools: Optional[Dict[str, AgentToolSpec]]) -> None:
        """更新所有 Agent 共享的工具白名单。"""
        self._shared_tools = dict(tools or {})
        for agents in self._pool.values():
            for agent in agents:
                agent.set_shared_tools(self._shared_tools)

    def set_domain_tools(self, tool_manager: Optional[Any]) -> None:
        """按角色分配领域工具白名单（经由 MCPToolManager 治理的平台 API 工具）。"""
        per_role: Dict[AgentType, Dict[str, AgentToolSpec]] = {
            AgentType.DIAGNOSIS: {**triage_tools(), **diagnosis_tools(tool_manager)},
            AgentType.PREVENTION: {},
            AgentType.MEDICATION: medication_tools(),
            AgentType.ESCALATION: escalation_tools(tool_manager),
        }
        for agent_type, tools in per_role.items():
            for agent in self._pool.get(agent_type, []):
                agent.set_domain_tools(tools)

    async def recognize_intent(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ):
        """对外暴露意图识别，供 API 层先判断是否需要 RAG 等前置能力。"""
        return await self._intent_recognizer.recognize(message, history=history)

    def _record_tool_trace(self, result: OrchestratorResult) -> None:
        trace = {
            "request_id": result.request_id,
            "timestamp": datetime.now().isoformat(),
            "intent": result.intent.value if result.intent else None,
            "primary_agent": result.primary_agent.value if result.primary_agent else None,
            "supporting_agents": [agent.value for agent in result.supporting_agents],
            "tools_used": list(result.tools_used),
            "tool_calls": list(result.tool_traces),
            "escalated": result.escalated,
            "latency_ms": round(result.latency_ms, 1),
        }
        self._recent_tool_traces.append(trace)

    def get_tool_trace(self, request_id: str) -> Optional[Dict[str, Any]]:
        for trace in reversed(self._recent_tool_traces):
            if trace.get("request_id") == request_id:
                return trace
        return None

    def get_recent_tool_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self._recent_tool_traces:
            return []
        limit = max(1, min(int(limit or 20), len(self._recent_tool_traces)))
        return list(reversed(list(self._recent_tool_traces)[-limit:]))

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def run(self, req: Request) -> OrchestratorResult:
        """
        处理一次请求的完整流程：
          意图识别 → 路由选 Agent → 执行 → 检查升级 → 返回结果
        """
        t0 = time.monotonic()

        # 1. 意图识别（如果调用方已识别则跳过）
        if req.intent is None:
            intent_result = await self._intent_recognizer.recognize(req.message, history=req.history)
            req.intent  = intent_result.intent
            req.intent_group = intent_result.intent_group
            req.urgency = intent_result.urgency
            req.intent_confidence = intent_result.confidence

        if self._needs_clarification(req):
            result = OrchestratorResult(
                request_id=req.request_id,
                response=(
                    "我还不能确定您想解决的是哪类问题。请补充一下："
                    "是要诊断叶片病害（可以直接上传叶片照片）、咨询病害防治方法、"
                    "了解用药安全（药剂/剂量/安全间隔期），还是需要转人工专家复核？"
                ),
                agent_type=AgentType.DIAGNOSIS,
                intent=req.intent,
                escalated=False,
                latency_ms=(time.monotonic() - t0) * 1000,
                agent_types=[AgentType.DIAGNOSIS],
                primary_agent=AgentType.DIAGNOSIS,
                routing_reason="低置信度 OTHER 意图，先澄清用户需求",
                routing_confidence=req.intent_confidence,
            )
            self._record_tool_trace(result)
            return result

        # 复杂问题自动并行协作，例如同一句同时涉及病害诊断和用药建议。
        decision = self._route_decision(req)
        if decision.multi_agent:
            return await self.run_parallel(req, decision)

        # 2. 执行主 Agent（含降级）
        response = await self._execute(req, decision.primary_agent)

        # 4. 升级检查
        escalated = False
        if response.escalate or req.urgency == UrgencyLevel.CRITICAL or req.intent in (
            IntentCategory.HUMAN_HANDOFF,
        ):
            escalated = True
            logger.warning(f"请求 {req.request_id} 触发升级: urgency={req.urgency}")
            # 生产环境：EscalationAgent 已创建专家复核反馈，此处可再接消息通知

        result = OrchestratorResult(
            request_id=req.request_id,
            response=response.content,
            agent_type=response.agent_type,
            intent=req.intent,
            escalated=escalated,
            latency_ms=(time.monotonic() - t0) * 1000,
            agent_types=[response.agent_type],
            primary_agent=decision.primary_agent,
            supporting_agents=[],
            tools_used=list(response.tools_used),
            tool_traces=list(response.tool_traces),
            routing_reason=decision.reason,
            routing_confidence=decision.confidence,
        )
        self._record_tool_trace(result)
        return result

    async def run_parallel(self, req: Request, decision: RoutingDecision) -> OrchestratorResult:
        """
        并行派发给多个 Agent，合并结果。
        适用于复杂问题（如同时涉及病害诊断和用药建议）。
        """
        t0 = time.monotonic()
        agent_types = decision.agent_types
        tasks = [self._execute(req, at) for at in agent_types]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        valid_responses = [r for r in responses if isinstance(r, AgentResponse)]
        combined = await self._composer.compose(req, valid_responses)
        escalated = any(isinstance(r, AgentResponse) and r.escalate for r in responses)
        tools_used = list(dict.fromkeys(
            tool_name
            for response in valid_responses
            for tool_name in response.tools_used
        ))
        tool_traces = [
            trace
            for response in valid_responses
            for trace in response.tool_traces
        ]
        result = OrchestratorResult(
            request_id=req.request_id,
            response=combined,
            agent_type=decision.primary_agent,
            intent=req.intent,
            escalated=escalated,
            latency_ms=(time.monotonic() - t0) * 1000,
            agent_types=[
                r.agent_type for r in responses
                if isinstance(r, AgentResponse) and r.success
            ] or agent_types,
            primary_agent=decision.primary_agent,
            supporting_agents=decision.supporting_agents,
            tools_used=tools_used,
            tool_traces=tool_traces,
            routing_reason=decision.reason,
            routing_confidence=decision.confidence,
        )
        self._record_tool_trace(result)
        return result

    # ── 路由逻辑 ──────────────────────────────────────────────────────────────

    def _route(self, intent: Optional[IntentCategory], urgency: Optional[UrgencyLevel]) -> AgentType:
        """
        三层路由决策：
          1. 意图映射
          2. 紧急度覆盖（CRITICAL 直接升级）
          3. 默认 DIAGNOSIS（前台分诊）
        """
        if urgency == UrgencyLevel.CRITICAL:
            return AgentType.ESCALATION

        if intent and intent in self._INTENT_ROUTING:
            target = self._INTENT_ROUTING[intent]
            # 如果目标类型有可用实例则使用，否则降级
            if target in self._pool and self._pool[target]:
                return target

        return AgentType.DIAGNOSIS

    def _route_decision(self, req: Request) -> RoutingDecision:
        """
        结构化路由决策。

        先处理紧急/转人工，再用领域分数决定主 Agent 和辅助 Agent。
        这样可以表达“主处理 + 辅助建议”，避免关键词命中后无主次地拼接。
        """
        if req.urgency == UrgencyLevel.CRITICAL:
            return RoutingDecision(
                primary_agent=AgentType.ESCALATION,
                reason="紧急度为 CRITICAL（灾情词命中），触发升级路由",
                confidence=1.0,
            )

        if req.intent == IntentCategory.HUMAN_HANDOFF:
            return RoutingDecision(
                primary_agent=AgentType.ESCALATION,
                reason=f"意图为 {req.intent.value if req.intent else 'unknown'}，触发升级路由",
                confidence=max(req.intent_confidence, 0.8),
            )

        scores = self._domain_scores(req)
        available_scores = {
            agent_type: score
            for agent_type, score in scores.items()
            if agent_type == AgentType.DIAGNOSIS or self._pool.get(agent_type)
        }
        if not available_scores:
            return RoutingDecision(
                primary_agent=AgentType.DIAGNOSIS,
                reason="无可用专属 Agent，降级到 DiagnosisAgent",
                confidence=0.1,
            )

        ordered = sorted(available_scores.items(), key=lambda item: item[1], reverse=True)
        primary_agent, primary_score = ordered[0]

        collaboration_targets = self._collaboration_targets(req)
        supporting_agents = [
            agent_type
            for agent_type in collaboration_targets
            if agent_type != primary_agent and agent_type in available_scores
        ]

        if not supporting_agents:
            supporting_agents = [
                agent_type
                for agent_type, score in ordered[1:]
                if agent_type != AgentType.DIAGNOSIS
                and score >= 0.45
                and score >= primary_score * 0.55
            ]

        reason = self._routing_reason(req, available_scores, primary_agent, supporting_agents)
        return RoutingDecision(
            primary_agent=primary_agent,
            supporting_agents=supporting_agents,
            reason=reason,
            confidence=round(min(primary_score, 1.0), 3),
        )

    def _domain_scores(self, req: Request) -> Dict[AgentType, float]:
        """按意图、关键词和实体为各领域 Agent 打分。"""
        msg = req.message.lower()
        scores = {
            AgentType.DIAGNOSIS: 0.1,
            AgentType.PREVENTION: 0.0,
            AgentType.MEDICATION: 0.0,
        }

        if req.intent in (
            IntentCategory.DISEASE_DIAGNOSIS,
            IntentCategory.GREETING,
            IntentCategory.OTHER,
        ):
            scores[AgentType.DIAGNOSIS] += 0.55

        if req.intent == IntentCategory.PREVENTION_QA:
            scores[AgentType.PREVENTION] += 0.75

        if req.intent == IntentCategory.MEDICATION_ADVICE:
            scores[AgentType.MEDICATION] += 0.75

        diagnosis_kws = ["病斑", "叶片", "叶子", "发黄", "霉层", "照片", "图片", "什么病", "啥病", "诊断", "斑点", "枯"]
        prevention_kws = ["防治", "预防", "怎么治", "怎么办", "发病条件", "轮作", "管理", "霜霉病", "白粉病", "炭疽病", "蔓枯病"]
        medication_kws = ["用什么药", "打药", "喷药", "杀菌剂", "剂量", "配比", "稀释", "安全间隔期", "间隔期", "用药", "禁忌", "轮换"]

        diagnosis_hits = sum(1 for kw in diagnosis_kws if kw in msg)
        prevention_hits = sum(1 for kw in prevention_kws if kw in msg)
        medication_hits = sum(1 for kw in medication_kws if kw in msg)

        scores[AgentType.DIAGNOSIS] += min(0.45, diagnosis_hits * 0.18)
        scores[AgentType.PREVENTION] += min(0.45, prevention_hits * 0.18)
        scores[AgentType.MEDICATION] += min(0.45, medication_hits * 0.18)

        entities = req.entities or {}
        if entities.get("disease"):
            scores[AgentType.PREVENTION] += 0.1
            scores[AgentType.DIAGNOSIS] += 0.1
        if entities.get("pesticide"):
            scores[AgentType.MEDICATION] += 0.2
        if entities.get("plant_part") or entities.get("spot_area") or entities.get("onset_days"):
            scores[AgentType.DIAGNOSIS] += 0.15
        if req.image_url:
            scores[AgentType.DIAGNOSIS] += 0.2

        return {agent_type: round(score, 3) for agent_type, score in scores.items()}

    @staticmethod
    def _routing_reason(
        req: Request,
        scores: Dict[AgentType, float],
        primary_agent: AgentType,
        supporting_agents: List[AgentType],
    ) -> str:
        score_text = ", ".join(
            f"{agent_type.value}={score:.2f}"
            for agent_type, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        )
        support_text = ", ".join(agent.value for agent in supporting_agents) or "none"
        intent = req.intent.value if req.intent else "unknown"
        return (
            f"intent={intent}, group={req.intent_group or 'unknown'}, "
            f"primary={primary_agent.value}, supporting={support_text}, scores=[{score_text}]"
        )

    def _collaboration_targets(self, req: Request) -> List[AgentType]:
        """
        判断是否需要多个 Agent 并行协作。

        意图识别通常只返回一个主意图；这里用领域关键词补充检测复合问题，
        例如"这是什么病，该打什么药"需要诊断和用药 Agent 同时处理。
        """
        msg = req.message.lower()
        targets: List[AgentType] = []

        diagnosis_kws = ["病斑", "什么病", "啥病", "霉层", "发黄", "照片", "图片", "诊断"]
        prevention_kws = ["防治", "预防", "怎么治", "怎么办", "发病条件", "轮作"]
        medication_kws = ["什么药", "打药", "喷药", "杀菌剂", "剂量", "安全间隔期", "间隔期", "用药"]

        if req.intent == IntentCategory.DISEASE_DIAGNOSIS or any(kw in msg for kw in diagnosis_kws):
            targets.append(AgentType.DIAGNOSIS)
        if req.intent == IntentCategory.PREVENTION_QA or any(kw in msg for kw in prevention_kws):
            targets.append(AgentType.PREVENTION)
        if req.intent == IntentCategory.MEDICATION_ADVICE or any(kw in msg for kw in medication_kws):
            targets.append(AgentType.MEDICATION)

        # 保持顺序去重，并只返回当前有实例的 Agent 类型。
        deduped = list(dict.fromkeys(targets))
        return [agent_type for agent_type in deduped if self._pool.get(agent_type)]

    @staticmethod
    def _needs_clarification(req: Request) -> bool:
        """低置信度且无明确意图时，先追问，避免误路由。"""
        if req.intent != IntentCategory.OTHER:
            return False
        text = (req.message or "").strip()
        if len(text) <= 2:
            return False
        return req.intent_confidence < 0.5

    def _best_agent(self, agent_type: AgentType) -> Optional[BaseAgent]:
        """
        性能路由：从同类 Agent 中选 routing_score() 最高的。
        这是"基于在线表现动态调整路由"的核心。
        """
        agents = self._pool.get(agent_type, [])
        if not agents:
            return None
        return max(agents, key=lambda a: a.stats.routing_score())

    async def _execute(self, req: Request, agent_type: AgentType) -> AgentResponse:
        """执行 Agent，失败时降级到 DiagnosisAgent。"""
        agent = self._best_agent(agent_type)
        if agent is None:
            agent = self._best_agent(AgentType.DIAGNOSIS)
        if agent is None:
            return AgentResponse(
                agent_type=AgentType.DIAGNOSIS,
                content="服务暂时不可用，请稍后重试。",
                success=False,
            )

        response = await agent.handle(req)

        # 专属 Agent 失败时降级到 DiagnosisAgent
        if not response.success and agent_type not in (AgentType.DIAGNOSIS, AgentType.ESCALATION):
            logger.warning(f"{agent_type.value} 失败，降级到 DiagnosisAgent")
            fallback = self._best_agent(AgentType.DIAGNOSIS)
            if fallback:
                response = await fallback.handle(req)

        return response

    # ── 统计（供 Monitor 读取）────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        result = {}
        for agent_type, agents in self._pool.items():
            for i, agent in enumerate(agents):
                key = f"{agent_type.value}_{i}"
                result[key] = {
                    "total":        agent.stats.total,
                    "success_rate": round(agent.stats.success_rate, 3),
                    "avg_ms":       round(agent.stats.avg_ms, 1),
                    "monitor_penalty": round(agent.stats.monitor_penalty, 3),
                    "routing_score": round(agent.stats.routing_score(), 3),
                    "role": agent.profile.role,
                    "workflow": list(agent.profile.workflow),
                    "tool_scope": list(agent.profile.tool_scope),
                    "available_tools": list(agent.get_tools()),
                    "model": agent._model,
                }
        return result

    def update_routing_penalties(self, penalties: Dict[str, float]) -> None:
        """
        接收 Monitor 的在线表现反馈，动态调整路由惩罚项。

        penalties 的 key 使用 get_stats() 中的 agent key，例如 diagnosis_0。
        """
        for agent_type, agents in self._pool.items():
            for i, agent in enumerate(agents):
                key = f"{agent_type.value}_{i}"
                penalty = penalties.get(key, 0.0)
                agent.stats.monitor_penalty = min(max(penalty, 0.0), 0.9)
