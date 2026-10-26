package com.interviewace.service.llm;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.interviewace.config.AppProperties;

/**
 * 通义千问嵌入 API 客户端（2048 维稠密向量）。
 * 对应 Python 侧 rag/embedding.py 的 OpenAIEmbeddings。
 * 带进程内缓存，同一文本不重复调 API。
 */
@Component
public class EmbeddingService {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingService.class);
    private static final int CACHE_MAX = 4096;

    private final HttpClient http;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String baseUrl;
    private final String model;
    private final ConcurrentHashMap<String, float[]> cache = new ConcurrentHashMap<>();
    private final java.util.concurrent.atomic.LongAdder hits = new java.util.concurrent.atomic.LongAdder();
    private final java.util.concurrent.atomic.LongAdder misses = new java.util.concurrent.atomic.LongAdder();

    /** 缓存统计（对应 Python dense_cache.stats()）*/
    public Map<String, Object> stats() {
        long h = hits.sum();
        long m = misses.sum();
        long total = h + m;
        Map<String, Object> out = new java.util.LinkedHashMap<>();
        out.put("name", "dense_embedding");
        out.put("size", cache.size());
        out.put("hits", h);
        out.put("misses", m);
        out.put("hit_rate", total == 0 ? 0.0 : Math.round(h * 1000.0 / total) / 1000.0);
        return out;
    }

    public EmbeddingService(AppProperties props, ObjectMapper objectMapper) {
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
        this.objectMapper = objectMapper;
        this.apiKey = props.getAi().getQwen().getApiKey();
        this.baseUrl = props.getAi().getQwen().getBaseUrl();
        this.model = props.getAi().getQwen().getEmbeddingModel();
    }

    /** 单条查询嵌入（带缓存） */
    public float[] embedQuery(String text) {
        if (text == null || text.isBlank()) return new float[0];
        float[] cached = cache.get(text);
        if (cached != null) {
            hits.increment();
            return cached;
        }
        misses.increment();
        return cache.computeIfAbsent(text, k -> {
            try {
                return callApi(k);
            } catch (Exception e) {
                log.warn("embedQuery failed: {}", e.getMessage());
                return new float[0];
            }
        });
    }

    /** 批量文档嵌入（入库用） */
    public List<float[]> embedDocuments(List<String> texts) {
        List<float[]> results = new ArrayList<>();
        // Qwen embedding 单次最多 20 条
        for (int i = 0; i < texts.size(); i += 20) {
            List<String> batch = new ArrayList<>(texts.subList(i, Math.min(i + 20, texts.size())));
            try {
                results.addAll(callApiBatch(batch));
            } catch (Exception e) {
                log.warn("embedDocuments batch {} failed: {}", i / 20, e.getMessage());
                // 失败则逐条重试
                for (String t : batch) {
                    results.add(callApi(t));
                }
            }
        }
        return results;
    }

    private float[] callApi(String text) {
        try {
            List<float[]> batch = callApiBatch(List.of(text));
            return batch.isEmpty() ? new float[0] : batch.get(0);
        } catch (Exception e) {
            log.warn("callApi failed: {}", e.getMessage());
            return new float[0];
        }
    }

    private List<float[]> callApiBatch(List<String> texts) throws IOException, InterruptedException {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", model);
        body.put("dimensions", 2048);
        ArrayNode input = body.putArray("input");
        texts.forEach(input::add);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/embeddings"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .timeout(Duration.ofSeconds(30))
                .POST(HttpRequest.BodyPublishers.ofString(body.toString(), StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200) {
            throw new IOException("Embedding HTTP " + resp.statusCode() + ": " + resp.body());
        }

        JsonNode root = objectMapper.readTree(resp.body());
        JsonNode data = root.path("data");
        List<float[]> results = new ArrayList<>();
        for (JsonNode item : data) {
            JsonNode embedding = item.path("embedding");
            float[] vec = new float[embedding.size()];
            for (int i = 0; i < vec.length; i++) {
                vec[i] = (float) embedding.get(i).asDouble();
            }
            results.add(vec);
        }
        return results;
    }
}
