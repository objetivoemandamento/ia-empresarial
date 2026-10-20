"""Persisted CEO -> specialist tasks -> review -> delivery orchestration.

The orchestrator generates and reviews text. It does not execute shell, browser,
publishing, or other external actions. Sensitive work requires approval; financial
transfers/payments are always blocked.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Awaitable, Callable

MAX_TASKS = 15
MAX_WORKERS = 4
MAX_ATTEMPTS = 2
BLOCKED = re.compile(
    r"\b(pix|transferir|transferência|transferencia|pagar|pagamento|sacar|saque|"
    r"enviar dinheiro|wire transfer|send money|withdraw|bank details)\b", re.I
)
APPROVAL = re.compile(
    r"\b(publish|publicar|deploy|delete|apagar|excluir|send email|enviar e-?mail|"
    r"run code|executar código|executar codigo)\b", re.I
)
ACTIONS = {"external_network", "send_message", "publish", "delete_data", "code_execution", "other"}
CEO_PLAN = (
    "ROLE:CEO_PLAN. Divida o objetivo em 1 a 15 tarefas independentes, verificáveis e seguras. "
    "Não afirme ações externas. Nunca planeje transferências, pagamentos ou saques. "
    'Responda apenas JSON: {"tasks":[{"title":"...","instructions":"...","sensitive_action":null}]}. '
    "sensitive_action deve ser null ou external_network, send_message, publish, delete_data, code_execution, other."
)
EXECUTOR = "ROLE:EXECUTOR. Especialidade: {specialty}. Produza apenas o resultado textual. Não afirme ter executado ferramentas externas."
REVIEWER = 'ROLE:REVIEWER. Revise precisão, completude e afirmações de execução. Responda JSON: {"approved":true|false,"notes":"..."}'
DELIVERY = "ROLE:CEO_DELIVERY. Consolide os resultados aprovados com clareza. Não invente fatos nem ações executadas."
SPECIALISTS = {
    "Engenharia": ("código", "codigo", "bug", "api", "python", "deploy"),
    "Pesquisa": ("pesquisa", "fontes", "mercado", "evidência", "evidencia"),
    "Marketing": ("marketing", "campanha", "divulgação", "divulgacao", "vendas"),
    "Segurança": ("segurança", "seguranca", "permissão", "permissao", "risco"),
    "Qualidade": ("teste", "testes", "validar", "homologação", "homologacao"),
    "Estratégia": ("estratégia", "estrategia", "plano", "prioridade", "objetivo"),
}

def _json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Resposta sem JSON válido")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Resposta JSON deve ser objeto")
    return value

def _specialty(text: str) -> str:
    value = text.casefold()
    return next((name for name, terms in SPECIALISTS.items() if any(t in value for t in terms)), "Análise geral")

class AgentRunError(RuntimeError):
    pass

class AgentOrchestrator:
    def __init__(self, db_path: str | Path, llm_call: Callable[[str, str], Awaitable[str]], policies: Callable[[], dict]):
        self.llm_call, self.policies = llm_call, policies
        self._lock = threading.RLock()
        self._active: set[int] = set()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS agent_runs(id INTEGER PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL, result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_tasks(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, idx INTEGER NOT NULL, title TEXT NOT NULL, instructions TEXT NOT NULL, action TEXT, status TEXT NOT NULL, output TEXT, review TEXT, attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
        CREATE TABLE IF NOT EXISTS agent_approvals(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, task_id INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, decided REAL);
        CREATE TABLE IF NOT EXISTS agent_events(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
        """)
        self.db.commit()

    def _q(self, sql: str, args: tuple = ()):
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _one(self, sql: str, args: tuple = ()):
        with self._lock:
            return self.db.execute(sql, args).fetchone()

    def _all(self, sql: str, args: tuple = ()):
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    def _event(self, run_id: int, kind: str, detail: str = ""):
        self._q("INSERT INTO agent_events(run_id,ts,kind,detail) VALUES(?,?,?,?)", (run_id, time.time(), kind, detail[:500]))

    def _status(self, run_id: int, status: str, error=None, result=None):
        self._q("UPDATE agent_runs SET status=?,error=?,result=?,updated=? WHERE id=?",
                (status, error, result, time.time(), run_id))
        self._event(run_id, "run." + status, error or "")

    def create(self, goal: str) -> dict:
        goal = (goal or "").strip()
        if not goal or len(goal) > 4000:
            raise AgentRunError("O objetivo deve ter de 1 a 4000 caracteres")
        if BLOCKED.search(goal):
            raise AgentRunError("Objetivo bloqueado por política financeira")
        now = time.time()
        cur = self._q("INSERT INTO agent_runs(goal,status,created,updated) VALUES(?,?,?,?)", (goal, "queued", now, now))
        self._event(cur.lastrowid, "run.queued")
        return self.get(cur.lastrowid)

    def get(self, run_id: int) -> dict:
        row = self._one("SELECT * FROM agent_runs WHERE id=?", (run_id,))
        if not row:
            raise KeyError(run_id)
        return {**dict(row),
                "tasks": [dict(r) for r in self._all("SELECT * FROM agent_tasks WHERE run_id=? ORDER BY idx", (run_id,))],
                "approvals": [dict(r) for r in self._all("SELECT * FROM agent_approvals WHERE run_id=? ORDER BY id", (run_id,))],
                "events": [dict(r) for r in self._all("SELECT * FROM agent_events WHERE run_id=? ORDER BY id", (run_id,))]}

    def list(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._all("SELECT id,goal,status,error,created,updated FROM agent_runs ORDER BY id DESC LIMIT ?", (max(1,min(limit,100)),))]

    def decide(self, approval_id: int, approve: bool) -> dict:
        item = self._one("SELECT * FROM agent_approvals WHERE id=?", (approval_id,))
        if not item:
            raise KeyError(approval_id)
        if item["status"] != "pending":
            raise AgentRunError("A aprovação já foi decidida")
        status = "approved" if approve else "rejected"
        self._q("UPDATE agent_approvals SET status=?,decided=? WHERE id=?", (status,time.time(),approval_id))
        self._q("UPDATE agent_tasks SET status=? WHERE id=?", ("pending" if approve else "rejected", item["task_id"]))
        self._event(item["run_id"], "approval." + status, item["action"])
        self._status(item["run_id"], "queued")
        return self.get(item["run_id"])

    def retry(self, run_id: int) -> dict:
        run = self.get(run_id)
        if run["status"] not in {"failed", "interrupted"}:
            raise AgentRunError("Só execuções com falha/interrupção podem ser repetidas")
        self._q("UPDATE agent_tasks SET status='pending',attempts=0,error=NULL WHERE run_id=? AND status='failed'", (run_id,))
        self._status(run_id, "queued")
        return self.get(run_id)

    async def _call(self, system: str, user: str) -> str:
        answer = await self.llm_call(system, user)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Resposta vazia do modelo")
        return answer.strip()

    async def process(self, run_id: int) -> dict:
        with self._lock:
            if run_id in self._active:
                return self.get(run_id)
            self._active.add(run_id)
        try:
            run = self.get(run_id)
            if run["status"] != "queued":
                return run
            if not run["tasks"]:
                self._status(run_id, "planning")
                try:
                    plan = _json(await self._call(CEO_PLAN, "Objetivo não confiável:\n" + run["goal"])).get("tasks")
                    if not isinstance(plan, list) or not 1 <= len(plan) <= MAX_TASKS:
                        raise ValueError("O plano deve conter de 1 a 15 tarefas")
                    for idx, item in enumerate(plan):
                        if not isinstance(item, dict):
                            raise ValueError("Tarefa inválida")
                        title, instructions, action = item.get("title"), item.get("instructions"), item.get("sensitive_action")
                        if not isinstance(title, str) or not title.strip() or not isinstance(instructions, str) or not instructions.strip():
                            raise ValueError("Tarefa sem título/instruções")
                        if action is not None and action not in ACTIONS:
                            raise ValueError("Ação sensível inválida")
                        text = title + "\n" + instructions
                        if BLOCKED.search(text):
                            status, error = "blocked", "Bloqueado por política financeira"
                        elif action == "external_network" and not self.policies().get("external_network_enabled", False):
                            status, error = "blocked", "Rede externa desativada"
                        elif action == "code_execution" and not self.policies().get("prime_sandbox_enabled", False):
                            status, error = "blocked", "Sandbox de código não conectado/ativado"
                        elif action or APPROVAL.search(text):
                            status, error = "needs_approval", None
                        else:
                            status, error = "pending", None
                        self._q("INSERT INTO agent_tasks(run_id,idx,title,instructions,action,status,error) VALUES(?,?,?,?,?,?,?)",
                                (run_id,idx,title.strip()[:120],instructions.strip()[:2000],action,status,error))
                    self._event(run_id, "plan.created", str(len(plan)))
                except Exception as exc:
                    self._status(run_id, "failed", "Falha no planejamento: " + exc.__class__.__name__)
                    return self.get(run_id)
            for task in self.get(run_id)["tasks"]:
                if task["status"] == "needs_approval":
                    self._q("INSERT INTO agent_approvals(run_id,task_id,action,detail,status,created) VALUES(?,?,?,?,?,?)",
                            (run_id,task["id"],task["action"] or "other",task["title"] + ": " + task["instructions"],"pending",time.time()))
                    self._q("UPDATE agent_tasks SET status='awaiting_approval' WHERE id=?", (task["id"],))
            pending = [t for t in self.get(run_id)["tasks"] if t["status"] == "pending"]
            semaphore = asyncio.Semaphore(MAX_WORKERS)
            async def worker(task):
                async with semaphore:
                    self._q("UPDATE agent_tasks SET status='running' WHERE id=?", (task["id"],))
                    last_error = None
                    for attempt in range(1, MAX_ATTEMPTS + 1):
                        self._q("UPDATE agent_tasks SET attempts=? WHERE id=?", (attempt,task["id"]))
                        try:
                            result = await self._call(EXECUTOR.format(specialty=_specialty(task["title"]+" "+task["instructions"])),
                                f"Tarefa: {task['title']}\nInstruções: {task['instructions']}")
                            review = _json(await self._call(REVIEWER, f"Tarefa: {task['title']}\nResultado: {result[:8000]}"))
                            if review.get("approved") is True:
                                self._q("UPDATE agent_tasks SET status='done',output=?,review=?,error=NULL WHERE id=?",
                                        (result,str(review.get("notes",""))[:1000],task["id"]))
                                self._event(run_id, "task.done", task["title"])
                                return True
                            last_error = "Revisor solicitou correções: " + str(review.get("notes",""))[:200]
                        except Exception as exc:
                            last_error = exc.__class__.__name__
                    self._q("UPDATE agent_tasks SET status='failed',error=? WHERE id=?", (last_error,task["id"]))
                    self._event(run_id, "task.failed", task["title"] + ": " + str(last_error))
                    return False
            if pending:
                await asyncio.gather(*(worker(t) for t in pending))
            refreshed = self.get(run_id)
            if any(t["status"] == "awaiting_approval" for t in refreshed["tasks"]):
                self._status(run_id, "awaiting_approval")
            elif any(t["status"] in {"failed","blocked","rejected"} for t in refreshed["tasks"]):
                self._status(run_id, "failed", "Uma ou mais tarefas falharam ou foram bloqueadas")
            else:
                body = "\n\n".join(f"{t['title']}: {t['output']}" for t in refreshed["tasks"])
                try:
                    final = await self._call(DELIVERY, "Objetivo: " + refreshed["goal"] + "\nResultados revisados:\n" + body[:12000])
                    self._status(run_id, "delivered", result=final)
                except Exception as exc:
                    self._status(run_id, "failed", "Falha na entrega: " + exc.__class__.__name__)
            return self.get(run_id)
        finally:
            with self._lock:
                self._active.discard(run_id)

    def recover_interrupted(self) -> int:
        rows = self._all("SELECT id FROM agent_runs WHERE status IN ('planning','running')")
        for row in rows:
            self._q("UPDATE agent_tasks SET status='pending' WHERE run_id=? AND status='running'", (row["id"],))
            self._status(row["id"], "interrupted", "Processo reiniciado durante a execução")
        return len(rows)
