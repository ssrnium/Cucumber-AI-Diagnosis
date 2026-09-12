package com.portfolio.cucumber;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
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
            "system:role:delete", "system:role:assign",
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
     * 示例知识库：与 cucumber-ai/data/disease_knowledge.json 同结构、同 source_id。
     */
    private void seedKnowledge() {
        createKnowledge("KB-JC-001", "炭疽病", "黄瓜炭疽病症状识别",
                "叶片初期出现水渍状小斑点，后扩大为圆形至不规则形褐色病斑，边缘有黄色晕圈，"
                        + "严重时病斑中央穿孔。茎蔓受害呈梭形凹陷斑。高湿环境下病斑上产生粉红色黏质孢子堆。",
                "A", "症状");
        createKnowledge("KB-SH-002", "霜霉病", "黄瓜霜霉病症状识别",
                "叶片正面出现多角形淡黄色至黄褐色病斑，受叶脉限制呈角状；叶背对应位置在清晨或高湿时"
                        + "长出灰黑色至紫灰色霉层。病害自下而上扩展，严重时全叶枯死。",
                "A", "症状");
        createKnowledge("KB-MK-003", "蔓枯病", "黄瓜蔓枯病症状识别",
                "叶片多从叶缘开始发病，形成 V 字形或不规则形大斑，黄褐色，上有轮纹并散生小黑点；"
                        + "茎蔓受害呈油渍状纵裂，溢出琥珀色胶状物，后期病部干枯。",
                "B", "症状");
        createKnowledge("KB-BF-004", "白粉病", "黄瓜白粉病防治",
                "发病初期叶面出现白色近圆形粉斑，扩展后连片呈白粉状。防治以选用抗病品种、合理密植、"
                        + "控制氮肥为主；发病初期可喷施醚菌酯、氟硅唑或硫磺悬浮剂，注意轮换用药。",
                "A", "防治");
        createKnowledge("KB-JK-005", "健康叶", "健康黄瓜叶片特征",
                "健康黄瓜叶片呈掌状五角形，叶色浓绿有光泽，叶面平展无病斑、无粉层、无霉层，"
                        + "叶缘锯齿清晰，叶脉纹理正常。保持良好通风透光与水肥均衡是预防病害的基础。",
                "B", "防治");
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
