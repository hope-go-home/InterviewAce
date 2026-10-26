package com.interviewace.service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.dto.FavoriteItem;
import com.interviewace.dto.FavoriteRequest;
import com.interviewace.entity.Favorite;
import com.interviewace.mapper.FavoriteMapper;

/**
 * 收藏/错题本服务：toggle 标记 + 列表查询。
 * 对应 mysql.py add_favorite / remove_favorite / list_favorites。
 */
@Service
public class FavoriteService {

    private final FavoriteMapper favoriteMapper;

    public FavoriteService(FavoriteMapper favoriteMapper) {
        this.favoriteMapper = favoriteMapper;
    }

    /** action=remove 删除标记；否则新增（已存在直接返回原 id，幂等） */
    public Map<String, Object> toggle(FavoriteRequest req, Integer userId) {
        if ("remove".equals(req.action())) {
            int n = favoriteMapper.delete(new LambdaQueryWrapper<Favorite>()
                    .eq(Favorite::getUserId, userId)
                    .eq(Favorite::getQuestionTitle, req.questionTitle())
                    .eq(Favorite::getFtype, req.ftype()));
            return Map.of("removed", n);
        }

        Favorite exist = favoriteMapper.selectOne(new LambdaQueryWrapper<Favorite>()
                .eq(Favorite::getUserId, userId)
                .eq(Favorite::getQuestionTitle, req.questionTitle())
                .eq(Favorite::getFtype, req.ftype())
                .last("LIMIT 1"));
        if (exist != null) {
            return Map.of("id", exist.getId());
        }

        Favorite row = new Favorite();
        row.setUserId(userId);
        row.setQuestionTitle(req.questionTitle());
        row.setQuestionUrl(req.questionUrl());
        row.setDomain(req.domain());
        row.setDifficulty(req.difficulty());
        row.setFtype(req.ftype());
        row.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        favoriteMapper.insert(row);
        return Map.of("id", row.getId());
    }

    public List<FavoriteItem> list(Integer userId, String ftype) {
        return favoriteMapper.selectList(new LambdaQueryWrapper<Favorite>()
                        .eq(Favorite::getUserId, userId)
                        .eq(Favorite::getFtype, ftype)
                        .orderByDesc(Favorite::getCreatedAt)
                        .last("LIMIT 200")).stream()
                .map(f -> new FavoriteItem(f.getId(), f.getQuestionTitle(), f.getQuestionUrl(),
                        f.getDomain(), f.getDifficulty(), f.getCreatedAt()))
                .toList();
    }
}
