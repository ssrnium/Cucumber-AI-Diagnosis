package com.portfolio.cucumber.integration.mq;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 诊断异步消息生产者：图片上传后将记录 ID 投递到队列，由 Listener 异步调用 AI 服务。
 */
@Component
@ConditionalOnProperty(name = "mq.enabled", havingValue = "true")
public class DiagnosisMessageProducer {

    private final RabbitTemplate rabbitTemplate;

    public DiagnosisMessageProducer(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void send(Long recordId) {
        rabbitTemplate.convertAndSend(RabbitConfig.DIAGNOSIS_QUEUE, String.valueOf(recordId));
    }
}
