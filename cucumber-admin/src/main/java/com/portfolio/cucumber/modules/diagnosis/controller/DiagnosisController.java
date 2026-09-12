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
import com.portfolio.cucumber.modules.model.entity.ModelVersion;
import com.portfolio.cucumber.modules.model.mapper.ModelVersionMapper;
import com.portfolio.cucumber.modules.system.annotation.OperLog;
import com.portfolio.cucumber.security.LoginUser;
import com.portfolio.cucumber.security.SecurityUtils;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1")
public class DiagnosisController {

    private final DiagnosisRecordMapper diagnosisRecordMapper;
    private final DiagnosisFeedbackMapper diagnosisFeedbackMapper;
    private final ModelVersionMapper modelVersionMapper;
    private final AiServiceClient aiServiceClient;
    private final ObjectProvider<DiagnosisMessageProducer> messageProducer;

    @Value("${upload.dir:./uploads}")
    private String uploadDir;

    @Value("${mq.enabled:false}")
    private boolean mqEnabled;

    public DiagnosisController(DiagnosisRecordMapper diagnosisRecordMapper,
                               DiagnosisFeedbackMapper diagnosisFeedbackMapper,
                               ModelVersionMapper modelVersionMapper,
                               AiServiceClient aiServiceClient,
                               ObjectProvider<DiagnosisMessageProducer> messageProducer) {
        this.diagnosisRecordMapper = diagnosisRecordMapper;
        this.diagnosisFeedbackMapper = diagnosisFeedbackMapper;
        this.modelVersionMapper = modelVersionMapper;
        this.aiServiceClient = aiServiceClient;
        this.messageProducer = messageProducer;
    }

    /**
     * 上传图片并诊断：存文件 -> 调 AI 服务 -> 存记录 -> 返回病斑框 + 诊断报告。
     * mq.enabled=true 时转为异步：记录置 PENDING 并投递消息，前端轮询详情获取结果。
     */
    @PostMapping(value = "/diagnosis", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @OperLog("上传图片诊断")
    @SuppressWarnings("unchecked")
    public Result<DiagnosisRecord> diagnose(@RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new BizException("请上传叶片图片");
        }
        String contentType = file.getContentType();
        if (contentType == null || !contentType.startsWith("image/")) {
            throw new BizException("仅支持上传图片文件（jpg/png/webp 等）");
        }
        String original = StringUtils.cleanPath(
                file.getOriginalFilename() == null ? "image.jpg" : file.getOriginalFilename());
        byte[] bytes = file.getBytes();
        String hash = contentHash(bytes);
        String filename = hash + extensionOf(original);
        Path dir = Paths.get(uploadDir).toAbsolutePath().normalize();
        Files.createDirectories(dir);
        Path target = dir.resolve(filename);

        LoginUser currentUser = SecurityUtils.current();
        Long uid = currentUser == null ? null : currentUser.getUserId();
        // 重复任务处理：同一用户上传内容完全相同的图片时，直接返回窗口期内的已有记录，
        // 不重复创建任务、不重复调用 AI 服务（文件名即内容哈希，天然幂等；改名不影响判定）。
        if (uid != null) {
            DiagnosisRecord existing = diagnosisRecordMapper.selectOne(new LambdaQueryWrapper<DiagnosisRecord>()
                    .eq(DiagnosisRecord::getUserId, uid)
                    .likeRight(DiagnosisRecord::getImageUrl, "/files/" + hash)
                    .ge(DiagnosisRecord::getCreateTime, LocalDateTime.now().minusSeconds(DEDUP_WINDOW_SECONDS))
                    .orderByDesc(DiagnosisRecord::getId)
                    .last("limit 1"));
            if (existing != null) {
                existing.setDuplicated(true);
                return Result.success(existing);
            }
        }
        if (!Files.exists(target)) {
            Files.write(target, bytes);
        }

        DiagnosisRecord record = new DiagnosisRecord();
        record.setRecordNo(generateRecordNo());
        record.setUserId(uid);
        record.setImageUrl("/files/" + filename);
        record.setModelVersion(activeDetectionModel());
        record.setStatus("PENDING");
        record.setCreateTime(LocalDateTime.now());

        if (mqEnabled) {
            diagnosisRecordMapper.insert(record);
            DiagnosisMessageProducer producer = messageProducer.getIfAvailable();
            if (producer != null) {
                producer.send(record.getId());
            }
            return Result.success(record);
        }

        try {
            Map<String, Object> detectResponse = aiServiceClient.detect(bytes, original);
            List<Map<String, Object>> detections =
                    (List<Map<String, Object>>) detectResponse.get("detections");
            Map<String, Object> report = aiServiceClient.diagnose(detections);
            record.setDetections(detections);
            record.setReport(report);
            Object inferenceMs = detectResponse.get("inference_ms");
            if (inferenceMs instanceof Number) {
                record.setInferenceMs(((Number) inferenceMs).doubleValue());
            }
            record.setStatus("DONE");
            diagnosisRecordMapper.insert(record);
            return Result.success(record);
        } catch (Exception e) {
            record.setStatus("FAILED");
            diagnosisRecordMapper.insert(record);
            return Result.error("AI 服务暂不可用，记录已保存（状态：失败），请稍后重试");
        }
    }

