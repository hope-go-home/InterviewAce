package com.interviewace.controller;

import java.sql.Connection;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.config.AppProperties;
import com.interviewace.service.llm.EmbeddingService;
import com.interviewace.service.rag.MilvusService;
import com.interviewace.service.rag.RetrievalService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 运维观测端点：/domains 题量统计、/cache/stats 缓存命中率、/ready 就绪探针。
 * 对应 FastAPI tags=ops / qa 的运维类路由。
 */
@Tag(name = "运维", description = "观测与探针")
@RestController
public class OpsController {

    private final MilvusService milvus;
    private final EmbeddingService embedding;
    private final RetrievalService retrieval;
    private final AppProperties props;
    private final DataSource dataSource;

    public OpsController(MilvusService milvus, EmbeddingService embedding,
                         RetrievalService retrieval, AppProperties props, DataSource dataSource) {
        this.milvus = milvus;
        this.embedding = embedding;
        this.retrieval = retrieval;
        this.props = props;
        this.dataSource = dataSource;
    }

    @Operation(summary = "各领域题量统计")
    @GetMapping("/domains")
    public Map<String, Object> domains(@CurrentUser UserContext user) {
        Map<String, Object> out = new LinkedHashMap<>();
        Map<String, Long> stats = new LinkedHashMap<>();
        long total = 0;
        for (String d : AppProperties.DOMAINS) {
            long c = milvus.isReady()
                    ? milvus.count("domain == \"" + d + "\"") : 0;
            stats.put(d, c);
            total += c;
        }
        out.put("total", total);
        out.put("domains", stats);
        return out;
    }

    @Operation(summary = "缓存命中率（排查成本/性能用）")
    @GetMapping("/cache/stats")
    public Map<String, Object> cacheStats(@CurrentUser UserContext user) {
        List<Map<String, Object>> caches = new ArrayList<>();
        caches.add(embedding.stats());
        caches.add(retrieval.stats());
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("caches", caches);
        out.put("heavy_concurrency_limit", props.getHeavyConcurrency());
        return out;
    }

    @Operation(summary = "就绪探针：MySQL + Milvus + 嵌入配置")
    @GetMapping("/ready")
    public Map<String, Object> ready() {
        boolean mysql = false;
        try (Connection conn = dataSource.getConnection()) {
            mysql = conn.isValid(2);
        } catch (Exception ignored) {
        }
        boolean milvusOk = milvus.isReady();
        boolean embeddingOk = props.getAi().getQwen().getApiKey() != null
                && !props.getAi().getQwen().getApiKey().isBlank();
        boolean ok = mysql && milvusOk && embeddingOk;
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", ok ? "ok" : "degraded");
        out.put("mysql", mysql);
        out.put("milvus", milvusOk);
        out.put("embedding", embeddingOk);
        return out;
    }
}
