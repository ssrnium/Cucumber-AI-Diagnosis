package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.modules.system.entity.SysUserRole;
import com.portfolio.cucumber.modules.system.mapper.SysUserMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserRoleMapper;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/v1/system/user")
public class SysUserController {

    private final SysUserMapper sysUserMapper;
    private final SysUserRoleMapper sysUserRoleMapper;
    private final PasswordEncoder passwordEncoder;

    public SysUserController(SysUserMapper sysUserMapper,
                             SysUserRoleMapper sysUserRoleMapper,
                             PasswordEncoder passwordEncoder) {
        this.sysUserMapper = sysUserMapper;
        this.sysUserRoleMapper = sysUserRoleMapper;
        this.passwordEncoder = passwordEncoder;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('system:user:list')")
    public Result<PageResult<SysUser>> list(@RequestParam(defaultValue = "1") long page,
                                            @RequestParam(defaultValue = "10") long size,
                                            @RequestParam(required = false) String keyword) {
        LambdaQueryWrapper<SysUser> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(keyword)) {
            wrapper.like(SysUser::getUsername, keyword).or().like(SysUser::getNickname, keyword);
        }
        wrapper.orderByDesc(SysUser::getCreateTime);
        Page<SysUser> result = sysUserMapper.selectPage(new Page<>(page, size), wrapper);
        result.getRecords().forEach(user -> user.setPassword(null));
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @PostMapping
    @PreAuthorize("hasAuthority('system:user:create')")
    @OperLog("新增用户")
    public Result<Void> create(@RequestBody SysUser user) {
        Long count = sysUserMapper.selectCount(
                new LambdaQueryWrapper<SysUser>().eq(SysUser::getUsername, user.getUsername()));
        if (count != null && count > 0) {
            throw new BizException("用户名已存在");
        }
        user.setId(null);
        String rawPassword = StringUtils.hasText(user.getPassword()) ? user.getPassword() : "123456";
        user.setPassword(passwordEncoder.encode(rawPassword));
        user.setStatus(user.getStatus() == null ? 1 : user.getStatus());
        user.setCreateTime(LocalDateTime.now());
        user.setUpdateTime(LocalDateTime.now());
        sysUserMapper.insert(user);
        return Result.success();
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('system:user:update')")
    @OperLog("修改用户")
    public Result<Void> update(@PathVariable Long id, @RequestBody SysUser user) {
        user.setId(id);
        user.setUsername(null);
        user.setPassword(null);
        user.setUpdateTime(LocalDateTime.now());
        sysUserMapper.updateById(user);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('system:user:delete')")
    @OperLog("删除用户")
    public Result<Void> delete(@PathVariable Long id) {
        sysUserMapper.deleteById(id);
        sysUserRoleMapper.delete(new LambdaQueryWrapper<SysUserRole>().eq(SysUserRole::getUserId, id));
        return Result.success();
    }

    @PutMapping("/{id}/reset-password")
    @PreAuthorize("hasAuthority('system:user:reset')")
    @OperLog("重置密码")
    public Result<Void> resetPassword(@PathVariable Long id, @RequestBody Map<String, String> body) {
        String newPassword = body.get("password");
        if (!StringUtils.hasText(newPassword)) {
            newPassword = "123456";
        }
        SysUser user = new SysUser();
        user.setId(id);
        user.setPassword(passwordEncoder.encode(newPassword));
        user.setUpdateTime(LocalDateTime.now());
        sysUserMapper.updateById(user);
        return Result.success();
    }

    @GetMapping("/{id}/roles")
    @PreAuthorize("hasAuthority('system:user:list')")
    public Result<List<Long>> userRoles(@PathVariable Long id) {
        List<Long> roleIds = sysUserRoleMapper.selectList(
                        new LambdaQueryWrapper<SysUserRole>().eq(SysUserRole::getUserId, id))
                .stream().map(SysUserRole::getRoleId).collect(Collectors.toList());
        return Result.success(roleIds);
    }

    @PutMapping("/{id}/roles")
    @PreAuthorize("hasAuthority('system:user:assign')")
    @OperLog("分配角色")
    public Result<Void> assignRoles(@PathVariable Long id, @RequestBody Map<String, List<Long>> body) {
        List<Long> roleIds = body.getOrDefault("roleIds", List.of());
        sysUserRoleMapper.delete(new LambdaQueryWrapper<SysUserRole>().eq(SysUserRole::getUserId, id));
        for (Long roleId : roleIds) {
            SysUserRole relation = new SysUserRole();
            relation.setUserId(id);
            relation.setRoleId(roleId);
            sysUserRoleMapper.insert(relation);
        }
        return Result.success();
    }
}
