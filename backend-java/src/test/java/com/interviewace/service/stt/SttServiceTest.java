package com.interviewace.service.stt;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import org.junit.jupiter.api.Test;

class SttServiceTest {

    /** 手工构造一个最小合法 WAV（16k/16bit/mono，PCM 数据为给定采样点） */
    private static byte[] wav16k(short... samples) throws IOException {
        byte[] pcm = new byte[samples.length * 2];
        ByteBuffer buf = ByteBuffer.wrap(pcm).order(ByteOrder.LITTLE_ENDIAN);
        for (short s : samples) buf.putShort(s);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteBuffer head = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        head.put("RIFF".getBytes());
        head.putInt(36 + pcm.length);
        head.put("WAVE".getBytes());
        head.put("fmt ".getBytes());
        head.putInt(16);            // fmt 块大小
        head.putShort((short) 1);   // PCM
        head.putShort((short) 1);   // mono
        head.putInt(16000);         // sample rate
        head.putInt(32000);         // byte rate
        head.putShort((short) 2);   // block align
        head.putShort((short) 16);  // bits
        head.put("data".getBytes());
        head.putInt(pcm.length);
        out.write(head.array());
        out.write(pcm);
        return out.toByteArray();
    }

    @Test
    void readWavPcm_extractsPcmAndRate() throws Exception {
        byte[] wav = wav16k((short) 100, (short) -200, (short) 30000);
        // 通过 transcribe 的解析路径直接验证：反射不必要，readWavPcm 是包私有静态
        var data = SttService.readWavPcm(wav);
        assertEquals(16000, data.rate());
        assertEquals(6, data.pcm().length);
    }

    @Test
    void readWavPcm_rejectsNonWav() {
        assertThrows(IOException.class,
                () -> SttService.readWavPcm("not a wav file at all".getBytes()));
    }

    @Test
    void resamplePcm16_halvesLengthWhenDownsampling2x() {
        // 32000Hz → 16000Hz：采样点数减半
        short[] in = new short[1000];
        for (int i = 0; i < in.length; i++) in[i] = (short) i;
        ByteBuffer buf = ByteBuffer.allocate(in.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (short s : in) buf.putShort(s);

        byte[] out = SttService.resamplePcm16(buf.array(), 32000, 16000);

        assertEquals(500 * 2, out.length);
    }

    @Test
    void resamplePcm16_sameRate_passThrough() {
        byte[] pcm = {1, 2, 3, 4};
        assertArrayEquals(pcm, SttService.resamplePcm16(pcm, 16000, 16000));
    }
}
