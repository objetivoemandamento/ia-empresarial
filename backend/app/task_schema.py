from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


VERSION = "0008_human_tasks"


def upgrade(connection: sqlite3.Connection) -> None:
    """Apply the idempotent SQLite migration for human tasks and audit events."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS human_tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN (
                'awaiting_approval', 'open', 'in_progress', 'blocked',
                'done', 'rejected', 'cancelled'
            )),
            priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
            owner TEXT,
            due_at TEXT,
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            idempotency_key TEXT UNIQUE,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            approved_scope TEXT,
            completion_note TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_human_tasks_status ON human_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_human_tasks_owner ON human_tasks(owner);
        CREATE INDEX IF NOT EXISTS idx_human_tasks_due_at ON human_tasks(due_at);
        CREATE TABLE IF NOT EXISTS human_task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES human_tasks(id) ON DELETE CASCADE,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_human_task_events_task_time
            ON human_task_events(task_id, created_at);
    """)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (VERSION, datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()


def downgrade(connection: sqlite3.Connection) -> None:
    """Remove only the human-task schema; callers must back up data first."""
    connection.executescript("""
        DROP TABLE IF EXISTS human_task_events;
        DROP TABLE IF EXISTS human_tasks;
    """)
    connection.execute("DELETE FROM schema_migrations WHERE version = ?", (VERSION,))
    connection.commit()
