package com.portfolio.cucumber.modules.knowledge.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("knowledge_entry")
public class KnowledgeEntry {

    @TableId(type = IdType.AUTO)
    private Long id;
    /** 来源编号，格式 KB-XXX-NNN，用于报告中的来源追溯 */
    private String sourceId;
    private String diseaseType;
    private String title;
    private String content;
    /** 证据等级 A/B/C */
    private String level;
    /** 分类：症状/防治/药剂 */
    private String category;
    private Integer status;
    private LocalDateTime createTime;
}
