package com.portfolio.cucumber.modules.system.aspect;

import com.portfolio.cucumber.modules.system.annotation.OperLog;
import com.portfolio.cucumber.modules.system.entity.SysOperationLog;
import com.portfolio.cucumber.modules.system.mapper.SysOperationLogMapper;
import com.portfolio.cucumber.security.LoginUser;
import com.portfolio.cucumber.security.SecurityUtils;
import jakarta.servlet.http.HttpServletRequest;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.time.LocalDateTime;

/**
 * 操作日志切面：记录方法、用户、IP、耗时、执行结果，写入 sys_operation_log。
 */
@Aspect
@Component
public class OperLogAspect {

    private static final Logger log = LoggerFactory.getLogger(OperLogAspect.class);

    private final SysOperationLogMapper operationLogMapper;

    public OperLogAspect(SysOperationLogMapper operationLogMapper) {
        this.operationLogMapper = operationLogMapper;
    }

    @Around("@annotation(operLog)")
    public Object around(ProceedingJoinPoint joinPoint, OperLog operLog) throws Throwable {
        long start = System.currentTimeMillis();
        String result = "SUCCESS";
        try {
            return joinPoint.proceed();
        } catch (Throwable throwable) {
            result = "FAIL";
            throw throwable;
        } finally {
            try {
                SysOperationLog operationLog = new SysOperationLog();
                LoginUser loginUser = SecurityUtils.current();
                operationLog.setUsername(loginUser == null ? "anonymous" : loginUser.getUsername());
                operationLog.setOperation(operLog.value());
                operationLog.setMethod(joinPoint.getSignature().toShortString());
                ServletRequestAttributes attributes =
                        (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
                if (attributes != null) {
                    HttpServletRequest request = attributes.getRequest();
                    operationLog.setUri(request.getRequestURI());
                    operationLog.setIp(request.getRemoteAddr());
                }
                operationLog.setCostMs(System.currentTimeMillis() - start);
                operationLog.setResult(result);
                operationLog.setCreateTime(LocalDateTime.now());
                operationLogMapper.insert(operationLog);
            } catch (Exception e) {
                log.warn("操作日志写入失败: {}", e.getMessage());
            }
        }
    }
}
