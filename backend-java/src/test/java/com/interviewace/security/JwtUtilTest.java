package com.interviewace.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import com.interviewace.common.BizException;
import com.interviewace.common.UserContext;
import com.interviewace.config.AppProperties;

class JwtUtilTest {

    private static final String SECRET = "test-secret-key-at-least-32-bytes-long!!";

    private JwtUtil jwtUtil(long expireMinutes) {
        AppProperties props = new AppProperties();
        props.getJwt().setSecret(SECRET);
        props.getJwt().setExpireMinutes(expireMinutes);
        return new JwtUtil(props);
    }

    @Test
    void createThenParse_roundTrip() {
        JwtUtil jwt = jwtUtil(60);
        String token = jwt.createAccessToken(new UserContext(1, "admin", "admin"));

        UserContext parsed = jwt.parseAccessToken(token);

        assertEquals(1, parsed.id());
        assertEquals("admin", parsed.username());
        assertEquals("admin", parsed.role());
    }

    @Test
    void parse_tamperedToken_throws401() {
        JwtUtil jwt = jwtUtil(60);
        String token = jwt.createAccessToken(new UserContext(1, "admin", "admin"));
        String tampered = token.substring(0, token.length() - 3) + "abc";

        BizException e = assertThrows(BizException.class, () -> jwt.parseAccessToken(tampered));
        assertEquals(HttpStatus.UNAUTHORIZED, e.status());
    }

    @Test
    void parse_expiredToken_throws401() {
        // 有效期 -2 分钟：签发即过期，且超出 30s 时钟宽限
        JwtUtil jwt = jwtUtil(-2);
        String token = jwt.createAccessToken(new UserContext(1, "admin", "admin"));

        BizException e = assertThrows(BizException.class, () -> jwt.parseAccessToken(token));
        assertEquals(HttpStatus.UNAUTHORIZED, e.status());
    }

    @Test
    void constructor_shortSecret_rejected() {
        AppProperties props = new AppProperties();
        props.getJwt().setSecret("too-short");
        assertThrows(IllegalStateException.class, () -> new JwtUtil(props));
    }
}
