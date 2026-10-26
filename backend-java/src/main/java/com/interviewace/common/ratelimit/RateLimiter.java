package com.interviewace.common.ratelimit;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 接口限流：固定窗口计数（对应 Python ratelimit.py FixedWindowLimiter），
 * 升级为 Redis 实现——多实例部署时限流额度全局共享（企业级做法）。
 *
 * <p>降级策略：Redis 不可用时自动回落到进程内限流（与 Python 单机行为一致），
 * 保证可用性优先，同时打警告日志暴露基础设施问题。
 */
@Component
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);

    /** 各业务桶的限额配置（与 ratelimit.py 完全一致） */
    public static final int CHAT_LIMIT = 30;
    public static final int INTERVIEW_LIMIT = 30;
    public static final int LOGIN_LIMIT = 20;
    public static final int UPLOAD_LIMIT = 20;
    public static final int FEEDBACK_LIMIT = 60;
    public static final int WINDOW_SECONDS = 60;

    private final StringRedisTemplate redis;
    private final ConcurrentHashMap<String, MemoryWindow> memoryBuckets = new ConcurrentHashMap<>();

    public RateLimiter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** 登录/注册：按 IP 限流 */
    public boolean allowLogin(String ip) {
        return allow("login", ip, LOGIN_LIMIT, WINDOW_SECONDS);
    }

    /** 提问（SSE 问答）：按用户限流 */
    public boolean allowChat(Integer userId) {
        return allow("chat", String.valueOf(userId), CHAT_LIMIT, WINDOW_SECONDS);
    }

    /** 面试/练习重操作：按用户限流 */
    public boolean allowInterview(Integer userId) {
        return allow("interview", String.valueOf(userId), INTERVIEW_LIMIT, WINDOW_SECONDS);
    }

    /** 上传：按用户限流 */
    public boolean allowUpload(Integer userId) {
        return allow("upload", String.valueOf(userId), UPLOAD_LIMIT, WINDOW_SECONDS);
    }

    /**
     * 固定窗口限流判定。
     * 窗口键含窗口序号（epoch/window），窗口滚动时 key 自然失效，无需清理任务。
     */
    public boolean allow(String bucket, String key, int limit, int windowSeconds) {
        long windowStart = System.currentTimeMillis() / 1000 / windowSeconds * windowSeconds;
        String redisKey = "rl:" + bucket + ":" + key + ":" + windowStart;
        try {
            Long count = redis.opsForValue().increment(redisKey);
            if (count != null && count == 1L) {
                redis.expire(redisKey, Duration.ofSeconds(windowSeconds + 1));
            }
            return count != null && count <= limit;
        } catch (Exception e) {
            log.warn("Redis 限流不可用，降级进程内限流: {}", e.getMessage());
            return allowMemory(bucket + ":" + key, limit, windowSeconds, windowStart);
        }
    }

    /** 进程内降级实现（与 Python 版语义一致） */
    private boolean allowMemory(String bucketKey, int limit, int windowSeconds, long windowStart) {
        MemoryWindow w = memoryBuckets.compute(bucketKey, (k, old) ->
                (old == null || old.windowStart != windowStart) ? new MemoryWindow(windowStart) : old);
        int n = w.count.incrementAndGet();
        // 控制降级桶数量，防止 key 膨胀
        if (memoryBuckets.size() > 10_000) {
            memoryBuckets.clear();
        }
        return n <= limit;
    }

    private static final class MemoryWindow {
        final long windowStart;
        final AtomicInteger count = new AtomicInteger();

        MemoryWindow(long windowStart) {
            this.windowStart = windowStart;
        }
    }
}
