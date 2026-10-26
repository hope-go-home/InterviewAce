package com.interviewace.service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.common.BizException;
import com.interviewace.common.UserContext;
import com.interviewace.common.audit.AuditService;
import com.interviewace.common.ratelimit.RateLimiter;
import com.interviewace.config.AppProperties;
import com.interviewace.dto.LoginRequest;
import com.interviewace.entity.User;
import com.interviewace.mapper.UserMapper;
import com.interviewace.security.JwtUtil;
import com.interviewace.security.PasswordService;

/**
 * 认证服务：登录 / 注册 / 当前用户。
 * 对应 main.py /auth/* 端点 + auth.py 密码与 token 逻辑。
 */
@Service
public class AuthService {

    private final UserMapper userMapper;
    private final PasswordService passwordService;
    private final JwtUtil jwtUtil;
    private final RateLimiter rateLimiter;
    private final AuditService auditService;
    private final AppProperties props;

    public AuthService(UserMapper userMapper, PasswordService passwordService, JwtUtil jwtUtil,
                       RateLimiter rateLimiter, AuditService auditService, AppProperties props) {
        this.userMapper = userMapper;
        this.passwordService = passwordService;
        this.jwtUtil = jwtUtil;
        this.rateLimiter = rateLimiter;
        this.auditService = auditService;
        this.props = props;
    }

    /** 登录：限流 → 校验 → 签发 JWT → 审计留痕 */
    public Map<String, Object> login(LoginRequest req, String ip) {
        if (!rateLimiter.allowLogin(ip)) {
            throw BizException.tooMany("尝试过于频繁，请稍后再试");
        }

        User user = findByUsername(req.username());
        if (user == null || !passwordService.matches(req.password(), user.getPasswordHash())) {
            auditService.write(null, req.username(), "login", "", "failed", ip);
            throw BizException.unauthorized("用户名或密码错误");
        }
        if (!Boolean.TRUE.equals(user.getActive())) {
            throw BizException.forbidden("账号已禁用");
        }

        String token = jwtUtil.createAccessToken(
                new UserContext(user.getId(), user.getUsername(), user.getRole()));
        auditService.write(user.getId(), user.getUsername(), "login", "", "success", ip);
        return Map.of(
                "token", token,
                "username", user.getUsername(),
                "role", user.getRole());
    }

    /** 注册：开关控制 → 限流 → 唯一性 → 建号 → 审计留痕 */
    public Map<String, Object> register(LoginRequest req, String ip) {
        if (!props.isAllowRegistration()) {
            throw BizException.forbidden("未开放注册，请联系管理员创建账号");
        }
        if (!rateLimiter.allowLogin(ip)) {
            throw BizException.tooMany("尝试过于频繁，请稍后再试");
        }
        if (findByUsername(req.username()) != null) {
            throw BizException.conflict("用户名已存在");
        }

        User user = new User();
        user.setUsername(req.username());
        user.setPasswordHash(passwordService.hash(req.password()));
        user.setRole("user");
        user.setActive(true);
        user.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        userMapper.insert(user);

        auditService.write(user.getId(), user.getUsername(), "register", "", "", ip);
        return Map.of("id", user.getId(), "username", user.getUsername());
    }

    /** 当前登录用户（token payload 即时返回，无 DB 查询——与 FastAPI Depends 行为一致） */
    public Map<String, Object> me(UserContext user) {
        return Map.of(
                "id", user.id(),
                "username", user.username(),
                "role", user.role());
    }

    private User findByUsername(String username) {
        return userMapper.selectOne(new LambdaQueryWrapper<User>()
                .eq(User::getUsername, username)
                .last("LIMIT 1"));
    }
}
