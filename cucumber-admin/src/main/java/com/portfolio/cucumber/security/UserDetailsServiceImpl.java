package com.portfolio.cucumber.security;

import com.portfolio.cucumber.modules.system.entity.SysRolePerm;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import com.portfolio.cucumber.modules.system.entity.SysUserRole;
import com.portfolio.cucumber.modules.system.mapper.SysRolePermMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserMapper;
import com.portfolio.cucumber.modules.system.mapper.SysUserRoleMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class UserDetailsServiceImpl implements UserDetailsService {

    private final SysUserMapper sysUserMapper;
    private final SysUserRoleMapper sysUserRoleMapper;
    private final SysRolePermMapper sysRolePermMapper;

    public UserDetailsServiceImpl(SysUserMapper sysUserMapper,
                                  SysUserRoleMapper sysUserRoleMapper,
                                  SysRolePermMapper sysRolePermMapper) {
        this.sysUserMapper = sysUserMapper;
        this.sysUserRoleMapper = sysUserRoleMapper;
        this.sysRolePermMapper = sysRolePermMapper;
    }

    @Override
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        SysUser user = sysUserMapper.selectOne(
                new LambdaQueryWrapper<SysUser>().eq(SysUser::getUsername, username));
        if (user == null) {
            throw new UsernameNotFoundException("用户不存在: " + username);
        }
        return new LoginUser(user.getId(), user.getUsername(), user.getPassword(), loadPerms(user.getId()));
    }

    /**
     * 查询用户全部权限标识（经 sys_user_role -> sys_role_perm 两表关联）。
     */
    public List<String> loadPerms(Long userId) {
        List<SysUserRole> userRoles = sysUserRoleMapper.selectList(
                new LambdaQueryWrapper<SysUserRole>().eq(SysUserRole::getUserId, userId));
        if (userRoles.isEmpty()) {
            return Collections.emptyList();
        }
        List<Long> roleIds = userRoles.stream().map(SysUserRole::getRoleId).collect(Collectors.toList());
        return sysRolePermMapper.selectList(
                        new LambdaQueryWrapper<SysRolePerm>().in(SysRolePerm::getRoleId, roleIds))
                .stream()
                .map(SysRolePerm::getPerm)
                .distinct()
                .collect(Collectors.toList());
    }
}
