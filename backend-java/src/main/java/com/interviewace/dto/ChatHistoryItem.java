package com.interviewace.dto;

import java.time.LocalDateTime;

/** 会话历史单条：对应 mysql.py get_history 的 dict 结构。 */
public record ChatHistoryItem(String question, String answer, LocalDateTime createdAt) {
}
