"""Agent 工具定义与实现。

所有 Agent 工具集中在这里，编排器只负责：
  1. 根据 Agent 类型暴露工具白名单
  2. 执行 LLM 返回的 tool_use
  3. 将工具结果回传给 LLM

工具本身保持确定性、可测试，并明确区分：
  - 当前请求分析（诊断分诊）
  - 图片诊断链路（cucumber-ai）
  - 诊断记录查询（cucumber-admin）
  - 用药安全合规检查
  - 人工升级交接（创建专家复核反馈）
  - 共享知识库 RAG（query_knowledge，带 source_id 来源追溯）

平台写操作（修改诊断记录、删除数据等）不在这里开放。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from agents.agent_orchestrator import Request


AgentToolHandler = Callable[["Request", Dict[str, Any]], Union[Any, Awaitable[Any]]]


@dataclass(frozen=True)
class AgentToolSpec:
    """Agent 可见工具的定义和执行函数。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: AgentToolHandler


def make_tool(
    name: str,
    description: str,
    properties: Dict[str, Any],
    handler: AgentToolHandler,
    required: Optional[List[str]] = None,
) -> AgentToolSpec:
    """创建带 JSON Schema 的 Agent 工具。"""
    return AgentToolSpec(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
        handler=handler,
    )


# ── 诊断分诊本地工具（确定性，不调外部系统）────────────────────────────────────

