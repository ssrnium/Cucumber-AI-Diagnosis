package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.entity.SysOperationLog;
import com.portfolio.cucumber.modules.system.mapper.SysOperationLogMapper;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 操作日志查询（只读）：配合 OperLog 切面写入，支撑审计追溯验收。
 */
@RestController
@RequestMapping("/api/v1/system/log")
public class SysLogController {

    private final SysOperationLogMapper sysOperationLogMapper;

    public SysLogController(SysOperationLogMapper sysOperationLogMapper) {
        this.sysOperationLogMapper = sysOperationLogMapper;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('system:log:list')")
    public Result<PageResult<SysOperationLog>> list(@RequestParam(defaultValue = "1") long page,
                                                    @RequestParam(defaultValue = "10") long size,
                                                    @RequestParam(required = false) String username) {
        LambdaQueryWrapper<SysOperationLog> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(username)) {
            wrapper.like(SysOperationLog::getUsername, username);
        }
        wrapper.orderByDesc(SysOperationLog::getId);
        Page<SysOperationLog> result = sysOperationLogMapper.selectPage(new Page<>(page, size), wrapper);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }
}
