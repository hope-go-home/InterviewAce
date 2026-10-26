package com.interviewace.dto;

/** SSE 问答请求（对应 Python QARequest）；question 允许为空——纯图片题由 Controller 层校验 question/image 二选一 */
public record QARequest(
        String question,
        String sessionId,
        String imageBase64,
        String position,
        String level) {
}
