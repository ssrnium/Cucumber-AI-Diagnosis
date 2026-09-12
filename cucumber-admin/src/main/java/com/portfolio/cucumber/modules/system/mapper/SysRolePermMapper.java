package com.portfolio.cucumber.modules.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.system.entity.SysRolePerm;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SysRolePermMapper extends BaseMapper<SysRolePerm> {
}
