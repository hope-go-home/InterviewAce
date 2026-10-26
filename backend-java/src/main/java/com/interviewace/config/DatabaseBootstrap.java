package com.interviewace.config;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

/**
 * 数据库就绪引导：在 DataSource/Flyway 初始化之前，
 * 以超级管理员连接自动执行 CREATE DATABASE IF NOT EXISTS。
 *
 * <p>对应 Python 侧 mysql.py _ensure_database()——共享 MySQL 实例
 * （rag-mysql 容器首启只建了 resume_rag_db），interviewace_db 按需创建。
 * 必须用 BeanFactoryPostProcessor 在所有 Bean 实例化前执行，
 * 否则 Flyway 会先于建库动作连接失败。
 */
@Configuration()
public class DatabaseBootstrap {

    private static final Logger log = LoggerFactory.getLogger(DatabaseBootstrap.class);

    @Bean
    public static BeanFactoryPostProcessor ensureDatabaseExists() {
        // 静态方法 + 匿名类：拿到 Environment 时任何业务 Bean 都尚未实例化
        return new BeanFactoryPostProcessor() {
            @Override
            public void postProcessBeanFactory(org.springframework.beans.factory.config.ConfigurableListableBeanFactory beanFactory) {
                Environment env = beanFactory.getBean(Environment.class);
                String host = env.getProperty("MYSQL_HOST", "127.0.0.1");
                String port = env.getProperty("MYSQL_PORT", "3306");
                String user = env.getProperty("MYSQL_USER", "root");
                String password = env.getProperty("MYSQL_PASSWORD", "123456");
                String database = env.getProperty("MYSQL_DATABASE", "interviewace_db");

                String url = "jdbc:mysql://" + host + ":" + port
                        + "/?useSSL=false&serverTimezone=Asia/Shanghai&characterEncoding=utf-8"
                        + "&connectTimeout=5000";
                try (Connection conn = DriverManager.getConnection(url, user, password);
                     Statement stmt = conn.createStatement()) {
                    stmt.execute("CREATE DATABASE IF NOT EXISTS `" + database + "` "
                            + "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
                    log.info("数据库 {} 就绪", database);
                } catch (SQLException e) {
                    // 与 Python 降级策略一致：只警告，交给后续 Flyway/连接池暴露真实错误
                    log.warn("自动建库失败（后续连接将直接使用目标库）: {}", e.getMessage());
                }
            }
        };
    }
}
