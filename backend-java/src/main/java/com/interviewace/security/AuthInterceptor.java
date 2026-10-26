package com.interviewace.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import com.interviewace.common.UserContext;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * 登录鉴权拦截器：校验 Authorization: Bearer <token>。
 *
 * <p>对应 FastAPI 的 Depends(get_current_user)：
 * 缺 token → 401 {"detail": "未登录或缺少 Token"}
 * token 过期/非法 → 401 {"detail": "Token 已过期"/"Token 无效"}
 * 校验通过 → 当前用户写入 request attribute，供 @CurrentUser 解析。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    public static final String BEARER_PREFIX = "Bearer ";

    private final JwtUtil jwtUtil;
    private final ObjectMapper objectMapper;

    public AuthInterceptor(JwtUtil jwtUtil, ObjectMapper objectMapper) {
        this.jwtUtil = jwtUtil;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        String header = request.getHeader("Authorization");
        if (header == null || header.isBlank()) {
            return reject(response, 401, "未登录或缺少 Token");
        }
        if (!header.startsWith(BEARER_PREFIX)) {
            return reject(response, 401, "Token 格式错误");
        }

        try {
            UserContext user = jwtUtil.parseAccessToken(header.substring(BEARER_PREFIX.length()).trim());
            request.setAttribute(UserContext.REQUEST_ATTRIBUTE, user);
            return true;
        } catch (Exception e) {
            String detail = e.getMessage() == null ? "Token 无效" : e.getMessage();
            return reject(response, 401, detail);
        }
    }

    private boolean reject(HttpServletResponse response, int status, String detail) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(java.util.Map.of("detail", detail)));
        return false;
    }
}
