package com.interviewace.service.llm;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.interviewace.config.AppProperties;

/**
 * DashScope 文本重排客户端（qwen3.7-text-rerank，原生 HTTP 接口，非 OpenAI 兼容协议）。
 * 对应 Python 侧本地 bge-reranker-v2-m3 CrossEncoder：输入 query + 候选文档，
 * 返回每个候选的 relevance_score（0-1，越大越相关）。
 * 失败返回 null，调用方回退为稠密检索顺序（优雅降级）。
 */
@Component
public class RerankService {

    private static final Logger log = LoggerFactory.getLogger(RerankService.class);

    private final HttpClient http;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String model;
    private final String url;

    public RerankService(AppProperties props, ObjectMapper objectMapper) {
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.objectMapper = objectMapper;
        this.apiKey = props.getAi().getQwen().getApiKey();
        this.model = props.getAi().getQwen().getRerankModel();
        this.url = props.getAi().getQwen().getRerankUrl();
    }

    public boolean configured() {
        return model != null && !model.isBlank() && apiKey != null && !apiKey.isBlank();
    }

    /**
     * 对候选文档按与 query 的相关性打分。返回与 documents 等长的分数数组；
     * 任何失败（网络/限流/模型不可用）返回 null，由调用方决定降级策略。
     */
    public double[] rerank(String query, List<String> documents) {
        if (!configured() || documents.isEmpty()) {
            return null;
        }
        try {
            ObjectNode body = objectMapper.createObjectNode();
            body.put("model", model);
            ObjectNode input = body.putObject("input");
            input.put("query", query);
            ArrayNode docs = input.putArray("documents");
            documents.forEach(docs::add);
            body.putObject("parameters")
                    .put("top_n", documents.size())
                    .put("return_documents", false);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + apiKey)
                    .timeout(Duration.ofSeconds(30))
                    .POST(HttpRequest.BodyPublishers.ofString(body.toString(), StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                log.warn("rerank HTTP {}: {}", resp.statusCode(),
                        resp.body().substring(0, Math.min(300, resp.body().length())));
                return null;
            }
            JsonNode results = objectMapper.readTree(resp.body()).path("output").path("results");
            if (!results.isArray() || results.isEmpty()) {
                log.warn("rerank empty results");
                return null;
            }
            double[] scores = new double[documents.size()];
            for (JsonNode r : results) {
                int idx = r.path("index").asInt(-1);
                if (idx >= 0 && idx < scores.length) {
                    scores[idx] = r.path("relevance_score").asDouble(0.0);
                }
            }
            return scores;
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("rerank failed: {}", e.getMessage());
            return null;
        }
    }
}
