package com.portfolio.cucumber.modules.agent;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.agent.AgentController.ChatRequest;
import com.portfolio.cucumber.modules.agent.entity.AgentMessage;
import com.portfolio.cucumber.modules.agent.entity.AgentSession;
import com.portfolio.cucumber.modules.agent.mapper.AgentMessageMapper;
import com.portfolio.cucumber.modules.agent.mapper.AgentSessionMapper;
import com.portfolio.cucumber.support.TestSupport;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AgentController 单元测试：对话转发（透传登录用户 ID）、agent 不可达降级、
 * 审计落库（会话新建/更新、USER+ASSISTANT 双消息）、审计失败不拖垮主链路。
 */
@ExtendWith(MockitoExtension.class)
class AgentControllerTest {

    @Mock
    private AgentServiceClient agentServiceClient;
    @Mock
    private AgentSessionMapper agentSessionMapper;
    @Mock
    private AgentMessageMapper agentMessageMapper;

    private AgentController controller;

    @BeforeEach
    void setUp() {
        TestSupport.initTableInfos();
        controller = new AgentController(agentServiceClient, agentSessionMapper, agentMessageMapper);
    }

    @AfterEach
    void tearDown() {
        TestSupport.logout();
    }

    private Map<String, Object> agentResponse() {
        return Map.of(
                "request_id", "req-001",
                "response", "这是黄瓜霜霉病的防治建议",
                "intent", "disease_advice",
                "agent_type", "agronomy",
                "primary_agent", "agronomy",
                "escalated", false,
                "tools_used", List.of("kb_search"),
                "latency_ms", 860);
    }

    @Test
    void chat_success_forwardsUserIdAndConvIdToAgent() {
        // 业务含义：admin 代理转发时必须把登录用户 ID 作为 user_id 透传给 agent，
        // 并生成/复用 conv_id，agent 侧多轮会话与审计归因都依赖这两个字段。
        TestSupport.loginAs(7L, "agent:chat");
        when(agentServiceClient.chat(anyMap())).thenReturn(agentResponse());
        when(agentSessionMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);

        Result<Map<String, Object>> result = controller.chat(new ChatRequest("黄瓜霜霉病怎么治", null, null, null));

        assertThat(result.getCode()).isEqualTo(200);
        assertThat(result.getData().get("response")).isEqualTo("这是黄瓜霜霉病的防治建议");
        ArgumentCaptor<Map<String, Object>> bodyCaptor = ArgumentCaptor.forClass(Map.class);
        verify(agentServiceClient).chat(bodyCaptor.capture());
        assertThat(bodyCaptor.getValue().get("user_id")).isEqualTo("7");
        assertThat(bodyCaptor.getValue().get("conv_id")).isNotNull();
        assertThat(bodyCaptor.getValue().get("message")).isEqualTo("黄瓜霜霉病怎么治");
    }

    @Test
    void chat_success_auditsNewSessionAndTwoMessages() {
        // 业务含义：新会话首轮对话落审计 —— 新建 agent_session（含 primary_agent/intent），
        // 并写入 USER 与 ASSISTANT 两条 agent_message，ASSISTANT 条带 request_id/工具/耗时。
        TestSupport.loginAs(7L, "agent:chat");
        when(agentServiceClient.chat(anyMap())).thenReturn(agentResponse());
        when(agentSessionMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);

        controller.chat(new ChatRequest("黄瓜霜霉病怎么治", "conv-1", null, null));

        ArgumentCaptor<AgentSession> sessionCaptor = ArgumentCaptor.forClass(AgentSession.class);
        verify(agentSessionMapper).insert(sessionCaptor.capture());
        AgentSession session = sessionCaptor.getValue();
        assertThat(session.getConvId()).isEqualTo("conv-1");
        assertThat(session.getUserId()).isEqualTo(7L);
        assertThat(session.getPrimaryAgent()).isEqualTo("agronomy");
        assertThat(session.getLastIntent()).isEqualTo("disease_advice");

        ArgumentCaptor<AgentMessage> messageCaptor = ArgumentCaptor.forClass(AgentMessage.class);
        verify(agentMessageMapper, times(2)).insert(messageCaptor.capture());
        List<AgentMessage> messages = messageCaptor.getAllValues();
        assertThat(messages.get(0).getRole()).isEqualTo("USER");
        assertThat(messages.get(0).getContent()).isEqualTo("黄瓜霜霉病怎么治");
        AgentMessage assistant = messages.get(1);
        assertThat(assistant.getRole()).isEqualTo("ASSISTANT");
        assertThat(assistant.getRequestId()).isEqualTo("req-001");
        assertThat(assistant.getIntent()).isEqualTo("disease_advice");
        assertThat(assistant.getAgentType()).isEqualTo("agronomy");
        assertThat(assistant.getToolsUsed()).containsExactly("kb_search");
        assertThat(assistant.getLatencyMs()).isEqualTo(860.0);
    }

    @Test
    void chat_existingSession_updatesInsteadOfInsert() {
        // 业务含义：同 conv_id 的追问复用已有会话记录（updateById），不重复建行，
        // 会话表一会话一行是审计页统计的基础。
        TestSupport.loginAs(7L, "agent:chat");
        AgentSession existing = new AgentSession();
        existing.setId(99L);
        existing.setConvId("conv-1");
        existing.setUserId(7L);
        when(agentServiceClient.chat(anyMap())).thenReturn(agentResponse());
        when(agentSessionMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(existing);

        controller.chat(new ChatRequest("再补充下用药剂量", "conv-1", null, null));

        verify(agentSessionMapper, never()).insert(any(AgentSession.class));
        verify(agentSessionMapper).updateById(existing);
    }

    @Test
    void chat_agentUnavailable_throwsDegradedBizException() {
        // 业务含义：cucumber-agent 宕机/超时时不暴露堆栈，降级为友好业务错误，
        // 且不落任何审计（消息根本没送达 agent）。
        TestSupport.loginAs(7L, "agent:chat");
        when(agentServiceClient.chat(anyMap())).thenThrow(new RuntimeException("Connection refused"));

        assertThatThrownBy(() -> controller.chat(new ChatRequest("你好", null, null, null)))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("智能体服务暂不可用");
        verify(agentSessionMapper, never()).insert(any(AgentSession.class));
        verify(agentMessageMapper, never()).insert(any(AgentMessage.class));
    }

    @Test
    void chat_notLoggedIn_throws401() {
        // 业务含义：无登录态调用对话接口返回 401，agent 本身无鉴权，admin 是唯一入口防线。
        assertThatThrownBy(() -> controller.chat(new ChatRequest("你好", null, null, null)))
                .isInstanceOf(BizException.class)
                .satisfies(e -> assertThat(((BizException) e).getCode()).isEqualTo(401));
    }

    @Test
    void chat_auditFailure_doesNotBreakMainFlow() {
        // 业务含义：审计落库失败（如 DB 抖动）仅告警，对话结果照常返回用户，
        // 审计是旁路，不能拖垮主链路。
        TestSupport.loginAs(7L, "agent:chat");
        when(agentServiceClient.chat(anyMap())).thenReturn(agentResponse());
        when(agentSessionMapper.selectOne(any(LambdaQueryWrapper.class)))
                .thenThrow(new RuntimeException("db down"));

        Result<Map<String, Object>> result = controller.chat(new ChatRequest("你好", null, null, null));

        assertThat(result.getCode()).isEqualTo(200);
        assertThat(result.getData().get("request_id")).isEqualTo("req-001");
    }
}
