package com.portfolio.cucumber.modules.model.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.model.entity.ModelVersion;
import com.portfolio.cucumber.modules.model.mapper.ModelVersionMapper;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/v1/model")
public class ModelController {

    private final ModelVersionMapper modelVersionMapper;

    public ModelController(ModelVersionMapper modelVersionMapper) {
        this.modelVersionMapper = modelVersionMapper;
    }

    @GetMapping
    public Result<List<ModelVersion>> list() {
        List<ModelVersion> models = modelVersionMapper.selectList(
                new LambdaQueryWrapper<ModelVersion>()
                        .orderByAsc(ModelVersion::getModelType)
                        .orderByDesc(ModelVersion::getCreateTime));
        return Result.success(models);
    }

    @PostMapping
    @PreAuthorize("hasAuthority('model:manage')")
    @OperLog("注册模型版本")
    public Result<Void> register(@RequestBody ModelVersion modelVersion) {
        Long count = modelVersionMapper.selectCount(new LambdaQueryWrapper<ModelVersion>()
                .eq(ModelVersion::getName, modelVersion.getName())
                .eq(ModelVersion::getVersion, modelVersion.getVersion()));
        if (count != null && count > 0) {
            throw new BizException("同名同版本模型已存在");
        }
        modelVersion.setId(null);
        modelVersion.setStatus("ARCHIVED");
        modelVersion.setCreateTime(LocalDateTime.now());
        modelVersionMapper.insert(modelVersion);
        return Result.success();
    }

    /**
     * 激活模型：同一 model_type 只允许一个 ACTIVE，其余置为 ARCHIVED。
     */
    @PutMapping("/{id}/activate")
    @PreAuthorize("hasAuthority('model:manage')")
    @OperLog("激活模型版本")
    @Transactional(rollbackFor = Exception.class)
    public Result<Void> activate(@PathVariable Long id) {
        ModelVersion target = modelVersionMapper.selectById(id);
        if (target == null) {
            throw new BizException("模型版本不存在");
        }
        modelVersionMapper.update(null, new LambdaUpdateWrapper<ModelVersion>()
                .eq(ModelVersion::getModelType, target.getModelType())
                .eq(ModelVersion::getStatus, "ACTIVE")
                .set(ModelVersion::getStatus, "ARCHIVED"));
        modelVersionMapper.update(null, new LambdaUpdateWrapper<ModelVersion>()
                .eq(ModelVersion::getId, id)
                .set(ModelVersion::getStatus, "ACTIVE"));
        return Result.success();
    }
}
