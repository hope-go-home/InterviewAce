package com.interviewace.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.LoginRequest;
import com.interviewace.service.AuthService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;

/**
 * 认证接口：登录 / 注册 / 当前用户。
 * 路径与响应结构和 FastAPI 版完全一致，前端零改动。
 */
@Tag(name = "认证", description = "登录注册与当前用户")
@RestController
@RequestMapping("/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @Operation(summary = "登录，返回 JWT token")
    @PostMapping("/login")
    public Map<String, Object> login(@Valid @RequestBody LoginRequest req, HttpServletRequest request) {
        return authService.login(req, clientIp(request));
    }

    @Operation(summary = "注册（受 app.allow-registration 开关控制）")
    @PostMapping("/register")
    public Map<String, Object> register(@Valid @RequestBody LoginRequest req, HttpServletRequest request) {
        return authService.register(req, clientIp(request));
    }

    @Operation(summary = "当前登录用户信息")
    @GetMapping("/me")
    public Map<String, Object> me(@CurrentUser UserContext user) {
        return authService.me(user);
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
