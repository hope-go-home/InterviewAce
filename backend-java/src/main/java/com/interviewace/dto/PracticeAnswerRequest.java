package com.interviewace.dto;

import jakarta.validation.constraints.NotBlank;

/** 练习作答请求 */
public record PracticeAnswerRequest(
        @NotBlank(message = "题目不能为空") String questionTitle,
        String questionUrl,
        String domain,
        Integer difficulty,
        String position,
        String level,
        @NotBlank(message = "作答不能为空") String myAnswer) {
}
