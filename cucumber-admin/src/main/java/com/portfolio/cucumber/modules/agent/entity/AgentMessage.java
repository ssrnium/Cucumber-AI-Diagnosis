package com.portfolio.cucumber.modules.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Data
@TableName(value = "agent_message", autoResultMap = true)
public class AgentMessage {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long sessionId;
    private String requestId;
    /** USER / ASSISTANT */
    private String role;
    private String content;
    private String intent;
    private String agentType;
    /** 本轮工具调用名列表（JSONB） */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<String> toolsUsed;
    private Double latencyMs;
    private LocalDateTime createTime;
}
