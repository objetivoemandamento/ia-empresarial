from __future__ import annotations
import asyncio
import json
import secrets
import tempfile
import threading
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, Depends
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from .audio import transcribe_audio, AudioUnavailable, ALLOWED_LANGUAGES
from .config import get_settings
from .llm import LLMEngine, LLMUnavailable
from .repository_manager import SkillManager, SkillError
from .schemas import ChatRequest, ChatResponse
from .security import UnsafeArchive
from .agent_orchestrator import AgentOrchestrator, AgentRunError
from .agent_orchestrator import AgentOrchestrator, AgentRunError
from .human_tasks import (
    HumanTaskStore, TaskCreate, TaskUpdate, TaskDecision, TaskCompletion,
    TaskStatusChange, TaskError,
)

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
skill_manager = SkillManager(settings)
llm = LLMEngine(settings)
task_store = HumanTaskStore(settings.data_dir / "human_tasks.sqlite3")

app = FastAPI(title="Modular AI Platform API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    # Development guard only; replace with OIDC/RBAC before production.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")
    token = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=403, detail="Invalid admin token")


POLICY_FILE = settings.data_dir / "policies.json"
POLICY_LOCK = threading.RLock()
DEFAULT_POLICIES = {
    "voice_enabled": True, "approved_skills_enabled": True,
    "prime_sandbox_enabled": False, "external_network_enabled": False,
    "optional_telemetry_enabled": True,
}
PROTECTED_CONTROLS = [
    {"key": "financial_actions", "title": "Transferências, pagamentos e saques bloqueados", "enabled": True},
    {"key": "bank_data_changes", "title": "Alterações de dados bancários bloqueadas", "enabled": True},
    {"key": "authentication", "title": "Autenticação obrigatória", "enabled": True},
    {"key": "security_audit", "title": "Auditoria de segurança obrigatória", "enabled": True},
    {"key": "untrusted_code", "title": "Código não confiável exige isolamento e revisão", "enabled": True},
]


class PolicyChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_enabled: bool | None = None
    approved_skills_enabled: bool | None = None
    prime_sandbox_enabled: bool | None = None
    external_network_enabled: bool | None = None
    optional_telemetry_enabled: bool | None = None


def read_policies() -> dict:
    with POLICY_LOCK:
        try:
            stored = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        return {**DEFAULT_POLICIES, **{k: v for k, v in stored.items() if k in DEFAULT_POLICIES}}


def policies_response() -> dict:
    return {**read_policies(), "protected_controls": PROTECTED_CONTROLS}


@app.get("/api/policies")
async def get_policies():
    return policies_response()


@app.patch("/api/policies", dependencies=[Depends(require_admin)])
async def patch_policies(changes: PolicyChanges):
    update = changes.model_dump(exclude_none=True)
    with POLICY_LOCK:
        current = read_policies()
        current.update(update)
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = POLICY_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        temporary.replace(POLICY_FILE)
    return policies_response()



POLICY_FILE = settings.data_dir / "policies.json"
POLICY_LOCK = threading.RLock()
DEFAULT_POLICIES = {
    "voice_enabled": True,
    "approved_skills_enabled": True,
    "prime_sandbox_enabled": False,
    "external_network_enabled": False,
    "optional_telemetry_enabled": True,
}
PROTECTED_CONTROLS = [
    {"key": "financial_actions", "title": "Transferências, pagamentos e saques bloqueados", "enabled": True},
    {"key": "bank_data_changes", "title": "Alterações de dados bancários bloqueadas", "enabled": True},
    {"key": "authentication", "title": "Autenticação obrigatória", "enabled": True},
    {"key": "security_audit", "title": "Auditoria de segurança obrigatória", "enabled": True},
    {"key": "untrusted_code", "title": "Código não confiável exige isolamento e revisão", "enabled": True},
]


class PolicyChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_enabled: bool | None = None
    approved_skills_enabled: bool | None = None
    prime_sandbox_enabled: bool | None = None
    external_network_enabled: bool | None = None
    optional_telemetry_enabled: bool | None = None


def read_policies() -> dict:
    with POLICY_LOCK:
        try:
            stored = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        return {**DEFAULT_POLICIES, **{k: v for k, v in stored.items() if k in DEFAULT_POLICIES}}


def policies_response() -> dict:
    return {**read_policies(), "protected_controls": PROTECTED_CONTROLS}


@app.get("/api/policies")
async def get_policies():
    return policies_response()


@app.patch("/api/policies", dependencies=[Depends(require_admin)])
async def patch_policies(changes: PolicyChanges):
    update = changes.model_dump(exclude_none=True)
    with POLICY_LOCK:
        current = read_policies()
        current.update(update)
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = POLICY_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        temporary.replace(POLICY_FILE)
    return policies_response()


