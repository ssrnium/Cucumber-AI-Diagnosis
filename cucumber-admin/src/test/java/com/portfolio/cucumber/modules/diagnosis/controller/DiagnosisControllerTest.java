package com.portfolio.cucumber.modules.diagnosis.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.portfolio.cucumber.common.BizException;
import com.portfolio.cucumber.common.PageResult;
import com.portfolio.cucumber.common.Result;
import com.portfolio.cucumber.integration.ai.AiServiceClient;
import com.portfolio.cucumber.integration.mq.DiagnosisMessageProducer;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisFeedback;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisFeedbackMapper;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisRecordMapper;
import com.portfolio.cucumber.modules.model.mapper.ModelVersionMapper;
import com.portfolio.cucumber.support.TestSupport;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * DiagnosisController 单元测试：上传去重、权限边界、文件类型校验、AI 宕机兜底、
 * 反馈提交/复核、低置信度自动转复核，mapper 与 AiServiceClient 全部 mock。
 */
@ExtendWith(MockitoExtension.class)
class DiagnosisControllerTest {

    @Mock
    private DiagnosisRecordMapper recordMapper;
    @Mock
    private DiagnosisFeedbackMapper feedbackMapper;
    @Mock
    private ModelVersionMapper modelVersionMapper;
    @Mock
    private AiServiceClient aiServiceClient;
    @Mock
    private ObjectProvider<DiagnosisMessageProducer> messageProducer;

    private DiagnosisController controller;

    @TempDir
    Path uploadDir;

    @BeforeEach
    void setUp() {
        TestSupport.initTableInfos();
        controller = new DiagnosisController(
                recordMapper, feedbackMapper, modelVersionMapper, aiServiceClient, messageProducer);
        ReflectionTestUtils.setField(controller, "uploadDir", uploadDir.toString());
        // mqEnabled 保持默认 false，走同步诊断分支
    }

    @AfterEach
    void tearDown() {
        TestSupport.logout();
    }

    private MockMultipartFile leafImage() {
        return new MockMultipartFile("file", "leaf.jpg", "image/jpeg", "fake-leaf-bytes".getBytes());
    }

    /** 让 dedup 查询返回 null（窗口内无同内容记录），激活模型返回 null（回落 mock-detector） */
    private void stubFreshUpload() {
        lenient().when(recordMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);
        lenient().when(modelVersionMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);
    }

    // ---------- 1. 上传去重 ----------

    @Test
    void diagnose_whenDuplicateWithinWindow_returnsExistingWithoutCallingAi() throws Exception {
        // 业务含义：同一用户 120s 内重复上传内容完全相同的图片（文件名=SHA-256 内容哈希），
        // 直接返回已有记录并标记 duplicated=true，不重复调 AI、不重复落库（幂等）。
        TestSupport.loginAs(7L);
        DiagnosisRecord existing = new DiagnosisRecord();
        existing.setId(99L);
        existing.setUserId(7L);
        existing.setStatus("DONE");
        when(recordMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(existing);

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), null);

