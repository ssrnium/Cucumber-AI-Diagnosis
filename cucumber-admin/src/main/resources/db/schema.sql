-- =============================================================
-- 黄瓜叶片病害智能识别与可信辅助诊断平台 - 数据库初始化脚本
-- PostgreSQL 16（兼容 pgvector/pgvector:pg16 镜像）
-- =============================================================

-- ---------- 系统模块 ----------
CREATE TABLE IF NOT EXISTS sys_user (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    password    VARCHAR(128) NOT NULL,
    nickname    VARCHAR(64),
    avatar      VARCHAR(255),
    email       VARCHAR(128),
    phone       VARCHAR(32),
    status      INT          NOT NULL DEFAULT 1,   -- 1 启用 0 禁用
    create_time TIMESTAMP    NOT NULL DEFAULT now(),
    update_time TIMESTAMP    NOT NULL DEFAULT now()
);
COMMENT ON TABLE sys_user IS '系统用户表';

CREATE TABLE IF NOT EXISTS sys_role (
    id          BIGSERIAL PRIMARY KEY,
    code        VARCHAR(64) NOT NULL UNIQUE,       -- ADMIN / EXPERT / USER
    name        VARCHAR(64) NOT NULL,
    remark      VARCHAR(255),
    create_time TIMESTAMP   NOT NULL DEFAULT now()
);
COMMENT ON TABLE sys_role IS '系统角色表';

CREATE TABLE IF NOT EXISTS sys_user_role (
    id      BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES sys_role(id) ON DELETE CASCADE,
    UNIQUE (user_id, role_id)
);
COMMENT ON TABLE sys_user_role IS '用户-角色关联表';

CREATE TABLE IF NOT EXISTS sys_role_perm (
    id      BIGSERIAL PRIMARY KEY,
    role_id BIGINT       NOT NULL REFERENCES sys_role(id) ON DELETE CASCADE,
    perm    VARCHAR(128) NOT NULL,
    UNIQUE (role_id, perm)
);
COMMENT ON TABLE sys_role_perm IS '角色-权限关联表';

CREATE TABLE IF NOT EXISTS sys_operation_log (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(64),
    operation   VARCHAR(128),
    method      VARCHAR(255),
    uri         VARCHAR(255),
    ip          VARCHAR(64),
    cost_ms     BIGINT,
    result      VARCHAR(16),
    create_time TIMESTAMP NOT NULL DEFAULT now()
);
COMMENT ON TABLE sys_operation_log IS '操作日志表';
CREATE INDEX IF NOT EXISTS idx_operation_log_create_time ON sys_operation_log (create_time);

-- ---------- 诊断模块 ----------
CREATE TABLE IF NOT EXISTS diagnosis_record (
    id            BIGSERIAL PRIMARY KEY,
    record_no     VARCHAR(64) NOT NULL UNIQUE,
    user_id       BIGINT      NOT NULL REFERENCES sys_user(id),
    image_url     VARCHAR(255) NOT NULL,
    detections    JSONB,                          -- 病斑框列表 [{x1,y1,x2,y2,confidence,label}]
    report        JSONB,                          -- 诊断报告 JSON
    model_version VARCHAR(64),
    status        VARCHAR(16) NOT NULL DEFAULT 'PENDING',  -- PENDING / DONE / FAILED
    create_time   TIMESTAMP   NOT NULL DEFAULT now()
);
COMMENT ON TABLE diagnosis_record IS '诊断记录表';
CREATE INDEX IF NOT EXISTS idx_diagnosis_record_user_id ON diagnosis_record (user_id);
CREATE INDEX IF NOT EXISTS idx_diagnosis_record_create_time ON diagnosis_record (create_time);
CREATE INDEX IF NOT EXISTS idx_diagnosis_record_status ON diagnosis_record (status);

