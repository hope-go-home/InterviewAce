package com.interviewace.security;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 密码哈希：BCrypt。
 *
 * <p>与 Python passlib[bcrypt] 产生的 $2b$ 哈希完全互通——
 * 数据库里已有的用户密码无需任何迁移即可在校验通过。
 */
@Component
public class PasswordService {

    /** passlib 默认 rounds=12，保持同一强度 */
    private final PasswordEncoder encoder = new BCryptPasswordEncoder(12);

    public String hash(String rawPassword) {
        return encoder.encode(rawPassword);
    }

    public boolean matches(String rawPassword, String passwordHash) {
        if (rawPassword == null || passwordHash == null || passwordHash.isBlank()) {
            return false;
        }
        try {
            return encoder.matches(rawPassword, passwordHash);
        } catch (Exception e) {
            return false;
        }
    }
}
