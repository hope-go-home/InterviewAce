package com.interviewace.service;

import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.BizException;
import com.interviewace.dto.InterviewListItem;
import com.interviewace.dto.InterviewReportResponse;
import com.interviewace.dto.InterviewReportResponse.SessionDetail;
import com.interviewace.dto.InterviewReportResponse.TurnItem;
import com.interviewace.entity.InterviewSession;
import com.interviewace.entity.InterviewTurn;
import com.interviewace.mapper.InterviewSessionMapper;
import com.interviewace.mapper.InterviewTurnMapper;

/**
 * 模拟面试服务（查询侧）：历史列表 / 面试报告。
 * 对应 mysql.py list_interviews / get_interview_session / list_turns；
 * 开场选题与逐轮评分在 InterviewRunService（M3）。
 */
@Service
public class InterviewService {

    private final InterviewSessionMapper sessionMapper;
    private final InterviewTurnMapper turnMapper;
    private final ObjectMapper objectMapper;

    public InterviewService(InterviewSessionMapper sessionMapper,
                            InterviewTurnMapper turnMapper, ObjectMapper objectMapper) {
        this.sessionMapper = sessionMapper;
        this.turnMapper = turnMapper;
        this.objectMapper = objectMapper;
    }

    public List<InterviewListItem> list(Integer userId) {
        return sessionMapper.selectList(new LambdaQueryWrapper<InterviewSession>()
                        .eq(InterviewSession::getUserId, userId)
                        .orderByDesc(InterviewSession::getCreatedAt)
                        .last("LIMIT 50")).stream()
                .map(s -> new InterviewListItem(s.getId(), s.getPosition(), s.getLevel(),
                        s.getNumQuestions(), s.getStatus(), s.getTotalScore(), s.getCreatedAt()))
                .toList();
    }

    /** 取报告：会话 + 总评报告 + 逐轮问答（session 归属校验，越权返回 404） */
    public InterviewReportResponse report(Integer sessionId, Integer userId) {
        InterviewSession s = sessionMapper.selectOne(new LambdaQueryWrapper<InterviewSession>()
                .eq(InterviewSession::getId, sessionId)
                .eq(InterviewSession::getUserId, userId)
                .last("LIMIT 1"));
        if (s == null) {
            throw BizException.notFound("面试不存在");
        }

        JsonNode report = s.getReportJson() == null ? null : readTree(s.getReportJson());
        SessionDetail detail = new SessionDetail(
                s.getId(), s.getUserId(), s.getPosition(), s.getLevel(),
                parseDomains(s.getDomains()), s.getNumQuestions(), s.getDifficultyCap(),
                s.getStatus(), s.getCurrentSeq(), s.getTotalScore(),
                s.getCreatedAt(), s.getFinishedAt());

        List<TurnItem> turns = turnMapper.selectList(new LambdaQueryWrapper<InterviewTurn>()
                        .eq(InterviewTurn::getSessionId, sessionId)
                        .orderByAsc(InterviewTurn::getSeq)
                        .orderByAsc(InterviewTurn::getFollowupNo)).stream()
                .map(this::toTurnItem)
                .toList();

        return new InterviewReportResponse(detail, report, turns);
    }

    private TurnItem toTurnItem(InterviewTurn t) {
        return new TurnItem(
                t.getId(), t.getSeq(), t.getParentTurnId(), t.getFollowupNo(),
                t.getQuestion(), t.getQuestionSource(), t.getAnswer(), t.getScore(),
                t.getFeedback(),
                readTreeOr(t.getMissingPoints(), "[]"),
                readTreeOr(t.getDimJson(), "{}"),
                readTreeOr(t.getQaRefs(), "[]"),
                t.getCreatedAt());
    }

    private List<String> parseDomains(String domainsJson) {
        JsonNode node = readTreeOr(domainsJson, "[]");
        List<String> result = new ArrayList<>();
        if (node.isArray()) {
            node.forEach(n -> result.add(n.asText()));
        }
        return result;
    }

    private JsonNode readTreeOr(String json, String fallback) {
        if (json == null || json.isBlank()) {
            json = fallback;
        }
        return readTree(json);
    }

    private JsonNode readTree(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (Exception e) {
            return objectMapper.createObjectNode();
        }
    }
}
