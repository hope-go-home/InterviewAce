package com.interviewace.service.interview;

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
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.BizException;
import com.interviewace.config.AppProperties;
import com.interviewace.entity.InterviewSession;
import com.interviewace.entity.InterviewTurn;
import com.interviewace.mapper.InterviewSessionMapper;
import com.interviewace.mapper.InterviewTurnMapper;
import com.interviewace.service.llm.LLMClient;
import com.interviewace.service.rag.MilvusService;
import com.interviewace.service.rag.RetrievalService;

/**
 * 模拟面试执行服务：开场选题 → 逐轮评分/追问 → 总评报告。
 * 对应 Python interview_service.py + practice_service.evaluate_answer。
 */
@Service
public class InterviewRunService {

    private static final Logger log = LoggerFactory.getLogger(InterviewRunService.class);
    private static final Random RNG = new Random();

    private final InterviewSessionMapper sessionMapper;
    private final InterviewTurnMapper turnMapper;
    private final MilvusService milvus;
    private final RetrievalService retrieval;
    private final LLMClient llm;
    private final ObjectMapper objectMapper;
    private final AppProperties props;

    public InterviewRunService(InterviewSessionMapper sessionMapper, InterviewTurnMapper turnMapper,
                               MilvusService milvus, RetrievalService retrieval,
                               LLMClient llm, ObjectMapper objectMapper, AppProperties props) {
        this.sessionMapper = sessionMapper;
        this.turnMapper = turnMapper;
        this.milvus = milvus;
        this.retrieval = retrieval;
        this.llm = llm;
        this.objectMapper = objectMapper;
        this.props = props;
    }

    /** 开一场面试：建场次 + 出第一题 */
    public Map<String, Object> start(Integer userId, String position, String level,
                                     List<String> domains, int numQuestions, int difficultyCap) {
        InterviewSession s = new InterviewSession();
        s.setUserId(userId);
        s.setPosition(position);
        s.setLevel(level);
        s.setDomains(toJson(domains));
        s.setNumQuestions(numQuestions);
        s.setDifficultyCap(difficultyCap);
        s.setStatus("in_progress");
        s.setCurrentSeq(1);
        s.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        sessionMapper.insert(s);
        int sid = s.getId();

        Map<String, Object> q = pickQuestion(s, 1, List.of());
        if (q == null) {
            throw BizException.badRequest("题库没有可用题目，请先扩充题库");
        }

        InterviewTurn turn = new InterviewTurn();
        turn.setSessionId(sid);
        turn.setSeq(1);
        turn.setQuestion((String) q.get("title"));
        turn.setQuestionSource((String) q.getOrDefault("question_source", "rag"));
        turn.setQaRefs(toJson(List.of(Map.of(
                "title", q.get("title"),
                "url", q.getOrDefault("url", ""),
                "domain", q.getOrDefault("domain", "")))));
        turn.setFollowupNo(0);
        turn.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        turnMapper.insert(turn);

        Map<String, Object> question = new HashMap<>();
        question.put("turn_id", turn.getId());
        question.put("seq", 1);
        question.put("text", q.get("title"));
        question.put("domain", q.getOrDefault("domain", ""));
        question.put("difficulty", q.getOrDefault("difficulty", 0));
        question.put("is_followup", false);
        question.put("source", q.get("question_source"));

        Map<String, Object> result = new HashMap<>();
        result.put("interview_id", sid);
        result.put("seq", 1);
        result.put("total", numQuestions);
        result.put("question", question);
        return result;
    }

