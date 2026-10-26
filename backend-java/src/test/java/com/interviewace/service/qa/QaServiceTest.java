package com.interviewace.service.qa;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.entity.ChatRecord;
import com.interviewace.entity.PendingQuestion;
import com.interviewace.mapper.ChatRecordMapper;
import com.interviewace.mapper.PendingQuestionMapper;
import com.interviewace.service.ProfileService;
import com.interviewace.service.llm.LLMClient;
import com.interviewace.service.rag.RetrievalService;
import com.interviewace.service.rag.RetrievalService.RetrievalResult;
import com.interviewace.service.rag.RetrievalService.RetrievalSource;

class QaServiceTest {

    private LLMClient llm;
    private RetrievalService retrieval;
    private ChatRecordMapper chatRecordMapper;
    private PendingQuestionMapper pendingQuestionMapper;
    private ProfileService profileService;
    private QaService service;

    /** 记录 SSE 回调的测试桩 */
    private static final class RecordingCallbacks implements QaService.QaCallbacks {
        final List<Map<String, Object>> thinking = new ArrayList<>();
        final List<List<Map<String, Object>>> sources = new ArrayList<>();
        final StringBuilder tokens = new StringBuilder();
        Map<String, Object> answer;

        @Override public void onThinking(Map<String, Object> step) { thinking.add(step); }
        @Override public void onSources(List<Map<String, Object>> s) { sources.add(s); }
        @Override public void onStats(Map<String, Object> stats) {}
        @Override public void onToken(String content) { tokens.append(content); }
        @Override public void onAnswer(Map<String, Object> data) { answer = data; }
    }

    @BeforeEach
    void setUp() {
        llm = mock(LLMClient.class);
        retrieval = mock(RetrievalService.class);
        chatRecordMapper = mock(ChatRecordMapper.class);
        pendingQuestionMapper = mock(PendingQuestionMapper.class);
        profileService = mock(ProfileService.class);
        service = new QaService(llm, retrieval, new ObjectMapper(),
                chatRecordMapper, pendingQuestionMapper, profileService);
        when(profileService.buildMemoryContext(any())).thenReturn("");
    }

    private RetrievalSource source(double rerankScore, String title) {
        return new RetrievalSource("父块内容", "子块", 1, (float) rerankScore, (float) rerankScore,
                "qa_pair", "rag", 2, "", "test", title, "");
    }

    @Test
    void loadHistory_mapsRecordsToUserAssistantPairs() {
        ChatRecord r1 = new ChatRecord();
        r1.setSessionId("s1"); r1.setUserId(1);
        r1.setQuestion("什么是RAG"); r1.setAnswer("检索增强生成");
        r1.setCreatedAt(LocalDateTime.now().minusMinutes(5));
        ChatRecord r2 = new ChatRecord();
        r2.setSessionId("s1"); r2.setUserId(1);
        r2.setQuestion("重排呢"); r2.setAnswer("对召回结果再排序");
        r2.setCreatedAt(LocalDateTime.now());
        when(chatRecordMapper.selectList(any())).thenReturn(List.of(r1, r2));

        List<Map<String, String>> history = service.loadHistory("s1", 1);

        assertEquals(4, history.size());
        assertEquals("user", history.get(0).get("role"));
        assertEquals("什么是RAG", history.get(0).get("content"));
        assertEquals("assistant", history.get(1).get("role"));
        assertEquals("user", history.get(2).get("role"));
        assertEquals("assistant", history.get(3).get("role"));
    }

    @Test
    void answer_chitChat_skipsRetrievalAndAnswersDirectly() {
        when(llm.chat(anyString(), eq(true), anyDouble()))
                .thenReturn("{\"intent\":\"chit_chat\",\"domain\":\"\",\"search_query\":\"\"}");
        when(llm.chatStream(anyString(), any())).thenReturn("你好！我是 InterviewAce 面试备考助手。");
        RecordingCallbacks cb = new RecordingCallbacks();

        String answer = service.answer(1, "你好", "", List.of(), "ai_app_dev", "campus", cb);

        assertEquals("你好！我是 InterviewAce 面试备考助手。", answer);
        verify(retrieval, never()).retrieve(anyString(), org.mockito.ArgumentMatchers.anyInt(), any(), anyString());
        assertTrue(cb.sources.isEmpty(), "闲聊不应有 sources 事件");
        assertEquals(false, cb.answer.get("is_fallback"));
    }