@app.get("/api/health")
async def health():
    llm_ready = llm.is_ready
    return {
        "ok": True,
        "language_default": "pt",
        "supported_languages": sorted(ALLOWED_LANGUAGES),
        "llm_ready": llm_ready,
        "llm_mode": "configured" if llm_ready else "demo",
        "llm_model": (settings.llm_model or ("multi-provider-router" if settings.ai_router_models_json.strip() else None)) if llm_ready else None,
        "transcription_ready": bool(settings.openai_api_key.strip()),
        "agent_orchestrator_ready": llm.is_ready,
        "agent_orchestrator_ready": llm.is_ready,
    }

@app.post("/api/repositories/upload")
async def upload_repository(file: UploadFile = File(...), _: None = Depends(require_admin)):
    if not read_policies()["approved_skills_enabled"]:
        raise HTTPException(status_code=403, detail="Instalação de skills desativada nas permissões")
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=415, detail="Upload must be a .zip file")
    with tempfile.NamedTemporaryFile(prefix="repo-upload-", suffix=".zip", delete=False) as temp:
        temp_path = Path(temp.name)
        total = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="ZIP exceeds upload size limit")
                temp.write(chunk)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
    try:
        try:
            skill = await run_in_threadpool(skill_manager.install_zip, temp_path)
        except UnsafeArchive as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SkillError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid skill package: {exc.__class__.__name__}") from exc
        return {"status": "pending_review", "skill": skill.model_dump()}
    finally:
        temp_path.unlink(missing_ok=True)

@app.get("/api/repositories")
async def list_repositories():
    return {"skills": [s.model_dump() for s in skill_manager.list_skills()]}

@app.post("/api/repositories/{skill_id}/approve", dependencies=[Depends(require_admin)])
async def approve_repository(skill_id: str):
    try:
        result = skill_manager.approve(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"skill": result.model_dump()}

@app.post("/api/repositories/{skill_id}/reject", dependencies=[Depends(require_admin)])
async def reject_repository(skill_id: str):
    try:
        result = skill_manager.reject(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"skill": result.model_dump()}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Explicit UI/API choice wins. If omitted/null, approved skill manifest may
    # suggest a supported language; Portuguese remains the final default.
    current_policies = read_policies()
    if request.skill_ids and not current_policies["approved_skills_enabled"]:
        raise HTTPException(status_code=403, detail="Uso de skills está desativado nas permissões")
    language = request.language or (skill_manager.preferred_language(request.skill_ids) if current_policies["approved_skills_enabled"] else None) or "pt"
    tools = skill_manager.active_tools(request.skill_ids, language) if current_policies["approved_skills_enabled"] else []
    messages = [m.model_dump() for m in request.messages]
    try:
        answer, provider = await llm.respond(messages, language, tools)
    except LLMUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(
        answer=answer,
        language=language,
        active_skills=sorted({tool["skill_id"] for tool in tools}),
        provider=provider,
    )

@app.post("/api/audio/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("pt"),
):
    if not read_policies()["voice_enabled"]:
        raise HTTPException(status_code=403, detail="Recursos de voz desativados nas permissões")
    if not read_policies()["voice_enabled"]:
        raise HTTPException(status_code=403, detail="Recursos de voz desativados nas permissões")
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(status_code=422, detail="Language must be pt, en, zh, es, or hi")
    max_audio = 25 * 1024 * 1024
    data = await file.read(max_audio + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(data) > max_audio:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB")
    try:
        text = await transcribe_audio(data, file.filename or "recording.webm", language, settings)
    except AudioUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"text": text, "language": language}


def _task_call(action, *args):
    try:
        return action(*args)
    except TaskError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/human-tasks", dependencies=[Depends(require_admin)])
async def list_human_tasks(status: str | None = None, owner: str | None = None):
    return {"tasks": _task_call(task_store.list, status, owner)}


@app.post("/api/human-tasks", status_code=201, dependencies=[Depends(require_admin)])
async def create_human_task(request: TaskCreate):
    return {"task": _task_call(task_store.create, request, "admin")}


@app.get("/api/human-tasks/{task_id}", dependencies=[Depends(require_admin)])
async def get_human_task(task_id: str):
    return {"task": _task_call(task_store.get, task_id)}


@app.patch("/api/human-tasks/{task_id}", dependencies=[Depends(require_admin)])
async def update_human_task(task_id: str, request: TaskUpdate):
    return {"task": _task_call(task_store.update, task_id, request, "admin")}


@app.post("/api/human-tasks/{task_id}/status", dependencies=[Depends(require_admin)])
async def change_human_task_status(task_id: str, request: TaskStatusChange):
    return {"task": _task_call(task_store.set_status, task_id, request.status, "admin", request.note)}