    /** 提交作答 → 评分 → 追问/下一题/结束 */
    public Map<String, Object> submitAnswer(int sessionId, int turnId, String answer, Integer userId) {
        InterviewSession s = sessionMapper.selectById(sessionId);
        if (s == null || !s.getUserId().equals(userId) || !"in_progress".equals(s.getStatus())) {
            throw BizException.badRequest("面试不存在或已结束");
        }
        InterviewTurn turn = turnMapper.selectById(turnId);
        if (turn == null || !turn.getSessionId().equals(sessionId)) {
            throw BizException.badRequest("题目不存在");
        }

        // 评分
        EvalResult eval = evaluateAnswer(turn.getQuestion(), answer, s.getLevel());
        turn.setAnswer(answer);
        turn.setScore(eval.score());
        turn.setFeedback(eval.feedback());
        turn.setMissingPoints(toJson(eval.missingPoints()));
        turn.setDimJson(toJson(eval.dimensions()));
        turnMapper.updateById(turn);

        int seq = turn.getSeq();
        int followupNo = turn.getFollowupNo() == null ? 0 : turn.getFollowupNo();
        String action = decideNext(eval.score(), followupNo, seq, s.getNumQuestions());

        Map<String, Object> feedback = new HashMap<>();
        feedback.put("score", eval.score());
        feedback.put("dimensions", eval.dimensions());
        feedback.put("feedback", eval.feedback());
        feedback.put("missing_points", eval.missingPoints());
        feedback.put("reference_url", eval.referenceUrl());

        Map<String, Object> out = new HashMap<>();
        out.put("feedback", feedback);
        out.put("action", action);
        out.put("seq", seq);
        out.put("total", s.getNumQuestions());

        if ("followup_clarify".equals(action) || "followup_deep".equals(action)) {
            String fq = genFollowup(turn.getQuestion(), answer, eval.missingPoints(), action);
            InterviewTurn ft = new InterviewTurn();
            ft.setSessionId(sessionId);
            ft.setSeq(seq);
            ft.setQuestion(fq);
            ft.setQuestionSource("llm");
            ft.setParentTurnId(turn.getId());
            ft.setFollowupNo(followupNo + 1);
            ft.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
            turnMapper.insert(ft);
            out.put("next", Map.of(
                    "turn_id", ft.getId(), "seq", seq, "text", fq,
                    "is_followup", true, "followup_no", followupNo + 1,
                    "domain", extractFirstDomain(turn.getQaRefs())));
        } else if ("next_question".equals(action)) {
            Map<String, Object> nq = pickQuestion(s, seq + 1, askedQuestions(sessionId));
            if (nq == null) {
                action = "finish";
            } else {
                InterviewTurn nt = new InterviewTurn();
                nt.setSessionId(sessionId);
                nt.setSeq(seq + 1);
                nt.setQuestion((String) nq.get("title"));
                nt.setQuestionSource((String) nq.getOrDefault("question_source", "rag"));
                nt.setQaRefs(toJson(List.of(Map.of(
                        "title", nq.get("title"),
                        "url", nq.getOrDefault("url", ""),
                        "domain", nq.getOrDefault("domain", "")))));
                nt.setFollowupNo(0);
                nt.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
                turnMapper.insert(nt);
                s.setCurrentSeq(seq + 1);
                sessionMapper.updateById(s);
                out.put("next", Map.of(
                        "turn_id", nt.getId(), "seq", seq + 1, "text", nq.get("title"),
                        "domain", nq.getOrDefault("domain", ""), "difficulty", nq.getOrDefault("difficulty", 0),
                        "is_followup", false, "source", nq.getOrDefault("question_source", "rag")));
            }
        }

        if ("finish".equals(action)) {
            Map<String, Object> report = finish(sessionId, userId);
            out.put("action", "finish");
            out.put("report", report);
        }
        return out;
    }

    /** 结束面试 → 生成总评报告 */
    public Map<String, Object> finish(int sessionId, Integer userId) {
        InterviewSession s = sessionMapper.selectById(sessionId);
        if (s == null || !s.getUserId().equals(userId)) {
            throw BizException.badRequest("面试不存在");
        }
        List<InterviewTurn> turns = turnMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<InterviewTurn>()
                        .eq(InterviewTurn::getSessionId, sessionId)
                        .orderByAsc(InterviewTurn::getSeq)
                        .orderByAsc(InterviewTurn::getFollowupNo));

