package com.portfolio.cucumber.integration.mq;

import com.portfolio.cucumber.integration.ai.AiServiceClient;
import com.portfolio.cucumber.modules.diagnosis.entity.DiagnosisRecord;
import com.portfolio.cucumber.modules.diagnosis.mapper.DiagnosisRecordMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

/**
 * 诊断异步消息消费者：PENDING 记录 -> 调用 AI 服务 -> DONE / FAILED。
 */
@Component
@ConditionalOnProperty(name = "mq.enabled", havingValue = "true")
public class DiagnosisMessageListener {

    private static final Logger log = LoggerFactory.getLogger(DiagnosisMessageListener.class);

    private final DiagnosisRecordMapper diagnosisRecordMapper;
    private final AiServiceClient aiServiceClient;

    @Value("${upload.dir:./uploads}")
    private String uploadDir;

    public DiagnosisMessageListener(DiagnosisRecordMapper diagnosisRecordMapper,
                                    AiServiceClient aiServiceClient) {
        this.diagnosisRecordMapper = diagnosisRecordMapper;
        this.aiServiceClient = aiServiceClient;
    }

    @RabbitListener(queues = RabbitConfig.DIAGNOSIS_QUEUE)
    @SuppressWarnings("unchecked")
    public void handle(String recordIdText) {
        Long recordId = Long.valueOf(recordIdText);
        DiagnosisRecord record = diagnosisRecordMapper.selectById(recordId);
        if (record == null) {
            log.warn("诊断记录不存在: {}", recordId);
            return;
        }
        try {
            String filename = record.getImageUrl().substring(record.getImageUrl().lastIndexOf('/') + 1);
            Path imagePath = Paths.get(uploadDir).toAbsolutePath().normalize().resolve(filename);
            byte[] imageBytes = Files.readAllBytes(imagePath);

            Map<String, Object> detectResponse = aiServiceClient.detect(imageBytes, filename);
            List<Map<String, Object>> detections =
                    (List<Map<String, Object>>) detectResponse.get("detections");
            Map<String, Object> report = aiServiceClient.diagnose(detections);

            record.setDetections(detections);
            record.setReport(report);
            record.setStatus("DONE");
        } catch (Exception e) {
            log.error("异步诊断失败, recordId={}: {}", recordId, e.getMessage());
            record.setStatus("FAILED");
        }
        diagnosisRecordMapper.updateById(record);
    }
}
