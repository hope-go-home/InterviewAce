package com.interviewace.dto;

import java.time.LocalDateTime;

/** 练习记录列表项：对应 mysql.py list_practice 的 dict 结构（不含正文 my_answer）。 */
public record PracticeRecordItem(
        Integer id,
        String questionTitle,
        String questionUrl,
        String domain,
        Integer difficulty,
        Integer score,
        String feedback,
        Boolean isWrong,
        LocalDateTime createdAt) {
}
