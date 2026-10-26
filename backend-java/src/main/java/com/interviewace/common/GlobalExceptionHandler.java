package com.interviewace.common;

import java.util.Map;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import jakarta.servlet.http.HttpServletRequest;

/**
 * 全局异常处理：一个类兜住所有 Controller 异常（AOP 思想）。
 *
 * <p>输出格式与 FastAPI HTTPException 对齐：{"detail": "..."} + 对应 HTTP 状态码，
 * 前端零改动（前端读取 err.detail 展示）。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /** 业务异常：按异常携带的状态码原样返回 */
    @ExceptionHandler(BizException.class)
    public ResponseEntity<Map<String, String>> handleBiz(BizException e) {
        return ResponseEntity.status(e.status()).body(Map.of("detail", String.valueOf(e.getMessage())));
    }

    /** 参数校验失败：@Valid 字段错误聚合为一条可读文案（对应 FastAPI 422 detail） */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidation(MethodArgumentNotValidException e) {
        String detail = e.getBindingResult().getFieldErrors().stream()
                .map(this::formatFieldError)
                .collect(Collectors.joining("；"));
        return ResponseEntity.badRequest().body(Map.of("detail", detail));
    }

    /** 404 静态资源/路由：与 FastAPI 404 detail 对齐 */
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, String>> handleNoResource(NoResourceFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("detail", "Not Found"));
    }

    /** 兜底：未知异常记日志，返回不泄露堆栈的通用文案 */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleUnknown(Exception e, HttpServletRequest request) {
        log.error("未处理异常 {} {}", request.getMethod(), request.getRequestURI(), e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("detail", "服务内部错误，请稍后重试"));
    }

    private String formatFieldError(FieldError e) {
        return e.getField() + " " + e.getDefaultMessage();
    }
}
