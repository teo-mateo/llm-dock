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
