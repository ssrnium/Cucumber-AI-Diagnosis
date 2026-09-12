package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import com.portfolio.cucumber.modules.system.entity.SysRole;
import com.portfolio.cucumber.modules.system.entity.SysRolePerm;
import com.portfolio.cucumber.modules.system.mapper.SysRoleMapper;
import com.portfolio.cucumber.modules.system.mapper.SysRolePermMapper;
import org.springframework.security.access.prepost.PreAuthorize;
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
@RequestMapping("/api/v1/system/role")
public class SysRoleController {

    private final SysRoleMapper sysRoleMapper;
    private final SysRolePermMapper sysRolePermMapper;

    public SysRoleController(SysRoleMapper sysRoleMapper, SysRolePermMapper sysRolePermMapper) {
        this.sysRoleMapper = sysRoleMapper;
        this.sysRolePermMapper = sysRolePermMapper;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('system:role:list')")
    public Result<PageResult<SysRole>> list(@RequestParam(defaultValue = "1") long page,
                                            @RequestParam(defaultValue = "10") long size,
                                            @RequestParam(required = false) String keyword) {
        LambdaQueryWrapper<SysRole> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(keyword)) {
            wrapper.like(SysRole::getName, keyword).or().like(SysRole::getCode, keyword);
        }
        wrapper.orderByAsc(SysRole::getId);
        Page<SysRole> result = sysRoleMapper.selectPage(new Page<>(page, size), wrapper);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @GetMapping("/all")
    @PreAuthorize("hasAuthority('system:role:list')")
    public Result<List<SysRole>> all() {
        return Result.success(sysRoleMapper.selectList(new LambdaQueryWrapper<SysRole>().orderByAsc(SysRole::getId)));
    }

    @PostMapping
    @PreAuthorize("hasAuthority('system:role:create')")
    @OperLog("新增角色")
    public Result<Void> create(@RequestBody SysRole role) {
        Long count = sysRoleMapper.selectCount(
                new LambdaQueryWrapper<SysRole>().eq(SysRole::getCode, role.getCode()));
        if (count != null && count > 0) {
            throw new BizException("角色编码已存在");
        }
        role.setId(null);
        role.setCreateTime(LocalDateTime.now());
        sysRoleMapper.insert(role);
        return Result.success();
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('system:role:update')")
    @OperLog("修改角色")
    public Result<Void> update(@PathVariable Long id, @RequestBody SysRole role) {
        role.setId(id);
        role.setCode(null);
        sysRoleMapper.updateById(role);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('system:role:delete')")
    @OperLog("删除角色")
    public Result<Void> delete(@PathVariable Long id) {
        sysRoleMapper.deleteById(id);
        sysRolePermMapper.delete(new LambdaQueryWrapper<SysRolePerm>().eq(SysRolePerm::getRoleId, id));
        return Result.success();
    }

    @GetMapping("/{id}/perms")
    @PreAuthorize("hasAuthority('system:role:list')")
    public Result<List<String>> rolePerms(@PathVariable Long id) {
        List<String> perms = sysRolePermMapper.selectList(
                        new LambdaQueryWrapper<SysRolePerm>().eq(SysRolePerm::getRoleId, id))
                .stream().map(SysRolePerm::getPerm).collect(Collectors.toList());
        return Result.success(perms);
    }

    @PutMapping("/{id}/perms")
    @PreAuthorize("hasAuthority('system:role:assign')")
    @OperLog("分配权限")
    public Result<Void> assignPerms(@PathVariable Long id, @RequestBody Map<String, List<String>> body) {
        List<String> perms = body.getOrDefault("perms", List.of());
        sysRolePermMapper.delete(new LambdaQueryWrapper<SysRolePerm>().eq(SysRolePerm::getRoleId, id));
        for (String perm : perms) {
            SysRolePerm rolePerm = new SysRolePerm();
            rolePerm.setRoleId(id);
            rolePerm.setPerm(perm);
            sysRolePermMapper.insert(rolePerm);
        }
        return Result.success();
    }
}
