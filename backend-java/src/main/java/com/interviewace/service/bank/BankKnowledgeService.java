package com.interviewace.service.bank;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.interviewace.common.BizException;
import com.interviewace.config.AppProperties;
import com.interviewace.service.llm.EmbeddingService;
import com.interviewace.service.llm.LLMClient;
import com.interviewace.service.rag.MilvusService;
import com.interviewace.service.resume.ResumeGenerateService;

/**
 * 题库知识服务：统计 / 浏览 / 手动入库 / 文档上传。
 * 对应 main.py 的 /bank/stats, /bank/questions, /bank/add, /bank/upload。
 */
@Service
public class BankKnowledgeService {

    private static final Logger log = LoggerFactory.getLogger(BankKnowledgeService.class);

    private final MilvusService milvus;
    private final EmbeddingService embedding;
    private final LLMClient llm;
    private final ResumeGenerateService resumeService;

    public BankKnowledgeService(MilvusService milvus, EmbeddingService embedding,
                                LLMClient llm, ResumeGenerateService resumeService) {
        this.milvus = milvus;
        this.embedding = embedding;
        this.llm = llm;
        this.resumeService = resumeService;
    }

    /** 题库统计：总题数/按域分布/按类型分布 */
    public Map<String, Object> stats() {
        if (!milvus.isReady()) {
            return Map.of("total", 0, "by_domain", List.of(), "by_type", List.of());
        }
        long total = milvus.count("");
        List<Map<String, Object>> byDomain = new ArrayList<>();
        for (String d : AppProperties.DOMAINS) {
            long c = milvus.count("domain == \"" + d + "\"");
            byDomain.add(Map.of("domain", d, "domain_name", AppProperties.domainName(d), "count", c));
        }
        List<Map<String, Object>> byType = new ArrayList<>();
        for (String t : MilvusService.PARTITIONS) {
            long c = milvus.count("q_type == \"" + t + "\"");
            byType.add(Map.of("q_type", t, "count", c));
        }
        Map<String, Object> result = new HashMap<>();
        result.put("total", total);
        result.put("by_domain", byDomain);
        result.put("by_type", byType);
        return result;
    }

    /** 题库浏览：分页 + 过滤 + 标题搜索 */
    public Map<String, Object> questions(String domain, Integer difficulty, String q,
                                          int page, int pageSize) {
        if (!milvus.isReady()) {
            throw BizException.serviceUnavailable("题库暂不可用");
        }
        String expr = MilvusService.buildFilterExpr(domain, "qa_pair", difficulty, null, null);
        expr = expr.isBlank() ? "q_type == \"qa_pair\"" : "q_type == \"qa_pair\" and " + expr;

        long total = milvus.count(expr);
        page = Math.max(1, page);
        pageSize = Math.min(50, Math.max(1, pageSize));

        List<Map<String, Object>> rows = milvus.query(expr,
                List.of("title", "domain", "difficulty", "company", "url", "parent_text"),
                pageSize, (page - 1) * pageSize);

        List<Map<String, Object>> items = rows.stream().map(r -> {
            Map<String, Object> item = new HashMap<>();
            item.put("title", str(r, "title"));
            item.put("domain", str(r, "domain"));
            item.put("domain_name", AppProperties.domainName(str(r, "domain")));
            item.put("difficulty", r.get("difficulty") instanceof Number n ? n.intValue() : 0);
            item.put("company", str(r, "company"));
            item.put("url", str(r, "url"));
            item.put("answer", str(r, "parent_text"));
            return item;
        }).toList();

        // 标题关键词搜索
        if (q != null && !q.isBlank()) {
            String kw = q.strip().toLowerCase();
            items = items.stream()
                    .filter(it -> str(it, "title").toLowerCase().contains(kw))
                    .toList();
        }

        Map<String, Object> result = new HashMap<>();
        result.put("total", total);
        result.put("page", page);
        result.put("page_size", pageSize);
        result.put("items", items);
        return result;
    }

    /** 手动录入一条 QA 到题库 */
    public Map<String, Object> add(String question, String answer, String domain,
                                    int difficulty, String company, String url, String username) {
        question = question.strip();
        answer = answer.strip();
        if (question.length() < 5) throw BizException.badRequest("题干至少 5 个字符");
        if (answer.length() < 20) throw BizException.badRequest("答案至少 20 个字符");
        if (!AppProperties.DOMAINS.contains(domain)) {
            throw BizException.badRequest("domain 必须是有效枚举值");
        }

        float[] vec = embedding.embedQuery(question + "\n" + answer);
        Map<String, Object> row = new HashMap<>();
        row.put("text", question);
        row.put("parent_text", answer);
        row.put("dense_vector", vec);
        row.put("q_type", "qa_pair");
        row.put("domain", domain);
        row.put("position", "ai_app_dev");
        row.put("company", company == null ? "" : company);
        row.put("difficulty", difficulty);
        row.put("source", "manual:" + username + ":" + java.util.UUID.randomUUID().toString().substring(0, 8));
        row.put("title", question);
        row.put("url", url == null ? "" : url);

        int n = milvus.insert(List.of(row), "qa_pair");
        Map<String, Object> result = new HashMap<>();
        result.put("inserted", n);
        result.put("question", question);
        return result;
    }

    /** 上传文档入库（简化版：整文档单块入库，不切分） */
    public Map<String, Object> upload(byte[] fileBytes, String filename, String domain,
                                       boolean asQa, String username) {
        String text;
        try {
            text = new org.apache.tika.Tika().parseToString(new java.io.ByteArrayInputStream(fileBytes));
            if (text.length() > 8000) text = text.substring(0, 8000);
        } catch (Exception e) {
            throw BizException.badRequest("文件解析失败：" + e.getMessage());
        }
        if (text.strip().length() < 50) {
            throw BizException.badRequest("文档内容太少，无法入库");
        }

        // 幂等清理
        String source = "upload:" + username + ":" + filename;
        milvus.deleteBySource(source);

        List<Map<String, Object>> rows = new ArrayList<>();
        // 简单按段落分块（每块约 500 字符）
        List<String> chunks = splitText(text, 500);
        List<float[]> vectors = embedding.embedDocuments(chunks);
        for (int i = 0; i < chunks.size(); i++) {
            Map<String, Object> row = new HashMap<>();
            row.put("text", chunks.get(i));
            row.put("parent_text", chunks.get(i));
            row.put("dense_vector", vectors.get(i));
            row.put("q_type", asQa ? "qa_pair" : "knowledge");
            row.put("domain", domain == null ? "cs_basic" : domain);
            row.put("position", "ai_app_dev");
            row.put("company", "");
            row.put("difficulty", 2);
            row.put("source", source);
            row.put("title", filename);
            row.put("url", "");
            rows.add(row);
        }

        int n = milvus.insert(rows, asQa ? "qa_pair" : "knowledge");
        Map<String, Object> result = new HashMap<>();
        result.put("inserted_chunks", n);
        result.put("filename", filename);
        result.put("domain", domain);
        return result;
    }

    private List<String> splitText(String text, int chunkSize) {
        List<String> chunks = new ArrayList<>();
        // 按段落优先切分
        String[] paragraphs = text.split("\n\\s*\n");
        StringBuilder current = new StringBuilder();
        for (String p : paragraphs) {
            if (current.length() + p.length() > chunkSize && current.length() > 0) {
                chunks.add(current.toString().strip());
                current = new StringBuilder();
            }
            current.append(p).append("\n\n");
        }
        if (current.length() > 0) chunks.add(current.toString().strip());
        return chunks.isEmpty() ? List.of(text) : chunks;
    }

    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? "" : v.toString();
    }
}
