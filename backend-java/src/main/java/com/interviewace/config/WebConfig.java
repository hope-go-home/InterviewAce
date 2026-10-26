package com.interviewace.config;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import com.interviewace.security.AuthInterceptor;
import com.interviewace.security.CurrentUserArgumentResolver;

/**
 * Web 层装配：CORS（对应 FastAPI CORSMiddleware）+ 鉴权拦截器 + @CurrentUser 解析。
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AuthInterceptor authInterceptor;
    private final CurrentUserArgumentResolver currentUserArgumentResolver;

    public WebConfig(AuthInterceptor authInterceptor,
                     CurrentUserArgumentResolver currentUserArgumentResolver) {
        this.authInterceptor = authInterceptor;
        this.currentUserArgumentResolver = currentUserArgumentResolver;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOrigins("http://localhost:5173", "http://127.0.0.1:5173")
                .allowedMethods("*")
                .allowedHeaders("*")
                .allowCredentials(true);
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns(
                        // 认证
                        "/auth/login", "/auth/register",
                        // 探针与监控（K8s/Docker 存活就绪、Prometheus 抓取）
                        "/health", "/ready",
                        "/actuator/health", "/actuator/health/**", "/actuator/prometheus",
                        "/actuator/info",
                        // 接口文档
                        "/doc.html", "/webjars/**", "/swagger-ui/**", "/swagger-resources/**",
                        "/v3/api-docs/**", "/favicon.ico",
                        // WebSocket（处理器内自带 ?token= 鉴权，MVC 拦截器管不到握手之外的升级）
                        "/ws/stt");
    }

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(currentUserArgumentResolver);
    }
}
