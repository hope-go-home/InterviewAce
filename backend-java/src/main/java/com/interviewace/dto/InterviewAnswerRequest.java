package com.interviewace.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/** 面试作答请求 */
public record InterviewAnswerRequest(
        @NotNull(message = "turn_id 不能为空") Integer turnId,
        @NotBlank(message = "answer 不能为空") String answer) {
}
