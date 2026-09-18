package com.portfolio.cucumber.integration.mq;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import static org.mockito.Mockito.verify;

/**
 * DiagnosisMessageProducer 单元测试：投递队列名与消息体格式。
 */
@ExtendWith(MockitoExtension.class)
class DiagnosisMessageProducerTest {

    @Mock
    private RabbitTemplate rabbitTemplate;

    @Test
    void send_postsRecordIdAsTextToDiagnosisQueue() {
        // 业务含义：生产者投递到约定队列 cucumber.diagnosis，消息体为记录 ID 字符串，
        // Listener 侧按 Long.valueOf 解析，格式不一致会导致异步链路消费失败。
        new DiagnosisMessageProducer(rabbitTemplate).send(123L);

        verify(rabbitTemplate).convertAndSend(RabbitConfig.DIAGNOSIS_QUEUE, "123");
    }
}
