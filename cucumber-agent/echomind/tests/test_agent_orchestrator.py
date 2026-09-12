import asyncio

from agents.agent_orchestrator import (
    AgentProfile,
    AgentResponse,
    AgentType,
    AgentOrchestrator,
    DiagnosisAgent,
    EscalationAgent,
    MedicationAgent,
    PreventionAgent,
    Request,
    ResponseComposer,
    RoutingDecision,
    build_shared_rag_tools,
)
from core.intent_recognizer import IntentCategory, UrgencyLevel


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

        class Messages:
            async def create(inner, **kwargs):
                self.calls.append(kwargs)
                if self.error:
                    raise self.error
                return self.response

        self.messages = Messages()


def make_request(**kwargs):
    values = {
        "message": "叶片出现多角形病斑确诊是霜霉病，该打什么药？",
        "user_id": "u1",
        "conv_id": "c1",
        "intent": IntentCategory.DISEASE_DIAGNOSIS,
        "intent_group": "disease_diagnosis",
        "urgency": UrgencyLevel.HIGH,
        "intent_confidence": 0.92,
        "entities": {"disease": ["霜霉病"], "plant_part": ["叶片"]},
    }
    values.update(kwargs)
    return Request(**values)


def test_agent_profiles_have_distinct_contracts_and_generation_config():
    assert isinstance(DiagnosisAgent.profile, AgentProfile)
    assert DiagnosisAgent.profile.role != PreventionAgent.profile.role
    assert PreventionAgent.profile.workflow != MedicationAgent.profile.workflow
    assert MedicationAgent.profile.temperature < DiagnosisAgent.profile.temperature
    assert "query_knowledge" in DiagnosisAgent.profile.tool_scope
    assert "diagnose_image" in DiagnosisAgent.profile.tool_scope
    assert "check_medication_safety" in MedicationAgent.profile.tool_scope


def test_domain_agents_build_different_role_packets():
    req = make_request()
    diagnosis_packet = DiagnosisAgent(FakeClient(), "test-model")._build_role_packet(req)
    prevention_packet = PreventionAgent(FakeClient(), "test-model")._build_role_packet(req)
    medication_packet = MedicationAgent(FakeClient(), "test-model")._build_role_packet(req)

    assert "triage_targets" in diagnosis_packet
    assert "citation_rule" in prevention_packet
    assert "medication_fields" in medication_packet
    assert diagnosis_packet != prevention_packet != medication_packet


def test_escalation_agent_is_a_real_non_llm_handoff_node():
    client = FakeClient()
    agent = EscalationAgent(client, "test-model")

    result = asyncio.run(agent.handle(make_request(
        intent=IntentCategory.HUMAN_HANDOFF,
        urgency=UrgencyLevel.CRITICAL,
    )))

    assert result.success is True
    assert result.escalate is True
    assert "人工专家复核" in result.content
    assert client.calls == []


def test_composer_fallback_preserves_primary_and_supporting_results():
    composer = ResponseComposer(FakeClient(error=RuntimeError("provider down")), "test-model")
    req = make_request()
    responses = [
        AgentResponse(AgentType.DIAGNOSIS, "符合霜霉病典型特征 [KB-DM-001]。", True),
        AgentResponse(AgentType.MEDICATION, "可选烯酰吗啉类，注意安全间隔期 [KB-SAFE-001]。", True),
    ]

    content = asyncio.run(composer.compose(req, responses))

    assert content.startswith("符合霜霉病典型特征 [KB-DM-001]。")
    assert "补充说明" in content
    assert "安全间隔期" in content


def test_routing_decision_can_target_escalation_pool():
    # Keep this assertion close to the public data contract used by the API.
    decision = RoutingDecision(
        primary_agent=AgentType.ESCALATION,
        reason="critical request",
        confidence=1.0,
    )
    assert decision.agent_types == [AgentType.ESCALATION]
    assert not decision.multi_agent


def test_composite_request_routes_explicit_medication_signal_as_supporting_agent():
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator._pool = {
        AgentType.DIAGNOSIS: [object()],
        AgentType.PREVENTION: [object()],
        AgentType.MEDICATION: [object()],
    }

    decision = orchestrator._route_decision(make_request())

    assert decision.primary_agent is AgentType.DIAGNOSIS
    assert decision.supporting_agents == [AgentType.MEDICATION]
    assert decision.multi_agent is True


def test_agent_tool_scopes_are_real_and_isolated():
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator._pool = {
        AgentType.DIAGNOSIS: [DiagnosisAgent(FakeClient(), "test-model")],
        AgentType.PREVENTION: [PreventionAgent(FakeClient(), "test-model")],
        AgentType.MEDICATION: [MedicationAgent(FakeClient(), "test-model")],
        AgentType.ESCALATION: [EscalationAgent(FakeClient(), "test-model")],
    }
    orchestrator.set_domain_tools(None)

    diagnosis = set(orchestrator._pool[AgentType.DIAGNOSIS][0].get_tools())
    prevention = set(orchestrator._pool[AgentType.PREVENTION][0].get_tools())
    medication = set(orchestrator._pool[AgentType.MEDICATION][0].get_tools())
    escalation = set(orchestrator._pool[AgentType.ESCALATION][0].get_tools())

    assert diagnosis == {
        "inspect_request_context", "suggest_required_fields",
        "diagnose_image", "query_diagnosis_records",
    }
    assert prevention == set()
    assert medication == {"check_medication_safety"}
    assert escalation == {"create_diagnosis_feedback"}
    assert not diagnosis & medication
    assert not medication & escalation


