package com.portfolio.cucumber.modules.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.agent.entity.AgentMessage;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AgentMessageMapper extends BaseMapper<AgentMessage> {
}
