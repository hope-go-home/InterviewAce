package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.PendingItem;
import com.interviewace.service.PendingService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 待补题池接口（查询侧）：列表按被问次数排序。
 * 采纳入库（LLM 生成标准答案）在 PendingAdoptController（M3）。
 */
@Tag(name = "待补题池", description = "题库外问题收集")
@RestController
public class PendingController {

    private final PendingService pendingService;

    public PendingController(PendingService pendingService) {
        this.pendingService = pendingService;
    }

    @Operation(summary = "待补题列表（可按 status 过滤）")
    @GetMapping("/pending/list")
    public Map<String, List<PendingItem>> list(
            @RequestParam(required = false) String status,
            @CurrentUser UserContext user) {
        return Map.of("items", pendingService.list(status));
    }
}
