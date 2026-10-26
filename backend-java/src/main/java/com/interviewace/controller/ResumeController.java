package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.ResumeDetail;
import com.interviewace.dto.ResumeListItem;
import com.interviewace.service.ResumeService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 简历备考接口（查询侧）：历史列表 / 详情。
 * 上传解析、话术生成、项目预演（依赖 Tika + LLM）在 ResumeGenerateController（M3）。
 */
@Tag(name = "简历备考", description = "简历历史与详情")
@RestController
public class ResumeController {

    private final ResumeService resumeService;

    public ResumeController(ResumeService resumeService) {
        this.resumeService = resumeService;
    }

    @Operation(summary = "历史简历列表")
    @GetMapping("/resume/list")
    public Map<String, List<ResumeListItem>> list(@CurrentUser UserContext user) {
        return Map.of("items", resumeService.list(user.id()));
    }

    @Operation(summary = "简历完整备考内容")
    @GetMapping("/resume/{resumeId}")
    public ResumeDetail detail(@PathVariable Integer resumeId, @CurrentUser UserContext user) {
        return resumeService.detail(resumeId, user.id());
    }
}
