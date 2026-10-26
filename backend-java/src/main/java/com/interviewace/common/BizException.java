package com.interviewace.common;

import org.springframework.http.HttpStatus;

/**
 * 业务异常：携带 HTTP 状态码 + 面向用户的 detail 文案。
 *
 * <p>全局异常处理器统一转成 FastAPI 风格的 {"detail": "..."}，
 * 与前端既有错误处理逻辑（err.detail）保持契约兼容。
 */
public class BizException extends RuntimeException {

    private final HttpStatus status;

    public BizException(HttpStatus status, String detail) {
        super(detail);
        this.status = status;
    }

    public static BizException badRequest(String detail) {
        return new BizException(HttpStatus.BAD_REQUEST, detail);
    }

    public static BizException unauthorized(String detail) {
        return new BizException(HttpStatus.UNAUTHORIZED, detail);
    }

    public static BizException forbidden(String detail) {
        return new BizException(HttpStatus.FORBIDDEN, detail);
    }

    public static BizException notFound(String detail) {
        return new BizException(HttpStatus.NOT_FOUND, detail);
    }

    public static BizException conflict(String detail) {
        return new BizException(HttpStatus.CONFLICT, detail);
    }

    public static BizException tooMany(String detail) {
        return new BizException(HttpStatus.TOO_MANY_REQUESTS, detail);
    }

    public static BizException serviceUnavailable(String detail) {
        return new BizException(HttpStatus.SERVICE_UNAVAILABLE, detail);
    }

    public static BizException serverError(String detail) {
        return new BizException(HttpStatus.INTERNAL_SERVER_ERROR, detail);
    }

    public HttpStatus status() {
        return status;
    }
}
