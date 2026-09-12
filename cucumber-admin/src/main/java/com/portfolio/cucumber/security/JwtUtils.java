package com.portfolio.cucumber.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.Date;

/**
 * JWT 工具类，基于 jjwt 0.12.x 新 API。
 * 注意：Jwts.parserBuilder() 已在 0.12 移除，统一使用 Jwts.parser().verifyWith(key).build()。
 */
@Component
public class JwtUtils {

    @Value("${jwt.secret}")
    private String secret;

    @Value("${jwt.expire-minutes:720}")
    private long expireMinutes;

    private SecretKey key() {
        return Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public String createToken(Long userId, String username, Collection<String> perms) {
        Date now = new Date();
        Date expiration = new Date(now.getTime() + expireMinutes * 60_000L);
        return Jwts.builder()
                .subject(username)
                .claim("userId", userId)
                .claim("perms", perms)
                .issuedAt(now)
                .expiration(expiration)
                .signWith(key())
                .compact();
    }

    public Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith(key())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }
}
