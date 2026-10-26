package com.interviewace.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 存活探针：Docker HEALTHCHECK / K8s livenessProbe 依赖 /health 永远可用。
 * 对应 FastAPI health.py /health，响应结构保持一致。
 */
@Tag(name = "探针", description = "存活与就绪探针")
@RestController
public class HealthController {

    @Operation(summary = "存活探针：进程存活即返回 ok")
    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "ok",
                "service", "InterviewAce");
    }
}
