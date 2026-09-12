package com.portfolio.cucumber.modules.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("sys_role_perm")
public class SysRolePerm {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long roleId;
    private String perm;
}
