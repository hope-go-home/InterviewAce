package com.interviewace.service.rag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyFloat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.interviewace.service.llm.EmbeddingService;
import com.interviewace.service.llm.RerankService;
import com.interviewace.service.rag.MilvusService.SearchHit;
import com.interviewace.service.rag.RetrievalService.RetrievalResult;

class RetrievalServiceTest {

    private MilvusService milvus;
    private EmbeddingService embedding;
    private RerankService rerank;
    private RetrievalService service;

    @BeforeEach
    void setUp() {
        milvus = mock(MilvusService.class);
        embedding = mock(EmbeddingService.class);
        rerank = mock(RerankService.class);
        service = new RetrievalService(milvus, embedding, rerank);

        when(milvus.isReady()).thenReturn(true);
        when(embedding.embedQuery(anyString())).thenReturn(new float[]{0.1f, 0.2f});
        // 稠密序：hitA(0.9) > hitB(0.8) > hitC(0.7)
        when(milvus.searchDense(any(), anyInt(), any(), isNull())).thenReturn(List.of(
                new SearchHit(0.9f, "子块A", "父块A", "qa_pair", "rag", 2, "", "s", "题目A", ""),
                new SearchHit(0.8f, "子块B", "父块B", "qa_pair", "rag", 2, "", "s", "题目B", ""),
                new SearchHit(0.7f, "子块C", "父块C", "qa_pair", "rag", 2, "", "s", "题目C", "")));
    }

    @Test
    void retrieve_rerankReordersCandidates() {
        // 重排翻盘：C 最相关（0.95），A 变得不相关（0.05）
        when(rerank.rerank(anyString(), anyList())).thenReturn(new double[]{0.05, 0.10, 0.95});

        RetrievalResult result = service.retrieve("查询", 2, null, "ai_app_dev");

        assertEquals(2, result.sources().size());
        assertEquals("父块C", result.sources().get(0).parentText(), "重排应把 C 提到第一");
        assertEquals(0.95, result.sources().get(0).rerankScore(), 1e-6);
        assertEquals("父块B", result.sources().get(1).parentText());
    }

    @Test
    void retrieve_rerankUnavailable_fallsBackToDenseOrder() {
        when(rerank.rerank(anyString(), anyList())).thenReturn(null);   // 降级路径

        RetrievalResult result = service.retrieve("查询", 2, null, "ai_app_dev");

        assertEquals(2, result.sources().size());
        assertEquals("父块A", result.sources().get(0).parentText(), "降级时保持稠密序");
        assertEquals("父块B", result.sources().get(1).parentText());
    }

    @Test
    void retrieve_milvusDown_returnsEmpty() {
        when(milvus.isReady()).thenReturn(false);

        RetrievalResult result = service.retrieve("查询", 8, null, "ai_app_dev");

        assertTrue(result.sources().isEmpty());
        assertTrue(result.documents().isEmpty());
    }
}
