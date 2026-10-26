package com.interviewace.dto;

import java.time.LocalDateTime;

/** 历史面试列表项：对应 mysql.py list_interviews 的 dict 结构。 */
public record InterviewListItem(
        Integer id,
        String position,
        String level,
        Integer numQuestions,
        String status,
        Integer totalScore,
        LocalDateTime createdAt) {
}
