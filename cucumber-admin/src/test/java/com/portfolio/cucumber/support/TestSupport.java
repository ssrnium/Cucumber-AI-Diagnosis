package com.portfolio.cucumber.support;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.portfolio.cucumber.modules.agent.entity.AgentMessage;
import com.portfolio.cucumber.modules.agent.entity.AgentSession;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisFeedback;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import com.portfolio.cucumber.modules.model.entity.ModelVersion;
import com.portfolio.cucumber.modules.system.entity.SysOperationLog;
import com.portfolio.cucumber.modules.system.entity.SysRole;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.security.LoginUser;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;

/**
 * 单测公共支撑：纯单元测试不启动 Spring / MyBatis 容器，
 * 但 MyBatis-Plus 的 LambdaQueryWrapper 在拼条件时需要实体的 TableInfo 元数据，
 * 这里手工初始化一次；登录态直接写入 SecurityContextHolder（SecurityUtils 即从此读取）。
 */
public final class TestSupport {

    private TestSupport() {
    }

    /** 初始化实体 TableInfo（幂等），否则 wrapper.eq(Entity::getXxx, ...) 会报 "can not find lambda cache" */
    public static void initTableInfos() {
        MapperBuilderAssistant assistant = new MapperBuilderAssistant(new MybatisConfiguration(), "");
        init(assistant, DiagnosisRecord.class);
        init(assistant, DiagnosisFeedback.class);
        init(assistant, ModelVersion.class);
        init(assistant, SysOperationLog.class);
        init(assistant, SysUser.class);
        init(assistant, SysRole.class);
        init(assistant, AgentSession.class);
        init(assistant, AgentMessage.class);
    }

    private static void init(MapperBuilderAssistant assistant, Class<?> entityClass) {
        if (TableInfoHelper.getTableInfo(entityClass) == null) {
            TableInfoHelper.initTableInfo(assistant, entityClass);
        }
    }

    /** 模拟登录：SecurityUtils.current()/hasAuthority() 读取的就是这里写入的上下文 */
    public static void loginAs(Long userId, String... perms) {
        LoginUser loginUser = new LoginUser(userId, "user" + userId, "", List.of(perms));
        UsernamePasswordAuthenticationToken authentication =
                new UsernamePasswordAuthenticationToken(loginUser, null, loginUser.getAuthorities());
        SecurityContextHolder.getContext().setAuthentication(authentication);
    }

    public static void logout() {
        SecurityContextHolder.clearContext();
    }
}
