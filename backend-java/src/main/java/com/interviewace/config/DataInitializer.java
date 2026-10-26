package com.interviewace.config;

import org.mybatis.spring.annotation.MapperScan;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.interviewace.entity.User;
import com.interviewace.mapper.UserMapper;
import com.interviewace.security.PasswordService;

/**
 * 启动种子数据：系统无任何用户时创建默认管理员。
 * 对应 Python mysql.py seed_default_admin()，失败只警告不阻断启动。
 */
@Component
@Order(0)
public class DataInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DataInitializer.class);

    private final UserMapper userMapper;
    private final PasswordService passwordService;
    private final AppProperties props;

    public DataInitializer(UserMapper userMapper, PasswordService passwordService, AppProperties props) {
        this.userMapper = userMapper;
        this.passwordService = passwordService;
        this.props = props;
    }

    @Override
    public void run(ApplicationArguments args) {
        try {
            Long count = userMapper.selectCount(null);
            if (count != null && count > 0) {
                return;
            }
            User admin = new User();
            admin.setUsername(props.getDefaultAdmin().getUsername());
            admin.setPasswordHash(passwordService.hash(props.getDefaultAdmin().getPassword()));
            admin.setRole("admin");
            admin.setActive(true);
            admin.setCreatedAt(java.time.LocalDateTime.now(java.time.ZoneOffset.UTC));
            userMapper.insert(admin);
            log.info("已创建默认管理员用户={}", admin.getUsername());
        } catch (Exception e) {
            log.warn("种子管理员创建失败: {}", e.getMessage());
        }
    }
}
