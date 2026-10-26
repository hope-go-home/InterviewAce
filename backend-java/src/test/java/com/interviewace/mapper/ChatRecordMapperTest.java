package com.interviewace.mapper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.sql.Connection;
import java.sql.Statement;
import java.util.List;

import javax.sql.DataSource;

import org.apache.ibatis.datasource.unpooled.UnpooledDataSource;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.interviewace.dto.SessionSummary;

/**
 * /sessions 聚合查询的回归测试（H2 内存库跑真实 SQL）。
 *
 * <p>历史 bug：SessionSummary 是 record，MyBatis 构造器自动映射按【位置】而非列名，
 * SELECT 列顺序与构造参数不一致时 count(LONG) 被塞进 lastTime(LocalDateTime) 直接 500。
 * 这个测试用真实 SQL + 真实映射守住契约。
 */
class ChatRecordMapperTest {

    private SqlSessionFactory factory;

    @BeforeEach
    void setUp() throws Exception {
        // 每个用例独立内存库，避免表重名
        DataSource ds = new UnpooledDataSource("org.h2.Driver",
                "jdbc:h2:mem:chat" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        try (Connection c = ds.getConnection(); Statement st = c.createStatement()) {
            st.execute("""
                    CREATE TABLE chat_records (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      session_id VARCHAR(64),
                      user_id INT,
                      question VARCHAR(1024),
                      answer CLOB,
                      created_at DATETIME
                    )""");
            st.execute("""
                    INSERT INTO chat_records (session_id, user_id, question, answer, created_at) VALUES
                    ('sessA', 1, '第一个问题', '回答1', '2026-10-11 10:00:00'),
                    ('sessA', 1, '第二个问题', '回答2', '2026-10-11 11:00:00'),
                    ('sessB', 1, '另一个会话的问题', '回答3', '2026-10-12 09:00:00'),
                    ('sessC', 2, '别人的问题', '回答4', '2026-10-12 12:00:00')
                    """);
        }
        Configuration cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
        cfg.addMapper(ChatRecordMapper.class);
        factory = new SqlSessionFactoryBuilder().build(cfg);
    }

    @Test
    void listSessions_aggregatesCountFirstQuestionAndLastTime() {
        try (SqlSession session = factory.openSession()) {
            List<SessionSummary> sessions = session.getMapper(ChatRecordMapper.class)
                    .listSessions(1, 50);

            assertEquals(2, sessions.size());
            // 按末次时间倒序：sessB 在前
            SessionSummary b = sessions.get(0);
            assertEquals("sessB", b.sessionId());
            assertEquals("另一个会话的问题", b.firstQuestion());
            assertEquals(1, b.count());
            assertNotNull(b.lastTime());   // 回归点：count(LONG) 不能再错位进 lastTime

            SessionSummary a = sessions.get(1);
            assertEquals("sessA", a.sessionId());
            assertEquals("第一个问题", a.firstQuestion());
            assertEquals(2, a.count());
            assertEquals("2026-10-11 11:00:00",
                    a.lastTime().format(com.interviewace.config.JacksonConfig.DATETIME_PATTERN));
        }
    }

    @Test
    void listSessions_isolatesByUser() {
        try (SqlSession session = factory.openSession()) {
            List<SessionSummary> sessions = session.getMapper(ChatRecordMapper.class)
                    .listSessions(2, 50);

            assertEquals(1, sessions.size());
            assertEquals("sessC", sessions.get(0).sessionId());
        }
    }
}
