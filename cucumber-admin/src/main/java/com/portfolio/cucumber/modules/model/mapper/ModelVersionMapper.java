package com.portfolio.cucumber.modules.model.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.model.entity.ModelVersion;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ModelVersionMapper extends BaseMapper<ModelVersion> {
}
