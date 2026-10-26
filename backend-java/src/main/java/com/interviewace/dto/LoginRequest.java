package com.interviewace.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * 登录/注册请求体（与前端 {username, password} 对齐）。
 * Jackson 全局 SNAKE_CASE 策略下字段名即契约名。
 */
public record LoginRequest(
        @NotBlank(message = "用户名不能为空") String username,
        @NotBlank(message = "密码不能为空") String password) {
}
