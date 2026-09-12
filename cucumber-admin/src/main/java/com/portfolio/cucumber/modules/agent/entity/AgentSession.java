package com.portfolio.cucumber.modules.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("agent_session")
public class AgentSession {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String convId;
    private Long userId;
    private String primaryAgent;
    private String lastIntent;
    private Boolean escalated;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
