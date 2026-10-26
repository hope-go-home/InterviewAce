package com.interviewace.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.InterviewListItem;
import com.interviewace.dto.InterviewReportResponse;
import com.interviewace.service.InterviewService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 模拟面试接口（查询侧）：历史列表 / 面试报告。
 * 开场、作答评分、快照、结束（依赖 Milvus + LLM）在 InterviewRunController（M3）。
 */
@Tag(name = "模拟面试", description = "面试历史与报告")
@RestController
public class InterviewController {

    private final InterviewService interviewService;

    public InterviewController(InterviewService interviewService) {
        this.interviewService = interviewService;
    }

    @Operation(summary = "历史面试列表")
    @GetMapping("/interviews")
    public List<InterviewListItem> list(@CurrentUser UserContext user) {
        return interviewService.list(user.id());
    }

    @Operation(summary = "面试报告（会话 + 总评 + 逐轮问答）")
    @GetMapping("/interview/{sessionId}/report")
    public InterviewReportResponse report(@PathVariable Integer sessionId,
                                          @CurrentUser UserContext user) {
        return interviewService.report(sessionId, user.id());
    }
}
