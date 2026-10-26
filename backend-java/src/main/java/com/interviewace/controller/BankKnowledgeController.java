package com.interviewace.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.dto.BankAddRequest;
import com.interviewace.service.bank.BankKnowledgeService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 题库知识接口：统计 / 浏览 / 手动入库 / 文档上传。
 * 收藏/错题本在 BankController。
 */
@Tag(name = "题库知识", description = "统计/浏览/入库/上传")
@RestController
public class BankKnowledgeController {

    private final BankKnowledgeService bankService;
    private final RateLimiter rateLimiter;

    public BankKnowledgeController(BankKnowledgeService bankService, RateLimiter rateLimiter) {
        this.bankService = bankService;
        this.rateLimiter = rateLimiter;
    }

    @Operation(summary = "题库统计")
    @GetMapping("/bank/stats")
    public Map<String, Object> stats(@CurrentUser UserContext user) {
        return bankService.stats();
    }

    @Operation(summary = "题库浏览（分页 + 过滤）")
    @GetMapping("/bank/questions")
    public Map<String, Object> questions(
            @RequestParam(required = false) String domain,
            @RequestParam(required = false) Integer difficulty,
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize,
            @CurrentUser UserContext user) {
        return bankService.questions(domain, difficulty, q, page, pageSize);
    }

    @Operation(summary = "手动录入一道 QA")
    @PostMapping("/bank/add")
    public Map<String, Object> add(@Valid @RequestBody BankAddRequest req,
                                   @CurrentUser UserContext user) {
        if (!rateLimiter.allowUpload(user.id())) {
            throw com.interviewace.common.BizException.tooMany("操作过于频繁，请稍后再试");
        }
        return bankService.add(req.question(), req.answer(),
                req.domain() != null ? req.domain() : "llm_basics",
                req.difficulty() != null ? req.difficulty() : 2,
                req.company(), req.url(), user.username());
    }

    @Operation(summary = "上传文档入库")
    @PostMapping("/bank/upload")
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file,
                                      @RequestParam(defaultValue = "cs_basic") String domain,
                                      @RequestParam(defaultValue = "false") boolean asQa,
                                      @CurrentUser UserContext user) {
        if (!rateLimiter.allowUpload(user.id())) {
            throw com.interviewace.common.BizException.tooMany("上传过于频繁，请稍后再试");
        }
        if (file.getSize() > 20 * 1024 * 1024) {
            throw com.interviewace.common.BizException.badRequest("文件不能超过 20MB");
        }
        try {
            return bankService.upload(file.getBytes(), file.getOriginalFilename(), domain, asQa, user.username());
        } catch (java.io.IOException e) {
            throw com.interviewace.common.BizException.badRequest("文件读取失败：" + e.getMessage());
        }
    }
}
