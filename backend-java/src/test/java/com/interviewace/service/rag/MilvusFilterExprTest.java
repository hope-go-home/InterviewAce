package com.interviewace.service.rag;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MilvusFilterExprTest {

    @Test
    void buildFilterExpr_combinesNonNullClausesWithAnd() {
        String expr = MilvusService.buildFilterExpr("rag", "qa_pair", 2, null, "ai_app_dev");

        assertEquals("domain == \"rag\" and q_type == \"qa_pair\" and difficulty == 2 and position == \"ai_app_dev\"",
                expr);
    }

    @Test
    void buildFilterExpr_allNull_emptyString() {
        assertEquals("", MilvusService.buildFilterExpr(null, null, null, null, null));
        assertEquals("", MilvusService.buildFilterExpr("", " ", null, "", null));
    }

    @Test
    void buildFilterExpr_escapesQuotesAndBackslashes() {
        // 防止标量过滤表达式被引号/反斜杠破坏（Milvus 表达式注入）
        String expr = MilvusService.buildFilterExpr("ra\"g", null, null, "a\\b", null);

        assertEquals("domain == \"ra\\\"g\" and company == \"a\\\\b\"", expr);
    }
}
