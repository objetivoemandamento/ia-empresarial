from __future__ import annotations
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable
from .config import Settings

class UnsafeArchive(ValueError):
    pass

_DRIVE = re.compile(r"^[A-Za-z]:")
_ALLOWED_MANIFEST = "manifest.json"

def _normalise_member(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise UnsafeArchive("Invalid archive member name")
    if name.startswith("/") or _DRIVE.match(name):
        raise UnsafeArchive("Absolute paths are not allowed")
    # Validate raw components before pathlib normalizes "." or repeated slashes.
    raw_parts = name.split("/")
    if raw_parts[-1] == "" and name.endswith("/"):
        raw_parts = raw_parts[:-1]  # directory entry, e.g. "docs/"
    if not raw_parts or any(part in ("", ".", "..") for part in raw_parts):
        raise UnsafeArchive("Path traversal or non-canonical path detected")
    # GitHub source archives commonly contain harmless repository metadata.
    # Allow a narrow set; block .git internals, environment files and arbitrary
    # hidden paths that could carry secrets or confusing filesystem semantics.
    allowed_hidden = {".github", ".gitignore", ".gitattributes", ".editorconfig"}
    if any(part.startswith(".") and part not in allowed_hidden for part in raw_parts):
        raise UnsafeArchive("Hidden path is not allowed in skill archives")
    return PurePosixPath(*raw_parts)

def inspect_zip(file_path: Path, settings: Settings) -> tuple[list[zipfile.ZipInfo], int]:
    try:
        archive = zipfile.ZipFile(file_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UnsafeArchive("Invalid or unreadable ZIP archive") from exc

    with archive:
        infos = archive.infolist()
        if not infos:
            raise UnsafeArchive("Empty ZIP archive")
        if len(infos) > settings.max_zip_files:
            raise UnsafeArchive("Archive contains too many entries")

        total = 0
        seen: set[str] = set()
        for info in infos:
            p = _normalise_member(info.filename)
            canonical = p.as_posix().rstrip("/")
            if canonical in seen:
                raise UnsafeArchive("Duplicate archive path")
            seen.add(canonical)

            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
                raise UnsafeArchive("Links and special files are not allowed")
            if info.flag_bits & 0x1:
                raise UnsafeArchive("Encrypted ZIP members are not supported")
            if info.file_size < 0 or info.compress_size < 0:
                raise UnsafeArchive("Invalid member size")
            total += info.file_size
            if total > settings.max_uncompressed_bytes:
                raise UnsafeArchive("Uncompressed archive exceeds size limit")
            if info.file_size > 0:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > settings.max_compression_ratio:
                    raise UnsafeArchive("Suspicious compression ratio")
        if not any(PurePosixPath(i.filename).name == _ALLOWED_MANIFEST for i in infos):
            raise UnsafeArchive("ZIP must contain manifest.json")
        return infos, total

def safe_extract(file_path: Path, destination: Path, settings: Settings) -> Path:
    infos, _ = inspect_zip(file_path, settings)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(file_path) as archive:
            for info in infos:
                rel = _normalise_member(info.filename)
                target = destination.joinpath(*rel.parts)
                # Resolve and enforce containment even after lexical checks.
                resolved = target.resolve()
                if destination.resolve() not in resolved.parents and resolved != destination.resolve():
                    raise UnsafeArchive("Resolved path escapes extraction root")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents overwriting duplicate/colliding files.
                with archive.open(info, "r") as source, target.open("xb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
        return destination
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
