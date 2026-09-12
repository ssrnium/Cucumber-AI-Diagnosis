package com.portfolio.cucumber.integration.mq;

import org.springframework.amqp.core.Queue;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 配置：仅当 mq.enabled=true 时生效（本地默认关闭，docker-compose 中开启）。
 */
@Configuration
@ConditionalOnProperty(name = "mq.enabled", havingValue = "true")
public class RabbitConfig {

    public static final String DIAGNOSIS_QUEUE = "cucumber.diagnosis";

    @Bean
    public Queue diagnosisQueue() {
        return new Queue(DIAGNOSIS_QUEUE, true);
    }
}
