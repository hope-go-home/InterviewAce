package com.interviewace.dto;

import java.time.LocalDateTime;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;

/** 简历详情：对应 main.py /resume/{id} 的结构（自由结构字段用 JsonNode 透传）。 */
public record ResumeDetail(
        Integer id,
        String filename,
        String name,
        String target,
        JsonNode skills,
        JsonNode projects,
        JsonNode questions,
        JsonNode pitch,
        JsonNode rehearse,
        LocalDateTime createdAt) {
}
