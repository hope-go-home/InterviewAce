package com.interviewace.service.practice;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.BizException;
import com.interviewace.entity.Favorite;
import com.interviewace.entity.PracticeRecord;
import com.interviewace.mapper.FavoriteMapper;
import com.interviewace.mapper.PracticeRecordMapper;
import com.interviewace.service.interview.InterviewRunService;
import com.interviewace.service.llm.LLMClient;
import com.interviewace.service.rag.MilvusService;
import com.interviewace.service.rag.RetrievalService;

/**
 * 答题练习服务：抽题 + AI 评分 + 练习记录。
 * 对应 Python practice_service.py。
 */
@Service
public class PracticeAnswerService {

    private static final Logger log = LoggerFactory.getLogger(PracticeAnswerService.class);
    private static final Random RNG = new Random();

    private final MilvusService milvus;
    private final RetrievalService retrieval;
    private final LLMClient llm;
    private final ObjectMapper objectMapper;
    private final PracticeRecordMapper practiceMapper;
    private final FavoriteMapper favoriteMapper;

    public PracticeAnswerService(MilvusService milvus, RetrievalService retrieval,
                                 LLMClient llm, ObjectMapper objectMapper,
                                 PracticeRecordMapper practiceMapper, FavoriteMapper favoriteMapper) {
        this.milvus = milvus;
        this.retrieval = retrieval;
        this.llm = llm;
        this.objectMapper = objectMapper;
        this.practiceMapper = practiceMapper;
        this.favoriteMapper = favoriteMapper;
    }

    /** 抽一道练习题 */
    public Map<String, Object> nextQuestion(String domain, Integer difficulty, String position,
                                            String level, List<String> exclude) {
        int diff = difficulty != null ? difficulty : pickDifficulty(level);
        Map<String, Object> q = randomQuestions(domain, diff, position, exclude, 1).stream()
                .findFirst().orElse(null);
        if (q == null) {
            throw BizException.notFound("没有符合条件的题目了，换个知识域试试");
        }
        return q;
    }

    /** 一次抽 n 道题 */
    public List<Map<String, Object>> batchQuestions(int n, String domain, Integer difficulty,
                                                    String position, String level, List<String> exclude) {
        int diff = difficulty != null ? difficulty : pickDifficulty(level);
        return randomQuestions(domain, diff, position, exclude, Math.min(20, Math.max(1, n)));
    }

    /** 提交作答 → 评分 → 写练习记录 → 错题入错题本 */
    public Map<String, Object> answer(String questionTitle, String questionUrl, String domain,
                                      Integer difficulty, String position, String level,
                                      String myAnswer, Integer userId) {
        EvalResult eval = evaluateAnswer(questionTitle, myAnswer, level);
        boolean isWrong = eval.score() != null && eval.score() < 60;

        PracticeRecord record = new PracticeRecord();
        record.setUserId(userId);
        record.setQuestionTitle(questionTitle);
        record.setQuestionUrl(questionUrl);
        record.setMyAnswer(myAnswer);
        record.setScore(eval.score() == null ? 0 : eval.score());
        record.setFeedback(eval.feedback());
        record.setMissingPoints(toJson(eval.missingPoints()));
        record.setDimJson(toJson(eval.dimensions()));
        record.setDomain(domain);
        record.setDifficulty(difficulty);
        record.setPosition(position);
        record.setLevel(level);
        record.setIsWrong(isWrong);
        record.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        practiceMapper.insert(record);

        if (isWrong) {
            Favorite exist = favoriteMapper.selectOne(
                    new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Favorite>()
                            .eq(Favorite::getUserId, userId)
                            .eq(Favorite::getQuestionTitle, questionTitle)
                            .eq(Favorite::getFtype, "wrong")
                            .last("LIMIT 1"));
            if (exist == null) {
                Favorite fav = new Favorite();
                fav.setUserId(userId);
                fav.setQuestionTitle(questionTitle);
                fav.setQuestionUrl(questionUrl);
                fav.setDomain(domain);
                fav.setDifficulty(difficulty);
                fav.setFtype("wrong");
                fav.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
                favoriteMapper.insert(fav);
            }
        }

        Map<String, Object> out = new HashMap<>();
        out.put("score", eval.score());
        out.put("dimensions", eval.dimensions());
        out.put("feedback", eval.feedback());
        out.put("missing_points", eval.missingPoints());
        out.put("reference_url", eval.referenceUrl());
        out.put("record_id", record.getId());
        out.put("is_wrong", isWrong);
        return out;
    }

