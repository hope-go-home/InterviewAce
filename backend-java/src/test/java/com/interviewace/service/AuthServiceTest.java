package com.interviewace.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import com.interviewace.common.BizException;
import com.interviewace.common.audit.AuditService;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.config.AppProperties;
import com.interviewace.dto.LoginRequest;
import com.interviewace.entity.User;
import com.interviewace.mapper.UserMapper;
import com.interviewace.security.JwtUtil;
import com.interviewace.security.PasswordService;

class AuthServiceTest {

    private UserMapper userMapper;
    private PasswordService passwordService;
    private JwtUtil jwtUtil;
    private RateLimiter rateLimiter;
    private AuditService auditService;
    private AppProperties props;
    private AuthService service;

    @BeforeEach
    void setUp() {
        userMapper = mock(UserMapper.class);
        passwordService = mock(PasswordService.class);
        jwtUtil = mock(JwtUtil.class);
        rateLimiter = mock(RateLimiter.class);
        auditService = mock(AuditService.class);
        props = new AppProperties();
        service = new AuthService(userMapper, passwordService, jwtUtil, rateLimiter, auditService, props);
        when(rateLimiter.allowLogin(anyString())).thenReturn(true);
    }

    private User activeUser() {
        User u = new User();
        u.setId(1);
        u.setUsername("admin");
        u.setPasswordHash("$2b$12$xxx");
        u.setRole("admin");
        u.setActive(true);
        return u;
    }

    @Test
    void login_success_returnsTokenAndAudits() {
        when(userMapper.selectOne(any())).thenReturn(activeUser());
        when(passwordService.matches("admin123", "$2b$12$xxx")).thenReturn(true);
        when(jwtUtil.createAccessToken(any())).thenReturn("jwt-token");

        Map<String, Object> result = service.login(new LoginRequest("admin", "admin123"), "127.0.0.1");

        assertEquals("jwt-token", result.get("token"));
        assertEquals("admin", result.get("username"));
        assertEquals("admin", result.get("role"));
        verify(auditService).write(eq(1), eq("admin"), eq("login"), eq(""), eq("success"), eq("127.0.0.1"));
    }

    @Test
    void login_wrongPassword_401AndFailureAudit() {
        when(userMapper.selectOne(any())).thenReturn(activeUser());
        when(passwordService.matches(anyString(), anyString())).thenReturn(false);

        BizException e = assertThrows(BizException.class,
                () -> service.login(new LoginRequest("admin", "bad"), "127.0.0.1"));

        assertEquals(HttpStatus.UNAUTHORIZED, e.status());
        assertEquals("用户名或密码错误", e.getMessage());
        verify(auditService).write(eq(null), eq("admin"), eq("login"), eq(""), eq("failed"), eq("127.0.0.1"));
        verify(jwtUtil, never()).createAccessToken(any());
    }

    @Test
    void login_disabledAccount_403() {
        User u = activeUser();
        u.setActive(false);
        when(userMapper.selectOne(any())).thenReturn(u);
        when(passwordService.matches(anyString(), anyString())).thenReturn(true);

        BizException e = assertThrows(BizException.class,
                () -> service.login(new LoginRequest("admin", "admin123"), "127.0.0.1"));
        assertEquals(HttpStatus.FORBIDDEN, e.status());
    }

    @Test
    void register_closed_403() {
        props.setAllowRegistration(false);

        BizException e = assertThrows(BizException.class,
                () -> service.register(new LoginRequest("newbie", "password123"), "127.0.0.1"));

        assertEquals(HttpStatus.FORBIDDEN, e.status());
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void register_duplicateUsername_409() {
        when(userMapper.selectOne(any())).thenReturn(activeUser());

        BizException e = assertThrows(BizException.class,
                () -> service.register(new LoginRequest("admin", "password123"), "127.0.0.1"));

        assertEquals(HttpStatus.CONFLICT, e.status());
        verify(userMapper, never()).insert(any(User.class));
    }
}
