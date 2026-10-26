package com.interviewace.dto;

import java.time.LocalDateTime;

/** 会话列表项：对应 mysql.py list_sessions 的 dict 结构。 */
public record SessionSummary(
        String sessionId,
        String firstQuestion,
        LocalDateTime lastTime,
        Integer count) {
}
