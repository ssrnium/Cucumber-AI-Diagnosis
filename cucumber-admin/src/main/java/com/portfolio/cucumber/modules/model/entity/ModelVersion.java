package com.portfolio.cucumber.modules.model.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

@Data
@TableName(value = "model_version", autoResultMap = true)
public class ModelVersion {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String name;
    private String version;
    /** DETECTION / LLM */
    private String modelType;
    private String weightsPath;
    private String sha256;

    /** 评测指标 JSON，如 {"mAP50": 0.93} */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private Map<String, Object> metrics;

    /** ACTIVE / ARCHIVED */
    private String status;
    private LocalDateTime createTime;
}
