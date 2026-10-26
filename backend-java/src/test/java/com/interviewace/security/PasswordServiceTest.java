package com.interviewace.security;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class PasswordServiceTest {

    /** 数据库里 admin 的真实哈希，由 Python passlib[bcrypt] 生成（密码 admin123） */
    private static final String PASSLIB_ADMIN123 =
            "$2b$12$PFejdRLgbg13p9ciSz91r.JwgCRp8qog7OI/CAzZBKb1rW.gtaRnK";

    private final PasswordService service = new PasswordService();

    @Test
    void hash_thenMatches() {
        String hash = service.hash("my-secret-pw");
        assertTrue(hash.startsWith("$2"));
        assertTrue(service.matches("my-secret-pw", hash));
    }

    @Test
    void matches_pythonPasslibHash_interoperable() {
        // 与 Python passlib 产生的 $2b$ 哈希互通：老库用户密码免迁移
        assertTrue(service.matches("admin123", PASSLIB_ADMIN123));
        assertFalse(service.matches("admin124", PASSLIB_ADMIN123));
    }

    @Test
    void matches_nullOrBlank_neverPasses() {
        assertFalse(service.matches(null, PASSLIB_ADMIN123));
        assertFalse(service.matches("admin123", null));
        assertFalse(service.matches("admin123", ""));
        assertFalse(service.matches("admin123", "not-a-bcrypt-hash"));
    }
}
