package com.portfolio.cucumber.integration.mq;

import com.portfolio.cucumber.integration.ai.AiServiceClient;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisRecordMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * DiagnosisMessageListener 单元测试：异步消费正常路径（DONE 落库）、
 * AI 服务异常路径（FAILED 落库）、记录不存在直接跳过。
 */
@ExtendWith(MockitoExtension.class)
class DiagnosisMessageListenerTest {

    @Mock
    private DiagnosisRecordMapper diagnosisRecordMapper;
    @Mock
    private AiServiceClient aiServiceClient;

    @TempDir
    Path uploadDir;

    private DiagnosisMessageListener listener;

    @BeforeEach
    void setUp() {
        listener = new DiagnosisMessageListener(diagnosisRecordMapper, aiServiceClient);
        ReflectionTestUtils.setField(listener, "uploadDir", uploadDir.toString());
    }

    private DiagnosisRecord pendingRecord() {
        DiagnosisRecord record = new DiagnosisRecord();
        record.setId(42L);
        record.setImageUrl("/uploads/leaf.jpg");
        record.setStatus("PENDING");
        return record;
    }

    @Test
    void handle_success_runsDetectAndDiagnoseThenMarksDone() throws Exception {
        // 业务含义：异步链路正常路径 —— 读图片字节 → /detect 拿检测框 → /diagnose 拿报告 →
        // 记录回写 detections+report 并置 DONE，用户轮询时看到完成态。
        Files.write(uploadDir.resolve("leaf.jpg"), new byte[]{1, 2, 3});
        when(diagnosisRecordMapper.selectById(42L)).thenReturn(pendingRecord());
        List<Map<String, Object>> detections = List.of(Map.of("label", "霜霉病", "confidence", 0.9));
        when(aiServiceClient.detect(any(byte[].class), eq("leaf.jpg")))
                .thenReturn(Map.of("detections", detections));
        when(aiServiceClient.diagnose(anyList())).thenReturn(Map.of("report_status", "polished"));

        listener.handle("42");

        ArgumentCaptor<DiagnosisRecord> captor = ArgumentCaptor.forClass(DiagnosisRecord.class);
        verify(diagnosisRecordMapper).updateById(captor.capture());
        DiagnosisRecord saved = captor.getValue();
        assertThat(saved.getStatus()).isEqualTo("DONE");
        assertThat(saved.getDetections()).hasSize(1);
        assertThat(saved.getReport()).containsEntry("report_status", "polished");
    }

    @Test
    void handle_aiServiceDown_marksFailed() {
        // 业务含义：AI 服务宕机/超时时不抛出（消息不重回队列死循环），
        // 记录置 FAILED 落库，前端可展示失败并允许重试。
        when(diagnosisRecordMapper.selectById(42L)).thenReturn(pendingRecord());
        when(aiServiceClient.detect(any(byte[].class), any()))
                .thenThrow(new RuntimeException("ai service unavailable"));
        try {
            Files.write(uploadDir.resolve("leaf.jpg"), new byte[]{1});
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }

        listener.handle("42");

        ArgumentCaptor<DiagnosisRecord> captor = ArgumentCaptor.forClass(DiagnosisRecord.class);
        verify(diagnosisRecordMapper).updateById(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo("FAILED");
        verify(aiServiceClient, never()).diagnose(anyList());
    }

    @Test
    void handle_recordNotFound_skipsSilently() {
        // 业务含义：消息到达但记录已被删除（极端并发）时仅告警跳过，
        // 不调用 AI、不写库，避免幽灵消息拖垮消费端。
        when(diagnosisRecordMapper.selectById(42L)).thenReturn(null);

        listener.handle("42");

        verifyNoInteractions(aiServiceClient);
        verify(diagnosisRecordMapper, never()).updateById(any(DiagnosisRecord.class));
    }
}
