package com.interviewace.service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.dto.PracticeRecordItem;
import com.interviewace.entity.PracticeRecord;
import com.interviewace.mapper.PracticeRecordMapper;

/**
 * 答题练习服务（查询侧）：练习记录列表 / 错题过滤。
 * 对应 mysql.py list_practice；作答评估在 PracticeAnswerService（M3）。
 */
@Service
public class PracticeService {

    private static final int LIST_LIMIT = 200;

    private final PracticeRecordMapper practiceRecordMapper;

    public PracticeService(PracticeRecordMapper practiceRecordMapper) {
        this.practiceRecordMapper = practiceRecordMapper;
    }

    public List<PracticeRecordItem> records(Integer userId, boolean wrongOnly) {
        LambdaQueryWrapper<PracticeRecord> qw = new LambdaQueryWrapper<PracticeRecord>()
                .eq(PracticeRecord::getUserId, userId)
                .orderByDesc(PracticeRecord::getCreatedAt)
                .last("LIMIT " + LIST_LIMIT);
        if (wrongOnly) {
            qw.eq(PracticeRecord::getIsWrong, true);
        }
        return practiceRecordMapper.selectList(qw).stream()
                .map(r -> new PracticeRecordItem(r.getId(), r.getQuestionTitle(), r.getQuestionUrl(),
                        r.getDomain(), r.getDifficulty(), r.getScore(), r.getFeedback(),
                        r.getIsWrong(), r.getCreatedAt()))
                .toList();
    }
}
