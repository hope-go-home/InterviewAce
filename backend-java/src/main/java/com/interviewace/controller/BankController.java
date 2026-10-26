package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.FavoriteItem;
import com.interviewace.dto.FavoriteRequest;
import com.interviewace.service.FavoriteService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 题库标记接口：收藏 / 错题本。
 * 题库统计、浏览、录入（依赖 Milvus）在 BankKnowledgeController（M3）。
 */
@Tag(name = "题库标记", description = "收藏与错题本")
@RestController
public class BankController {

    private final FavoriteService favoriteService;

    public BankController(FavoriteService favoriteService) {
        this.favoriteService = favoriteService;
    }

    @Operation(summary = "收藏/错题 标记切换（action=add|remove，ftype=fav|wrong）")
    @PostMapping("/bank/favorite")
    public Map<String, Object> toggle(@Valid @RequestBody FavoriteRequest req,
                                      @CurrentUser UserContext user) {
        return favoriteService.toggle(req, user.id());
    }

    @Operation(summary = "我的收藏列表")
    @GetMapping("/bank/favorites")
    public Map<String, List<FavoriteItem>> favorites(@CurrentUser UserContext user) {
        return Map.of("items", favoriteService.list(user.id(), "fav"));
    }

    @Operation(summary = "我的错题本列表")
    @GetMapping("/bank/wrong")
    public Map<String, List<FavoriteItem>> wrong(@CurrentUser UserContext user) {
        return Map.of("items", favoriteService.list(user.id(), "wrong"));
    }
}
