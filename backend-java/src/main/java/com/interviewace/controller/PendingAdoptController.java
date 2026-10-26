package com.interviewace.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.service.pending.PendingAdoptService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 待补题池采纳接口。列表在 PendingController。
 */
@Tag(name = "待补题采纳", description = "采纳入库")
@RestController
public class PendingAdoptController {

    private final PendingAdoptService adoptService;

    public PendingAdoptController(PendingAdoptService adoptService) {
        this.adoptService = adoptService;
    }

    @Operation(summary = "采纳入库（LLM 生成标准答案 → 入题库）")
    @PostMapping("/pending/{pendingId}/adopt")
    public Map<String, Object> adopt(@PathVariable int pendingId, @CurrentUser UserContext user) {
        return adoptService.adopt(pendingId, user.id(), user.username());
    }
}