    /**
     * 诊断记录分页列表：普通用户仅看自己的，管理员/专家（diagnosis:list:all）看全部。
     */
    @GetMapping("/diagnosis")
    public Result<PageResult<DiagnosisRecord>> list(@RequestParam(defaultValue = "1") long page,
                                                    @RequestParam(defaultValue = "10") long size,
                                                    @RequestParam(required = false) String status) {
        LambdaQueryWrapper<DiagnosisRecord> wrapper = new LambdaQueryWrapper<>();
        if (!SecurityUtils.hasAuthority("diagnosis:list:all")) {
            wrapper.eq(DiagnosisRecord::getUserId, SecurityUtils.currentUserId());
        }
        if (StringUtils.hasText(status)) {
            wrapper.eq(DiagnosisRecord::getStatus, status);
        }
        wrapper.orderByDesc(DiagnosisRecord::getCreateTime);
        Page<DiagnosisRecord> result = diagnosisRecordMapper.selectPage(new Page<>(page, size), wrapper);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    /**
     * 诊断详情（含 detections 病斑框与 report 报告全文，report.source_ids 即来源追溯编号）。
     */
    @GetMapping("/diagnosis/{id}")
    public Result<DiagnosisRecord> detail(@PathVariable Long id) {
        DiagnosisRecord record = diagnosisRecordMapper.selectById(id);
        if (record == null) {
            throw new BizException("记录不存在");
        }
        if (!SecurityUtils.hasAuthority("diagnosis:list:all")
                && !record.getUserId().equals(SecurityUtils.currentUserId())) {
            throw new BizException(403, "没有访问权限");
        }
        return Result.success(record);
    }

    /**
     * 用户纠错反馈：诊断有误时提交修正病害类型与说明。
     */
    @PostMapping("/diagnosis/{id}/feedback")
    @OperLog("提交诊断反馈")
    public Result<Void> feedback(@PathVariable Long id, @RequestBody DiagnosisFeedback feedback) {
        DiagnosisRecord record = diagnosisRecordMapper.selectById(id);
        if (record == null) {
            throw new BizException("记录不存在");
        }
        feedback.setId(null);
        feedback.setRecordId(id);
        feedback.setUserId(SecurityUtils.currentUserId());
        feedback.setReviewStatus("PENDING");
        feedback.setReviewerId(null);
        feedback.setCreateTime(LocalDateTime.now());
        feedback.setUpdateTime(LocalDateTime.now());
        diagnosisFeedbackMapper.insert(feedback);
        return Result.success();
    }

    /**
     * 专家复核列表：查看全部（或按状态筛选）用户反馈。
     */
    @GetMapping("/feedback")
    @PreAuthorize("hasAuthority('feedback:review')")
    public Result<PageResult<DiagnosisFeedback>> feedbackList(
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) String reviewStatus) {
        LambdaQueryWrapper<DiagnosisFeedback> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(reviewStatus)) {
            wrapper.eq(DiagnosisFeedback::getReviewStatus, reviewStatus);
        }
        wrapper.orderByDesc(DiagnosisFeedback::getCreateTime);
        Page<DiagnosisFeedback> result = diagnosisFeedbackMapper.selectPage(new Page<>(page, size), wrapper);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    /**
     * 专家处理反馈：标记为已复核。
     */
    @PutMapping("/feedback/{id}/review")
    @PreAuthorize("hasAuthority('feedback:review')")
    @OperLog("复核诊断反馈")
    public Result<Void> review(@PathVariable Long id) {
        DiagnosisFeedback feedback = diagnosisFeedbackMapper.selectById(id);
        if (feedback == null) {
            throw new BizException("反馈不存在");
        }
        feedback.setReviewStatus("REVIEWED");
        feedback.setReviewerId(SecurityUtils.currentUserId());
        feedback.setUpdateTime(LocalDateTime.now());
        diagnosisFeedbackMapper.updateById(feedback);
        return Result.success();
    }

    private static final long DEDUP_WINDOW_SECONDS = 120;

    private String contentHash(byte[] bytes) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private String extensionOf(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot >= 0 ? filename.substring(dot) : ".jpg";
    }

    private String generateRecordNo() {
        return "D" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss"))
                + ThreadLocalRandom.current().nextInt(1000, 10000);
    }

    private String activeDetectionModel() {
        ModelVersion active = modelVersionMapper.selectOne(new LambdaQueryWrapper<ModelVersion>()
                .eq(ModelVersion::getModelType, "DETECTION")
                .eq(ModelVersion::getStatus, "ACTIVE")
                .last("LIMIT 1"));
        return active == null ? "mock-detector" : active.getName() + ":" + active.getVersion();
    }
}
