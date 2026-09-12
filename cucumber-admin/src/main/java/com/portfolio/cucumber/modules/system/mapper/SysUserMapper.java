package com.portfolio.cucumber.modules.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.system.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SysUserMapper extends BaseMapper<SysUser> {
}
