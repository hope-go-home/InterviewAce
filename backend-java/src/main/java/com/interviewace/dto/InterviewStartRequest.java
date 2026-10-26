package com.interviewace.dto;

import java.util.List;

/** 面试开场请求 */
public record InterviewStartRequest(
        String position,
        String level,
        List<String> domains,
        Integer numQuestions,
        Integer difficultyCap) {
}
