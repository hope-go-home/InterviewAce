package com.interviewace.dto;

import jakarta.validation.constraints.NotBlank;

/** 手动录入题目请求 */
public record BankAddRequest(
        @NotBlank(message = "题干不能为空") String question,
        @NotBlank(message = "答案不能为空") String answer,
        String domain,
        Integer difficulty,
        String company,
        String url) {
}
