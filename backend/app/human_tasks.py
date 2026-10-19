from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .task_schema import upgrade


TaskStatus = Literal[
    "awaiting_approval", "open", "in_progress", "blocked", "done", "rejected", "cancelled"
]
TaskPriority = Literal["low", "normal", "high", "urgent"]


class TaskError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: TaskPriority = "normal"
    owner: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    requires_approval: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title cannot be blank")
        return value.strip()


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    dependencies: list[str] | None = Field(default=None, max_length=100)
    evidence: list[str] | None = Field(default=None, max_length=100)


class TaskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    scope: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=2000)

    @field_validator("scope")
    @classmethod
    def scope_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scope cannot be blank")
        return value.strip()


class TaskStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "in_progress", "blocked", "cancelled"]
    note: str = Field(default="", max_length=2000)


class TaskCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=100)


_OUTGOING_FINANCIAL = re.compile(
    r"\b(pix|transferir|transferencia|transferencias|saque|saques|retirar dinheiro|"
    r"transfer funds|wire transfer|withdrawal|outgoing payment|pagamento de saida|"
    r"pagar boleto|pagar fornecedor|enviar dinheiro|envio de dinheiro|fazer um pix)\b"
)


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def assert_safe_action(*values: str | None, evidence: list[str] | None = None) -> None:
    text = " ".join(v for v in values if v) + " " + " ".join(evidence or [])
    if _OUTGOING_FINANCIAL.search(_normalise(text)):
        raise TaskError(403, "Tarefas de Pix, saques ou pagamentos/transferências de saída são bloqueadas.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class HumanTaskStore:
    """SQLite-backed task ledger with idempotency and append-only audit events."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._session() as connection:
            upgrade(connection)

    def _record_event(self, connection: sqlite3.Connection, task_id: str,
                      actor: str, action: str, detail: dict) -> None:
        connection.execute(
            "INSERT INTO human_task_events(task_id, actor, action, detail_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, actor, action, _json(detail), _now()),
        )

    def _serialize(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        item["dependencies"] = json.loads(item.pop("dependencies_json"))
        item["evidence"] = json.loads(item.pop("evidence_json"))
        item["requires_approval"] = bool(item["requires_approval"])
        return item

    def _validate_dependencies(self, connection: sqlite3.Connection, task_id: str | None,
                               dependencies: list[str]) -> list[str]:
        deps = list(dict.fromkeys(dependencies))
        if len(deps) != len(dependencies):
            raise TaskError(422, "Dependências duplicadas não são permitidas.")
        if task_id and task_id in deps:
            raise TaskError(422, "Uma tarefa não pode depender dela própria.")
        if deps:
            placeholders = ",".join("?" for _ in deps)
            found = {row["id"] for row in connection.execute(
                f"SELECT id FROM human_tasks WHERE id IN ({placeholders})", deps
            ).fetchall()}
            missing = set(deps) - found
            if missing:
                raise TaskError(422, "Uma ou mais dependências não existem.")
        # Reject dependency cycles when editing an existing task.
        if task_id:
            seen: set[str] = set()
            pending = list(deps)
            while pending:
                current = pending.pop()
                if current == task_id:
                    raise TaskError(409, "Dependência circular detectada.")
                if current in seen:
                    continue
                seen.add(current)
                row = connection.execute(
                    "SELECT dependencies_json FROM human_tasks WHERE id = ?", (current,)
                ).fetchone()
                if row:
                    pending.extend(json.loads(row["dependencies_json"]))
        return deps

    def create(self, request: TaskCreate, actor: str) -> dict:
        assert_safe_action(request.title, request.description, request.owner, evidence=request.evidence)
        now = _now()
        with self._session() as connection:
            if request.idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM human_tasks WHERE idempotency_key = ?",
                    (request.idempotency_key,),
                ).fetchone()
                if existing:
                    return self._serialize(existing)
            dependencies = self._validate_dependencies(connection, None, request.dependencies)
            task_id = str(uuid.uuid4())
            status = "awaiting_approval" if request.requires_approval else "open"
            connection.execute(
                """INSERT INTO human_tasks(
                    id,title,description,status,priority,owner,due_at,dependencies_json,
                    evidence_json,idempotency_key,requires_approval,created_by,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id, request.title, request.description, status, request.priority,
                    request.owner, request.due_at.isoformat() if request.due_at else None,
                    _json(dependencies), _json(request.evidence), request.idempotency_key,
                    int(request.requires_approval), actor, now, now,
                ),
            )
            self._record_event(connection, task_id, actor, "created", {
                "status": status, "priority": request.priority,
                "requires_approval": request.requires_approval,
            })
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._serialize(row)

    def list(self, status: str | None = None, owner: str | None = None) -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if owner:
            clauses.append("owner = ?")
            params.append(owner)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM human_tasks" + where +
                " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'normal' THEN 2 ELSE 3 END, "
                "CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, created_at DESC",
                params,
            ).fetchall()
            return [self._serialize(row) for row in rows]

    def get(self, task_id: str) -> dict:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise TaskError(404, "Tarefa não encontrada.")
            return self._serialize(row)

    def update(self, task_id: str, request: TaskUpdate, actor: str) -> dict:
        changes = request.model_dump(exclude_unset=True)
        if not changes:
            return self.get(task_id)
        with self._session() as connection:
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise TaskError(404, "Tarefa não encontrada.")
            if row["status"] in ("done", "rejected", "cancelled"):
                raise TaskError(409, "Tarefas encerradas não podem ser alteradas.")
            title = changes.get("title", row["title"])
            description = changes.get("description", row["description"])
            owner = changes.get("owner", row["owner"])
            evidence = changes.get("evidence", json.loads(row["evidence_json"]))
            assert_safe_action(title, description, owner, evidence=evidence or [])
            if "dependencies" in changes:
                dependencies = self._validate_dependencies(connection, task_id, changes.pop("dependencies") or [])
                changes["dependencies_json"] = _json(dependencies)
            if "evidence" in changes:
                changes["evidence_json"] = _json(changes.pop("evidence") or [])
            if "due_at" in changes:
                changes["due_at"] = changes["due_at"].isoformat() if changes["due_at"] else None
            if "title" in changes:
                if changes["title"] is None:
                    raise TaskError(422, "O título não pode ficar vazio.")
                changes["title"] = changes["title"].strip()
                if not changes["title"]:
                    raise TaskError(422, "O título não pode ficar vazio.")
            if "description" in changes and changes["description"] is None:
                changes["description"] = ""
            if "priority" in changes and changes["priority"] is None:
                changes.pop("priority")
            fields = list(changes)
            values = [changes[field] for field in fields]
            values.extend([_now(), task_id])
            connection.execute(
                f"UPDATE human_tasks SET {', '.join(field + ' = ?' for field in fields)}, updated_at = ? WHERE id = ?",
                values,
            )
            self._record_event(connection, task_id, actor, "updated", {
                "fields": fields,
            })
            updated = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._serialize(updated)

    def set_status(self, task_id: str, status: Literal["open", "in_progress", "blocked", "cancelled"],
                   actor: str, note: str = "") -> dict:
        allowed = {
            "open": {"in_progress", "blocked", "cancelled"},
            "in_progress": {"open", "blocked", "cancelled"},
            "blocked": {"open", "in_progress", "cancelled"},
        }
        with self._session() as connection:
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise TaskError(404, "Tarefa não encontrada.")
            if status not in allowed.get(row["status"], set()):
                raise TaskError(409, f"Transição de {row['status']} para {status} não permitida.")
            connection.execute(
                "UPDATE human_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), task_id),
            )
            self._record_event(connection, task_id, actor, "status_changed", {"status": status, "note": note})
            updated = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._serialize(updated)

    def decide(self, task_id: str, request: TaskDecision, actor: str) -> dict:
        assert_safe_action(request.scope, request.note)
        with self._session() as connection:
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise TaskError(404, "Tarefa não encontrada.")
            if row["status"] != "awaiting_approval":
                raise TaskError(409, "A tarefa não está aguardando aprovação.")
            status = "open" if request.decision == "approve" else "rejected"
            approved_scope = request.scope if request.decision == "approve" else None
            connection.execute(
                "UPDATE human_tasks SET status = ?, approved_scope = ?, updated_at = ? WHERE id = ?",
                (status, approved_scope, _now(), task_id),
            )
            self._record_event(connection, task_id, actor, request.decision, {
                "scope": request.scope, "note": request.note,
                "effect": "approval records this exact scope only; no external action executed",
            })
            updated = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._serialize(updated)

    def complete(self, task_id: str, request: TaskCompletion, actor: str) -> dict:
        current = self.get(task_id)
        assert_safe_action(current["title"], current["description"], request.note, evidence=request.evidence)
        with self._session() as connection:
            row = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise TaskError(404, "Tarefa não encontrada.")
            if row["status"] in ("awaiting_approval", "rejected", "cancelled", "done"):
                raise TaskError(409, "A tarefa não pode ser concluída neste estado.")
            dependencies = json.loads(row["dependencies_json"])
            if dependencies:
                placeholders = ",".join("?" for _ in dependencies)
                unfinished = connection.execute(
                    f"SELECT id FROM human_tasks WHERE id IN ({placeholders}) AND status != 'done'",
                    dependencies,
                ).fetchall()
                if unfinished:
                    raise TaskError(409, "Conclua as dependências antes desta tarefa.")
            now = _now()
            old_evidence = json.loads(row["evidence_json"])
            combined_evidence = list(dict.fromkeys(old_evidence + request.evidence))
            connection.execute(
                "UPDATE human_tasks SET status='done', completion_note=?, evidence_json=?, "
                "completed_at=?, updated_at=? WHERE id=?",
                (request.note, _json(combined_evidence), now, now, task_id),
            )
            self._record_event(connection, task_id, actor, "completed", {
                "note": request.note, "evidence_added": request.evidence,
            })
            updated = connection.execute("SELECT * FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._serialize(updated)

    def history(self, task_id: str) -> list[dict]:
        with self._session() as connection:
            exists = connection.execute("SELECT 1 FROM human_tasks WHERE id = ?", (task_id,)).fetchone()
            if not exists:
                raise TaskError(404, "Tarefa não encontrada.")
            rows = connection.execute(
                "SELECT id, task_id, actor, action, detail_json, created_at "
                "FROM human_task_events WHERE task_id = ? ORDER BY id",
                (task_id,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["detail"] = json.loads(item.pop("detail_json"))
                result.append(item)
            return result
