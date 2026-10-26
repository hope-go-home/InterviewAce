package com.interviewace.controller;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.interviewace.common.BizException;
import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.service.stt.SttService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 语音转文字：接收 WAV（16k mono 16bit）→ 豆包流式 ASR → 返回文本。
 * 对应 FastAPI POST /stt。
 */
@Tag(name = "语音", description = "语音识别")
@RestController
public class SttController {

    private final SttService sttService;

    public SttController(SttService sttService) {
        this.sttService = sttService;
    }

    @Operation(summary = "WAV 语音转文字（豆包流式 ASR）")
    @PostMapping(value = "/stt", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> speechToText(@RequestParam("file") MultipartFile file,
                                            @CurrentUser UserContext user) throws Exception {
        byte[] data = file.getBytes();
        if (data.length < 100) {
            throw BizException.badRequest("音频太短");
        }
        if (data.length > 25 * 1024 * 1024) {
            throw BizException.badRequest("音频不能超过 25MB");
        }
        try {
            return Map.of("text", sttService.transcribe(data));
        } catch (BizException e) {
            throw e;
        } catch (Exception e) {
            throw new BizException(org.springframework.http.HttpStatus.BAD_GATEWAY,
                    "语音识别失败：" + e.getMessage());
        }
    }
}
