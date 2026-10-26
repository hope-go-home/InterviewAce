package com.interviewace.dto;

import java.util.List;

/** 能力画像：对应 mysql.py profile_stats 的 dict 结构。 */
public record ProfileStats(
        int totalPracticed,
        double avgScore,
        List<DomainScore> domains,
        List<DomainScore> weakDomains,
        int streakDays,
        List<CalendarDay> calendar) {

    /** 各域统计：{domain, avg_score, count, mastered, weak} */
    public record DomainScore(String domain, double avgScore, int count, int mastered, int weak) {
    }

    /** 学习日历：{day, count} */
    public record CalendarDay(String day, int count) {
    }
}
