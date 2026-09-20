package com.portfolio.cucumber.integration.ai;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * AI 服务（cucumber-ai, FastAPI）HTTP 客户端。
 * base-url 由配置 ai.base-url 注入，默认 http://localhost:8000；调用超时 30s。
 */
@Component
public class AiServiceClient {

    private final RestClient restClient;

    public AiServiceClient(@Value("${ai.base-url:http://localhost:8000}") String baseUrl) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(10));
        // 受控润色可能触发"首润+纠错重润"两次 LLM 调用（Kimi k3 单次可达 20-40s），读超时给足 150s
        requestFactory.setReadTimeout(Duration.ofSeconds(150));
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();
    }

    /**
     * 调用 POST /api/v1/detect：上传图片，返回 {"detections": [...]}。
     */
    public Map<String, Object> detect(byte[] imageBytes, String filename) {
        MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
        bodyBuilder.part("file", new ByteArrayResource(imageBytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        });
        return restClient.post()
                .uri("/api/v1/detect")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(bodyBuilder.build())
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /**
     * 调用 POST /api/v1/diagnose：传入病斑框证据（无症状描述），返回受控生成的诊断报告 JSON。
     */
    public Map<String, Object> diagnose(List<Map<String, Object>> detections) {
        return diagnose(detections, List.of());
    }

    /**
     * 调用 POST /api/v1/diagnose：传入病斑框证据 + 用户补充的症状描述关键词。
     * 症状仅作辅助证据由 AI 服务清洗后纳入报告"症状线索"，不影响检测结论；
     * symptoms 传 null 时按空列表处理（兼容不传）。
     */
    public Map<String, Object> diagnose(List<Map<String, Object>> detections, List<String> symptoms) {
        return restClient.post()
                .uri("/api/v1/diagnose")
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("detections", detections,
                        "symptoms", symptoms == null ? List.<String>of() : symptoms))
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }
}
