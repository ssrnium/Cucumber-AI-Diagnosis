package com.portfolio.cucumber.modules.knowledge.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.knowledge.entity.KnowledgeEntry;
import com.portfolio.cucumber.modules.knowledge.mapper.KnowledgeEntryMapper;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;

@RestController
@RequestMapping("/api/v1/knowledge")
public class KnowledgeController {

    private final KnowledgeEntryMapper knowledgeEntryMapper;

    public KnowledgeController(KnowledgeEntryMapper knowledgeEntryMapper) {
        this.knowledgeEntryMapper = knowledgeEntryMapper;
    }

    /**
     * 知识库查询：登录即可，按病害类型 / 关键词过滤。
     */
    @GetMapping
    public Result<PageResult<KnowledgeEntry>> list(@RequestParam(defaultValue = "1") long page,
                                                   @RequestParam(defaultValue = "10") long size,
                                                   @RequestParam(required = false) String diseaseType,
                                                   @RequestParam(required = false) String keyword) {
        LambdaQueryWrapper<KnowledgeEntry> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(diseaseType)) {
            wrapper.eq(KnowledgeEntry::getDiseaseType, diseaseType);
        }
        if (StringUtils.hasText(keyword)) {
            wrapper.and(w -> w.like(KnowledgeEntry::getTitle, keyword)
                    .or().like(KnowledgeEntry::getContent, keyword)
                    .or().like(KnowledgeEntry::getSourceId, keyword));
        }
        wrapper.eq(KnowledgeEntry::getStatus, 1).orderByAsc(KnowledgeEntry::getSourceId);
        Page<KnowledgeEntry> result = knowledgeEntryMapper.selectPage(new Page<>(page, size), wrapper);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @GetMapping("/{id}")
    public Result<KnowledgeEntry> detail(@PathVariable Long id) {
        KnowledgeEntry entry = knowledgeEntryMapper.selectById(id);
        if (entry == null) {
            throw new BizException("知识条目不存在");
        }
        return Result.success(entry);
    }

    @PostMapping
    @PreAuthorize("hasAuthority('knowledge:manage')")
    @OperLog("新增知识条目")
    public Result<Void> create(@RequestBody KnowledgeEntry entry) {
        Long count = knowledgeEntryMapper.selectCount(
                new LambdaQueryWrapper<KnowledgeEntry>().eq(KnowledgeEntry::getSourceId, entry.getSourceId()));
        if (count != null && count > 0) {
            throw new BizException("source_id 已存在");
        }
        entry.setId(null);
        entry.setStatus(entry.getStatus() == null ? 1 : entry.getStatus());
        entry.setCreateTime(LocalDateTime.now());
        knowledgeEntryMapper.insert(entry);
        return Result.success();
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('knowledge:manage')")
    @OperLog("修改知识条目")
    public Result<Void> update(@PathVariable Long id, @RequestBody KnowledgeEntry entry) {
        entry.setId(id);
        entry.setSourceId(null);
        knowledgeEntryMapper.updateById(entry);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('knowledge:manage')")
    @OperLog("删除知识条目")
    public Result<Void> delete(@PathVariable Long id) {
        knowledgeEntryMapper.deleteById(id);
        return Result.success();
    }
}