    /** 评分：RAG 找参考答案 + LLM rubric 评分 */
    public EvalResult evaluateAnswer(String question, String answer, String level) {
        String reference = "";
        String refUrl = "";
        try {
            RetrievalService.RetrievalResult rr = retrieval.retrieve(question, 3, null, null);
            if (!rr.sources().isEmpty()) {
                reference = rr.sources().get(0).parentText();
                refUrl = rr.sources().get(0).url();
            }
        } catch (Exception e) {
            log.warn("evaluate retrieve failed: {}", e.getMessage());
        }
        if (reference.isBlank()) reference = "（题库未收录该题参考答案，请基于你的专业判断评分）";

        String levelNote = switch (level == null ? "campus" : level) {
            case "intern" -> "这是实习级问题，作答抓住核心概念即可，不必苛求深度。";
            case "social" -> "这是社招级问题，要求原理 + 权衡 + 实战深度，评分从严。";
            default -> "这是校招级问题，要求概念准确 + 一定的原理理解。";
        };

        String prompt = String.format("""
                你是一位严格且专业的技术面试官。请根据【参考答案】评估【考生的作答】。

                【题目】%s
                【参考答案】%s
                【考生作答】%s

                请输出 JSON（不要 markdown 包裹）：
                {"score": 0-100 的整数总分, "dimensions": {"准确性": 0-100, "深度": 0-100, "表达": 0-100}, "feedback": "一两句总体点评", "missing_points": ["遗漏点1", "关键点2"]}

                评分标准：准确性/深度/表达。作答明显偏离题意或几乎为空时 score ≤40。%s
                """, question, reference.length() > 2500 ? reference.substring(0, 2500) : reference,
                answer.length() > 2500 ? answer.substring(0, 2500) : answer, levelNote);

        Map<String, Object> data;
        try {
            String raw = llm.chat(prompt, true, 0);
            data = objectMapper.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.warn("evaluate llm failed: {}", e.getMessage());
            data = Map.of();
        }

        Integer score = toInt(data.get("score"));
        Map<String, Integer> dimensions = new HashMap<>();
        if (data.get("dimensions") instanceof Map<?, ?> dm) {
            dm.forEach((k, v) -> dimensions.put(k.toString(), toInt(v)));
        }
        List<String> missing = new ArrayList<>();
        if (data.get("missing_points") instanceof List<?> ml) {
            ml.forEach(o -> missing.add(o.toString()));
        }
        return new EvalResult(score, dimensions,
                data.getOrDefault("feedback", "").toString(), missing, refUrl);
    }

    private List<Map<String, Object>> randomQuestions(String domain, int difficulty,
                                                       String position, List<String> exclude, int n) {
        if (!milvus.isReady()) return List.of();
        String expr = MilvusService.buildFilterExpr(domain, "qa_pair", difficulty, null, position);
        expr = expr.isBlank() ? "q_type == \"qa_pair\"" : "q_type == \"qa_pair\" and " + expr;

        long total = milvus.count(expr);
        if (total == 0) return List.of();

        java.util.Set<String> excludeSet = new java.util.HashSet<>(exclude == null ? List.of() : exclude);
        List<Map<String, Object>> picked = new ArrayList<>();
        java.util.Set<String> seen = new java.util.HashSet<>();
        int maxOffset = (int) Math.max(0, total - 1);

        for (int i = 0; i < Math.min(total, 40) && picked.size() < n; i++) {
            int offset = RNG.nextInt(maxOffset + 1);
            List<Map<String, Object>> rows = milvus.query(expr,
                    List.of("title", "domain", "difficulty", "company", "url"), 1, offset);
            if (rows.isEmpty()) continue;
            Map<String, Object> r = rows.get(0);
            String title = str(r, "title");
            if (title.isBlank() || seen.contains(title) || excludeSet.contains(title)) continue;
            seen.add(title);
            Map<String, Object> q = new HashMap<>();
            q.put("title", title);
            q.put("domain", str(r, "domain"));
            q.put("difficulty", r.get("difficulty") instanceof Number num ? num.intValue() : 0);
            q.put("company", str(r, "company"));
            q.put("url", str(r, "url"));
            picked.add(q);
        }
        return picked;
    }

    private int pickDifficulty(String level) {
        return switch (level == null ? "campus" : level) {
            case "intern" -> RNG.nextBoolean() ? 1 : 2;
            case "social" -> RNG.nextBoolean() ? 3 : 2;
            default -> 1 + RNG.nextInt(3);
        };
    }

    public record EvalResult(Integer score, Map<String, Integer> dimensions, String feedback,
                             List<String> missingPoints, String referenceUrl) {}

    private String toJson(Object o) {
        try { return objectMapper.writeValueAsString(o); } catch (Exception e) { return "[]"; }
    }

    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? "" : v.toString();
    }

    private static Integer toInt(Object v) {
        if (v instanceof Number n) return n.intValue();
        try { return Integer.parseInt(v.toString()); } catch (Exception e) { return null; }
    }
}
