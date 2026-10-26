package com.interviewace.security;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

import javax.crypto.SecretKey;

import org.springframework.stereotype.Component;

import com.interviewace.common.BizException;
import com.interviewace.common.UserContext;
import com.interviewace.config.AppProperties;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

/**
 * JWT 签发与校验（HS256）。
 *
 * <p>与 Python PyJWT 互通：同一 secret、同一算法、同一 claims 结构
 * （sub / username / role / iat / exp），因此 Python 签发的老 token
 * 与 Java 签发的新 token 可互相校验，支持灰度切换。
 */
@Component
public class JwtUtil {

    private static final long EXPIRE_SLACK_SECONDS = 30;

    private final AppProperties props;
    private final SecretKey key;

    public JwtUtil(AppProperties props) {
        this.props = props;
        byte[] secret = props.getJwt().getSecret().getBytes(StandardCharsets.UTF_8);
        if (secret.length < 32) {
            throw new IllegalStateException("JWT_SECRET 至少需要 32 字节（请在 .env 中升级密钥）");
        }
        this.key = Keys.hmacShaKeyFor(secret);
    }

    /** 签发登录 token，claims 与 PyJWT payload 完全一致 */
    public String createAccessToken(UserContext user) {
        Instant now = Instant.now();
        Instant exp = now.plusSeconds(props.getJwt().getExpireMinutes() * 60);
        return Jwts.builder()
                .subject(String.valueOf(user.id()))
                .claim("username", user.username())
                .claim("role", user.role())
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .signWith(key, Jwts.SIG.HS256)
                .compact();
    }

    /** 解析并校验 token，失败抛 401 业务异常（文案与 auth.py 对齐） */
    public UserContext parseAccessToken(String token) {
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(key)
                    .clockSkewSeconds(EXPIRE_SLACK_SECONDS)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            Integer id = parseIntOrNull(claims.getSubject());
            if (id == null) {
                throw BizException.unauthorized("Token 无效");
            }
            return new UserContext(id,
                    claims.get("username", String.class),
                    claims.get("role", String.class));
        } catch (JwtException | IllegalArgumentException e) {
            throw BizException.unauthorized(e.getMessage() == null ? "Token 无效" : e.getMessage());
        }
    }

    private Integer parseIntOrNull(String s) {
        try {
            return Integer.valueOf(s);
        } catch (Exception e) {
            return null;
        }
    }
}