        List<InterviewTurn> mainTurns = turns.stream()
                .filter(t -> (t.getFollowupNo() == null || t.getFollowupNo() == 0) && t.getScore() != null)
                .toList();
        if (mainTurns.isEmpty()) {
            throw BizException.badRequest("还没有作答记录");
        }

        double avg = mainTurns.stream().mapToInt(InterviewTurn::getScore).average().orElse(0);
        double roundedAvg = Math.round(avg * 10) / 10.0;

        // 四维均分
        Map<String, List<Integer>> dims = new HashMap<>();
        for (InterviewTurn t : mainTurns) {
            Map<String, Integer> d = parseDimJson(t.getDimJson());
            d.forEach((k, v) -> dims.computeIfAbsent(k, x -> new ArrayList<>()).add(v));
        }
        Map<String, Double> dimAvg = new HashMap<>();
        dims.forEach((k, v) -> dimAvg.put(k, Math.round(v.stream().mapToInt(i -> i).average().orElse(0) * 10) / 10.0));

        // 按域聚合找薄弱
        Map<String, List<Integer>> byDomain = new HashMap<>();
        for (InterviewTurn t : mainTurns) {
            String domain = extractFirstDomain(t.getQaRefs());
            byDomain.computeIfAbsent(domain.isEmpty() ? "综合" : domain, x -> new ArrayList<>()).add(t.getScore());
        }
        List<Map<String, Object>> domainAvg = byDomain.entrySet().stream()
                .map(e -> Map.<String, Object>of("domain", e.getKey(),
                        "avg", Math.round(e.getValue().stream().mapToInt(i -> i).average().orElse(0) * 10) / 10.0))
                .sorted((a, b) -> Double.compare((Double) a.get("avg"), (Double) b.get("avg")))
                .toList();
        List<Map<String, Object>> weak = domainAvg.size() > 3 ? domainAvg.subList(0, 3) : domainAvg;

        // LLM 总评
        String summary = "";
        try {
            StringBuilder brief = new StringBuilder();
            for (int i = 0; i < Math.min(10, mainTurns.size()); i++) {
                InterviewTurn t = mainTurns.get(i);
                String q = t.getQuestion() != null && t.getQuestion().length() > 40
                        ? t.getQuestion().substring(0, 40) : t.getQuestion();
                brief.append("Q").append(t.getSeq()).append("[").append(t.getScore()).append("分]: ").append(q).append("\n");
            }
            summary = llm.chat(
                    "你是技术面试官。这是一场面试的逐题得分：\n" + brief + "\n\n请写一段 100 字左右的总评（优势 + 待提升 + 建议）。",
                    false, 0.4);
        } catch (Exception e) {
            log.warn("interview summary failed: {}", e.getMessage());
        }

        List<Map<String, Object>> perQuestion = mainTurns.stream()
                .map(t -> Map.<String, Object>of(
                        "seq", t.getSeq(), "question", t.getQuestion(), "score", t.getScore(),
                        "feedback", t.getFeedback() == null ? "" : t.getFeedback(),
                        "qa_refs", parseJsonList(t.getQaRefs())))
                .toList();

        Map<String, Object> report = new HashMap<>();
        report.put("total_score", roundedAvg);
        report.put("dimensions", dimAvg);
        report.put("weak_domains", weak);
        report.put("summary", summary);
        report.put("per_question", perQuestion);

