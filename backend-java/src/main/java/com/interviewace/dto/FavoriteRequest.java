package com.interviewace.dto;

import java.time.LocalDateTime;

import jakarta.validation.constraints.NotBlank;

/**
 * 收藏/错题标记请求体（对应 main.py FavoriteRequest）。
 * ftype: fav/wrong，action: add/remove，缺省值与 Python 默认一致。
 */
public record FavoriteRequest(
        @NotBlank(message = "question_title 不能为空") String questionTitle,
        String questionUrl,
        String domain,
        Integer difficulty,
        String ftype,
        String action) {

    public FavoriteRequest {
        questionUrl = questionUrl == null ? "" : questionUrl;
        domain = domain == null ? "" : domain;
        difficulty = difficulty == null ? 0 : difficulty;
        ftype = ftype == null || ftype.isBlank() ? "fav" : ftype;
        action = action == null || action.isBlank() ? "add" : action;
    }
}
