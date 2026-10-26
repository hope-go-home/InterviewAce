package com.interviewace.common;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记 Controller 方法参数为当前登录用户，例如：
 * <pre>{@code
 * public Result me(@CurrentUser UserContext user) { ... }
 * }</pre>
 * 由 CurrentUserArgumentResolver 解析（等价于 FastAPI 的 Depends(get_current_user)）。
 */
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface CurrentUser {
}
