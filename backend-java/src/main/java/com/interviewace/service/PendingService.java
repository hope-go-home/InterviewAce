package com.interviewace.service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.dto.PendingItem;
import com.interviewace.entity.PendingQuestion;
import com.interviewace.mapper.PendingQuestionMapper;

/**
 * 待补题池服务（查询侧）：列表按被问次数排序。
 * 对应 mysql.py list_pending；采纳入库（LLM 生成答案）在 PendingAdoptService（M3）。
 */
@Service
public class PendingService {

    private final PendingQuestionMapper pendingMapper;

    public PendingService(PendingQuestionMapper pendingMapper) {
        this.pendingMapper = pendingMapper;
    }

    public List<PendingItem> list(String status) {
        LambdaQueryWrapper<PendingQuestion> qw = new LambdaQueryWrapper<PendingQuestion>()
                .orderByDesc(PendingQuestion::getAskCount)
                .orderByDesc(PendingQuestion::getCreatedAt)
                .last("LIMIT 100");
        if (status != null && !status.isBlank()) {
            qw.eq(PendingQuestion::getStatus, status);
        }
        return pendingMapper.selectList(qw).stream()
                .map(p -> new PendingItem(p.getId(), p.getQuestion(), p.getDomain(),
                        p.getPosition(), p.getAskCount(), p.getDraftAnswer(), p.getSourceUrl(),
                        p.getStatus(), p.getCreatedAt()))
                .toList();
    }
}
