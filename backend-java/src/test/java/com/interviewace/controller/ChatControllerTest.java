package com.interviewace.controller;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.datatype.jsr310.ser.LocalDateTimeSerializer;
import com.interviewace.common.GlobalExceptionHandler;
import com.interviewace.common.UserContext;
import com.interviewace.config.JacksonConfig;
import com.interviewace.dto.SessionSummary;
import com.interviewace.security.CurrentUserArgumentResolver;
import com.interviewace.service.ChatService;

/**
 * 会话接口契约测试（standalone MockMvc）。
 * 守住前端依赖的 JSON 契约：snake_case 字段名 + "yyyy-MM-dd HH:mm:ss" 时间格式。
 */
class ChatControllerTest {

    private ChatService chatService;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        chatService = mock(ChatService.class);
        // 与生产 JacksonConfig + application.yml 的序列化约定保持一致
        ObjectMapper om = new ObjectMapper();
        om.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        SimpleModule sm = new SimpleModule();
        sm.addSerializer(LocalDateTime.class, new LocalDateTimeSerializer(JacksonConfig.DATETIME_PATTERN));
        om.registerModule(sm);

        mvc = MockMvcBuilders.standaloneSetup(new ChatController(chatService))
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new CurrentUserArgumentResolver())
                .setMessageConverters(new MappingJackson2HttpMessageConverter(om))
                .build();
    }

    @Test
    void sessions_returnsSnakeCaseContract() throws Exception {
        when(chatService.listSessions(1)).thenReturn(List.of(
                new SessionSummary("abc123", "什么是RAG",
                        LocalDateTime.of(2026, 10, 11, 19, 53, 9), 3)));

        mvc.perform(get("/sessions")
                        .requestAttr(UserContext.REQUEST_ATTRIBUTE, new UserContext(1, "admin", "admin")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessions[0].session_id").value("abc123"))
                .andExpect(jsonPath("$.sessions[0].first_question").value("什么是RAG"))
                .andExpect(jsonPath("$.sessions[0].last_time").value("2026-10-11 19:53:09"))
                .andExpect(jsonPath("$.sessions[0].count").value(3));
    }

    @Test
    void sessions_withoutLogin_401() throws Exception {
        mvc.perform(get("/sessions"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("未登录或缺少 Token"));
    }
}
