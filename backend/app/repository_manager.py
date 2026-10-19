from __future__ import annotations
import json
import os
import shutil
import uuid
from threading import RLock
from pathlib import Path
from typing import Any
from pydantic import ValidationError
from .config import Settings
from .schemas import SkillManifest, SkillSummary
from .security import safe_extract, UnsafeArchive

class SkillError(ValueError):
    pass

class SkillManager:
    """Filesystem-backed development catalog. Use DB/object storage in production."""
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir.resolve() / "skills"
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog: dict[str, dict[str, Any]] = {}
        self.catalog_file = self.settings.data_dir.resolve() / "skills-catalog.json"
        # Initialize the lock before loading so all catalog access uses one discipline.
        self._lock = RLock()
        self._load_catalog()

    def install_zip(self, zip_path: Path) -> SkillSummary:
        install_id = uuid.uuid4().hex
        destination = self.root / f"pending-{install_id}"
        try:
            safe_extract(zip_path, destination, self.settings)
            manifests = list(destination.rglob("manifest.json"))
            if len(manifests) != 1:
                raise SkillError("Archive must contain exactly one manifest.json")
            raw = json.loads(manifests[0].read_text(encoding="utf-8"))
            manifest = SkillManifest.model_validate(raw)
            skill_dir = manifests[0].parent
            # Do not silently ignore sibling payloads outside a nested package root.
            for item in destination.rglob("*"):
                if item == skill_dir or skill_dir in item.parents:
                    continue
                if item.is_file() or (item.is_dir() and item != destination):
                    raise SkillError("Archive contains files outside the manifest package root")
            # Require every path within the package root to stay declarative.
            for item in skill_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() in {".py", ".js", ".mjs", ".cjs", ".sh", ".bat", ".ps1", ".exe", ".dll", ".so"}:
                    raise SkillError(f"Executable source/binary is not accepted in declarative skills: {item.name}")
            key = manifest.id
            record = {
                "manifest": manifest,
                "status": "pending_review",
                "path": str(skill_dir),
                "install_id": install_id,
            }
            # This prototype keeps one installed version per skill ID. Reject
            # every duplicate ID rather than silently replacing another version.
            with self._lock:
                existing = self.catalog.get(key)
                if existing and existing["status"] != "rejected":
                    raise SkillError("This skill ID is already installed; update flow is not supported yet")
                # Rejected packages are removed from disk and may be submitted again
                # for a fresh review; active or pending IDs cannot be overwritten.
                self.catalog[key] = record
                try:
                    self._save_catalog_locked()
                except OSError:
                    if existing is None:
                        self.catalog.pop(key, None)
                    else:
                        self.catalog[key] = existing
                    raise
                return self._summary(key, record)
        except (UnsafeArchive, ValidationError, json.JSONDecodeError, OSError, SkillError):
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def approve(self, skill_id: str) -> SkillSummary:
        with self._lock:
            record = self.catalog.get(skill_id)
            if not record:
                raise KeyError(skill_id)
            if record["status"] != "pending_review":
                raise SkillError("Only skills pending review can be approved")
            record["status"] = "active"
            try:
                self._save_catalog_locked()
            except OSError:
                record["status"] = "pending_review"
                raise
            return self._summary(skill_id, record)

    def reject(self, skill_id: str) -> SkillSummary:
        with self._lock:
            record = self.catalog.get(skill_id)
            if not record:
                raise KeyError(skill_id)
            if record["status"] != "pending_review":
                raise SkillError("Only skills pending review can be rejected")
            record["status"] = "rejected"
            try:
                self._save_catalog_locked()
            except OSError:
                record["status"] = "pending_review"
                raise
            package_root = Path(record["path"]).parent
            summary = self._summary(skill_id, record)
        shutil.rmtree(package_root, ignore_errors=True)
        return summary

    def list_skills(self) -> list[SkillSummary]:
        with self._lock:
            return [self._summary(k, v) for k, v in self.catalog.items()]

    def preferred_language(self, skill_ids: list[str]) -> str | None:
        """Return the first approved skill's language hint; explicit user choice always wins."""
        with self._lock:
            for key in skill_ids:
                record = self.catalog.get(key)
                if not record or record["status"] != "active":
                    continue
                manifest: SkillManifest = record["manifest"]
                if manifest.default_language and manifest.default_language in manifest.languages:
                    return manifest.default_language
        return None

    def active_tools(self, skill_ids: list[str], language: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        with self._lock:
            for key in skill_ids:
                record = self.catalog.get(key)
                if not record or record["status"] != "active":
                    continue
                manifest: SkillManifest = record["manifest"]
                if language not in manifest.languages:
                    continue
                for tool in manifest.tools:
                    result.append({
                        "skill_id": key,
                        "name": tool.name,
                        "description": tool.description,
                        "template": tool.template,
                    })
        return result


    def _load_catalog(self) -> None:
        """Restore declarative skill metadata after restart; never deserialize executable objects."""
        if not self.catalog_file.exists():
            return
        try:
            payload = json.loads(self.catalog_file.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("catalog must be a list")
            for item in payload:
                manifest = SkillManifest.model_validate(item["manifest"])
                status = item["status"]
                if status not in {"pending_review", "active", "rejected"}:
                    continue
                skill_path = Path(item["path"]).resolve()
                if self.root not in skill_path.parents or not skill_path.is_dir():
                    continue
                self.catalog[manifest.id] = {
                    "manifest": manifest, "status": status, "path": str(skill_path),
                    "install_id": str(item.get("install_id", "restored")),
                }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, ValidationError):
            # Fail closed: corrupt metadata must not prevent API startup or activate skills.
            self.catalog = {}

    def _save_catalog_locked(self) -> None:
        payload = [{
            "manifest": record["manifest"].model_dump(), "status": record["status"],
            "path": record["path"], "install_id": record["install_id"],
        } for record in self.catalog.values()]
        self.catalog_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.catalog_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.catalog_file)

    @staticmethod
    def _summary(key: str, record: dict[str, Any]) -> SkillSummary:
        m: SkillManifest = record["manifest"]
        return SkillSummary(
            id=key, name=m.name, version=m.version, description=m.description,
            status=record["status"], languages=m.languages,
            tools=[tool.name for tool in m.tools],
        )
