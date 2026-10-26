package com.interviewace.security;

import org.springframework.core.MethodParameter;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

import com.interviewace.common.BizException;
import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;

/**
 * 解析 @CurrentUser 参数：从 request attribute 取拦截器放入的登录用户。
 * 拦截器已保证白名单外的请求必然携带有效用户，此处为防御性兜底。
 */
@Component
public class CurrentUserArgumentResolver implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentUser.class)
                && UserContext.class.isAssignableFrom(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mavContainer,
                                  NativeWebRequest webRequest, WebDataBinderFactory binderFactory) {
        Object attr = webRequest.getNativeRequest(jakarta.servlet.http.HttpServletRequest.class)
                .getAttribute(UserContext.REQUEST_ATTRIBUTE);
        if (attr instanceof UserContext user) {
            return user;
        }
        throw BizException.unauthorized("未登录或缺少 Token");
    }
}
