package com.portfolio.cucumber.modules.diagnosis.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("diagnosis_feedback")
public class DiagnosisFeedback {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long recordId;
    private Long userId;
    /** CORRECT / WRONG */
    private String verdict;
    private String correctedDiseaseType;
    private String comment;
    /** PENDING / REVIEWED */
    private String reviewStatus;
    private Long reviewerId;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
