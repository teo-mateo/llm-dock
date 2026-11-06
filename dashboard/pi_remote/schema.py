SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pi_sessions (
    session_id          TEXT NOT NULL,
    instance_id         TEXT NOT NULL,
    session_file        TEXT,
    cwd                 TEXT NOT NULL,
    name                TEXT,
    pid                 INTEGER NOT NULL,
    model_provider      TEXT,
    model_id            TEXT,
    thinking_level      TEXT,
    reason              TEXT NOT NULL,
    previous_session_id TEXT,
    pi_version          TEXT,
    ext_version         TEXT NOT NULL,
    first_seen          INTEGER NOT NULL,
    last_seen           INTEGER NOT NULL,
    ended_at            INTEGER,
    end_reason          TEXT,
    acked_seq           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, instance_id)
);

CREATE INDEX IF NOT EXISTS idx_pi_sessions_last_seen ON pi_sessions(last_seen);

CREATE TABLE IF NOT EXISTS pi_events (
    session_id   TEXT NOT NULL,
    instance_id  TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    type         TEXT NOT NULL,
    ts           INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    gap_from     INTEGER,
    gap_to       INTEGER,
    received_at  INTEGER NOT NULL,
    PRIMARY KEY (session_id, instance_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_pi_events_session_seq
    ON pi_events(session_id, instance_id, seq);

CREATE TABLE IF NOT EXISTS pi_commands (
    command_id   TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    instance_id  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    args_digest  TEXT NOT NULL,
    issued_at    INTEGER NOT NULL,
    completed_at INTEGER,
    ok           INTEGER,
    error        TEXT,
    outcome      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pi_commands_session
    ON pi_commands(session_id, instance_id, issued_at);

CREATE TABLE IF NOT EXISTS pi_prompts (
    session_id      TEXT NOT NULL,
    instance_id     TEXT NOT NULL,
    prompt_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    title           TEXT,
    message         TEXT,
    options_json    TEXT NOT NULL DEFAULT '[]',
    allow_free_text INTEGER NOT NULL DEFAULT 0,
    timeout_ms      INTEGER,
    status          TEXT NOT NULL,
    value_json      TEXT,
    answered_by     TEXT,
    opened_seq      INTEGER NOT NULL,
    opened_ts       INTEGER NOT NULL,
    closed_seq      INTEGER,
    closed_ts       INTEGER,
    PRIMARY KEY (session_id, instance_id, prompt_id)
);

CREATE INDEX IF NOT EXISTS idx_pi_prompts_session_status
    ON pi_prompts(session_id, instance_id, status);
"""

UPSERT_PROMPT_SQL = """
INSERT INTO pi_prompts (
    session_id, instance_id, prompt_id, kind, title, message,
    options_json, allow_free_text, timeout_ms, status,
    opened_seq, opened_ts
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
ON CONFLICT(session_id, instance_id, prompt_id) DO UPDATE SET
    kind = excluded.kind,
    title = excluded.title,
    message = excluded.message,
    options_json = excluded.options_json,
    allow_free_text = excluded.allow_free_text,
    timeout_ms = excluded.timeout_ms,
    status = 'open',
    value_json = NULL,
    answered_by = NULL,
    opened_seq = excluded.opened_seq,
    opened_ts = excluded.opened_ts,
    closed_seq = NULL,
    closed_ts = NULL
"""

CLOSE_PROMPT_SQL = """
UPDATE pi_prompts SET status = ?, value_json = ?, answered_by = ?, closed_seq = ?, closed_ts = ?
 WHERE session_id = ? AND instance_id = ? AND prompt_id = ?
"""


UPSERT_SQL = """
INSERT INTO pi_sessions (
    session_id, instance_id, session_file, cwd, name, pid,
    model_provider, model_id, thinking_level, reason,
    previous_session_id, pi_version, ext_version,
    first_seen, last_seen, ended_at, end_reason, acked_seq
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)
ON CONFLICT(session_id, instance_id) DO UPDATE SET
    session_file = excluded.session_file,
    cwd = excluded.cwd,
    name = excluded.name,
    pid = excluded.pid,
    model_provider = excluded.model_provider,
    model_id = excluded.model_id,
    thinking_level = excluded.thinking_level,
    reason = excluded.reason,
    previous_session_id = excluded.previous_session_id,
    pi_version = excluded.pi_version,
    ext_version = excluded.ext_version,
    last_seen = excluded.last_seen,
    ended_at = NULL,
    end_reason = NULL
"""

INSERT_EVENT_SQL = """
INSERT OR IGNORE INTO pi_events (
    session_id, instance_id, seq, type, ts, payload_json, gap_from, gap_to, received_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
