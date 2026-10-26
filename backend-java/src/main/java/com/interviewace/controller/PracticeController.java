package com.interviewace.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.PracticeRecordItem;
import com.interviewace.service.PracticeService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 答题练习接口（查询侧）：练习记录 / 错题过滤。
 * 抽题与作答评估（依赖 Milvus + LLM）在 PracticeAnswerController（M3）。
 */
@Tag(name = "答题练习", description = "练习记录查询")
@RestController
public class PracticeController {

    private final PracticeService practiceService;

    public PracticeController(PracticeService practiceService) {
        this.practiceService = practiceService;
    }

    @Operation(summary = "练习记录列表（wrong_only=true 只看错题）")
    @GetMapping("/practice/records")
    public Map<String, List<PracticeRecordItem>> records(
            @RequestParam(required = false, defaultValue = "false") boolean wrongOnly,
            @CurrentUser UserContext user) {
        return Map.of("records", practiceService.records(user.id(), wrongOnly));
    }
}
