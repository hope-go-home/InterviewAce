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
import com.interviewace.service.llm.RerankService;

/**
 * 稠密检索 + 云端重排：embed → Milvus dense search → qwen3.7-text-rerank 重排 → 截断。
 * 对应 Python retriever.py 的稠密通道 + CrossEncoder 重排段（稀疏通道不移植）。
 * 重排服务不可用时自动降级为稠密分数排序，保证检索永远可用。
 */
@Service
public class RetrievalService {

    private static final Logger log = LoggerFactory.getLogger(RetrievalService.class);
    private static final int CACHE_TTL_MS = 300_000;
    private static final int CACHE_MAX = 512;

    private final MilvusService milvus;
    private final EmbeddingService embedding;
    private final RerankService rerank;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();
    private final java.util.concurrent.atomic.LongAdder hits = new java.util.concurrent.atomic.LongAdder();
    private final java.util.concurrent.atomic.LongAdder misses = new java.util.concurrent.atomic.LongAdder();

    public RetrievalService(MilvusService milvus, EmbeddingService embedding, RerankService rerank) {
        this.milvus = milvus;
        this.embedding = embedding;
        this.rerank = rerank;
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

    /** 核心检索：域过滤 + 稠密向量检索 + 云端重排 */
    public RetrievalResult retrieve(String query, int topK, String domain, String position) {
        return retrieve(query, topK, domain, position, null);
    }

    /** qType 供评测/调试过滤题型（如 qa_pair）；QA 主链路不过滤（与 Python 一致） */
    public RetrievalResult retrieve(String query, int topK, String domain, String position, String qType) {
        if (!milvus.isReady()) {
            return RetrievalResult.empty();
        }

        // 缓存
        String key = query + "|" + domain + "|" + position + "|" + qType;
        CacheEntry cached = cache.get(key);
        if (cached != null && System.currentTimeMillis() - cached.time < CACHE_TTL_MS) {
            hits.increment();
            return cached.result;
        }
        misses.increment();

        // 构造过滤
        String expr = MilvusService.buildFilterExpr(domain, qType, null, null, position);
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

        // 去重（候选池保留到重排规模，截断留给重排后做）
        List<MilvusService.SearchHit> candidates = new ArrayList<>();
        java.util.HashSet<String> seen = new java.util.HashSet<>();
        for (MilvusService.SearchHit hit : hits) {
            String id = hit.parentText() + "|" + hit.title();
            if (!seen.add(id)) continue;
            candidates.add(hit);
        }

        // 云端重排（对应 Python CrossEncoder rerank；失败降级为稠密分排序）
        double[] scores = rerank.rerank(query,
                candidates.stream().map(MilvusService.SearchHit::parentText).toList());
        List<RetrievalSource> sources = new ArrayList<>();
        if (scores != null) {
            Integer[] order = new Integer[candidates.size()];
            for (int i = 0; i < order.length; i++) order[i] = i;
            java.util.Arrays.sort(order, (a, b) -> Double.compare(scores[b], scores[a]));
            int rank = 0;
            for (int idx : order) {
                MilvusService.SearchHit hit = candidates.get(idx);
                sources.add(toSource(hit, ++rank, scores[idx]));
                if (sources.size() >= topK) break;
            }
        } else {
            for (MilvusService.SearchHit hit : candidates) {
                sources.add(toSource(hit, sources.size() + 1, hit.score()));
                if (sources.size() >= topK) break;
            }
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

    private static RetrievalSource toSource(MilvusService.SearchHit hit, int rank, double rerankScore) {
        return new RetrievalSource(
                hit.parentText(), hit.text(),
                rank, hit.score(), (float) rerankScore,
                hit.qType(), hit.domain(), hit.difficulty(),
                hit.company(), hit.source(), hit.title(), hit.url());
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