def inspect_request_context(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """诊断分诊工具：返回脱敏后的当前请求快照。"""
    return {
        "intent": req.intent.value if req.intent else None,
        "intent_group": req.intent_group,
        "urgency": req.urgency.name if req.urgency else None,
        "intent_confidence": round(req.intent_confidence, 4),
        "entities": req.entities or {},
        "image_url": req.image_url,
        "record_id": req.record_id,
        "context_available": bool(req.context),
        "requested_focus": str(args.get("focus", "diagnosis"))[:40],
    }


def suggest_required_fields(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """诊断分诊工具：按意图计算下一轮只需向用户补充的字段。"""
    intent = req.intent.value if req.intent else "other"
    fields: List[str] = []
    if intent == "disease_diagnosis":
        fields = ["叶片照片（上传图片）", "发病部位", "发病天数"]
    elif intent == "prevention_qa":
        fields = ["病害名称或症状描述", "栽培方式（设施/露地）"]
    elif intent == "medication_advice":
        fields = ["确诊的病害名称", "距离预计采收的天数"]
    elif intent == "other":
        fields = ["希望解决的具体问题（诊断/防治/用药/转人工）"]
    return {
        "intent": intent,
        "required_fields": fields,
        "known_entities": req.entities or {},
        "has_image": bool(req.image_url),
    }


# ── 用药安全合规工具（确定性规则，不编造药剂信息）──────────────────────────────

_BANNED_PESTICIDES = ["甲胺磷", "对硫磷", "甲基对硫磷", "久效磷", "磷胺",
                      "氧乐果", "克百威", "涕灭威", "水胺硫磷", "灭线磷"]

_REGISTERED_CATEGORIES = ["三唑类", "甲氧基丙烯酸酯类", "烯酰吗啉类", "氰霜唑", "霜脲氰", "代森锰锌", "百菌清"]


def check_medication_safety(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """用药安全工具：检查药剂合规边界与安全间隔期提醒，不提供具体剂量结论。"""
    pesticide = str(args.get("pesticide", "")).strip()
    days_to_harvest = args.get("days_to_harvest")
    result: Dict[str, Any] = {
        "pesticide": pesticide or None,
        "banned": False,
        "registered_hint": False,
        "warnings": [],
        "boundary": "具体药剂品种、剂型、剂量与安全间隔期以农药登记标签和当地植保部门指导为准",
    }
    if not pesticide:
        result["warnings"].append("未提供药剂名称，请先确认拟使用的药剂")
    else:
        if any(banned in pesticide for banned in _BANNED_PESTICIDES):
            result["banned"] = True
            result["warnings"].append(f"{pesticide} 属于蔬菜禁用/限用农药，禁止在黄瓜上使用")
        if any(cat in pesticide or pesticide in cat for cat in _REGISTERED_CATEGORIES):
            result["registered_hint"] = True
    if isinstance(days_to_harvest, (int, float)) and days_to_harvest <= 7:
        result["warnings"].append(
            f"距采收仅 {int(days_to_harvest)} 天：必须核对所选药剂标签上的安全间隔期，"
            "间隔期不足时应优先选用生物制剂或延后采收"
        )
    result["rotation_rule"] = "同一作用机理的杀菌剂同一生长季连续使用不超过 2-3 次，应轮换不同机理药剂"
    return result


def triage_tools() -> Dict[str, AgentToolSpec]:
    """诊断分诊（前台接待）工具：请求快照 + 待补充字段建议。"""
    return {
        "inspect_request_context": make_tool(
            "inspect_request_context",
            "查看当前请求的意图、紧急度、实体、图片与记录上下文可用性；不查询外部业务系统。",
            {"focus": {"type": "string", "description": "希望关注的方向，如 diagnosis/medication"}},
            inspect_request_context,
        ),
        "suggest_required_fields": make_tool(
            "suggest_required_fields",
            "根据当前意图建议下一轮只需向用户补充的字段（如叶片照片、发病部位、距采收天数）。",
            {},
            suggest_required_fields,
        ),
    }


# ── 平台工具（Agent 工具 → MCPToolManager → 真实 handler）──────────────────────

def build_shared_rag_tools(tool_manager: Any) -> Dict[str, AgentToolSpec]:
    """构建所有 Agent 可共享的黄瓜病害知识库 RAG 工具。"""

    async def query_knowledge(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or req.message or "").strip()
        top_k = int(args.get("top_k", 5) or 5)
        if not query:
            return {"success": False, "error": "query 不能为空", "results": []}
        if tool_manager is None:
            return {"success": False, "error": "RAG 工具未初始化", "results": []}

        result = await tool_manager.search_with_rewrite(
            "knowledge_search",
            query,
            top_k=top_k,
        )
        if not getattr(result, "success", False):
            return {
                "success": False,
                "query": query,
                "error": getattr(result, "error", "知识库检索失败"),
                "results": [],
                "reranked": False,
            }

        return {
            "success": True,
            "query": query,
            "top_k": top_k,
            "results": result.data,
            "reranked": bool(getattr(result, "reranked", False)),
            "citation_rule": "回答中引用的每条知识必须标注其 source_id",
        }

    return {
        "query_knowledge": make_tool(
            "query_knowledge",
            "检索黄瓜病害知识库（症状/发病条件/防治/用药安全），返回带 source_id 的知识片段；引用时必须标注来源编号。",
            {
                "query": {"type": "string", "description": "用户问题或检索关键词，如 霜霉病防治"},
                "top_k": {"type": "integer", "description": "返回结果条数"},
            },
            query_knowledge,
            required=["query"],
        )
    }


def diagnosis_tools(tool_manager: Any) -> Dict[str, AgentToolSpec]:
    """诊断 Agent 工具：图片诊断链路 + 诊断记录查询。"""

    async def diagnose_image(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
        image_url = str(args.get("image_url") or req.image_url or "").strip()
        if not image_url:
            return {"success": False, "error": "缺少图片地址，请引导用户先上传叶片照片"}
        if tool_manager is None:
            return {"success": False, "error": "诊断工具未初始化"}
        symptoms = args.get("symptoms") or []
        if isinstance(symptoms, str):
            symptoms = [symptoms]
        result = await tool_manager.call(
            "diagnose_image",
            {"image_url": image_url, "symptoms": list(symptoms)},
            context={"user_id": req.user_id, "request_id": req.request_id},
        )
        if not result.success:
            return {"success": False, "image_url": image_url,
                    "error": result.error or "诊断服务暂不可用"}
        return {"success": True, "image_url": image_url, **(result.data or {})}

    async def query_diagnosis_records(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_manager is None:
            return {"success": False, "error": "记录查询工具未初始化"}
        params: Dict[str, Any] = {
            "page": int(args.get("page", 1) or 1),
            "size": min(int(args.get("size", 5) or 5), 20),
        }
        if args.get("record_id"):
            params["record_id"] = int(args["record_id"])
        elif req.record_id:
            params["record_id"] = int(req.record_id)
        if args.get("status"):
            params["status"] = str(args["status"])
        result = await tool_manager.call(
            "query_diagnosis_records",
            params,
            context={"user_id": req.user_id, "request_id": req.request_id},
        )
        if not result.success:
            return {"success": False, "error": result.error or "诊断记录查询失败"}
        return {"success": True, **(result.data or {})}

    return {
        "diagnose_image": make_tool(
            "diagnose_image",
            "对用户上传的黄瓜叶片图片执行检测与受控诊断，返回病斑框和带来源追溯的诊断报告；需要 image_url（可用请求自带的图片地址）。",
            {
                "image_url": {"type": "string", "description": "叶片图片地址，如 /files/xxx.jpg"},
                "symptoms": {"type": "array", "description": "用户描述的症状关键词（可选）"},
            },
            diagnose_image,
        ),
        "query_diagnosis_records": make_tool(
            "query_diagnosis_records",
            "查询历史诊断记录列表或指定 record_id 的诊断详情（含病斑框、报告与来源编号）。",
            {
                "record_id": {"type": "integer", "description": "诊断记录 ID（查详情时提供）"},
                "status": {"type": "string", "description": "按状态筛选：PENDING/DONE/FAILED"},
                "page": {"type": "integer", "description": "页码"},
                "size": {"type": "integer", "description": "每页条数，最大 20"},
            },
            query_diagnosis_records,
        ),
    }


def medication_tools() -> Dict[str, AgentToolSpec]:
    """用药建议 Agent 工具：用药安全合规检查（确定性规则）。"""
    return {
        "check_medication_safety": make_tool(
            "check_medication_safety",
            "检查拟用农药的合规边界（禁限用名录）与安全间隔期风险提醒；不给出具体剂量结论。",
            {
                "pesticide": {"type": "string", "description": "药剂名称，如 烯酰吗啉"},
                "days_to_harvest": {"type": "integer", "description": "距离预计采收的天数（可选）"},
            },
            check_medication_safety,
        ),
    }


def escalation_tools(tool_manager: Any) -> Dict[str, AgentToolSpec]:
    """人工升级 Agent 工具：创建专家复核反馈（真实写操作，经 MCPToolManager 治理）。"""

    async def create_diagnosis_feedback(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
        record_id = args.get("record_id") or req.record_id
        if not record_id:
            return {"success": False, "error": "缺少 record_id，无法关联诊断记录创建反馈"}
        if tool_manager is None:
            return {"success": False, "error": "反馈工具未初始化"}
        result = await tool_manager.call(
            "create_diagnosis_feedback",
            {
                "record_id": int(record_id),
                "corrected_disease_type": str(args.get("corrected_disease_type", ""))[:40],
                "comment": str(args.get("comment") or req.message or "")[:500],
            },
            context={"user_id": req.user_id, "request_id": req.request_id},
        )
        if not result.success:
            return {"success": False, "record_id": int(record_id),
                    "error": result.error or "反馈创建失败"}
        return {"success": True, "record_id": int(record_id), "review_status": "PENDING"}

    return {
        "create_diagnosis_feedback": make_tool(
            "create_diagnosis_feedback",
            "针对某条诊断记录创建专家复核反馈（人工升级交接时使用），反馈进入 PENDING 待专家复核。",
            {
                "record_id": {"type": "integer", "description": "诊断记录 ID"},
                "corrected_disease_type": {"type": "string", "description": "用户认为正确的病害类型（可选）"},
                "comment": {"type": "string", "description": "交接说明/用户补充描述"},
            },
            create_diagnosis_feedback,
            required=["record_id"],
        ),
    }
