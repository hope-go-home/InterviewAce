package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.dto.PracticeAnswerRequest;
import com.interviewace.entity.PracticeRecord;
import com.interviewace.mapper.PracticeRecordMapper;
import com.interviewace.service.practice.PracticeAnswerService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 答题练习接口：抽题 / 作答评分 / 记录查询。
 * 记录查询在 PracticeController。
 */
@Tag(name = "答题练习执行", description = "抽题/作答评分")
@RestController
public class PracticeAnswerController {

    private final PracticeAnswerService answerService;
    private final PracticeRecordMapper practiceMapper;
    private final RateLimiter rateLimiter;

    public PracticeAnswerController(PracticeAnswerService answerService,
                                    PracticeRecordMapper practiceMapper, RateLimiter rateLimiter) {
        this.answerService = answerService;
        this.practiceMapper = practiceMapper;
        this.rateLimiter = rateLimiter;
    }

    @Operation(summary = "抽一道练习题")
    @GetMapping("/practice/next")
    public Map<String, Object> next(
            @RequestParam(required = false) String domain,
            @RequestParam(required = false) Integer difficulty,
            @RequestParam(required = false) String position,
            @RequestParam(required = false, defaultValue = "campus") String level,
            @CurrentUser UserContext user) {
        List<String> exclude = practicedTitles(user.id());
        return answerService.nextQuestion(domain, difficulty, position, level, exclude);
    }

    @Operation(summary = "一次抽 n 道题（前端预取队列）")
    @GetMapping("/practice/batch")
    public Map<String, Object> batch(
            @RequestParam(defaultValue = "8") int n,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false) Integer difficulty,
            @RequestParam(required = false) String position,
            @RequestParam(required = false, defaultValue = "campus") String level,
            @CurrentUser UserContext user) {
        List<String> exclude = practicedTitles(user.id());
        List<Map<String, Object>> items = answerService.batchQuestions(n, domain, difficulty, position, level, exclude);
        return Map.of("items", items);
    }

    @Operation(summary = "提交作答 → AI 评分")
    @PostMapping("/practice/answer")
    public Map<String, Object> answer(@Valid @RequestBody PracticeAnswerRequest req,
                                      @CurrentUser UserContext user) {
        String myAnswer = req.myAnswer() == null ? "" : req.myAnswer().strip();
        if (myAnswer.isBlank()) {
            throw com.interviewace.common.BizException.badRequest("请先写下你的作答");
        }
        if (!rateLimiter.allowInterview(user.id())) {
            throw com.interviewace.common.BizException.tooMany("操作过于频繁，请稍后再试");
        }
        return answerService.answer(
                req.questionTitle(), req.questionUrl(), req.domain(),
                req.difficulty(), req.position(),
                req.level() != null ? req.level() : "campus",
                myAnswer, user.id());
    }

    private List<String> practicedTitles(Integer userId) {
        return practiceMapper.selectList(new LambdaQueryWrapper<PracticeRecord>()
                        .eq(PracticeRecord::getUserId, userId)
                        .orderByDesc(PracticeRecord::getCreatedAt)
                        .last("LIMIT 500")).stream()
                .map(PracticeRecord::getQuestionTitle)
                .toList();
    }
}
