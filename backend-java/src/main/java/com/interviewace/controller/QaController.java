package com.interviewace.controller;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.dto.QARequest;
import com.interviewace.service.qa.QaService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;

/**
 * 题库问答 SSE 流式接口。
 * 事件序列：session → thinking → sources → stats → token* → answer → done
 * 与前端 stream.js 约定一致。
 */
@Tag(name = "题库问答", description = "SSE 流式 RAG 问答")
@RestController
public class QaController {

    private static final Logger log = LoggerFactory.getLogger(QaController.class);
    private static final ExecutorService SSE_POOL = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "sse-qa");
        t.setDaemon(true);
        return t;
    });

    private final QaService qaService;
    private final RateLimiter rateLimiter;
    private final ObjectMapper objectMapper;

    public QaController(QaService qaService, RateLimiter rateLimiter, ObjectMapper objectMapper) {
        this.qaService = qaService;
        this.rateLimiter = rateLimiter;
        this.objectMapper = objectMapper;
    }

    @Operation(summary = "题库问答（SSE 流式）")
    @PostMapping(value = "/qa/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter qaStream(@Valid @RequestBody QARequest req, @CurrentUser UserContext user) {
        String question = req.question() == null ? "" : req.question().strip();
        String image = req.imageBase64() == null ? "" : req.imageBase64().strip();
        if (question.isBlank() && image.isBlank()) {
            throw com.interviewace.common.BizException.badRequest("问题或图片不能为空");
        }
        if (question.isBlank()) question = "（图片题目）";

        if (!rateLimiter.allowChat(user.id())) {
            throw com.interviewace.common.BizException.tooMany("提问过于频繁，请稍后再试");
        }

        String sessionId = req.sessionId() != null && !req.sessionId().isBlank()
                ? req.sessionId() : qaService.newSessionId();
        String position = req.position() != null ? req.position() : "ai_app_dev";
        String level = req.level() != null ? req.level() : "campus";
        final String finalQuestion = question;

        // 超时给足 10 分钟：兜底路径 = 3 轮检索改写 + 联网搜索(≤3min) + 离线降级(≤3min)，5 分钟不够
        SseEmitter emitter = new SseEmitter(600_000L);

        SSE_POOL.submit(() -> {
            try {
                // 先发 session 事件
                emitter.send(SseEmitter.event()
                        .name("session")
                        .data(sseData(Map.of("session_id", sessionId))));

                // 取历史会话（MySQL 持久化，对应 Python db.get_history）
                List<Map<String, String>> history = qaService.loadHistory(sessionId, user.id());

                // 执行问答（流式回调 → SSE）
                String finalAnswer = qaService.answer(user.id(), finalQuestion, image, history,
                        position, level, new QaService.QaCallbacks() {
                            @Override
                            public void onThinking(Map<String, Object> step) {
                                sendEvent(emitter, "thinking", step);
                            }

                            @Override
                            public void onSources(List<Map<String, Object>> sources) {
                                sendEvent(emitter, "sources", sources);
                            }

                            @Override
                            public void onStats(Map<String, Object> stats) {
                                sendEvent(emitter, "stats", stats);
                            }

                            @Override
                            public void onToken(String content) {
                                sendEvent(emitter, "token", Map.of("content", content));
                            }

                            @Override
                            public void onAnswer(Map<String, Object> answerData) {
                                sendEvent(emitter, "answer", answerData);
                            }
                        });

                // 持久化
                qaService.saveRecord(sessionId, user.id(), finalQuestion, finalAnswer);

                // done 事件
                emitter.send(SseEmitter.event().name("done").data(sseData(Map.of())));
                emitter.complete();
            } catch (Exception e) {
                log.error("qa/stream failed", e);
                try {
                    emitter.send(SseEmitter.event()
                            .name("error")
                            .data(sseData(Map.of("message", "服务内部错误，请稍后重试"))));
                } catch (Exception ignore) {}
                emitter.completeWithError(e);
            }
        });

        return emitter;
    }

    private void sendEvent(SseEmitter emitter, String name, Object data) {
        try {
            emitter.send(SseEmitter.event().name(name).data(sseData(data)));
        } catch (Exception e) {
            log.warn("SSE send {} failed: {}", name, e.getMessage());
        }
    }

    private String sseData(Object data) {
        try {
            return objectMapper.writeValueAsString(data);
        } catch (Exception e) {
            return "{}";
        }
    }
}
