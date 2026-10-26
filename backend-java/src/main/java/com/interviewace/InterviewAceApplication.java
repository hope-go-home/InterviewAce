package com.interviewace;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * InterviewAce 企业级后端启动类。
 *
 * <p>对应 Python 侧 interviewace/backend/main.py，能力对照：
 * <ul>
 *   <li>FastAPI lifespan 初始化 → 启动期 Flyway 迁移 + 种子数据</li>
 *   <li>HTTPException(detail) → 全局异常处理器统一返回 {"detail": ...}</li>
 *   <li>Depends(get_current_user) → JWT 拦截器 + @CurrentUser 参数解析</li>
 * </ul>
 */
@SpringBootApplication
@MapperScan("com.interviewace.mapper")
public class InterviewAceApplication {

    public static void main(String[] args) {
        SpringApplication.run(InterviewAceApplication.class, args);
    }
}
