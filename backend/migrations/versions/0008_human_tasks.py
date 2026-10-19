"""Version 0008: human tasks and audit history.

This project uses SQLite for the task subsystem so local development requires no
external database. The runtime applies this migration idempotently at startup.
"""
from app.task_schema import downgrade, upgrade

revision = "0008_human_tasks"
down_revision = None


def upgrade_migration(connection):
    upgrade(connection)


def downgrade_migration(connection):
    downgrade(connection)