CREATE TABLE IF NOT EXISTS diagnosis_feedback (
    id                     BIGSERIAL PRIMARY KEY,
    record_id              BIGINT NOT NULL REFERENCES diagnosis_record(id) ON DELETE CASCADE,
    user_id                BIGINT NOT NULL REFERENCES sys_user(id),
    verdict                VARCHAR(16) NOT NULL,            -- CORRECT / WRONG
    corrected_disease_type VARCHAR(64),
    comment                TEXT,
    review_status          VARCHAR(16) NOT NULL DEFAULT 'PENDING',  -- PENDING / REVIEWED
    reviewer_id            BIGINT REFERENCES sys_user(id),
    create_time            TIMESTAMP NOT NULL DEFAULT now(),
    update_time            TIMESTAMP NOT NULL DEFAULT now()
);
COMMENT ON TABLE diagnosis_feedback IS '诊断反馈（用户纠错 / 专家复核）表';
CREATE INDEX IF NOT EXISTS idx_feedback_record_id ON diagnosis_feedback (record_id);
CREATE INDEX IF NOT EXISTS idx_feedback_review_status ON diagnosis_feedback (review_status);

-- ---------- 知识库模块 ----------
CREATE TABLE IF NOT EXISTS knowledge_entry (
    id           BIGSERIAL PRIMARY KEY,
    source_id    VARCHAR(32) NOT NULL UNIQUE,     -- 格式 KB-XXX-NNN
    disease_type VARCHAR(64) NOT NULL,
    title        VARCHAR(128) NOT NULL,
    content      TEXT NOT NULL,
    level        VARCHAR(4)  NOT NULL DEFAULT 'B',  -- A/B/C 证据等级
    category     VARCHAR(16) NOT NULL DEFAULT '症状', -- 症状/防治/药剂
    status       INT NOT NULL DEFAULT 1,
    create_time  TIMESTAMP NOT NULL DEFAULT now()
);
COMMENT ON TABLE knowledge_entry IS '农技知识库条目表';
CREATE INDEX IF NOT EXISTS idx_knowledge_disease_type ON knowledge_entry (disease_type);

-- ---------- 模型版本模块 ----------
CREATE TABLE IF NOT EXISTS model_version (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(64) NOT NULL,
    version      VARCHAR(32) NOT NULL,
    model_type   VARCHAR(16) NOT NULL,            -- DETECTION / LLM
    weights_path VARCHAR(255),
    sha256       VARCHAR(64),
    metrics      JSONB,
    status       VARCHAR(16) NOT NULL DEFAULT 'ARCHIVED',  -- ACTIVE / ARCHIVED
    create_time  TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);
COMMENT ON TABLE model_version IS '模型版本登记表';
CREATE INDEX IF NOT EXISTS idx_model_version_type_status ON model_version (model_type, status);

-- ---------- 智能体模块（cucumber-agent 对话审计） ----------
CREATE TABLE IF NOT EXISTS agent_session (
    id           BIGSERIAL PRIMARY KEY,
    conv_id      VARCHAR(64) NOT NULL,
    user_id      BIGINT      NOT NULL REFERENCES sys_user(id),
    primary_agent VARCHAR(32),
    last_intent  VARCHAR(32),
    escalated    BOOLEAN     NOT NULL DEFAULT FALSE,
    create_time  TIMESTAMP   NOT NULL DEFAULT now(),
    update_time  TIMESTAMP   NOT NULL DEFAULT now(),
    UNIQUE (user_id, conv_id)
);
COMMENT ON TABLE agent_session IS '智能体会话审计表';
CREATE INDEX IF NOT EXISTS idx_agent_session_user_id ON agent_session (user_id);

CREATE TABLE IF NOT EXISTS agent_message (
    id           BIGSERIAL PRIMARY KEY,
    session_id   BIGINT      NOT NULL REFERENCES agent_session(id) ON DELETE CASCADE,
    request_id   VARCHAR(32),
    role         VARCHAR(16) NOT NULL,              -- USER / ASSISTANT
    content      TEXT        NOT NULL,
    intent       VARCHAR(32),
    agent_type   VARCHAR(32),
    tools_used   JSONB,                             -- 本轮工具调用名列表
    latency_ms   DOUBLE PRECISION,
    create_time  TIMESTAMP   NOT NULL DEFAULT now()
);
COMMENT ON TABLE agent_message IS '智能体消息审计表';
CREATE INDEX IF NOT EXISTS idx_agent_message_session_id ON agent_message (session_id);
CREATE INDEX IF NOT EXISTS idx_agent_message_create_time ON agent_message (create_time);
