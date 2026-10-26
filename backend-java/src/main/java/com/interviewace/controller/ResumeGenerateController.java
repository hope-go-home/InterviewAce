package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.dto.RehearseRequest;
import com.interviewace.dto.ResumeGenRequest;
import com.interviewace.service.resume.ResumeGenerateService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 简历备考生成接口：上传解析 / 话术生成 / 项目预演。
 * 历史列表与详情在 ResumeController。
 */
@Tag(name = "简历备考生成", description = "上传解析/话术/预演")
@RestController
public class ResumeGenerateController {

    private final ResumeGenerateService generateService;
    private final RateLimiter rateLimiter;

    public ResumeGenerateController(ResumeGenerateService generateService, RateLimiter rateLimiter) {
        this.generateService = generateService;
        this.rateLimiter = rateLimiter;
    }

    @Operation(summary = "上传简历（PDF/DOCX/TXT/MD）→ 解析并生成面试题")
    @PostMapping("/resume/upload")
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file,
                                      @CurrentUser UserContext user) {
        if (!rateLimiter.allowUpload(user.id())) {
            throw com.interviewace.common.BizException.tooMany("上传过于频繁，请稍后再试");
        }
        if (file.getSize() > 10 * 1024 * 1024) {
            throw com.interviewace.common.BizException.badRequest("文件不能超过 10MB");
        }
        try {
            return generateService.upload(file.getBytes(), file.getOriginalFilename(), user.id());
        } catch (java.io.IOException e) {
            throw com.interviewace.common.BizException.badRequest("文件读取失败：" + e.getMessage());
        }
    }

    @Operation(summary = "生成 60s/90s 自我介绍话术")
    @PostMapping("/resume/pitch")
    public Map<String, Object> pitch(@Valid @RequestBody ResumeGenRequest req,
                                     @CurrentUser UserContext user) {
        return generateService.generatePitch(req.profile(),
                req.level() != null ? req.level() : "campus", req.resumeId());
    }

    @Operation(summary = "项目预演：深挖问题 + 应答要点")
    @PostMapping("/resume/rehearse")
    public Map<String, Object> rehearse(@Valid @RequestBody RehearseRequest req,
                                        @CurrentUser UserContext user) {
        return generateService.rehearseProject(req.project(),
                req.skills() != null ? req.skills() : List.of(),
                req.n() != null ? req.n() : 5, req.resumeId());
    }
}
