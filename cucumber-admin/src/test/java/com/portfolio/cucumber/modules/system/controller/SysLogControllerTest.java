package com.portfolio.cucumber.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.system.entity.SysOperationLog;
import com.portfolio.cucumber.modules.system.mapper.SysOperationLogMapper;
import com.portfolio.cucumber.support.TestSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * SysLogController 单元测试：操作日志分页结构（total/list）与用户名筛选。
 */
@ExtendWith(MockitoExtension.class)
class SysLogControllerTest {

    @Mock
    private SysOperationLogMapper sysOperationLogMapper;

    private SysLogController controller;

    @BeforeEach
    void setUp() {
        TestSupport.initTableInfos();
        controller = new SysLogController(sysOperationLogMapper);
    }

    @Test
    void list_returnsPagedTotalAndList() {
        // 业务含义：操作日志分页返回结构正确 —— total 为总条数、list 为当前页数据，
        // 前端审计页依赖该结构渲染分页器。
        SysOperationLog log1 = new SysOperationLog();
        log1.setId(2L);
        log1.setUsername("admin");
        log1.setOperation("激活模型版本");
        SysOperationLog log2 = new SysOperationLog();
        log2.setId(1L);
        log2.setUsername("expert");
        log2.setOperation("复核诊断反馈");
        Page<SysOperationLog> page = new Page<>(1, 10);
        page.setTotal(25L);
        page.setRecords(List.of(log1, log2));
        when(sysOperationLogMapper.selectPage(any(Page.class), any(LambdaQueryWrapper.class)))
                .thenReturn(page);

        Result<PageResult<SysOperationLog>> result = controller.list(1, 10, null);

        assertThat(result.getCode()).isEqualTo(200);
        PageResult<SysOperationLog> data = result.getData();
        assertThat(data.getTotal()).isEqualTo(25L);
        assertThat(data.getList()).hasSize(2);
        assertThat(data.getList().get(0).getOperation()).isEqualTo("激活模型版本");
    }

    @Test
    void list_withUsernameFilter_appliesLikeCondition() {
        // 业务含义：按用户名模糊筛选日志时，wrapper 带 username LIKE 条件，支撑审计追溯按人查询。
        when(sysOperationLogMapper.selectPage(any(Page.class), any(LambdaQueryWrapper.class)))
                .thenReturn(new Page<>());

        controller.list(1, 10, "admin");

        ArgumentCaptor<LambdaQueryWrapper<SysOperationLog>> captor = ArgumentCaptor.forClass(LambdaQueryWrapper.class);
        verify(sysOperationLogMapper).selectPage(any(Page.class), captor.capture());
        assertThat(captor.getValue().getSqlSegment()).contains("username").contains("LIKE");
        assertThat(captor.getValue().getParamNameValuePairs()).containsValue("%admin%");
    }
}
