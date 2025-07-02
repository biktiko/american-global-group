# SQL queries used in the bot

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id      BIGINT      PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    last_name    TEXT,
    phone_number VARCHAR(20),
    language     VARCHAR(2)  NOT NULL DEFAULT 'hy',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS logs (
    log_id     BIGSERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    details    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_BROADCASTS_TABLE = """
CREATE TABLE IF NOT EXISTS broadcasts (
    broadcast_id BIGSERIAL PRIMARY KEY,
    admin_id     BIGINT NOT NULL,
    message_hy   TEXT,
    message_en   TEXT,
    recipients   BIGINT[],
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_ADMINS_TABLE = """
CREATE TABLE IF NOT EXISTS admins (
    admin_id BIGINT PRIMARY KEY
);
"""

INSERT_USER = """
INSERT INTO users (
    user_id, username, first_name, last_name, phone_number, language, last_seen_at
) VALUES (
    %s, %s, %s, %s, %s, COALESCE(%s, 'hy'), NOW()
)
ON CONFLICT (user_id) DO UPDATE SET
    username     = EXCLUDED.username,
    first_name   = EXCLUDED.first_name,
    last_name    = EXCLUDED.last_name,
    phone_number = COALESCE(EXCLUDED.phone_number, users.phone_number),
    language     = COALESCE(EXCLUDED.language, users.language),
    last_seen_at = NOW();
"""

INSERT_LOG = "INSERT INTO logs (user_id, action, details) VALUES (%s, %s, %s)"

INSERT_BROADCAST = """
INSERT INTO broadcasts (admin_id, message_hy, message_en, recipients)
VALUES (%s, %s, %s, %s)
"""