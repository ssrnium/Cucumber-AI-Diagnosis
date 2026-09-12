package com.portfolio.cucumber.modules.agent;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.agent.entity.AgentMessage;
import com.portfolio.cucumber.modules.agent.entity.AgentSession;
import com.portfolio.cucumber.modules.agent.mapper.AgentMessageMapper;
import com.portfolio.cucumber.modules.agent.mapper.AgentSessionMapper;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import com.portfolio.cucumber.security.LoginUser;
import com.portfolio.cucumber.security.SecurityUtils;
import jakarta.validation.constraints.NotBlank;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.MediaType;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 智能体模块：代理 cucumber-agent（EchoMind 二开）的对话/监控/评测/Skills 接口。
 *
 * 安全边界：cucumber-agent 本身无鉴权，一律经本模块 JWT 鉴权后代理暴露；
 * 对话接口落 agent_session / agent_message 审计，并把登录用户 ID 作为 user_id 透传。
 */
@RestController
@RequestMapping("/api/v1/agent")
public class AgentController {

    public record ChatRequest(@NotBlank(message = "消息不能为空") String message,
                              String convId,
                              String imageUrl,
                              Long recordId) {
    }

    private final AgentServiceClient agentServiceClient;
    private final AgentSessionMapper agentSessionMapper;
    private final AgentMessageMapper agentMessageMapper;

    public AgentController(AgentServiceClient agentServiceClient,
                           AgentSessionMapper agentSessionMapper,
                           AgentMessageMapper agentMessageMapper) {
        this.agentServiceClient = agentServiceClient;
        this.agentSessionMapper = agentSessionMapper;
        this.agentMessageMapper = agentMessageMapper;
    }

    /**
     * 智能体对话：代理到 cucumber-agent /chat，落审计，透传登录用户 ID。
     */
    @PostMapping("/chat")
    @PreAuthorize("hasAuthority('agent:chat')")
    @OperLog("智能体对话")
    @SuppressWarnings("unchecked")
    public Result<Map<String, Object>> chat(@Validated @RequestBody ChatRequest request) {
        LoginUser currentUser = SecurityUtils.current();
        if (currentUser == null) {
            throw new BizException(401, "未登录或登录已过期");
        }
        String convId = request.convId() == null || request.convId().isBlank()
                ? UUID.randomUUID().toString() : request.convId();

        Map<String, Object> body = new HashMap<>();
        body.put("message", request.message());
        body.put("user_id", String.valueOf(currentUser.getUserId()));
        body.put("conv_id", convId);
        if (request.imageUrl() != null && !request.imageUrl().isBlank()) {
            body.put("image_url", request.imageUrl());
        }
        if (request.recordId() != null) {
            body.put("record_id", request.recordId());
        }

        Map<String, Object> agentResponse;
        try {
            agentResponse = agentServiceClient.chat(body);
        } catch (Exception e) {
            throw new BizException("智能体服务暂不可用，请稍后重试");
        }

        audit(currentUser.getUserId(), convId, request.message(), agentResponse);
        return Result.success(agentResponse);
    }

    /** 监控摘要：Agent 成功率/延迟/路由罚分 + 工具熔断状态。 */
    @GetMapping("/monitor")
    @PreAuthorize("hasAuthority('agent:monitor')")
    public Result<Map<String, Object>> monitor() {
        return Result.success(agentServiceClient.monitor());
    }

    /** 运行评测（意图准确率 + LLM-as-Judge 六维评分 + 回归检测）。 */
    @PostMapping("/eval/run")
    @PreAuthorize("hasAuthority('agent:eval')")
    @OperLog("运行智能体评测")
    public Result<Map<String, Object>> evalRun(@RequestBody(required = false) Map<String, Object> body) {
        return Result.success(agentServiceClient.evalRun(body));
    }

    /** Skills 摘要。 */
    @GetMapping("/skills")
    @PreAuthorize("hasAuthority('agent:skills')")
    public Result<Map<String, Object>> skills() {
        return Result.success(agentServiceClient.skills());
    }

    /** Skills 热加载。 */
    @PostMapping("/skills/reload")
    @PreAuthorize("hasAuthority('agent:skills')")
    @OperLog("热加载智能体 Skills")
    public Result<Map<String, Object>> reloadSkills() {
        return Result.success(agentServiceClient.reloadSkills());
    }

