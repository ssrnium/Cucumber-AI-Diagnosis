package com.portfolio.cucumber.modules.model.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.model.entity.ModelVersion;
import com.portfolio.cucumber.modules.model.mapper.ModelVersionMapper;
import com.portfolio.cucumber.support.TestSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ModelController 单元测试：模型激活互斥（同类型只允许一个 ACTIVE）、注册查重。
 */
@ExtendWith(MockitoExtension.class)
class ModelControllerTest {

    @Mock
    private ModelVersionMapper modelVersionMapper;

    private ModelController controller;

    @BeforeEach
    void setUp() {
        TestSupport.initTableInfos();
        controller = new ModelController(modelVersionMapper);
    }

    @Test
    void activate_archivesOtherActiveModelsOfSameType_thenActivatesTarget() {
        // 业务含义：激活某个 DETECTION 模型时，同类型其他 ACTIVE 模型先转 ARCHIVED（互斥），
        // 再把目标模型置 ACTIVE —— 保证线上同时只有一个生效的检测模型。
        ModelVersion target = new ModelVersion();
        target.setId(3L);
        target.setName("yolov8-cucumber");
        target.setVersion("v3");
        target.setModelType("DETECTION");
        when(modelVersionMapper.selectById(3L)).thenReturn(target);

        Result<Void> result = controller.activate(3L);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<LambdaUpdateWrapper<ModelVersion>> captor = ArgumentCaptor.forClass(LambdaUpdateWrapper.class);
        verify(modelVersionMapper, times(2)).update(isNull(), captor.capture());
        List<LambdaUpdateWrapper<ModelVersion>> wrappers = captor.getAllValues();

        // 第一步：把同类型（DETECTION）且当前 ACTIVE 的全部置 ARCHIVED
        LambdaUpdateWrapper<ModelVersion> archive = wrappers.get(0);
        assertThat(archive.getSqlSegment()).contains("model_type").contains("status");
        assertThat(archive.getParamNameValuePairs()).containsValue("DETECTION");
        assertThat(archive.getSqlSet()).contains("status");
        assertThat(archive.getParamNameValuePairs()).containsValue("ARCHIVED");

        // 第二步：把目标 id 置 ACTIVE
        LambdaUpdateWrapper<ModelVersion> activate = wrappers.get(1);
        assertThat(activate.getSqlSegment()).contains("id");
        assertThat(activate.getParamNameValuePairs()).containsValue(3L);
        assertThat(activate.getParamNameValuePairs()).containsValue("ACTIVE");
    }

    @Test
    void activate_whenModelMissing_throwsBizException() {
        // 业务含义：激活不存在的模型版本 → 业务异常，不执行任何更新。
        when(modelVersionMapper.selectById(404L)).thenReturn(null);

        assertThatThrownBy(() -> controller.activate(404L))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("模型版本不存在");
        verify(modelVersionMapper, never()).update(any(), any(LambdaUpdateWrapper.class));
    }

    @Test
    void register_whenSameNameAndVersionExists_throwsBizException() {
        // 业务含义：同名同版本模型禁止重复注册（版本唯一性约束）。
        when(modelVersionMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(1L);
        ModelVersion dup = new ModelVersion();
        dup.setName("yolov8-cucumber");
        dup.setVersion("v3");

        assertThatThrownBy(() -> controller.register(dup))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("同名同版本模型已存在");
        verify(modelVersionMapper, never()).insert(any(ModelVersion.class));
    }

    @Test
    void register_newModel_savesAsArchived() {
        // 业务含义：新注册的模型默认 ARCHIVED，必须显式激活才能上线（防止误发布）。
        when(modelVersionMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);
        ModelVersion model = new ModelVersion();
        model.setId(777L); // 伪造 id，应被清空
        model.setName("yolov8-cucumber");
        model.setVersion("v4");
        model.setModelType("DETECTION");

        Result<Void> result = controller.register(model);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<ModelVersion> captor = ArgumentCaptor.forClass(ModelVersion.class);
        verify(modelVersionMapper).insert(captor.capture());
        assertThat(captor.getValue().getId()).isNull();
        assertThat(captor.getValue().getStatus()).isEqualTo("ARCHIVED");
        assertThat(captor.getValue().getCreateTime()).isNotNull();
    }
}
