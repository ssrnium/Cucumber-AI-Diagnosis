package com.portfolio.cucumber.modules.diagnosis.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Data
@TableName(value = "diagnosis_record", autoResultMap = true)
public class DiagnosisRecord {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String recordNo;
    private Long userId;
    private String imageUrl;

    /** 病斑框列表 [{x1,y1,x2,y2,confidence,label}]，PostgreSQL jsonb 存储 */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<Map<String, Object>> detections;

    /** 诊断报告 JSON，PostgreSQL jsonb 存储 */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private Map<String, Object> report;

    private String modelVersion;
    /** PENDING / DONE / FAILED */
    private String status;
    private LocalDateTime createTime;
}