def test_shared_rag_tool_is_available_to_all_agents():
    class RagManager:
        async def search_with_rewrite(self, tool_name, query, top_k=5):
            return type(
                "Result",
                (),
                {"success": True,
                 "data": [{"title": "黄瓜霜霉病症状识别", "content": "多角形病斑", "source_id": "KB-DM-001"}],
                 "reranked": True},
            )()

    shared = build_shared_rag_tools(RagManager())

    diagnosis = DiagnosisAgent(FakeClient(), "test-model")
    prevention = PreventionAgent(FakeClient(), "test-model")
    medication = MedicationAgent(FakeClient(), "test-model")
    escalation = EscalationAgent(FakeClient(), "test-model")

    for agent in (diagnosis, prevention, medication, escalation):
        agent.set_shared_tools(shared)
        tools = agent.get_tools()
        assert "query_knowledge" in tools


def test_tool_input_validation_rejects_unknown_fields():
    from agents.tools import medication_tools

    agent = MedicationAgent(FakeClient(), "test-model")
    agent.set_domain_tools(medication_tools())
    spec = agent.get_tools()["check_medication_safety"]

    try:
        agent._validate_tool_input(spec, {"pesticide": "烯酰吗啉", "secret": "nope"})
    except ValueError as exc:
        assert "不允许的工具参数" in str(exc)
    else:
        raise AssertionError("unknown tool fields should be rejected")


def test_medication_safety_tool_flags_banned_pesticide_and_harvest_window():
    from agents.tools import check_medication_safety

    result = check_medication_safety(make_request(), {"pesticide": "氧乐果", "days_to_harvest": 3})
    assert result["banned"] is True
    assert any("禁用" in w or "禁止" in w for w in result["warnings"])
    assert any("安全间隔期" in w for w in result["warnings"])

    ok = check_medication_safety(make_request(), {"pesticide": "烯酰吗啉", "days_to_harvest": 20})
    assert ok["banned"] is False
    assert ok["registered_hint"] is True


def test_tool_use_round_trip_executes_only_whitelisted_tool():
    class ToolUseBlock:
        type = "tool_use"
        id = "toolu_1"
        name = "check_medication_safety"
        input = {"pesticide": "烯酰吗啉"}

    class TextBlock:
        type = "text"
        text = "已核对用药合规边界，请按标签执行安全间隔期。"

    class ToolClient:
        def __init__(self):
            self.calls = []
            self.responses = [
                type("Response", (), {"content": [ToolUseBlock()]})(),
                type("Response", (), {"content": [TextBlock()]})(),
            ]

        class Messages:
            def __init__(self, owner):
                self.owner = owner

            async def create(self, **kwargs):
                self.owner.calls.append(kwargs)
                return self.owner.responses.pop(0)

        @property
        def messages(self):
            return self.Messages(self)

    from agents.tools import medication_tools

    client = ToolClient()
    agent = MedicationAgent(client, "test-model")
    agent.set_domain_tools(medication_tools())
    response = asyncio.run(agent.handle(make_request()))

    assert response.success is True
    assert response.tools_used == ["check_medication_safety"]
    assert len(client.calls) == 2
    assert {tool["name"] for tool in client.calls[0]["tools"]} == {
        "check_medication_safety",
    }
    assert "tool_result" in str(client.calls[1]["messages"])


# ── 知识库种子与元数据透传 ──────────────────────────────────────────────────────

def _make_kb():
    """用 EphemeralClient + 轻量假 embedding 构建知识库，避免测试下载 ONNX 模型。"""
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction  # noqa: F401  (确认依赖可用)

    class _HashEmbedding:
        """稳定的字符哈希向量，仅供测试，不做语义匹配。"""

        def __call__(self, input):
            import hashlib
            vecs = []
            for text in input:
                vec = [0.0] * 16
                for i, ch in enumerate(text):
                    vec[i % 16] += (ord(ch) % 7) - 3
                vecs.append(vec)
            return vecs

        def name(self):
            return "hash-embedding-test"

    from mcp.knowledge_base import KnowledgeBase

    client = chromadb.EphemeralClient()
    client.get_or_create_collection(
        name=KnowledgeBase.COLLECTION_NAME,
        embedding_function=_HashEmbedding(),
    )
    return KnowledgeBase(client=client)


def test_knowledge_seed_loads_28_cucumber_entries():
    kb = _make_kb()
    assert kb.doc_count >= 28

    results = kb.search("霜霉病 症状", top_k=3)
    assert results
    hit = results[0]
    # metadata 透传：来源编号与病害类别随检索结果带出
    assert hit["source_id"].startswith("KB-")
    assert hit["disease_type"]
    assert hit["level"] in {"A", "B"}
    assert hit["category"]


def test_knowledge_metadata_passthrough_on_add():
    kb = _make_kb()
    before = kb.doc_count
    added = kb.add_documents([{
        "title": "测试条目",
        "content": "黄瓜测试病害的防治内容。",
        "source_id": "KB-TEST-001",
        "disease_type": "测试病害",
        "level": "B",
        "category": "症状",
    }])
    assert added == 1
    assert kb.doc_count == before + 1

    results = kb.search("测试病害", top_k=kb.doc_count)
    assert any(item["source_id"] == "KB-TEST-001" for item in results)
