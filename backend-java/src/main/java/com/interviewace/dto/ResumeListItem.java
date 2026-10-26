package com.interviewace.dto;

import java.time.LocalDateTime;

/** 简历历史列表项：对应 mysql.py list_resumes 的 dict 结构。 */
public record ResumeListItem(
        Integer id,
        String filename,
        String name,
        String target,
        LocalDateTime createdAt) {
}
