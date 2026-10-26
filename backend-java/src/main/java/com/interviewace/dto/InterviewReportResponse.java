package com.interviewace.dto;

import java.time.LocalDateTime;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * 面试报告响应：对应 main.py /interview/{id}/report 的结构。
 * report 自由结构（LLM 生成）用 JsonNode 透传；turns 为逐轮问答。
 */
public record InterviewReportResponse(
        SessionDetail session,
        JsonNode report,
        List<TurnItem> turns) {

    /** 对应 mysql.py get_interview_session 的 dict 结构 */
    public record SessionDetail(
            Integer id,
            Integer userId,
            String position,
            String level,
            List<String> domains,
            Integer numQuestions,
            Integer difficultyCap,
            String status,
            Integer currentSeq,
            Integer totalScore,
            LocalDateTime createdAt,
            LocalDateTime finishedAt) {
    }

    /** 对应 mysql.py list_turns 的 dict 结构 */
    public record TurnItem(
            Integer id,
            Integer seq,
            Integer parentTurnId,
            Integer followupNo,
            String question,
            String questionSource,
            String answer,
            Integer score,
            String feedback,
            JsonNode missingPoints,
            JsonNode dimensions,
            JsonNode qaRefs,
            LocalDateTime createdAt) {
    }
}
