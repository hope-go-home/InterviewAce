package com.interviewace.controller;

import java.net.URI;
import java.nio.ByteBuffer;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.UserContext;
import com.interviewace.security.JwtUtil;
import com.interviewace.service.stt.DoubaoAsrSession;
import com.interviewace.service.stt.SttService;

/**
 * 实时语音识别 /ws/stt：浏览器推 16k/16bit 单声道 PCM 二进制流 →
 * 豆包边识别边回文本；协议与 Python 版一致：
 *   浏览器→服务端：二进制帧 = PCM；文本帧 "END" = 结束
 *   服务端→浏览器：JSON {type: "partial"|"final"|"done"|"error", text}
 * WebSocket 无法带自定义 header，鉴权走 query 参数 ?token=
 */
@Component
public class WsSttHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(WsSttHandler.class);
    private static final CloseStatus UNAUTHORIZED = new CloseStatus(4401, "unauthorized");

    private final JwtUtil jwtUtil;
    private final SttService sttService;
    private final ObjectMapper objectMapper;

    public WsSttHandler(JwtUtil jwtUtil, SttService sttService, ObjectMapper objectMapper) {
        this.jwtUtil = jwtUtil;
        this.sttService = sttService;
        this.objectMapper = objectMapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        String token = queryParam(session, "token");
        UserContext user = null;
        try {
            if (token != null && !token.isBlank()) {
                user = jwtUtil.parseAccessToken(token);
            }
        } catch (Exception ignored) {
        }
        if (user == null) {
            session.close(UNAUTHORIZED);
            return;
        }
        if (!sttService.configured()) {
            sendJson(session, Map.of("type", "error", "text", "语音识别未配置（缺 VOLC_ASR_API_KEY）"));
            session.close(CloseStatus.NOT_ACCEPTABLE);
            return;
        }

        DoubaoAsrSession doubao;
        try {
            doubao = DoubaoAsrSession.connect(sttService.config());
        } catch (Exception e) {
            log.warn("ws/stt connect doubao failed: {}", e.getMessage());
            sendJson(session, Map.of("type", "error", "text", "识别服务连接失败：" + e.getMessage()));
            session.close();
            return;
        }
        session.getAttributes().put("doubao", doubao);

        // 豆包识别结果 → 浏览器（读线程）
        Thread reader = new Thread(() -> {
            try {
                long lastData = System.currentTimeMillis();
                while (session.isOpen() && System.currentTimeMillis() - lastData < 60_000) {
                    byte[] frame = doubao.poll(2_000);
                    if (frame == null) continue;
                    if (frame == DoubaoAsrSession.EOF || frame.length == 0) break;
                    lastData = System.currentTimeMillis();
                    DoubaoAsrSession.Parsed p = doubao.parse(frame);
                    if (p.code != 0) {
                        log.warn("doubao asr error code={}", p.code);
                        sendJson(session, Map.of("type", "error", "text", "识别错误 code=" + p.code));
                        break;
                    }
                    String text = !p.definiteText.isEmpty() ? p.definiteText
                            : (!p.allText.isEmpty() ? p.allText : p.text);
                    if (!text.isEmpty()) {
                        sendJson(session, Map.of(
                                "type", p.isLast || !p.definiteText.isEmpty() ? "final" : "partial",
                                "text", text));
                    }
                    if (p.isLast) {
                        sendJson(session, Map.of("type", "done", "text", ""));
                        break;
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                log.warn("ws/stt reader ended: {}", e.getMessage());
            } finally {
                try {
                    if (session.isOpen()) session.close();
                } catch (Exception ignored) {
                }
            }
        }, "ws-stt-reader");
        reader.setDaemon(true);
        reader.start();
    }

    @Override
    protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) {
        DoubaoAsrSession doubao = (DoubaoAsrSession) session.getAttributes().get("doubao");
        ByteBuffer payload = message.getPayload();
        if (doubao != null && payload.remaining() > 0) {
            byte[] bytes = new byte[payload.remaining()];
            payload.get(bytes);
            doubao.sendAudio(bytes, false);
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        if ("END".equals(message.getPayload())) {
            DoubaoAsrSession doubao = (DoubaoAsrSession) session.getAttributes().get("doubao");
            if (doubao != null) doubao.finish();
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        DoubaoAsrSession doubao = (DoubaoAsrSession) session.getAttributes().get("doubao");
        if (doubao != null) doubao.close();
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.warn("ws/stt transport error: {}", exception.getMessage());
        DoubaoAsrSession doubao = (DoubaoAsrSession) session.getAttributes().get("doubao");
        if (doubao != null) doubao.close();
    }

    private synchronized void sendJson(WebSocketSession session, Map<String, String> payload) {
        try {
            if (session.isOpen()) {
                session.sendMessage(new TextMessage(objectMapper.writeValueAsString(payload)));
            }
        } catch (Exception ignored) {
        }
    }

    private static String queryParam(WebSocketSession session, String name) {
        URI uri = session.getUri();
        if (uri == null || uri.getQuery() == null) return null;
        for (String pair : uri.getQuery().split("&")) {
            int eq = pair.indexOf('=');
            String k = eq > 0 ? pair.substring(0, eq) : pair;
            if (k.equals(name)) {
                String v = eq > 0 ? pair.substring(eq + 1) : "";
                try {
                    return java.net.URLDecoder.decode(v, java.nio.charset.StandardCharsets.UTF_8);
                } catch (Exception e) {
                    return v;
                }
            }
        }
        return null;
    }
}
