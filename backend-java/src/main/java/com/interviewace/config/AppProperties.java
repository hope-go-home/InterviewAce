package com.interviewace.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import lombok.Data;

/**
 * 业务配置绑定（对应 Python 侧 config.py + .env）。
 * 所有敏感项都通过 ${ENV_VAR:default} 从环境/.env 注入，不硬编码。
 */
@Data
@Component
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private Jwt jwt = new Jwt();
    private boolean allowRegistration = true;
    private int dailyTokenBudget;
    private DefaultAdmin defaultAdmin = new DefaultAdmin();
    private int heavyConcurrency = 8;
    private Ai ai = new Ai();
    private Stt stt = new Stt();

    @Data
    public static class Jwt {
        private String secret;
        private long expireMinutes = 720;
    }

    @Data
    public static class DefaultAdmin {
        private String username = "admin";
        private String password = "admin123";
    }

    @Data
    public static class Ai {
        private Qwen qwen = new Qwen();
        private Milvus milvus = new Milvus();
    }

    @Data
    public static class Qwen {
        private String apiKey;
        private String baseUrl;
        private String model;
        private String embeddingModel;
        private String judgeModel;
        private String vlModel;
    }

    @Data
    public static class Milvus {
        private String host = "127.0.0.1";
        private int port = 19530;
        private String collection = "interview_kb";
        private int dim = 2048;
    }

    /** 豆包流式语音识别（火山引擎 sauc bigmodel_async）*/
    @Data
    public static class Stt {
        private String apiKey;
        private String resourceId;
        private String endpoint = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async";
        private int sampleRate = 16000;
        private int segmentMs = 200;
    }

    /** 知识域 → 中文名（对应 main.py DOMAIN_NAMES / mysql.py DOMAIN_CN） */
    public static final List<String> DOMAINS = List.of(
            "llm_basics", "prompt", "rag", "agent", "vectordb",
            "framework", "python_backend", "ml_dl", "cs_basic");

    public static String domainName(String key) {
        return switch (key == null ? "" : key) {
            case "llm_basics" -> "LLM 原理";
            case "prompt" -> "Prompt 工程";
            case "rag" -> "RAG";
            case "agent" -> "Agent";
            case "vectordb" -> "向量数据库";
            case "framework" -> "框架";
            case "python_backend" -> "Python 后端";
            case "ml_dl" -> "ML/DL";
            case "cs_basic" -> "CS 基础";
            default -> key == null ? "" : key;
        };
    }
}
