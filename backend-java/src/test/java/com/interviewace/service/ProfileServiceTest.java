package com.interviewace.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.interviewace.dto.ProfileStats;
import com.interviewace.entity.ChatRecord;
import com.interviewace.entity.PracticeRecord;
import com.interviewace.mapper.ChatRecordMapper;
import com.interviewace.mapper.PracticeRecordMapper;

class ProfileServiceTest {

    private PracticeRecordMapper practiceRecordMapper;
    private ChatRecordMapper chatRecordMapper;
    private ProfileService service;

    @BeforeEach
    void setUp() {
        practiceRecordMapper = mock(PracticeRecordMapper.class);
        chatRecordMapper = mock(ChatRecordMapper.class);
        service = new ProfileService(practiceRecordMapper, chatRecordMapper);
    }

    private PracticeRecord record(String domain, Integer score, LocalDateTime at) {
        PracticeRecord r = new PracticeRecord();
        r.setUserId(1);
        r.setDomain(domain);
        r.setScore(score);
        r.setCreatedAt(at);
        return r;
    }

    @Test
    void profileStats_empty_zeroes() {
        when(practiceRecordMapper.selectList(any())).thenReturn(List.of());

        ProfileStats stats = service.profileStats(1);

        assertEquals(0, stats.totalPracticed());
        assertEquals(0.0, stats.avgScore());
        assertTrue(stats.domains().isEmpty());
        assertEquals(0, stats.streakDays());
    }

    @Test
    void profileStats_aggregatesDomainAvgAndWeak() {
        when(practiceRecordMapper.selectList(any())).thenReturn(List.of(
                record("rag", 40, LocalDateTime.now()),
                record("rag", 60, LocalDateTime.now()),
                record("cs_basic", 90, LocalDateTime.now()),
                record("cs_basic", 95, LocalDateTime.now())));

        ProfileStats stats = service.profileStats(1);

        assertEquals(4, stats.totalPracticed());
        assertEquals(71.3, stats.avgScore());   // (40+60+90+95)/4
        assertEquals(2, stats.domains().size());
        // 按均分升序：rag(50) 在前，cs_basic(92.5) 在后
        assertEquals("rag", stats.domains().get(0).domain());
        assertEquals(50.0, stats.domains().get(0).avgScore());
        // 薄弱域 = 均分 < 70
        assertEquals(1, stats.weakDomains().size());
        assertEquals("rag", stats.weakDomains().get(0).domain());
    }

    @Test
    void profileStats_streak_countsConsecutiveDaysFromToday() {
        LocalDateTime now = LocalDateTime.now();
        when(practiceRecordMapper.selectList(any())).thenReturn(List.of(
                record("rag", 80, now),
                record("rag", 70, now.minusDays(1)),
                record("rag", 60, now.minusDays(3))));   // 前天断了

        ProfileStats stats = service.profileStats(1);

        assertEquals(2, stats.streakDays());
        assertEquals(3, stats.calendar().size());
    }

    @Test
    void buildMemoryContext_empty_whenNoRecords() {
        when(practiceRecordMapper.selectList(any())).thenReturn(List.of());
        when(chatRecordMapper.selectList(any())).thenReturn(List.of());

        assertEquals("", service.buildMemoryContext(1));
    }

    @Test
    void buildMemoryContext_containsWeakDomainAndTopics() {
        when(practiceRecordMapper.selectList(any())).thenReturn(List.of(
                record("rag", 50, LocalDateTime.now()),
                record("rag", 60, LocalDateTime.now())));
        ChatRecord chat = new ChatRecord();
        chat.setUserId(1);
        chat.setQuestion("RAG 里向量索引怎么选？");
        chat.setCreatedAt(LocalDateTime.now());
        when(chatRecordMapper.selectList(any())).thenReturn(List.of(chat));

        String memory = service.buildMemoryContext(1);

        assertTrue(memory.contains("薄弱知识域"), memory);
        assertTrue(memory.contains("RAG"), memory);          // 域名中文映射 + 常问主题关键词
        assertTrue(memory.contains("已练习 2 题"), memory);
        assertFalse(memory.contains("较强"), memory);
    }
}
