package com.interviewace.common.ratelimit;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

/** Redis 不可用时降级进程内限流的路径（生产上 Redis 挂过一次后加的防御） */
class RateLimiterTest {

    private RateLimiter limiter;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenThrow(new RedisConnectionFailureException("down"));
        limiter = new RateLimiter(redis);
    }

    @Test
    void allowChat_withinWindow_enforcesLimit() {
        for (int i = 0; i < RateLimiter.CHAT_LIMIT; i++) {
            assertTrue(limiter.allowChat(1), "第 " + (i + 1) + " 次应放行");
        }
        assertFalse(limiter.allowChat(1), "超过窗口限额应拒绝");
    }

    @Test
    void allowChat_differentUsers_independentBuckets() {
        for (int i = 0; i < RateLimiter.CHAT_LIMIT; i++) {
            limiter.allowChat(1);
        }
        assertFalse(limiter.allowChat(1));
        assertTrue(limiter.allowChat(2), "不同用户的额度互不影响");
    }
}
