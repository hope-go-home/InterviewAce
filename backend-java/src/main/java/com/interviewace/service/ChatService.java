package com.interviewace.service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.dto.ChatHistoryItem;
import com.interviewace.dto.SessionSummary;
import com.interviewace.entity.ChatRecord;
import com.interviewace.mapper.ChatRecordMapper;

/**
 * 问答会话服务：会话列表 / 历史 / 删除（按用户隔离）。
 * 对应 mysql.py 的 get_history / list_sessions / delete_session。
 */
@Service
public class ChatService {

    private final ChatRecordMapper chatRecordMapper;

    public ChatService(ChatRecordMapper chatRecordMapper) {
        this.chatRecordMapper = chatRecordMapper;
    }

    public List<SessionSummary> listSessions(Integer userId) {
        return chatRecordMapper.listSessions(userId, 50);
    }

    public List<ChatHistoryItem> history(String sessionId, Integer userId) {
        List<ChatRecord> records = chatRecordMapper.selectList(new LambdaQueryWrapper<ChatRecord>()
                .eq(ChatRecord::getSessionId, sessionId)
                .eq(ChatRecord::getUserId, userId)
                .orderByAsc(ChatRecord::getCreatedAt));
        return records.stream()
                .map(r -> new ChatHistoryItem(r.getQuestion(), r.getAnswer(), r.getCreatedAt()))
                .toList();
    }

    /** 删除会话的全部问答记录，返回删除条数（user_id 校验归属） */
    public int deleteSession(String sessionId, Integer userId) {
        return chatRecordMapper.delete(new LambdaQueryWrapper<ChatRecord>()
                .eq(ChatRecord::getSessionId, sessionId)
                .eq(ChatRecord::getUserId, userId));
    }
}
