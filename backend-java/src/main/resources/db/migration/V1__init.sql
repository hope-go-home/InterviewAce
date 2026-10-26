-- ============================================================
-- InterviewAce 初始表结构（V1）
-- 与 Python 侧 SQLAlchemy 模型（interviewace/backend/database/mysql.py）
-- 逐字段对齐：已有 Python 建好的库会被 Flyway baseline 跳过本脚本，
-- 全新环境则由本脚本建表，两边收敛到同一 schema。
-- 时间统一存 UTC（与 Python datetime.utcnow() 行为一致）。
-- ============================================================

-- 用户表：角色绑定在服务端，前端不可伪造
CREATE TABLE IF NOT EXISTS users (
    id            INT           NOT NULL AUTO_INCREMENT,
    username      VARCHAR(64)   NOT NULL,
    password_hash VARCHAR(255)  NOT NULL,
    role          VARCHAR(16)   NOT NULL DEFAULT 'user',   -- admin / user
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    created_at    DATETIME      NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ix_users_username (username)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 审计日志：登录、提问、上传、删除等敏感操作留痕
CREATE TABLE IF NOT EXISTS audit_logs (
    id         INT           NOT NULL AUTO_INCREMENT,
    user_id    INT           NULL,
    username   VARCHAR(64)   NULL,
    action     VARCHAR(32)   NOT NULL,                      -- login / chat / upload / delete
    resource   VARCHAR(255)  NULL,
    detail     TEXT          NULL,
    ip         VARCHAR(64)   NULL,
    created_at DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_audit_logs_user_id (user_id),
    KEY ix_audit_logs_username (username)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 问答会话记录：历史会话按用户隔离
CREATE TABLE IF NOT EXISTS chat_records (
    id         INT           NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(64)   NOT NULL,
    user_id    INT           NULL,
    question   TEXT          NOT NULL,
    answer     TEXT          NOT NULL,
    created_at DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_chat_records_session_id (session_id),
    KEY ix_chat_records_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 答案反馈：点赞/点踩，闭环收集 badcase（与 Python schema 保持一致）
CREATE TABLE IF NOT EXISTS feedback (
    id         INT           NOT NULL AUTO_INCREMENT,
    user_id    INT           NULL,
    session_id VARCHAR(64)   NULL,
    question   TEXT          NULL,
    answer     TEXT          NULL,
    rating     VARCHAR(8)    NOT NULL,                      -- up / down
    comment    TEXT          NULL,
    created_at DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_feedback_user_id (user_id),
    KEY ix_feedback_session_id (session_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 每日 token 用量：成本预算熔断
CREATE TABLE IF NOT EXISTS token_usage (
    id         INT           NOT NULL AUTO_INCREMENT,
    user_id    INT           NULL,
    day        VARCHAR(10)   NOT NULL,                      -- YYYY-MM-DD
    tokens     INT           NOT NULL DEFAULT 0,
    updated_at DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_token_usage_user_id (user_id),
    KEY ix_token_usage_day (day)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 答题练习记录：每次作答的评分与点评
CREATE TABLE IF NOT EXISTS practice_record (
    id             INT           NOT NULL AUTO_INCREMENT,
    user_id        INT           NOT NULL,
    question_title VARCHAR(512)  NOT NULL,                  -- 题干（题没有自增 id，用 title 标识）
    question_url   VARCHAR(512)  NULL,
    domain         VARCHAR(64)   NULL,
    difficulty     INT           NULL,
    position       VARCHAR(64)   NULL,
    level          VARCHAR(16)   NULL,                      -- intern / campus / social
    my_answer      TEXT          NULL,
    score          INT           NULL,                      -- 0-100
    dim_json       TEXT          NULL,                      -- 各维度得分 JSON
    feedback       TEXT          NULL,
    missing_points TEXT          NULL,                      -- JSON list
    is_wrong       TINYINT(1)    NOT NULL DEFAULT 0,        -- score<60 进错题本
    created_at     DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_practice_record_user_id (user_id),
    KEY ix_practice_record_domain (domain),
    KEY ix_practice_record_created_at (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 收藏 / 错题标记
CREATE TABLE IF NOT EXISTS favorite (
    id             INT           NOT NULL AUTO_INCREMENT,
    user_id        INT           NOT NULL,
    question_title VARCHAR(512)  NOT NULL,
    question_url   VARCHAR(512)  NULL,
    domain         VARCHAR(64)   NULL,
    difficulty     INT           NULL,
    ftype          VARCHAR(8)    NOT NULL DEFAULT 'fav',    -- fav / wrong
    created_at     DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_favorite_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 待补题池：题库外被问到的问题，待生成答案入库
CREATE TABLE IF NOT EXISTS pending_question (
    id           INT           NOT NULL AUTO_INCREMENT,
    question     VARCHAR(512)  NOT NULL,
    domain       VARCHAR(64)   NULL,
    position     VARCHAR(64)   NULL,
    ask_count    INT           NOT NULL DEFAULT 1,
    draft_answer TEXT          NULL,
    source_url   VARCHAR(512)  NULL,
    status       VARCHAR(16)   NOT NULL DEFAULT 'pending',  -- pending / drafted / adopted
    created_at   DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_pending_question_question (question)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 模拟面试：一场面试的配置与状态
CREATE TABLE IF NOT EXISTS interview_session (
    id             INT           NOT NULL AUTO_INCREMENT,
    user_id        INT           NOT NULL,
    position       VARCHAR(64)   NULL,
    level          VARCHAR(16)   NULL,
    domains        TEXT          NULL,                      -- JSON 选中的知识域列表
    num_questions  INT           NOT NULL DEFAULT 10,
    difficulty_cap INT           NOT NULL DEFAULT 3,
    status         VARCHAR(16)   NOT NULL DEFAULT 'in_progress',  -- in_progress / finished
    current_seq    INT           NOT NULL DEFAULT 1,
    total_score    INT           NULL,
    report_json    TEXT          NULL,                      -- 总评报告 JSON
    created_at     DATETIME      NULL,
    finished_at    DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_interview_session_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 模拟面试：一轮问答（含追问，parent_turn_id 挂到主问题）
CREATE TABLE IF NOT EXISTS interview_turn (
    id              INT           NOT NULL AUTO_INCREMENT,
    session_id      INT           NOT NULL,
    seq             INT           NOT NULL,                 -- 主问题序号
    parent_turn_id  INT           NULL,                     -- 追问链：指向主问题 turn id
    followup_no     INT           NOT NULL DEFAULT 0,       -- 0=主问题，1/2=第几层追问
    question        TEXT          NOT NULL,
    question_source VARCHAR(16)   NOT NULL DEFAULT 'rag',   -- rag / resume / llm
    qa_refs         TEXT          NULL,                     -- JSON：检索到的参考题
    answer          TEXT          NULL,
    score           INT           NULL,                     -- 0-100
    dim_json        TEXT          NULL,                     -- 四维得分 JSON
    feedback        TEXT          NULL,
    missing_points  TEXT          NULL,                     -- JSON list
    created_at      DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_interview_turn_session_id (session_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 简历备考历史：上传的简历及生成的备考内容
CREATE TABLE IF NOT EXISTS resume (
    id             INT           NOT NULL AUTO_INCREMENT,
    user_id        INT           NOT NULL,
    filename       VARCHAR(255)  NOT NULL,
    target         VARCHAR(128)  NULL,                      -- 目标岗位
    name           VARCHAR(64)   NULL,                      -- 姓名
    profile_json   TEXT          NULL,                      -- 结构化简历
    questions_json TEXT          NULL,                      -- 生成的面试题
    pitch_json     TEXT          NULL,                      -- 自我介绍话术
    rehearse_json  TEXT          NULL,                      -- 项目预演
    created_at     DATETIME      NULL,
    updated_at     DATETIME      NULL,
    PRIMARY KEY (id),
    KEY ix_resume_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
