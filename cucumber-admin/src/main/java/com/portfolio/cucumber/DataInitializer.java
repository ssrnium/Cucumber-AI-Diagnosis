package com.portfolio.cucumber;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.portfolio.cucumber.modules.knowledge.entity.KnowledgeEntry;
import com.portfolio.cucumber.modules.knowledge.mapper.KnowledgeEntryMapper;
import com.portfolio.cucumber.modules.system.entity.SysRole;
import com.portfolio.cucumber.modules.system.entity.SysRolePerm;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.modules.system.entity.SysUserRole;
import com.portfolio.cucumber.modules.system.mapper.SysRoleMapper;
import com.portfolio.cucumber.modules.system.mapper.SysRolePermMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserRoleMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 数据初始化：表为空时写入默认账号、角色权限与示例知识库。
 * 密码在启动时由 BCryptPasswordEncoder 现场编码，不硬编码 hash。
 * 默认账号：admin/Admin@123、expert/Expert@123、user/User@123、svc-agent/SvcAgent@123（SERVICE）。
 */
@Component
public class DataInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DataInitializer.class);

    private static final List<String> ADMIN_PERMS = List.of(
            "system:user:list", "system:user:create", "system:user:update",
            "system:user:delete", "system:user:reset", "system:user:assign",
            "system:role:list", "system:role:create", "system:role:update",
            "system:role:delete", "system:role:assign", "system:log:list",
            "knowledge:manage", "feedback:review", "model:manage", "diagnosis:list:all",
            "agent:chat", "agent:monitor", "agent:eval", "agent:skills");

    private static final List<String> EXPERT_PERMS = List.of(
            "knowledge:manage", "feedback:review", "model:manage", "diagnosis:list:all",
            "agent:chat", "agent:monitor", "agent:eval", "agent:skills");

    private static final List<String> USER_PERMS = List.of("agent:chat");

    /** 智能体服务账号：仅业务查询与反馈创建（配合 /diagnosis/{id}/feedback 无额外权限注解） */
    private static final List<String> SERVICE_PERMS = List.of("diagnosis:list:all");

    private final SysUserMapper sysUserMapper;
    private final SysRoleMapper sysRoleMapper;
    private final SysUserRoleMapper sysUserRoleMapper;
    private final SysRolePermMapper sysRolePermMapper;
    private final KnowledgeEntryMapper knowledgeEntryMapper;
    private final PasswordEncoder passwordEncoder;

    public DataInitializer(SysUserMapper sysUserMapper,
                           SysRoleMapper sysRoleMapper,
                           SysUserRoleMapper sysUserRoleMapper,
                           SysRolePermMapper sysRolePermMapper,
                           KnowledgeEntryMapper knowledgeEntryMapper,
                           PasswordEncoder passwordEncoder) {
        this.sysUserMapper = sysUserMapper;
        this.sysRoleMapper = sysRoleMapper;
        this.sysUserRoleMapper = sysUserRoleMapper;
        this.sysRolePermMapper = sysRolePermMapper;
        this.knowledgeEntryMapper = knowledgeEntryMapper;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(ApplicationArguments args) {
        Long userCount = sysUserMapper.selectCount(null);
        if (userCount != null && userCount > 0) {
            return;
        }
        log.info("检测到空库，写入初始化数据（默认账号 / 角色权限 / 示例知识库）");

        SysRole adminRole = createRole("ADMIN", "系统管理员", "拥有全部权限");
        SysRole expertRole = createRole("EXPERT", "农技专家", "知识库管理与反馈复核");
        SysRole userRole = createRole("USER", "普通用户", "叶片诊断与历史查询");
        SysRole serviceRole = createRole("SERVICE", "服务账号", "智能体服务（svc-agent）业务查询与反馈创建");

        createUser("admin", "Admin@123", "管理员", adminRole);
        createUser("expert", "Expert@123", "农技专家", expertRole);
        createUser("user", "User@123", "种植户", userRole);
        // 智能体服务账号：密码由环境变量覆盖，默认仅用于本地联调
        createUser("svc-agent", System.getenv().getOrDefault("SVC_AGENT_PASSWORD", "SvcAgent@123"),
                "智能体服务", serviceRole);

        ADMIN_PERMS.forEach(perm -> createRolePerm(adminRole.getId(), perm));
        EXPERT_PERMS.forEach(perm -> createRolePerm(expertRole.getId(), perm));
        USER_PERMS.forEach(perm -> createRolePerm(userRole.getId(), perm));
        SERVICE_PERMS.forEach(perm -> createRolePerm(serviceRole.getId(), perm));

        seedKnowledge();
    }

    private SysRole createRole(String code, String name, String remark) {
        SysRole role = new SysRole();
        role.setCode(code);
        role.setName(name);
        role.setRemark(remark);
        role.setCreateTime(LocalDateTime.now());
        sysRoleMapper.insert(role);
        return role;
    }

    private void createUser(String username, String rawPassword, String nickname, SysRole role) {
        SysUser user = new SysUser();
        user.setUsername(username);
        user.setPassword(passwordEncoder.encode(rawPassword));
        user.setNickname(nickname);
        user.setStatus(1);
        user.setCreateTime(LocalDateTime.now());
        user.setUpdateTime(LocalDateTime.now());
        sysUserMapper.insert(user);

        SysUserRole relation = new SysUserRole();
        relation.setUserId(user.getId());
        relation.setRoleId(role.getId());
        sysUserRoleMapper.insert(relation);
    }

    private void createRolePerm(Long roleId, String perm) {
        SysRolePerm rolePerm = new SysRolePerm();
        rolePerm.setRoleId(roleId);
        rolePerm.setPerm(perm);
        sysRolePermMapper.insert(rolePerm);
    }

    /**
     * 知识库种子：加载 db/knowledge_seed.json（由 cucumber-ai 的论文嵌套知识库聚合生成，
     * 28 个真实 source_id，与诊断报告的 source_ids 引用一致，支撑来源追溯）。
     */
    private void seedKnowledge() {
        try {
            ClassPathResource resource = new ClassPathResource("db/knowledge_seed.json");
            List<KnowledgeEntry> entries = new ObjectMapper().readValue(
                    resource.getInputStream(), new TypeReference<List<KnowledgeEntry>>() {
                    });
            for (KnowledgeEntry e : entries) {
                createKnowledge(e.getSourceId(), e.getDiseaseType(), e.getTitle(),
                        e.getContent(), e.getLevel(), e.getCategory());
            }
        } catch (Exception e) {
            log.warn("知识库种子加载失败: {}", e.getMessage());
        }
    }

    private void createKnowledge(String sourceId, String diseaseType, String title,
                                 String content, String level, String category) {
        Long count = knowledgeEntryMapper.selectCount(
                new LambdaQueryWrapper<KnowledgeEntry>().eq(KnowledgeEntry::getSourceId, sourceId));
        if (count != null && count > 0) {
            return;
        }
        KnowledgeEntry entry = new KnowledgeEntry();
        entry.setSourceId(sourceId);
        entry.setDiseaseType(diseaseType);
        entry.setTitle(title);
        entry.setContent(content);
        entry.setLevel(level);
        entry.setCategory(category);
        entry.setStatus(1);
        entry.setCreateTime(LocalDateTime.now());
        knowledgeEntryMapper.insert(entry);
    }
}
