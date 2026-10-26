package com.interviewace.service.rag;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.interviewace.service.llm.EmbeddingService;

/**
 * 简化版稠密检索器：embed → Milvus dense search → 结构化结果。
 * Java 版不使用 BGE-M3 稀疏向量和 CrossEncoder 重排（Python ML 依赖），
 * 改为纯稠密 IP 检索 + 按分数截断，效果相近且零额外依赖。
 */
@Service
public class RetrievalService {

    private static final Logger log = LoggerFactory.getLogger(RetrievalService.class);
    private static final int CACHE_TTL_MS = 300_000;
    private static final int CACHE_MAX = 512;

    private final MilvusService milvus;
    private final EmbeddingService embedding;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();
    private final java.util.concurrent.atomic.LongAdder hits = new java.util.concurrent.atomic.LongAdder();
    private final java.util.concurrent.atomic.LongAdder misses = new java.util.concurrent.atomic.LongAdder();

    public RetrievalService(MilvusService milvus, EmbeddingService embedding) {
        this.milvus = milvus;
        this.embedding = embedding;
    }

    /** 缓存统计（对应 Python cache.stats()）*/
    public Map<String, Object> stats() {
        long h = hits.sum();
        long m = misses.sum();
        long total = h + m;
        Map<String, Object> out = new java.util.LinkedHashMap<>();
        out.put("name", "retrieval");
        out.put("size", cache.size());
        out.put("hits", h);
        out.put("misses", m);
        out.put("hit_rate", total == 0 ? 0.0 : Math.round(h * 1000.0 / total) / 1000.0);
        return out;
    }

    /** 核心检索：域过滤 + 稠密向量检索 */
    public RetrievalResult retrieve(String query, int topK, String domain, String position) {
        if (!milvus.isReady()) {
            return RetrievalResult.empty();
        }

        // 缓存
        String key = query + "|" + domain + "|" + position;
        CacheEntry cached = cache.get(key);
        if (cached != null && System.currentTimeMillis() - cached.time < CACHE_TTL_MS) {
            hits.increment();
            return cached.result;
        }
        misses.increment();

        // 构造过滤
        String expr = MilvusService.buildFilterExpr(domain, null, null, null, position);
        boolean crossDomain = false;

        // 嵌入查询
        float[] vec = embedding.embedQuery(query);
        if (vec.length == 0) return RetrievalResult.empty();

        // 检索
        int pool = Math.max(topK * 3, 20);
        List<MilvusService.SearchHit> hits = milvus.searchDense(vec, pool, expr, null);

        // 域过滤不足时 fallback 全库
        if (hits.size() < 3 && domain != null && !domain.isBlank()) {
            hits = milvus.searchDense(vec, pool, null, null);
            crossDomain = true;
        }

        // 去重 + 截断
        List<RetrievalSource> sources = new ArrayList<>();
        java.util.HashSet<String> seen = new java.util.HashSet<>();
        for (MilvusService.SearchHit hit : hits) {
            String id = hit.parentText() + "|" + hit.title();
            if (!seen.add(id)) continue;
            sources.add(new RetrievalSource(
                    hit.parentText(), hit.text(),
                    sources.size() + 1, hit.score(), hit.score(),
                    hit.qType(), hit.domain(), hit.difficulty(),
                    hit.company(), hit.source(), hit.title(), hit.url()));
            if (sources.size() >= topK) break;
        }

        List<String> documents = sources.stream().map(RetrievalSource::parentText).toList();
        RetrievalResult result = new RetrievalResult(documents, sources, hits.size(), hits.size(),
                sources.size(), crossDomain);

        // 存缓存（简单 LRU）
        if (cache.size() > CACHE_MAX) {
            cache.entrySet().stream()
                    .sorted(Map.Entry.comparingByValue(Comparator.comparing(e -> e.time)))
                    .limit(32)
                    .map(Map.Entry::getKey)
                    .toList()
                    .forEach(cache::remove);
        }
        cache.put(key, new CacheEntry(result, System.currentTimeMillis()));
        return result;
    }

    private record CacheEntry(RetrievalResult result, long time) {}

    /** 检索单条来源元数据 */
    public record RetrievalSource(
            String parentText, String text,
            int rank, float score, float rerankScore,
            String qType, String domain, int difficulty,
            String company, String source, String title, String url) {
    }

    /** 检索结果包装 */
    public record RetrievalResult(
            List<String> documents, List<RetrievalSource> sources,
            int denseHits, int sparseHits, int fusedCount, boolean crossDomain) {
        static RetrievalResult empty() {
            return new RetrievalResult(List.of(), List.of(), 0, 0, 0, false);
        }
    }
}