@app.post("/api/human-tasks/{task_id}/decision", dependencies=[Depends(require_admin)])
async def decide_human_task(task_id: str, request: TaskDecision):
    return {"task": _task_call(task_store.decide, task_id, request, "admin")}


@app.post("/api/human-tasks/{task_id}/complete", dependencies=[Depends(require_admin)])
async def complete_human_task(task_id: str, request: TaskCompletion):
    return {"task": _task_call(task_store.complete, task_id, request, "admin")}


@app.get("/api/human-tasks/{task_id}/history", dependencies=[Depends(require_admin)])
async def human_task_history(task_id: str):
    return {"events": _task_call(task_store.history, task_id)}

# ---- CEO -> agentes especialistas -> revisão -> entrega ----
agent_orchestrator = AgentOrchestrator(settings.data_dir / "agent_runs.sqlite3", lambda system, user: llm.complete(system, user), read_policies)
agent_orchestrator.recover_interrupted()
_background_runs: set[asyncio.Task] = set()


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=4000)


class AgentApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


async def _process_agent_run(run_id: int) -> None:
    try:
        await agent_orchestrator.process(run_id)
    except Exception as exc:
        agent_orchestrator._status(run_id, "failed", "Erro interno: " + exc.__class__.__name__)


def _schedule_agent_run(run_id: int) -> None:
    task = asyncio.create_task(_process_agent_run(run_id))
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)


@app.post("/api/agent-runs", status_code=202, dependencies=[Depends(require_admin)])
async def create_agent_run(body: AgentRunCreate):
    try:
        run = agent_orchestrator.create(body.goal)
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _schedule_agent_run(run["id"])
    return run


@app.get("/api/agent-runs", dependencies=[Depends(require_admin)])
async def list_agent_runs():
    return {"runs": agent_orchestrator.list()}


@app.get("/api/agent-runs/{run_id}", dependencies=[Depends(require_admin)])
async def get_agent_run(run_id: int):
    try:
        return agent_orchestrator.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execução não encontrada") from exc


@app.post("/api/agent-runs/{run_id}/retry", status_code=202, dependencies=[Depends(require_admin)])
async def retry_agent_run(run_id: int):
    try:
        run = agent_orchestrator.retry(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execução não encontrada") from exc
    except AgentRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_agent_run(run_id)
    return run


@app.post("/api/agent-approvals/{approval_id}/decision", dependencies=[Depends(require_admin)])
async def decide_agent_approval(approval_id: int, body: AgentApprovalDecision):
    try:
        run = agent_orchestrator.decide(approval_id, body.approve)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Aprovação não encontrada") from exc
    except AgentRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_agent_run(run["id"])
    return run

# ---- CEO -> agentes especialistas -> revisão -> entrega ----
agent_orchestrator = AgentOrchestrator(
    settings.data_dir / "agent_runs.sqlite3",
    lambda system, user: llm.complete(system, user),
    read_policies,
)
agent_orchestrator.recover_interrupted()
_background_runs: set[asyncio.Task] = set()


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=4000)


class AgentApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


async def _process_agent_run(run_id: int) -> None:
    try:
        await agent_orchestrator.process(run_id)
    except Exception as exc:
        agent_orchestrator._status(run_id, "failed", "Erro interno: " + exc.__class__.__name__)


def _schedule_agent_run(run_id: int) -> None:
    task = asyncio.create_task(_process_agent_run(run_id))
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)


@app.post("/api/agent-runs", status_code=202, dependencies=[Depends(require_admin)])
async def create_agent_run(body: AgentRunCreate):
    try:
        run = agent_orchestrator.create(body.goal)
    except AgentRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _schedule_agent_run(run["id"])
    return run


@app.get("/api/agent-runs", dependencies=[Depends(require_admin)])
async def list_agent_runs():
    return {"runs": agent_orchestrator.list()}


@app.get("/api/agent-runs/{run_id}", dependencies=[Depends(require_admin)])
async def get_agent_run(run_id: int):
    try:
        return agent_orchestrator.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execução não encontrada") from exc


@app.post("/api/agent-runs/{run_id}/retry", status_code=202, dependencies=[Depends(require_admin)])
async def retry_agent_run(run_id: int):
    try:
        run = agent_orchestrator.retry(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Execução não encontrada") from exc
    except AgentRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_agent_run(run_id)
    return run


@app.post("/api/agent-approvals/{approval_id}/decision", dependencies=[Depends(require_admin)])
async def decide_agent_approval(approval_id: int, body: AgentApprovalDecision):
    try:
        run = agent_orchestrator.decide(approval_id, body.approve)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Aprovação não encontrada") from exc
    except AgentRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _schedule_agent_run(run["id"])
    return run
