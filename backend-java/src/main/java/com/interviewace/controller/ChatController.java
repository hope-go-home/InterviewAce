package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.ChatHistoryItem;
import com.interviewace.dto.SessionSummary;
import com.interviewace.service.ChatService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 问答会话接口：会话列表 / 历史记录 / 删除会话（按用户隔离）。
 */
@Tag(name = "问答会话", description = "题库问答的会话与历史")
@RestController
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @Operation(summary = "我的会话列表（首问/末次时间/条数）")
    @GetMapping("/sessions")
    public Map<String, List<SessionSummary>> sessions(@CurrentUser UserContext user) {
        return Map.of("sessions", chatService.listSessions(user.id()));
    }

    @Operation(summary = "某个会话的完整问答历史")
    @GetMapping("/history/{sessionId}")
    public Map<String, List<ChatHistoryItem>> history(@PathVariable String sessionId,
                                                      @CurrentUser UserContext user) {
        return Map.of("history", chatService.history(sessionId, user.id()));
    }

    @Operation(summary = "删除会话（含全部问答记录）")
    @DeleteMapping("/sessions/{sessionId}")
    public Map<String, Integer> deleteSession(@PathVariable String sessionId,
                                              @CurrentUser UserContext user) {
        return Map.of("deleted", chatService.deleteSession(sessionId, user.id()));
    }
}
