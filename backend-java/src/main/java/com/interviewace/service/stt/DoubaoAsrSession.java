package com.interviewace.service.stt;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.config.AppProperties;

/**
 * 豆包流式 ASR（火山引擎 sauc bigmodel_async）二进制协议客户端。
 * 协议帧格式与 Python 版 stt_service.py 完全一致：
 *   [4B header][4B seq][4B payload_len][gzip(json payload)]
 * 连接断开时 inbound 队列收到 EOF 哨兵（空数组）。
 */
public class DoubaoAsrSession implements AutoCloseable {

    private static final Logger log = LoggerFactory.getLogger(DoubaoAsrSession.class);

    /** 连接关闭哨兵 */
    public static final byte[] EOF = new byte[0];

    private static final int PV1 = 0b0001;
    private static final int MT_FULL_REQ = 0b0001;
    private static final int MT_AUDIO_ONLY = 0b0010;
    private static final int MT_SERVER_FULL_RESP = 0b1001;
    private static final int MT_SERVER_ERROR = 0b1111;
    private static final int FLAG_POS_SEQ = 0b0001;
    private static final int FLAG_NEG_WITH_SEQ = 0b0011;
    private static final int SER_JSON = 0b0001;
    private static final int COMP_GZIP = 0b0001;

    private final WebSocket ws;
    private final AppProperties.Stt cfg;
    private final ObjectMapper mapper = new ObjectMapper();
    private final BlockingQueue<byte[]> inbound;
    private volatile boolean closed;
    private int seq = 1;

    private DoubaoAsrSession(WebSocket ws, AppProperties.Stt cfg, BlockingQueue<byte[]> inbound) {
        this.ws = ws;
        this.cfg = cfg;
        this.inbound = inbound;
    }

    /** 建连 + 发送配置帧 + 等待握手回包 */
    public static DoubaoAsrSession connect(AppProperties.Stt cfg) throws Exception {
        if (cfg.getApiKey() == null || cfg.getApiKey().isBlank()) {
            throw new IOException("VOLC_ASR_API_KEY 未配置");
        }
        Listener listener = new Listener();
        WebSocket ws = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build()
                .newWebSocketBuilder()
                .header("X-Api-Key", cfg.getApiKey())
                .header("X-Api-Resource-Id", cfg.getResourceId() == null ? "" : cfg.getResourceId())
                .header("X-Api-Request-Id", UUID.randomUUID().toString())
                .buildAsync(URI.create(cfg.getEndpoint()), listener)
                .get(15, TimeUnit.SECONDS);
        DoubaoAsrSession session = new DoubaoAsrSession(ws, cfg, listener.inbound);
        session.sendFullRequest(buildPayload(cfg));
        byte[] handshake = session.poll(10_000);
        if (handshake == null || handshake.length == 0) {
            session.close();
            throw new IOException("豆包 ASR 握手失败（无回包）");
        }
        Parsed p = session.parse(handshake);
        if (p.code != 0) {
            session.close();
            throw new IOException("豆包 ASR 握手错误 code=" + p.code);
        }
        log.info("doubao asr session ready");
        return session;
    }

    /** 发送音频分片（最后一包 seq 取负）*/
    public void sendAudio(byte[] pcm, boolean isLast) {
        if (closed) return;
        int s = seq;
        int flags = FLAG_POS_SEQ;
        if (isLast) {
            flags = FLAG_NEG_WITH_SEQ;
            s = -seq;
        } else {
            seq++;
        }
        sendFrame(MT_AUDIO_ONLY, flags, s, gzip(pcm));
    }

    /** 发送结束包（空音频，seq 取负）*/
    public void finish() {
        if (closed) return;
        sendFrame(MT_AUDIO_ONLY, FLAG_NEG_WITH_SEQ, -seq, gzip(new byte[0]));
        closed = true;
    }

    /** 阻塞等待一帧服务端回包；超时返回 null，连接断开返回 EOF */
    public byte[] poll(long timeoutMs) throws InterruptedException {
        return inbound.poll(timeoutMs, TimeUnit.MILLISECONDS);
    }

    private void sendFullRequest(JsonNode payload) {
        byte[] body = gzip(payload.toString().getBytes(StandardCharsets.UTF_8));
        sendFrame(MT_FULL_REQ, FLAG_POS_SEQ, seq++, body);
    }

    private void sendFrame(int messageType, int flags, int frameSeq, byte[] body) {
        try {
            ByteBuffer buf = ByteBuffer.allocate(4 + 4 + 4 + body.length).order(ByteOrder.BIG_ENDIAN);
            buf.put((byte) ((PV1 << 4) | 1));
            buf.put((byte) ((messageType << 4) | flags));
            buf.put((byte) ((SER_JSON << 4) | COMP_GZIP));
            buf.put((byte) 0x00);
            buf.putInt(frameSeq);
            buf.putInt(body.length);
            buf.put(body);
            ws.sendBinary(ByteBuffer.wrap(buf.array()), true);
        } catch (Exception e) {
            log.warn("doubao send failed: {}", e.getMessage());
        }
    }