    /** 单次请求的工具调用轨迹（对话页 trace 抽屉）。 */
    @GetMapping("/trace/tool/{requestId}")
    @PreAuthorize("hasAuthority('agent:chat')")
    public Result<Map<String, Object>> toolTrace(@PathVariable String requestId) {
        return Result.success(agentServiceClient.toolTrace(requestId));
    }

    /** 最近 N 次请求的工具调用轨迹。 */
    @GetMapping("/trace/tools")
    @PreAuthorize("hasAuthority('agent:monitor')")
    public Result<Map<String, Object>> recentToolTraces(@RequestParam(defaultValue = "20") int limit) {
        return Result.success(agentServiceClient.recentToolTraces(limit));
    }

    /** 知识库批量导入（带 source_id 元数据）。 */
    @PostMapping("/knowledge/add")
    @PreAuthorize("hasAuthority('agent:skills')")
    @OperLog("智能体知识库导入")
    public Result<Map<String, Object>> knowledgeAdd(@RequestBody Map<String, Object> body) {
        return Result.success(agentServiceClient.knowledgeAdd(body));
    }

    /** 知识库统计。 */
    @GetMapping("/knowledge/stats")
    @PreAuthorize("hasAuthority('agent:monitor')")
    public Result<Map<String, Object>> knowledgeStats() {
        return Result.success(agentServiceClient.knowledgeStats());
    }

    /** 知识库文件导入（.txt/.md/.json，multipart 代理）。 */
    @PostMapping(value = "/knowledge/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAuthority('agent:skills')")
    @OperLog("智能体知识库文件导入")
    public Result<Map<String, Object>> knowledgeUpload(@RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new BizException("请选择要上传的文件");
        }
        String filename = StringUtils.cleanPath(
                file.getOriginalFilename() == null ? "knowledge.txt" : file.getOriginalFilename());
        return Result.success(agentServiceClient.knowledgeUpload(file.getBytes(), filename));
    }

    // ── 审计落库 ────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private void audit(Long userId, String convId, String userMessage, Map<String, Object> agentResponse) {
        try {
            AgentSession session = agentSessionMapper.selectOne(new LambdaQueryWrapper<AgentSession>()
                    .eq(AgentSession::getUserId, userId)
                    .eq(AgentSession::getConvId, convId));
            boolean isNew = session == null;
            if (isNew) {
                session = new AgentSession();
                session.setConvId(convId);
                session.setUserId(userId);
                session.setCreateTime(LocalDateTime.now());
            }
            session.setPrimaryAgent(str(agentResponse.get("primary_agent")));
            session.setLastIntent(str(agentResponse.get("intent")));
            session.setEscalated(Boolean.TRUE.equals(agentResponse.get("escalated")));
            session.setUpdateTime(LocalDateTime.now());
            if (isNew) {
                agentSessionMapper.insert(session);
            } else {
                agentSessionMapper.updateById(session);
            }

            AgentMessage userMsg = new AgentMessage();
            userMsg.setSessionId(session.getId());
            userMsg.setRole("USER");
            userMsg.setContent(userMessage);
            userMsg.setCreateTime(LocalDateTime.now());
            agentMessageMapper.insert(userMsg);

            AgentMessage assistantMsg = new AgentMessage();
            assistantMsg.setSessionId(session.getId());
            assistantMsg.setRequestId(str(agentResponse.get("request_id")));
            assistantMsg.setRole("ASSISTANT");
            assistantMsg.setContent(str(agentResponse.get("response")));
            assistantMsg.setIntent(str(agentResponse.get("intent")));
            assistantMsg.setAgentType(str(agentResponse.get("agent_type")));
            Object tools = agentResponse.get("tools_used");
            if (tools instanceof List) {
                assistantMsg.setToolsUsed((List<String>) tools);
            }
            Object latency = agentResponse.get("latency_ms");
            if (latency instanceof Number) {
                assistantMsg.setLatencyMs(((Number) latency).doubleValue());
            }
            assistantMsg.setCreateTime(LocalDateTime.now());
            agentMessageMapper.insert(assistantMsg);
        } catch (Exception e) {
            // 审计失败不影响主链路
            org.slf4j.LoggerFactory.getLogger(AgentController.class).warn("智能体对话审计落库失败: {}", e.getMessage());
        }
    }

    private static String str(Object value) {
        return value == null ? null : String.valueOf(value);
    }
}
