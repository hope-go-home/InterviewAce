package com.interviewace.dto;

import java.time.LocalDateTime;

/** 收藏/错题列表项：对应 mysql.py list_favorites 的 dict 结构。 */
public record FavoriteItem(
        Integer id,
        String questionTitle,
        String questionUrl,
        String domain,
        Integer difficulty,
        LocalDateTime createdAt) {
}