    @Test
    void answer_inBank_retrievesAndGenerates_withoutFallback() {
        when(llm.chat(anyString(), eq(true), anyDouble()))
                .thenReturn("{\"intent\":\"tech_question\",\"domain\":\"rag\",\"search_query\":\"RAG 重排\"}");
        when(retrieval.retrieve(anyString(), eq(8), any(), anyString()))
                .thenReturn(new RetrievalResult(List.of("父块内容"), List.of(source(0.9, "RAG 重排")), 24, 0, 8, false));
        when(llm.chatStream(anyString(), any())).thenReturn("重排是对召回结果的二次排序[1]。");
        RecordingCallbacks cb = new RecordingCallbacks();

        String answer = service.answer(1, "RAG 中重排的作用", "", List.of(), "ai_app_dev", "campus", cb);

        assertEquals("重排是对召回结果的二次排序[1]。", answer);
        assertEquals(false, cb.answer.get("is_fallback"));
        assertEquals(1, cb.sources.size());
        verify(pendingQuestionMapper, never()).insert(any(PendingQuestion.class));
    }

    @Test
    void answer_outOfBank_retriesThenFallsBackAndRecordsPending() {
        when(llm.chat(anyString(), eq(true), anyDouble()))
                .thenReturn("{\"intent\":\"tech_question\",\"domain\":\"\",\"search_query\":\"舒芙蕾\"}");
        // 改写查询（jsonMode=false）返回新检索词
        when(llm.chat(anyString(), eq(false), anyDouble())).thenReturn("舒芙蕾 塌陷 原因");
        // 三轮检索都不达标（最高分 0.3 < 0.5）
        when(retrieval.retrieve(anyString(), eq(8), any(), anyString()))
                .thenReturn(new RetrievalResult(List.of("弱相关"), List.of(source(0.3, "不相关")), 24, 0, 8, false));
        when(llm.chatWithSearch(anyString()))
                .thenReturn(new LLMClient.SearchAnswer("联网答案正文", List.of("https://example.com/a"), true));
        when(pendingQuestionMapper.selectOne(any())).thenReturn(null);
        RecordingCallbacks cb = new RecordingCallbacks();

        String answer = service.answer(1, "法式舒芙蕾怎么烤", "", List.of(), "ai_app_dev", "campus", cb);

        assertEquals("联网答案正文", answer);
        assertEquals(true, cb.answer.get("is_fallback"));
        // 检索重试满 3 轮
        verify(retrieval, org.mockito.Mockito.times(3)).retrieve(anyString(), eq(8), any(), anyString());
        // 待补题池写入：新问题 askCount=1、status=pending、带草稿答案与来源
        ArgumentCaptor<PendingQuestion> captor = ArgumentCaptor.forClass(PendingQuestion.class);
        verify(pendingQuestionMapper).insert(captor.capture());
        PendingQuestion inserted = captor.getValue();
        assertEquals("法式舒芙蕾怎么烤", inserted.getQuestion());
        assertEquals(1, inserted.getAskCount());
        assertEquals("pending", inserted.getStatus());
        assertEquals("联网答案正文", inserted.getDraftAnswer());
        assertEquals("https://example.com/a", inserted.getSourceUrl());
    }

    @Test
    void answer_fallback_existingPending_incrementsAskCount() {
        when(llm.chat(anyString(), eq(true), anyDouble()))
                .thenReturn("{\"intent\":\"tech_question\",\"domain\":\"\",\"search_query\":\"x\"}");
        when(llm.chat(anyString(), eq(false), anyDouble())).thenReturn("x 改写");
        when(retrieval.retrieve(anyString(), eq(8), any(), anyString()))
                .thenReturn(new RetrievalResult(List.of("弱相关"), List.of(source(0.2, "不相关")), 24, 0, 8, false));
        when(llm.chatWithSearch(anyString()))
                .thenReturn(new LLMClient.SearchAnswer("答案", List.of(), false));
        PendingQuestion existing = new PendingQuestion();
        existing.setId(9);
        existing.setQuestion("题库外问题");
        existing.setAskCount(2);
        existing.setStatus("pending");
        when(pendingQuestionMapper.selectOne(any())).thenReturn(existing);
        RecordingCallbacks cb = new RecordingCallbacks();

        service.answer(1, "题库外问题", "", List.of(), "ai_app_dev", "campus", cb);

        ArgumentCaptor<PendingQuestion> captor = ArgumentCaptor.forClass(PendingQuestion.class);
        verify(pendingQuestionMapper).updateById(captor.capture());
        assertEquals(3, captor.getValue().getAskCount());
        verify(pendingQuestionMapper, never()).insert(any(PendingQuestion.class));
    }
}
