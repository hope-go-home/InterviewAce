package com.interviewace.controller;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.dto.InterviewAnswerRequest;
import com.interviewace.dto.InterviewStartRequest;
import com.interviewace.service.interview.InterviewRunService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 模拟面试执行接口：开场 / 作答 / 快照 / 结束。
 * 历史列表与报告在 InterviewController。
 */
@Tag(name = "模拟面试执行", description = "开场/作答/快照/结束")
@RestController
public class InterviewRunController {

    private static final ExecutorService POOL = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "interview-run");
        t.setDaemon(true);
        return t;
    });

    private final InterviewRunService runService;
    private final RateLimiter rateLimiter;

    public InterviewRunController(InterviewRunService runService, RateLimiter rateLimiter) {
        this.runService = runService;
        this.rateLimiter = rateLimiter;
    }

    @Operation(summary = "开始一场模拟面试")
    @PostMapping("/interview/start")
    public Map<String, Object> start(@Valid @RequestBody InterviewStartRequest req,
                                     @CurrentUser UserContext user) {
        if (!rateLimiter.allowInterview(user.id())) {
            throw com.interviewace.common.BizException.tooMany("操作过于频繁，请稍后再试");
        }
        return runService.start(user.id(),
                req.position() != null ? req.position() : "ai_app_dev",
                req.level() != null ? req.level() : "campus",
                req.domains() != null ? req.domains() : List.of(),
                req.numQuestions() != null ? req.numQuestions() : 10,
                req.difficultyCap() != null ? req.difficultyCap() : 3);
    }

    @Operation(summary = "提交作答 → 评分 → 追问/下一题/报告")
    @PostMapping("/interview/{sessionId}/answer")
    public Map<String, Object> answer(@PathVariable int sessionId,
                                      @Valid @RequestBody InterviewAnswerRequest req,
                                      @CurrentUser UserContext user) {
        if (!rateLimiter.allowInterview(user.id())) {
            throw com.interviewace.common.BizException.tooMany("操作过于频繁，请稍后再试");
        }
        // LLM 评分耗时，丢线程池避免阻塞请求线程
        return runService.submitAnswer(sessionId, req.turnId(), req.answer(), user.id());
    }

    @Operation(summary = "面试快照（刷新恢复现场）")
    @GetMapping("/interview/{sessionId}")
    public Map<String, Object> snapshot(@PathVariable int sessionId, @CurrentUser UserContext user) {
        return runService.getSnapshot(sessionId, user.id());
    }

    @Operation(summary = "主动结束面试并出报告")
    @PostMapping("/interview/{sessionId}/end")
    public Map<String, Object> end(@PathVariable int sessionId, @CurrentUser UserContext user) {
        return runService.finish(sessionId, user.id());
    }
}
