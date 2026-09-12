package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.entity.SysRole;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.modules.system.entity.SysUserRole;
import com.portfolio.cucumber.modules.system.mapper.SysRoleMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserRoleMapper;
import com.portfolio.cucumber.security.JwtUtils;
import com.portfolio.cucumber.security.LoginUser;
import com.portfolio.cucumber.security.SecurityUtils;
import com.portfolio.cucumber.security.UserDetailsServiceImpl;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    public record LoginRequest(@NotBlank(message = "用户名不能为空") String username,
                               @NotBlank(message = "密码不能为空") String password) {
    }

    public record RegisterRequest(@NotBlank(message = "用户名不能为空")
                                  @Size(min = 3, max = 20, message = "用户名长度需在 3-20 之间") String username,
                                  @NotBlank(message = "密码不能为空")
                                  @Size(min = 6, max = 32, message = "密码长度需在 6-32 之间") String password,
                                  String nickname) {
    }

    private final SysUserMapper sysUserMapper;
    private final SysRoleMapper sysRoleMapper;
    private final SysUserRoleMapper sysUserRoleMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtils jwtUtils;
    private final UserDetailsServiceImpl userDetailsService;

    public AuthController(SysUserMapper sysUserMapper,
                          SysRoleMapper sysRoleMapper,
                          SysUserRoleMapper sysUserRoleMapper,
                          PasswordEncoder passwordEncoder,
                          JwtUtils jwtUtils,
                          UserDetailsServiceImpl userDetailsService) {
        this.sysUserMapper = sysUserMapper;
        this.sysRoleMapper = sysRoleMapper;
        this.sysUserRoleMapper = sysUserRoleMapper;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtils = jwtUtils;
        this.userDetailsService = userDetailsService;
    }

    @PostMapping("/login")
    public Result<Map<String, Object>> login(@Validated @RequestBody LoginRequest request) {
        SysUser user = sysUserMapper.selectOne(
                new LambdaQueryWrapper<SysUser>().eq(SysUser::getUsername, request.username()));
        if (user == null || !passwordEncoder.matches(request.password(), user.getPassword())) {
            throw new BizException("用户名或密码错误");
        }
        if (user.getStatus() != null && user.getStatus() == 0) {
            throw new BizException("账号已被禁用，请联系管理员");
        }
        List<String> perms = userDetailsService.loadPerms(user.getId());
        String token = jwtUtils.createToken(user.getId(), user.getUsername(), perms);

        user.setPassword(null);
        Map<String, Object> data = new HashMap<>();
        data.put("token", token);
        data.put("userInfo", user);
        data.put("perms", perms);
        return Result.success(data);
    }

    @PostMapping("/register")
    public Result<Void> register(@Validated @RequestBody RegisterRequest request) {
        Long count = sysUserMapper.selectCount(
                new LambdaQueryWrapper<SysUser>().eq(SysUser::getUsername, request.username()));
        if (count != null && count > 0) {
            throw new BizException("用户名已存在");
        }
        SysUser user = new SysUser();
        user.setUsername(request.username());
        user.setPassword(passwordEncoder.encode(request.password()));
        user.setNickname(request.nickname() == null || request.nickname().isBlank()
                ? request.username() : request.nickname());
        user.setStatus(1);
        user.setCreateTime(LocalDateTime.now());
        user.setUpdateTime(LocalDateTime.now());
        sysUserMapper.insert(user);

        SysRole userRole = sysRoleMapper.selectOne(
                new LambdaQueryWrapper<SysRole>().eq(SysRole::getCode, "USER"));
        if (userRole != null) {
            SysUserRole relation = new SysUserRole();
            relation.setUserId(user.getId());
            relation.setRoleId(userRole.getId());
            sysUserRoleMapper.insert(relation);
        }
        return Result.success();
    }

    @GetMapping("/profile")
    public Result<Map<String, Object>> profile() {
        LoginUser loginUser = SecurityUtils.current();
        if (loginUser == null) {
            throw new BizException(401, "未登录或登录已过期");
        }
        SysUser user = sysUserMapper.selectById(loginUser.getUserId());
        if (user == null) {
            throw new BizException("用户不存在");
        }
        user.setPassword(null);
        Map<String, Object> data = new HashMap<>();
        data.put("userInfo", user);
        data.put("perms", loginUser.getPerms());
        return Result.success(data);
    }
}
