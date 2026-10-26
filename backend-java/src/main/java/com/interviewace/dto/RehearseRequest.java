package com.interviewace.dto;

import java.util.List;

import jakarta.validation.constraints.NotBlank;

/** 项目预演请求 */
public record RehearseRequest(
        @NotBlank(message = "project 不能为空") String project,
        List<String> skills,
        Integer n,
        Integer resumeId) {
}
