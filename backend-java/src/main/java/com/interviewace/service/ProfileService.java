package com.interviewace.service;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.config.AppProperties;
import com.interviewace.dto.ProfileStats;
import com.interviewace.dto.ProfileStats.CalendarDay;
import com.interviewace.dto.ProfileStats.DomainScore;
import com.interviewace.entity.ChatRecord;
import com.interviewace.entity.PracticeRecord;
import com.interviewace.mapper.ChatRecordMapper;
import com.interviewace.mapper.PracticeRecordMapper;

/**
 * 能力画像服务：聚合练习记录 → 各域平均分/掌握度、薄弱域、连续学习天数、学习日历。
 * 对应 mysql.py profile_stats()。
 */
@Service
public class ProfileService {

    /** 长期记忆：常问主题的关键词表（对应 mysql.py get_top_topics，粗粒度够用） */
    private static final List<String> TOPIC_KEYWORDS = List.of(
            "RAG", "Transformer", "Agent", "注意力", "微调", "向量", "索引",
            "Redis", "MySQL", "LangChain", "LangGraph", "重排", "分块", "Prompt",
            "GIL", "协程", "缓存", "事务", "并发");

    private final PracticeRecordMapper practiceRecordMapper;
    private final ChatRecordMapper chatRecordMapper;

    public ProfileService(PracticeRecordMapper practiceRecordMapper, ChatRecordMapper chatRecordMapper) {
        this.practiceRecordMapper = practiceRecordMapper;
        this.chatRecordMapper = chatRecordMapper;
    }

    public ProfileStats profileStats(Integer userId) {
        List<PracticeRecord> rows = practiceRecordMapper.selectList(
                new LambdaQueryWrapper<PracticeRecord>()
                        .eq(PracticeRecord::getUserId, userId)
                        .orderByAsc(PracticeRecord::getCreatedAt));

        // 各域分数收集（未分类按 "未分类" 聚合，与 Python 口径一致）
        Map<String, List<Integer>> byDomain = new LinkedHashMap<>();
        Map<String, Integer> dayCount = new LinkedHashMap<>();
        for (PracticeRecord r : rows) {
            if (r.getScore() != null) {
                byDomain.computeIfAbsent(
                        r.getDomain() == null || r.getDomain().isBlank() ? "未分类" : r.getDomain(),
                        k -> new ArrayList<>()).add(r.getScore());
            }
            if (r.getCreatedAt() != null) {
                dayCount.merge(r.getCreatedAt().toLocalDate().toString(), 1, Integer::sum);
            }
        }

        List<DomainScore> domains = byDomain.entrySet().stream()
                .map(e -> {
                    List<Integer> scores = e.getValue();
                    int count = scores.size();
                    int mastered = (int) scores.stream().filter(s -> s >= 85).count();
                    int weak = (int) scores.stream().filter(s -> s < 60).count();
                    double avg = round1(scores.stream().mapToInt(Integer::intValue).sum() / (double) count);
                    return new DomainScore(e.getKey(), avg, count, mastered, weak);
                })
                .sorted((a, b) -> Double.compare(a.avgScore(), b.avgScore()))
                .toList();

        int scored = (int) rows.stream().filter(r -> r.getScore() != null).count();
        double scoreSum = rows.stream()
                .filter(r -> r.getScore() != null)
                .mapToInt(PracticeRecord::getScore).sum();
        double avgScore = round1(scoreSum / Math.max(1, scored));

        List<DomainScore> weakDomains = domains.stream()
                .filter(d -> d.avgScore() < 70)
                .limit(3)
                .toList();

        // 连续学习天数：从今天（本地时区，与 Python date.today() 一致）往回数
        TreeSet<String> daySet = new TreeSet<>(dayCount.keySet());
        int streak = 0;
        LocalDate cursor = LocalDate.now();
        while (daySet.contains(cursor.toString())) {
            streak++;
            cursor = cursor.minusDays(1);
        }

        List<CalendarDay> calendar = dayCount.keySet().stream().sorted()
                .map(day -> new CalendarDay(day, dayCount.get(day)))
                .toList();

        return new ProfileStats(rows.size(), avgScore, domains, weakDomains, streak, calendar);
    }

    private double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }

    /**
     * 长期记忆：把学习画像压成一段短文本注入 prompt（对应 mysql.py build_memory_context，
     * 控制在 ~120 token 内）；无任何记录时返回空串。
     */
    public String buildMemoryContext(Integer userId) {
        ProfileStats stats = profileStats(userId);
        List<String> topics = topTopics(userId, 5);
        if (stats.totalPracticed() == 0 && topics.isEmpty()) {
            return "";
        }
        List<String> parts = new ArrayList<>();
        if (stats.totalPracticed() > 0) {
            double avgOfDomains = stats.domains().stream()
                    .mapToDouble(DomainScore::avgScore).average().orElse(0.0);
            parts.add(String.format("该用户已练习 %d 题，平均 %.1f 分", stats.totalPracticed(), round1(avgOfDomains)));
        }
        List<DomainScore> weak = stats.domains().stream()
                .filter(d -> d.avgScore() < 70).limit(3).toList();
        if (!weak.isEmpty()) {
            parts.add("薄弱知识域：" + weak.stream()
                    .map(d -> AppProperties.domainName(d.domain()) + "(" + d.avgScore() + "分)")
                    .reduce((a, b) -> a + "、" + b).orElse(""));
        }
        List<DomainScore> strong = stats.domains().stream()
                .filter(d -> d.avgScore() >= 85).limit(2).toList();
        if (!strong.isEmpty()) {
            parts.add("较强：" + strong.stream()
                    .map(d -> AppProperties.domainName(d.domain()))
                    .reduce((a, b) -> a + "、" + b).orElse(""));
        }
        if (!topics.isEmpty()) {
            parts.add("近期常问：" + String.join("、", topics));
        }
        return String.join("；", parts);
    }

    /** 跨会话高频关注主题：扫最近 300 条提问，按关键词出现频次取 TOP（对应 mysql.py get_top_topics） */
    private List<String> topTopics(Integer userId, int limit) {
        List<ChatRecord> rows = chatRecordMapper.selectList(new LambdaQueryWrapper<ChatRecord>()
                .eq(ChatRecord::getUserId, userId)
                .orderByDesc(ChatRecord::getCreatedAt)
                .last("LIMIT 300"));
        Map<String, Integer> freq = new LinkedHashMap<>();
        for (ChatRecord r : rows) {
            String q = r.getQuestion() == null ? "" : r.getQuestion().toLowerCase();
            for (String k : TOPIC_KEYWORDS) {
                if (q.contains(k.toLowerCase())) {
                    freq.merge(k, 1, Integer::sum);
                }
            }
        }
        return freq.entrySet().stream()
                .sorted(Map.Entry.<String, Integer>comparingByValue().reversed())
                .limit(limit)
                .map(Map.Entry::getKey)
                .toList();
    }
}
