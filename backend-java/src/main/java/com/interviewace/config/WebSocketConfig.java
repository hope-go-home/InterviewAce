package com.interviewace.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

import com.interviewace.controller.WsSttHandler;

/**
 * WebSocket 注册：实时语音识别 /ws/stt。
 * Vite 代理 /api → :8002（rewrite 去掉 /api，ws: true），前端连 /api/ws/stt。
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final WsSttHandler wsSttHandler;

    public WebSocketConfig(WsSttHandler wsSttHandler) {
        this.wsSttHandler = wsSttHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(wsSttHandler, "/ws/stt").setAllowedOrigins("*");
    }
}
