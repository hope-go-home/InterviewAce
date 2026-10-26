package com.interviewace.service.pending;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.common.BizException;
import com.interviewace.entity.PendingQuestion;
import com.interviewace.mapper.PendingQuestionMapper;
import com.interviewace.service.bank.BankKnowledgeService;
import com.interviewace.service.llm.LLMClient;

/**
 * 待补题池采纳入库服务：LLM 生成标准答案 → 入库题库。
 * 对应 main.py 的 /pending/{id}/adopt。
 */
@Service
public class PendingAdoptService {

    private final PendingQuestionMapper pendingMapper;
    private final LLMClient llm;
    private final BankKnowledgeService bankService;

    public PendingAdoptService(PendingQuestionMapper pendingMapper, LLMClient llm,
                               BankKnowledgeService bankService) {
        this.pendingMapper = pendingMapper;
        this.llm = llm;
        this.bankService = bankService;
    }

    public Map<String, Object> adopt(int pendingId, Integer userId, String username) {
        PendingQuestion target = pendingMapper.selectOne(
                new LambdaQueryWrapper<PendingQuestion>()
                        .eq(PendingQuestion::getId, pendingId)
                        .last("LIMIT 1"));
        if (target == null) {
            throw BizException.notFound("待补题不存在");
        }

        String question = target.getQuestion();
        String answer = target.getDraftAnswer() == null ? "" : target.getDraftAnswer();

        // 没有草稿答案就现场生成
        if (answer.length() < 80) {
            answer = llm.chat(
                    "你是技术面试专家。请为这道面试题写一份分点、专业、200-400字的参考答案。\n\n题目：" + question,
                    false, 0.4);
            if (answer.isBlank()) {
                throw BizException.serverError("生成答案失败");
            }
        }

        String domain = target.getDomain() == null || target.getDomain().isBlank()
                ? "llm_basics" : target.getDomain();
        String url = target.getSourceUrl() == null ? "" : target.getSourceUrl();

        Map<String, Object> result = bankService.add(question, answer, domain, 2, "", url, username);

        // 标记已采纳
        target.setStatus("adopted");
        pendingMapper.updateById(target);

        result.put("answer_len", answer.length());
        return result;
    }
}
