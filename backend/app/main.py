from __future__ import annotations
import secrets
import tempfile
from pathlib import Path
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
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    # Development guard only; replace with OIDC/RBAC before production.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")
    token = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=403, detail="Invalid admin token")

@app.get("/api/health")
async def health():
    llm_ready = llm.is_ready
    return {
        "ok": True,
        "language_default": "pt",
        "supported_languages": sorted(ALLOWED_LANGUAGES),
        "llm_ready": llm_ready,
        "llm_mode": "configured" if llm_ready else "demo",
        "llm_model": settings.llm_model if llm_ready else None,
        "transcription_ready": bool(settings.openai_api_key.strip()),
    }

@app.post("/api/repositories/upload")
async def upload_repository(file: UploadFile = File(...), _: None = Depends(require_admin)):
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
    language = request.language or skill_manager.preferred_language(request.skill_ids) or "pt"
    tools = skill_manager.active_tools(request.skill_ids, language)
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
