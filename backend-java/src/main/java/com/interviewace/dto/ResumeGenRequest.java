package com.interviewace.dto;

import java.util.Map;

import jakarta.validation.constraints.NotNull;

/** 简历话术生成请求 */
public record ResumeGenRequest(
        @NotNull(message = "profile 不能为空") Map<String, Object> profile,
        String level,
        Integer resumeId) {
}
