package com.interviewace.dto;

import java.time.LocalDateTime;

/** 待补题列表项：对应 mysql.py list_pending 的 dict 结构。 */
public record PendingItem(
        Integer id,
        String question,
        String domain,
        String position,
        Integer askCount,
        String draftAnswer,
        String sourceUrl,
        String status,
        LocalDateTime createdAt) {
}
