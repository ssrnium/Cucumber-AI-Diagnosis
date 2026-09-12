package com.portfolio.cucumber.modules.agent;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.Map;

/**
 * 智能体服务（cucumber-agent, FastAPI，基于 EchoMind 二开）HTTP 客户端。
 * base-url 由配置 agent.base-url 注入，默认 http://localhost:8002；对话调用超时 120s。
 */
@Component
public class AgentServiceClient {

    private final RestClient restClient;

    public AgentServiceClient(@Value("${agent.base-url:http://localhost:8002}") String baseUrl) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(10));
        requestFactory.setReadTimeout(Duration.ofSeconds(120));
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();
    }

    /** POST /chat：透传 user_id/conv_id/image_url/record_id，返回完整编排结果。 */
    public Map<String, Object> chat(Map<String, Object> body) {
        return restClient.post()
                .uri("/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** GET /monitor：Agent/工具统计、告警与优化建议。 */
    public Map<String, Object> monitor() {
        return restClient.get()
                .uri("/monitor")
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** POST /eval/run：运行评测（body 为空时使用内置默认用例）。 */
    public Map<String, Object> evalRun(Map<String, Object> body) {
        return restClient.post()
                .uri("/eval/run")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body == null ? Map.of() : body)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** GET /skills：已加载 Skills 摘要。 */
    public Map<String, Object> skills() {
        return restClient.get()
                .uri("/skills")
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** POST /skills/reload：热加载 Skills。 */
    public Map<String, Object> reloadSkills() {
        return restClient.post()
                .uri("/skills/reload")
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** GET /trace/tool/{requestId}：单次请求工具调用明细。 */
    public Map<String, Object> toolTrace(String requestId) {
        return restClient.get()
                .uri("/trace/tool/{requestId}", requestId)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** GET /trace/tools：最近 N 次请求工具调用明细。 */
    public Map<String, Object> recentToolTraces(int limit) {
        return restClient.get()
                .uri("/trace/tools?limit={limit}", limit)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** POST /knowledge/add：批量导入知识文档（带 source_id 等元数据）。 */
    public Map<String, Object> knowledgeAdd(Map<String, Object> body) {
        return restClient.post()
                .uri("/knowledge/add")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** POST /knowledge/upload：multipart 文件导入知识库。 */
    public Map<String, Object> knowledgeUpload(byte[] fileBytes, String filename) {
        MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
        bodyBuilder.part("file", new ByteArrayResource(fileBytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        });
        return restClient.post()
                .uri("/knowledge/upload")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(bodyBuilder.build())
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    /** GET /knowledge/stats：知识库片段总数。 */
    public Map<String, Object> knowledgeStats() {
        return restClient.get()
                .uri("/knowledge/stats")
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }
}
