package com.portfolio.cucumber.modules.diagnosis.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisFeedback;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

@Mapper
public interface DiagnosisFeedbackMapper extends BaseMapper<DiagnosisFeedback> {

    /**
     * 反馈判定统计（verdict: CORRECT / WRONG），用于计算反馈准确率。
     */
    @Select("SELECT verdict, COUNT(*) AS count FROM diagnosis_feedback GROUP BY verdict")
    List<Map<String, Object>> verdictCounts();
}
