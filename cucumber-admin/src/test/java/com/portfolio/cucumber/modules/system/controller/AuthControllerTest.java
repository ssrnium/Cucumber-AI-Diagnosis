package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.controller.AuthController.LoginRequest;
import com.portfolio.cucumber.modules.system.controller.AuthController.RegisterRequest;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.modules.system.mapper.SysRoleMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserRoleMapper;
import com.portfolio.cucumber.security.JwtUtils;
import com.portfolio.cucumber.security.UserDetailsServiceImpl;
import com.portfolio.cucumber.support.TestSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AuthController 单元测试：登录签发 JWT、密码错误拒绝、禁用账号拒绝、注册重名拒绝。
 */
@ExtendWith(MockitoExtension.class)
class AuthControllerTest {

    @Mock
    private SysUserMapper sysUserMapper;
    @Mock
    private SysRoleMapper sysRoleMapper;
    @Mock
    private SysUserRoleMapper sysUserRoleMapper;
    @Mock
    private PasswordEncoder passwordEncoder;
    @Mock
    private JwtUtils jwtUtils;
    @Mock
    private UserDetailsServiceImpl userDetailsService;

    private AuthController controller;

    @BeforeEach
    void setUp() {
        TestSupport.initTableInfos();
        controller = new AuthController(sysUserMapper, sysRoleMapper, sysUserRoleMapper,
                passwordEncoder, jwtUtils, userDetailsService);
    }

    private SysUser enabledUser() {
        SysUser user = new SysUser();
        user.setId(1L);
        user.setUsername("expert");
        user.setPassword("{bcrypt}hashed");
        user.setStatus(1);
        return user;
    }

    @Test
    void login_success_returnsTokenPermsAndHidesPassword() {
        // 业务含义：登录成功返回 token + 权限列表（前端按 perms 过滤菜单/按钮），
        // 且响应中的 userInfo 必须抹掉密码哈希，避免哈希外泄。
        SysUser user = enabledUser();
        when(sysUserMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(user);
        when(passwordEncoder.matches("secret", "{bcrypt}hashed")).thenReturn(true);
        when(userDetailsService.loadPerms(1L)).thenReturn(List.of("feedback:review"));
        when(jwtUtils.createToken(eq(1L), eq("expert"), anyList())).thenReturn("jwt-token");

        Result<Map<String, Object>> result = controller.login(new LoginRequest("expert", "secret"));

        assertThat(result.getCode()).isEqualTo(200);
        assertThat(result.getData().get("token")).isEqualTo("jwt-token");
        assertThat((List<String>) result.getData().get("perms")).containsExactly("feedback:review");
        SysUser userInfo = (SysUser) result.getData().get("userInfo");
        assertThat(userInfo.getPassword()).isNull();
    }

    @Test
    void login_wrongPassword_throwsAndNeverIssuesToken() {
        // 业务含义：密码错误拒绝，且绝不走到签发 token 一步。
        when(sysUserMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(enabledUser());
        when(passwordEncoder.matches("bad", "{bcrypt}hashed")).thenReturn(false);

        assertThatThrownBy(() -> controller.login(new LoginRequest("expert", "bad")))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("用户名或密码错误");
        verify(jwtUtils, never()).createToken(any(), any(), anyList());
    }

    @Test
    void login_unknownUser_throwsSameMessageAsWrongPassword() {
        // 业务含义：用户不存在与密码错误返回同一文案，避免暴露账号是否存在（防枚举）。
        when(sysUserMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);

        assertThatThrownBy(() -> controller.login(new LoginRequest("ghost", "secret")))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("用户名或密码错误");
    }

    @Test
    void login_disabledUser_throwsAndNeverIssuesToken() {
        // 业务含义：禁用账号即使密码正确也不能登录，token 不签发。
        SysUser user = enabledUser();
        user.setStatus(0);
        when(sysUserMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(user);
        when(passwordEncoder.matches("secret", "{bcrypt}hashed")).thenReturn(true);

        assertThatThrownBy(() -> controller.login(new LoginRequest("expert", "secret")))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("禁用");
        verify(jwtUtils, never()).createToken(any(), any(), anyList());
    }

    @Test
    void register_duplicateUsername_throwsAndNeverInserts() {
        // 业务含义：注册重名拒绝，不落库，保证用户名唯一约束在应用层先行拦截。
        when(sysUserMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(1L);

        assertThatThrownBy(() -> controller.register(new RegisterRequest("expert", "secret6", null)))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("已存在");
        verify(sysUserMapper, never()).insert(any(SysUser.class));
    }
}
