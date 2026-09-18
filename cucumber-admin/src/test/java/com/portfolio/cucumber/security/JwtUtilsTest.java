package com.portfolio.cucumber.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.security.SignatureException;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * JwtUtils 单元测试：签发/解析往返、过期拒绝、篡改签名拒绝。
 */
class JwtUtilsTest {

    private static final String SECRET = "cucumber-diagnosis-platform-jwt-secret-key-2026";

    private JwtUtils jwtUtils(long expireMinutes) {
        JwtUtils utils = new JwtUtils();
        ReflectionTestUtils.setField(utils, "secret", SECRET);
        ReflectionTestUtils.setField(utils, "expireMinutes", expireMinutes);
        return utils;
    }

    @Test
    void createToken_parse_roundTripReturnsClaims() {
        // 业务含义：登录签发的 token 必须能解析回 userId/username/perms，
        // 后续请求鉴权完全依赖这三个声明还原登录态。
        JwtUtils utils = jwtUtils(720);

        String token = utils.createToken(7L, "admin", List.of("system:user:list", "agent:chat"));
        Claims claims = utils.parseToken(token);

        assertThat(claims.getSubject()).isEqualTo("admin");
        assertThat(claims.get("userId", Long.class)).isEqualTo(7L);
        assertThat(claims.get("perms", List.class)).containsExactly("system:user:list", "agent:chat");
    }

    @Test
    void parseToken_expired_throwsExpiredJwtException() {
        // 业务含义：过期 token 一律拒绝，防止注销/离职账号的旧凭证长期可用。
        JwtUtils utils = jwtUtils(-1);
        String token = utils.createToken(7L, "admin", List.of());

        assertThatThrownBy(() -> utils.parseToken(token))
                .isInstanceOf(ExpiredJwtException.class);
    }

    @Test
    void parseToken_tamperedSignature_throwsSignatureException() {
        // 业务含义：用别的密钥签的（或被篡改的）token 不能通过验签，
        // 这是伪造权限声明（如自加 admin 权限）的防线。
        JwtUtils issuer = jwtUtils(720);
        String token = issuer.createToken(7L, "admin", List.of("*"));

        JwtUtils otherKey = new JwtUtils();
        ReflectionTestUtils.setField(otherKey, "secret", "another-secret-key-that-is-long-enough-123456");
        ReflectionTestUtils.setField(otherKey, "expireMinutes", 720L);

        assertThatThrownBy(() -> otherKey.parseToken(token))
                .isInstanceOf(SignatureException.class);
    }
}