    private static JsonNode buildPayload(AppProperties.Stt cfg) {
        ObjectMapper mapper = new ObjectMapper();
        var node = mapper.createObjectNode();
        node.putObject("user").put("uid", "interviewace");
        var audio = node.putObject("audio");
        audio.put("format", "pcm");
        audio.put("codec", "raw");
        audio.put("rate", cfg.getSampleRate());
        audio.put("bits", 16);
        audio.put("channel", 1);
        var request = node.putObject("request");
        request.put("model_name", "bigmodel");
        request.put("enable_itn", true);
        request.put("enable_punc", true);
        request.put("enable_ddc", true);
        request.put("show_utterances", true);
        request.put("end_window_size", 800);
        return node;
    }

    /** 解析服务端二进制帧（对应 Python _parse_response）*/
    public Parsed parse(byte[] msg) {
        Parsed r = new Parsed();
        if (msg.length < 4) return r;
        int headerSize = (msg[0] & 0x0F) * 4;
        int messageType = (msg[1] >> 4) & 0x0F;
        int flags = msg[1] & 0x0F;
        int compression = msg[2] & 0x0F;
        ByteBuffer buf = ByteBuffer.wrap(msg).order(ByteOrder.BIG_ENDIAN);
        buf.position(Math.min(headerSize, msg.length));

        r.isLast = (flags & 0x02) != 0;
        if ((flags & 0x01) != 0 && buf.remaining() >= 4) buf.getInt();
        if ((flags & 0x04) != 0 && buf.remaining() >= 4) buf.getInt();

        if (messageType == MT_SERVER_FULL_RESP && buf.remaining() >= 4) {
            buf.getInt();
        } else if (messageType == MT_SERVER_ERROR && buf.remaining() >= 8) {
            r.code = buf.getInt();
            buf.getInt();
        }

        byte[] payload = new byte[buf.remaining()];
        buf.get(payload);
        if (payload.length == 0) return r;
        if (compression == COMP_GZIP) {
            try {
                payload = gunzip(payload);
            } catch (Exception e) {
                log.warn("gzip decompress failed: {}", e.getMessage());
                return r;
            }
        }
        try {
            JsonNode data = mapper.readTree(payload);
            JsonNode res = data.path("result");
            r.text = res.path("text").asText(data.path("text").asText(""));
            StringBuilder definite = new StringBuilder();
            StringBuilder all = new StringBuilder();
            JsonNode utts = res.path("utterances");
            if (!utts.isArray()) utts = data.path("utterances");
            for (JsonNode u : utts) {
                String t = u.path("text").asText("");
                all.append(t);
                if (u.path("definite").asBoolean(false)) definite.append(t);
            }
            r.definiteText = definite.toString();
            r.allText = all.toString();
        } catch (Exception e) {
            log.warn("parse response payload failed: {}", e.getMessage());
        }
        return r;
    }

    static byte[] gzip(byte[] data) {
        try {
            ByteArrayOutputStream bos = new ByteArrayOutputStream(data.length + 16);
            try (GZIPOutputStream gz = new GZIPOutputStream(bos)) {
                gz.write(data);
            }
            return bos.toByteArray();
        } catch (IOException e) {
            return data;
        }
    }

    static byte[] gunzip(byte[] data) throws IOException {
        try (GZIPInputStream gin = new GZIPInputStream(new ByteArrayInputStream(data))) {
            return gin.readAllBytes();
        }
    }

    @Override
    public void close() {
        closed = true;
        try {
            ws.sendClose(WebSocket.NORMAL_CLOSURE, "bye");
        } catch (Exception ignored) {
        }
    }

    /** 服务端帧解析结果 */
    public static class Parsed {
        public int code;
        public boolean isLast;
        public String text = "";
        public String definiteText = "";
        public String allText = "";
    }

    /** WebSocket 监听器：把二进制帧累积后收进队列 */
    private static class Listener implements WebSocket.Listener {
        final BlockingQueue<byte[]> inbound = new LinkedBlockingQueue<>();
        private final ByteArrayOutputStream pending = new ByteArrayOutputStream();

        @Override
        public void onOpen(WebSocket webSocket) {
            webSocket.request(1);
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket webSocket, ByteBuffer data, boolean last) {
            byte[] chunk = new byte[data.remaining()];
            data.get(chunk);
            synchronized (pending) {
                pending.writeBytes(chunk);
                if (last) {
                    if (pending.size() > 0) {
                        inbound.offer(pending.toByteArray());
                    }
                    pending.reset();
                }
            }
            webSocket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
            inbound.offer(EOF);
            return null;
        }

        @Override
        public void onError(WebSocket webSocket, Throwable error) {
            log.warn("doubao asr ws error: {}", error.getMessage());
            inbound.offer(EOF);
        }
    }
}
