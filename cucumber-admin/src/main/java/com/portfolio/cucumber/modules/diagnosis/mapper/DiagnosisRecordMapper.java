package com.portfolio.cucumber.modules.diagnosis.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

@Mapper
public interface DiagnosisRecordMapper extends BaseMapper<DiagnosisRecord> {

    /**
     * 近 30 天各病害类型分布（病害类型取自 report jsonb 的 disease_type 字段）。
     */
    @Select("SELECT report->>'disease_type' AS disease_type, COUNT(*) AS count "
            + "FROM diagnosis_record "
            + "WHERE status = 'DONE' AND create_time >= now() - interval '30 days' "
            + "GROUP BY report->>'disease_type' ORDER BY count DESC")
    List<Map<String, Object>> diseaseDistributionLast30Days();
}
