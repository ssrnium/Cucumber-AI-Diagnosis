package com.portfolio.cucumber.modules.stats.controller;

import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisFeedbackMapper;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisRecordMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/stats")
public class StatsController {

    private final DiagnosisRecordMapper diagnosisRecordMapper;
    private final DiagnosisFeedbackMapper diagnosisFeedbackMapper;

    public StatsController(DiagnosisRecordMapper diagnosisRecordMapper,
                           DiagnosisFeedbackMapper diagnosisFeedbackMapper) {
        this.diagnosisRecordMapper = diagnosisRecordMapper;
        this.diagnosisFeedbackMapper = diagnosisFeedbackMapper;
    }

    /**
     * 首页看板总览：累计诊断数、今日诊断数、近 30 天病害分布、反馈准确率。
     */
    @GetMapping("/overview")
    public Result<Map<String, Object>> overview() {
        Long totalCount = diagnosisRecordMapper.selectCount(null);
        Long todayCount = diagnosisRecordMapper.selectCount(new LambdaQueryWrapper<DiagnosisRecord>()
                .ge(DiagnosisRecord::getCreateTime, LocalDate.now().atStartOfDay()));
        List<Map<String, Object>> distribution = diagnosisRecordMapper.diseaseDistributionLast30Days();

        long correct = 0;
        long wrong = 0;
        for (Map<String, Object> row : diagnosisFeedbackMapper.verdictCounts()) {
            long count = ((Number) row.get("count")).longValue();
            if ("CORRECT".equals(row.get("verdict"))) {
                correct = count;
            } else if ("WRONG".equals(row.get("verdict"))) {
                wrong = count;
            }
        }
        double feedbackAccuracy = (correct + wrong) == 0 ? 0.0 : (double) correct / (correct + wrong);

        Map<String, Object> data = new HashMap<>();
        data.put("totalCount", totalCount == null ? 0 : totalCount);
        data.put("todayCount", todayCount == null ? 0 : todayCount);
        data.put("diseaseDistribution", distribution);
        data.put("feedbackAccuracy", Math.round(feedbackAccuracy * 10000) / 100.0);
        return Result.success(data);
    }
}