        s.setStatus("finished");
        s.setTotalScore((int) roundedAvg);
        s.setReportJson(toJson(report));
        s.setFinishedAt(LocalDateTime.now(ZoneOffset.UTC));
        sessionMapper.updateById(s);
        return report;
    }

    /** 面试快照（刷新恢复现场） */
    public Map<String, Object> getSnapshot(int sessionId, Integer userId) {
        InterviewSession s = sessionMapper.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<InterviewSession>()
                        .eq(InterviewSession::getId, sessionId)
                        .eq(InterviewSession::getUserId, userId)
                        .last("LIMIT 1"));
        if (s == null) {
            throw BizException.notFound("面试不存在");
        }
        List<InterviewTurn> turns = turnMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<InterviewTurn>()
                        .eq(InterviewTurn::getSessionId, sessionId)
                        .orderByAsc(InterviewTurn::getSeq)
                        .orderByAsc(InterviewTurn::getFollowupNo));

        List<Map<String, Object>> turnList = turns.stream().map(t -> {
            Map<String, Object> m = new HashMap<>();
            m.put("id", t.getId());
            m.put("seq", t.getSeq());
            m.put("parent_turn_id", t.getParentTurnId());
            m.put("followup_no", t.getFollowupNo());
            m.put("question", t.getQuestion());
            m.put("question_source", t.getQuestionSource());
            m.put("answer", t.getAnswer());
            m.put("score", t.getScore());
            m.put("feedback", t.getFeedback());
            m.put("domain", extractFirstDomain(t.getQaRefs()));
            return m;
        }).toList();

        Map<String, Object> sessionMap = new HashMap<>();
        sessionMap.put("id", s.getId());
        sessionMap.put("position", s.getPosition());
        sessionMap.put("level", s.getLevel());
        sessionMap.put("num_questions", s.getNumQuestions());
        sessionMap.put("difficulty_cap", s.getDifficultyCap());
        sessionMap.put("status", s.getStatus());
        sessionMap.put("current_seq", s.getCurrentSeq());
        sessionMap.put("total_score", s.getTotalScore());
        sessionMap.put("report", s.getReportJson() == null ? null : parseJsonObject(s.getReportJson()));

        Map<String, Object> result = new HashMap<>();
        result.put("session", sessionMap);
        result.put("turns", turnList);
        return result;
    }

    // ---- 内部方法 ----

    private Map<String, Object> pickQuestion(InterviewSession s, int seq, List<String> asked) {
        List<String> domains = parseJsonList(s.getDomains()).stream()
                .map(o -> o.toString()).toList();
        String domain = pickDomain(domains, seq);
        int difficulty = targetDifficulty(seq, s.getNumQuestions(), s.getLevel(), s.getDifficultyCap());

        Map<String, Object> q = randomQuestion(domain, difficulty, s.getPosition(), asked);
        if (q == null) {
            q = randomQuestion(null, difficulty, s.getPosition(), asked);
        }
        return q;
    }

    private Map<String, Object> randomQuestion(String domain, int difficulty, String position, List<String> exclude) {
        if (!milvus.isReady()) return null;
        String expr = MilvusService.buildFilterExpr(domain, "qa_pair", difficulty, null, position);
        if (expr.isBlank()) expr = "q_type == \"qa_pair\"";
        else expr = "q_type == \"qa_pair\" and " + expr;

        long total = milvus.count(expr);
        if (total == 0) return null;

        java.util.Set<String> excludeSet = new java.util.HashSet<>(exclude);
        for (int attempt = 0; attempt < 40; attempt++) {
            int offset = RNG.nextInt((int) total);
            List<Map<String, Object>> rows = milvus.query(expr,
                    List.of("title", "domain", "difficulty", "company", "url"), 1, offset);
            if (rows.isEmpty()) continue;
            Map<String, Object> r = rows.get(0);
            String title = str(r, "title");
            if (title.isBlank() || excludeSet.contains(title)) continue;
            Map<String, Object> q = new HashMap<>();
            q.put("title", title);
            q.put("domain", str(r, "domain"));
            q.put("difficulty", r.get("difficulty") instanceof Number n ? n.intValue() : 0);
            q.put("company", str(r, "company"));
            q.put("url", str(r, "url"));
            q.put("question_source", "rag");
            return q;
        }
        return null;
    }

    private EvalResult evaluateAnswer(String question, String answer, String level) {
        // RAG 找参考答案
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
        if (reference.isBlank()) {
            reference = "（题库未收录该题参考答案，请基于你的专业判断评分）";
        }

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
        Object dimsObj = data.get("dimensions");
        if (dimsObj instanceof Map<?, ?> dm) {
            dm.forEach((k, v) -> dimensions.put(k.toString(), toInt(v)));
        }
        List<String> missing = new ArrayList<>();
        Object mpObj = data.get("missing_points");
        if (mpObj instanceof List<?> ml) {
            ml.forEach(o -> missing.add(o.toString()));
        }

        return new EvalResult(score, dimensions,
                data.getOrDefault("feedback", "").toString(), missing,
                reference, refUrl);
    }

    private String genFollowup(String question, String answer, List<String> missing, String kind) {
        String style = "followup_clarify".equals(kind)
                ? "针对考生答错/遗漏的点，用一个更基础的澄清式追问，引导他补上。"
                : "针对考生的正确回答，追问一层原理/权衡/实战踩坑，考察深度。";
        String prompt = String.format("""
                你是技术面试官。题目：%s
                考生作答：%s
                遗漏点：%s

                %s 只输出追问的题干一句话，不要多余内容。
                """, question, answer.length() > 500 ? answer.substring(0, 500) : answer,
                toJson(missing), style);
        try {
            String q = llm.chat(prompt, false, 0.5);
            return q.isBlank() ? "能再展开讲讲刚才的回答吗？" : q.strip();
        } catch (Exception e) {
            return "能再展开讲讲刚才的回答吗？";
        }
    }

    private String decideNext(Integer score, int followupNo, int seq, int numQuestions) {
        if (score != null) {
            if (score < 60 && followupNo < 2) return "followup_clarify";
            if (score >= 60 && score < 85 && followupNo < 1 && RNG.nextDouble() < 0.5) return "followup_deep";
        }
        if (seq < numQuestions) return "next_question";
        return "finish";
    }

    private String pickDomain(List<String> domains, int seq) {
        if (domains.isEmpty()) return null;
        return domains.get((seq - 1) % domains.size());
    }

    private int targetDifficulty(int seq, int total, String level, int cap) {
        int third = Math.max(1, total / 3);
        int base = seq <= third ? 1 : seq <= third * 2 ? 2 : 3;
        if ("social".equals(level)) base = Math.min(cap, base + RNG.nextInt(2));
        else if ("intern".equals(level)) base = Math.max(1, base - RNG.nextInt(2));
        return Math.min(cap, base);
    }

    private List<String> askedQuestions(int sessionId) {
        return turnMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<InterviewTurn>()
                        .eq(InterviewTurn::getSessionId, sessionId)).stream()
                .map(InterviewTurn::getQuestion).toList();
    }

    private record EvalResult(Integer score, Map<String, Integer> dimensions, String feedback,
                              List<String> missingPoints, String reference, String referenceUrl) {}

    // ---- JSON 工具 ----

    private String toJson(Object o) {
        try { return objectMapper.writeValueAsString(o); } catch (Exception e) { return "[]"; }
    }

    private List<Object> parseJsonList(String json) {
        try { return objectMapper.readValue(json, new TypeReference<List<Object>>() {}); }
        catch (Exception e) { return List.of(); }
    }

    private Map<String, Object> parseJsonObject(String json) {
        try { return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {}); }
        catch (Exception e) { return Map.of(); }
    }

    private Map<String, Integer> parseDimJson(String json) {
        try { return objectMapper.readValue(json, new TypeReference<Map<String, Integer>>() {}); }
        catch (Exception e) { return Map.of(); }
    }

    private String extractFirstDomain(String qaRefsJson) {
        try {
            List<Object> refs = objectMapper.readValue(qaRefsJson, new TypeReference<List<Object>>() {});
            if (!refs.isEmpty() && refs.get(0) instanceof Map<?, ?> m) {
                Object d = m.get("domain");
                return d == null ? "" : d.toString();
            }
        } catch (Exception ignore) {}
        return "";
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
