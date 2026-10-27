package com.interviewace.service.stt;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.interviewace.config.AppProperties;

/**
 * 语音转文字：WAV（16k mono 16bit）→ 分片流式送豆包 ASR → 最终文本。
 * 对应 Python services/stt_service.py 的 transcribe_wav。
 */
@Service
public class SttService {

    private static final Logger log = LoggerFactory.getLogger(SttService.class);

    private final AppProperties.Stt cfg;

    public SttService(AppProperties props) {
        this.cfg = props.getStt();
    }

    public boolean configured() {
        return cfg.getApiKey() != null && !cfg.getApiKey().isBlank();
    }

    public AppProperties.Stt config() {
        return cfg;
    }

    /** 转写一段 WAV，返回最终文本（流式送识别，非实时）*/
    public String transcribe(byte[] wav) throws Exception {
        PcmData pcmData = readWavPcm(wav);
        byte[] pcm = pcmData.pcm();
        if (pcmData.rate() != cfg.getSampleRate()) {
            log.info("wav sample rate {} → resample to {}", pcmData.rate(), cfg.getSampleRate());
            pcm = resamplePcm16(pcmData.pcm(), pcmData.rate(), cfg.getSampleRate());
        }

        // 分片：每片 segmentMs 毫秒（16k*16bit*mono → 32000 字节/秒 → 6400 字节/200ms）
        int segSize = Math.max(2, cfg.getSampleRate() * 2 * cfg.getSegmentMs() / 1000);
        List<byte[]> segments = new ArrayList<>();
        for (int i = 0; i < pcm.length; i += segSize) {
            segments.add(java.util.Arrays.copyOfRange(pcm, i, Math.min(i + segSize, pcm.length)));
        }
        if (segments.isEmpty()) segments.add(new byte[0]);

        // 豆包每帧的 utterances 是累计列表（已 definite 的句子会重复出现在后续帧），
        // 所以不能逐帧 append——保留最新一帧的 definite 拼接即可，最后一帧即完整定稿
        List<String> finalTexts = new ArrayList<>();
        StringBuilder lastText = new StringBuilder();
        try (DoubaoAsrSession sess = DoubaoAsrSession.connect(cfg)) {
            for (int i = 0; i < segments.size(); i++) {
                boolean isLast = (i == segments.size() - 1);
                sess.sendAudio(segments.get(i), isLast);
                if (!isLast) {
                    Thread.sleep(cfg.getSegmentMs());
                }
            }
            long deadline = System.currentTimeMillis() + 20_000;
            while (System.currentTimeMillis() < deadline) {
                byte[] frame = sess.poll(2_000);
                if (frame == null) continue;
                if (frame == DoubaoAsrSession.EOF || frame.length == 0) break;
                DoubaoAsrSession.Parsed p = sess.parse(frame);
                if (p.code != 0) {
                    log.warn("doubao asr error code={}", p.code);
                    break;
                }
                if (!p.definiteText.isEmpty()) {
                    finalTexts.clear();
                    finalTexts.add(p.definiteText);
                }
                if (!p.allText.isEmpty()) {
                    lastText.setLength(0);
                    lastText.append(p.allText);
                }
                if (p.isLast) break;
            }
        }

        String text = String.join("", finalTexts).strip();
        if (text.isEmpty()) text = lastText.toString().strip();
        if (text.isEmpty()) text = "（未识别到内容）";
        log.info("stt transcribe done, {} final segments, {} chars", finalTexts.size(), text.length());
        return text;
    }

    /** 从 WAV 提取裸 PCM 与采样率（遍历块，兼容 fmt 块 16/18/40 字节）*/
    static PcmData readWavPcm(byte[] wav) throws IOException {
        if (wav.length < 44 || wav[0] != 'R' || wav[1] != 'I' || wav[2] != 'F' || wav[3] != 'F'
                || wav[8] != 'W' || wav[9] != 'A' || wav[10] != 'V' || wav[11] != 'E') {
            throw new IOException("不是合法的 WAV 文件");
        }
        ByteBuffer buf = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN);
        int sampleRate = 0;
        int pos = 12;
        while (pos + 8 <= wav.length) {
            buf.position(pos);
            String chunkId = new String(new char[]{(char) buf.get(), (char) buf.get(),
                    (char) buf.get(), (char) buf.get()});
            int chunkSize = buf.getInt();
            int body = pos + 8;
            if (chunkSize < 0 || body + chunkSize > wav.length) break;
            if ("fmt ".equals(chunkId)) {
                buf.position(body + 4);
                sampleRate = buf.getInt();
            } else if ("data".equals(chunkId)) {
                byte[] pcm = java.util.Arrays.copyOfRange(wav, body, body + chunkSize);
                if (sampleRate <= 0) sampleRate = 16000;
                return new PcmData(pcm, sampleRate);
            }
            pos = body + chunkSize + (chunkSize & 1);
        }
        throw new IOException("WAV 缺少 data 块");
    }

    /** 16bit 单声道 PCM 线性插值重采样（如 22050 → 16000）*/
    static byte[] resamplePcm16(byte[] pcm, int fromRate, int toRate) {
        if (fromRate == toRate || pcm.length < 2) return pcm;
        int nIn = pcm.length / 2;
        short[] samples = new short[nIn];
        ByteBuffer buf = ByteBuffer.wrap(pcm, 0, nIn * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < nIn; i++) samples[i] = buf.getShort();
        int nOut = (int) ((long) nIn * toRate / fromRate);
        double ratio = (double) fromRate / toRate;
        ByteBuffer out = ByteBuffer.allocate(nOut * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < nOut; i++) {
            double pos = i * ratio;
            int i0 = (int) pos;
            int i1 = Math.min(i0 + 1, nIn - 1);
            double frac = pos - i0;
            short v = (short) (samples[i0] + (samples[i1] - samples[i0]) * frac);
            out.putShort(v);
        }
        return out.array();
    }

    record PcmData(byte[] pcm, int rate) {}

    /** 供 /stt 控制器做快速体积校验 */
    public static byte[] utf8(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }
}