        assertThat(result.getCode()).isEqualTo(200);
        assertThat(result.getData().getId()).isEqualTo(99L);
        assertThat(result.getData().getDuplicated()).isTrue();
        verify(aiServiceClient, never()).detect(any(), anyString());
        verify(recordMapper, never()).insert(any(DiagnosisRecord.class));
        verify(feedbackMapper, never()).insert(any(DiagnosisFeedback.class));
    }

    @Test
    void diagnose_whenDedupQueryMisses_createsNewRecord() throws Exception {
        // 业务含义：窗口内查不到同内容记录（超窗或图片内容不同，哈希不同 → likeRight 不匹配），
        // 正常走"调 AI + 新建记录"流程。同时验证高置信度（0.92 ≥ 0.75）不触发自动复核。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        Map<String, Object> detection = Map.of("label", "霜霉病", "confidence", 0.92);
        when(aiServiceClient.detect(any(), anyString()))
                .thenReturn(Map.of("detections", List.of(detection), "inference_ms", 35));
        when(aiServiceClient.diagnose(anyList(), any())).thenReturn(Map.of("summary", "建议防治"));

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), null);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<DiagnosisRecord> captor = ArgumentCaptor.forClass(DiagnosisRecord.class);
        verify(recordMapper).insert(captor.capture());
        DiagnosisRecord saved = captor.getValue();
        assertThat(saved.getStatus()).isEqualTo("DONE");
        assertThat(saved.getUserId()).isEqualTo(7L);
        assertThat(saved.getImageUrl()).startsWith("/files/");
        assertThat(saved.getInferenceMs()).isEqualTo(35.0);
        assertThat(saved.getModelVersion()).isEqualTo("mock-detector");
        assertThat(saved.getDuplicated()).isNull();
        verify(feedbackMapper, never()).insert(any(DiagnosisFeedback.class));
    }

    // ---------- 3. 错误文件类型 ----------

    @Test
    void diagnose_whenNotImage_throwsBizException() {
        // 业务含义：上传 txt/pdf 等非 image/* 文件直接拒绝，不写文件、不调 AI。
        TestSupport.loginAs(7L);
        MockMultipartFile txt = new MockMultipartFile("file", "note.txt", "text/plain", "hello".getBytes());

        assertThatThrownBy(() -> controller.diagnose(txt, null))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("仅支持上传图片文件");
    }

    // ---------- 4. AI 宕机兜底 ----------

    @Test
    void diagnose_whenAiServiceDown_savesFailedRecordAndReturnsFriendlyError() throws Exception {
        // 业务含义：AI 服务不可用时记录仍以 FAILED 状态落库（可追溯、可重试），
        // 接口返回友好提示而不是 500 堆栈。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        when(aiServiceClient.detect(any(), anyString())).thenThrow(new RuntimeException("connection refused"));

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), null);

        assertThat(result.getCode()).isEqualTo(500);
        assertThat(result.getMessage()).contains("AI 服务暂不可用");
        ArgumentCaptor<DiagnosisRecord> captor = ArgumentCaptor.forClass(DiagnosisRecord.class);
        verify(recordMapper).insert(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo("FAILED");
    }

    // ---------- 7. 低置信度自动转专家复核 ----------

    @Test
    void diagnose_whenTopConfidenceBelowThreshold_createsUncertainPendingFeedback() throws Exception {
        // 业务含义：检测最高置信度 < 0.75 时，系统自动创建 UNCERTAIN/PENDING 反馈单转专家复核。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        Map<String, Object> weak = Map.of("label", "靶斑病", "confidence", 0.52);
        when(aiServiceClient.detect(any(), anyString())).thenReturn(Map.of("detections", List.of(weak)));
        when(aiServiceClient.diagnose(anyList(), any())).thenReturn(Map.of());

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), null);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<DiagnosisFeedback> captor = ArgumentCaptor.forClass(DiagnosisFeedback.class);
        verify(feedbackMapper).insert(captor.capture());
        DiagnosisFeedback auto = captor.getValue();
        assertThat(auto.getVerdict()).isEqualTo("UNCERTAIN");
        assertThat(auto.getReviewStatus()).isEqualTo("PENDING");
        assertThat(auto.getUserId()).isEqualTo(7L);
        assertThat(auto.getComment()).contains("0.75");
        assertThat(auto.getCreateTime()).isNotNull();
    }

    @Test
    void diagnose_whenNoDetections_alsoCreatesUncertainFeedback() throws Exception {
        // 业务含义：无检出（detections 为空 → 最高置信度按 0.0 计）同样属于低置信场景，自动转复核。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        when(aiServiceClient.detect(any(), anyString()))
                .thenReturn(Map.of("detections", List.of()));
        when(aiServiceClient.diagnose(anyList(), any())).thenReturn(Map.of());

        controller.diagnose(leafImage(), null);

        ArgumentCaptor<DiagnosisFeedback> captor = ArgumentCaptor.forClass(DiagnosisFeedback.class);
        verify(feedbackMapper).insert(captor.capture());
        assertThat(captor.getValue().getVerdict()).isEqualTo("UNCERTAIN");
        assertThat(captor.getValue().getReviewStatus()).isEqualTo("PENDING");
    }

    // ---------- 8. 症状描述透传（辅助证据，结论仍以检测为准） ----------

    @Test
    void diagnose_whenSymptomsProvided_forwardsThemToAiService() throws Exception {
        // 业务含义：前端补充的症状描述随诊断请求透传给 AI 服务（报告"症状线索"），
        // admin 不做内容改写，只负责转发。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        Map<String, Object> detection = Map.of("label", "霜霉病", "confidence", 0.92);
        when(aiServiceClient.detect(any(), anyString()))
                .thenReturn(Map.of("detections", List.of(detection)));
        when(aiServiceClient.diagnose(anyList(), any())).thenReturn(Map.of());

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), List.of("黄斑", "叶背霉层"));

        assertThat(result.getCode()).isEqualTo(200);
        verify(aiServiceClient).diagnose(anyList(), eq(List.of("黄斑", "叶背霉层")));
    }

    @Test
    void diagnose_whenNoSymptoms_forwardsEmptyList() throws Exception {
        // 业务含义：不传症状（兼容旧调用）时按空列表透传，AI 服务走无临床症状的既有口径。
        TestSupport.loginAs(7L);
        stubFreshUpload();
        Map<String, Object> detection = Map.of("label", "霜霉病", "confidence", 0.92);
        when(aiServiceClient.detect(any(), anyString()))
                .thenReturn(Map.of("detections", List.of(detection)));
        when(aiServiceClient.diagnose(anyList(), any())).thenReturn(Map.of());

        Result<DiagnosisRecord> result = controller.diagnose(leafImage(), null);

        assertThat(result.getCode()).isEqualTo(200);
        verify(aiServiceClient).diagnose(anyList(), eq(List.of()));
    }

    // ---------- 5 / 10. 用户反馈提交（verdict 语义不被覆盖） ----------

    @Test
    void feedback_forcesPendingAndPathRecordId_andKeepsUserVerdict() {
        // 业务含义：用户纠错反馈以路径 id 为准（body 里的 recordId/id 不可信，强制覆盖），
        // reviewStatus 强制 PENDING、清空 reviewerId、写入时间戳；
        // 用户语义 verdict=WRONG 保留，与系统自动单的 UNCERTAIN 区分开（行为 10）。
        TestSupport.loginAs(8L);
        DiagnosisRecord record = new DiagnosisRecord();
        record.setId(55L);
        when(recordMapper.selectById(55L)).thenReturn(record);

        DiagnosisFeedback body = new DiagnosisFeedback();
        body.setId(12345L);          // 伪造 id，应被清空
        body.setRecordId(999L);      // 伪造 recordId，应被路径 id 覆盖
        body.setVerdict("WRONG");
        body.setCorrectedDiseaseType("细菌性角斑病");
        body.setReviewStatus("REVIEWED"); // 伪造状态，应被强制 PENDING
        body.setReviewerId(666L);         // 伪造复核人，应被清空

        Result<Void> result = controller.feedback(55L, body);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<DiagnosisFeedback> captor = ArgumentCaptor.forClass(DiagnosisFeedback.class);
        verify(feedbackMapper).insert(captor.capture());
        DiagnosisFeedback saved = captor.getValue();
        assertThat(saved.getId()).isNull();
        assertThat(saved.getRecordId()).isEqualTo(55L);
        assertThat(saved.getUserId()).isEqualTo(8L);
        assertThat(saved.getReviewStatus()).isEqualTo("PENDING");
        assertThat(saved.getReviewerId()).isNull();
        assertThat(saved.getVerdict()).isEqualTo("WRONG");
        assertThat(saved.getCreateTime()).isNotNull();
        assertThat(saved.getUpdateTime()).isNotNull();
    }

    @Test
    void feedback_whenRecordMissing_throwsBizException() {
        // 业务含义：对不存在的诊断记录提交反馈 → 业务异常，不落库。
        TestSupport.loginAs(8L);
        when(recordMapper.selectById(404L)).thenReturn(null);

        assertThatThrownBy(() -> controller.feedback(404L, new DiagnosisFeedback()))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("记录不存在");
        verify(feedbackMapper, never()).insert(any(DiagnosisFeedback.class));
    }

    // ---------- 6. 专家复核 ----------

    @Test
    void review_marksReviewedWithReviewerAndUpdateTime() {
        // 业务含义：专家复核后反馈置 REVIEWED，记录复核人 reviewerId 与 updateTime。
        TestSupport.loginAs(100L);
        DiagnosisFeedback feedback = new DiagnosisFeedback();
        feedback.setId(9L);
        feedback.setReviewStatus("PENDING");
        when(feedbackMapper.selectById(9L)).thenReturn(feedback);

        Result<Void> result = controller.review(9L);

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<DiagnosisFeedback> captor = ArgumentCaptor.forClass(DiagnosisFeedback.class);
        verify(feedbackMapper).updateById(captor.capture());
        DiagnosisFeedback updated = captor.getValue();
        assertThat(updated.getReviewStatus()).isEqualTo("REVIEWED");
        assertThat(updated.getReviewerId()).isEqualTo(100L);
        assertThat(updated.getUpdateTime()).isNotNull();
    }

    @Test
    void review_whenFeedbackMissing_throwsBizException() {
        // 业务含义：复核不存在的反馈 → 业务异常。
        TestSupport.loginAs(100L);
        when(feedbackMapper.selectById(404L)).thenReturn(null);

        assertThatThrownBy(() -> controller.review(404L))
                .isInstanceOf(BizException.class)
                .hasMessageContaining("反馈不存在");
    }

    // ---------- 2. 权限边界：记录分页数据隔离 ----------

    @Test
    void list_withoutListAllPermission_restrictsQueryToOwnUserId() {
        // 业务含义：普通用户（无 diagnosis:list:all）分页查询被约束在本人 userId，数据隔离。
        TestSupport.loginAs(7L); // 无任何权限
        when(recordMapper.selectPage(any(Page.class), any(LambdaQueryWrapper.class)))
                .thenReturn(new Page<>());

        controller.list(1, 10, null);

        ArgumentCaptor<LambdaQueryWrapper<DiagnosisRecord>> captor = ArgumentCaptor.forClass(LambdaQueryWrapper.class);
        verify(recordMapper).selectPage(any(Page.class), captor.capture());
        LambdaQueryWrapper<DiagnosisRecord> wrapper = captor.getValue();
        assertThat(wrapper.getSqlSegment()).contains("user_id");
        assertThat(wrapper.getParamNameValuePairs()).containsValue(7L);
    }

    @Test
    void list_withListAllPermission_hasNoUserIdConstraint() {
        // 业务含义：持有 diagnosis:list:all 的管理员/专家可查看全部记录，wrapper 不带 userId 约束。
        TestSupport.loginAs(1L, "diagnosis:list:all");
        when(recordMapper.selectPage(any(Page.class), any(LambdaQueryWrapper.class)))
                .thenReturn(new Page<>());

        Result<PageResult<DiagnosisRecord>> result = controller.list(1, 10, "DONE");

        assertThat(result.getCode()).isEqualTo(200);
        ArgumentCaptor<LambdaQueryWrapper<DiagnosisRecord>> captor = ArgumentCaptor.forClass(LambdaQueryWrapper.class);
        verify(recordMapper).selectPage(any(Page.class), captor.capture());
        LambdaQueryWrapper<DiagnosisRecord> wrapper = captor.getValue();
        assertThat(wrapper.getSqlSegment()).doesNotContain("user_id");
        // status 筛选仍然生效
        assertThat(wrapper.getSqlSegment()).contains("status");
        assertThat(wrapper.getParamNameValuePairs()).containsValue("DONE");
    }
}
