import json
import zipfile
from pathlib import Path
import pytest
from app.config import Settings
from app.security import inspect_zip, safe_extract, UnsafeArchive
from app.repository_manager import SkillManager

def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, max_upload_bytes=1_000_000,
                    max_zip_files=100, max_uncompressed_bytes=1_000_000,
                    max_compression_ratio=100)

def make_zip(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return path

def manifest() -> str:
    return json.dumps({
        "schema_version": "1.0", "id": "hello-skill", "name": "Hello",
        "version": "1.0.0", "description": "test skill", "languages": ["pt"], "default_language": "pt",
        "tools": [{"name": "hello", "description": "hello tool",
                   "kind": "prompt_template", "template": "Hello {{input}}"}]
    })

def test_safe_archive_extracts(tmp_path):
    z = make_zip(tmp_path / "ok.zip", {"manifest.json": manifest(), "docs/readme.txt": "hi"})
    dest = tmp_path / "out"
    safe_extract(z, dest, settings(tmp_path))
    assert (dest / "manifest.json").is_file()

@pytest.mark.parametrize("bad", ["../escape.txt", "/tmp/escape.txt", "C:/escape.txt", r"..\\escape.txt", ".env"])
def test_rejects_unsafe_paths(tmp_path, bad):
    z = make_zip(tmp_path / "bad.zip", {"manifest.json": manifest(), bad: "x"})
    with pytest.raises(UnsafeArchive):
        inspect_zip(z, settings(tmp_path))

def test_rejects_corrupt_zip(tmp_path):
    z = tmp_path / "bad.zip"
    z.write_bytes(b"not a zip")
    with pytest.raises(UnsafeArchive):
        inspect_zip(z, settings(tmp_path))

def test_skill_requires_approval(tmp_path):
    z = make_zip(tmp_path / "skill.zip", {"manifest.json": manifest()})
    manager = SkillManager(settings(tmp_path))
    skill = manager.install_zip(z)
    assert skill.status == "pending_review"
    assert manager.active_tools(["hello-skill"], "pt") == []
    assert manager.preferred_language(["hello-skill"]) is None
    manager.approve("hello-skill")
    assert manager.preferred_language(["hello-skill"]) == "pt"
    assert len(manager.active_tools(["hello-skill"], "pt")) == 1
    assert manager.active_tools(["hello-skill"], "en") == []

def test_rejects_executable_source(tmp_path):
    z = make_zip(tmp_path / "skill.zip", {"manifest.json": manifest(), "evil.py": "print('bad')"})
    manager = SkillManager(settings(tmp_path))
    with pytest.raises(ValueError):
        manager.install_zip(z)


def test_allows_common_non_executable_github_metadata(tmp_path):
    z = make_zip(tmp_path / "github.zip", {
        "manifest.json": manifest(),
        ".gitignore": "*.pyc\n",
        ".github/workflows/ci.yml": "name: validation\n",
    })
    dest = tmp_path / "github-out"
    safe_extract(z, dest, settings(tmp_path))
    assert (dest / ".gitignore").is_file()
    assert (dest / ".github/workflows/ci.yml").is_file()


def test_skill_id_duplicate_is_rejected_without_replacing_original(tmp_path):
    z1 = make_zip(tmp_path / "skill-one.zip", {"manifest.json": manifest()})
    z2 = make_zip(tmp_path / "skill-two.zip", {"manifest.json": manifest()})
    manager = SkillManager(settings(tmp_path))
    first = manager.install_zip(z1)
    with pytest.raises(ValueError, match="already installed"):
        manager.install_zip(z2)
    assert manager.list_skills()[0].id == first.id
    assert manager.list_skills()[0].status == "pending_review"

def test_rejects_empty_zip_and_missing_manifest(tmp_path):
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w"):
        pass
    with pytest.raises(UnsafeArchive, match="Empty"):
        inspect_zip(empty, settings(tmp_path))
    no_manifest = make_zip(tmp_path / "no-manifest.zip", {"readme.txt": "hello"})
    with pytest.raises(UnsafeArchive, match="manifest.json"):
        inspect_zip(no_manifest, settings(tmp_path))


def test_rejects_too_many_entries_and_uncompressed_size(tmp_path):
    many = make_zip(tmp_path / "many.zip", {
        "manifest.json": manifest(), "one.txt": "1", "two.txt": "2",
    })
    with pytest.raises(UnsafeArchive, match="too many"):
        inspect_zip(many, Settings(data_dir=tmp_path, max_zip_files=2,
                                  max_uncompressed_bytes=1_000_000, max_compression_ratio=100))
    large = make_zip(tmp_path / "large.zip", {"manifest.json": manifest(), "large.txt": "x" * 5000})
    with pytest.raises(UnsafeArchive, match="size limit"):
        inspect_zip(large, Settings(data_dir=tmp_path, max_zip_files=100,
                                   max_uncompressed_bytes=1000, max_compression_ratio=100))


def test_rejects_duplicate_archive_paths(tmp_path):
    archive_path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", manifest())
        z.writestr("docs/readme.txt", "one")
        z.writestr("docs/readme.txt", "two")
    with pytest.raises(UnsafeArchive, match="Duplicate"):
        inspect_zip(archive_path, settings(tmp_path))


def test_rejects_symlink_and_special_archive_entries(tmp_path):
    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", manifest())
        z.writestr(link, "target.txt")
    with pytest.raises(UnsafeArchive, match="Links and special"):
        inspect_zip(archive_path, settings(tmp_path))


def test_rejects_high_compression_ratio(tmp_path):
    archive_path = tmp_path / "ratio.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", manifest())
        z.writestr("repeat.txt", "A" * 10000)
    limits = Settings(data_dir=tmp_path, max_zip_files=100,
                      max_uncompressed_bytes=1_000_000, max_compression_ratio=2)
    with pytest.raises(UnsafeArchive, match="compression ratio"):
        inspect_zip(archive_path, limits)

def test_rejected_skill_is_removed_and_can_be_resubmitted(tmp_path):
    z = make_zip(tmp_path / "skill.zip", {"manifest.json": manifest()})
    manager = SkillManager(settings(tmp_path))
    first = manager.install_zip(z)
    package_root = Path(manager.catalog[first.id]["path"]).parent
    rejected = manager.reject(first.id)
    assert rejected.status == "rejected"
    assert not package_root.exists()
    second = manager.install_zip(z)
    assert second.id == first.id
    assert second.status == "pending_review"


def test_catalog_reloads_approved_skills_and_fails_closed_when_corrupt(tmp_path):
    z = make_zip(tmp_path / "skill.zip", {"manifest.json": manifest()})
    manager = SkillManager(settings(tmp_path))
    manager.install_zip(z)
    manager.approve("hello-skill")
    restored = SkillManager(settings(tmp_path))
    assert restored.list_skills()[0].status == "active"
    assert restored.active_tools(["hello-skill"], "pt")
    restored.catalog_file.write_text("{broken", encoding="utf-8")
    corrupt = SkillManager(settings(tmp_path))
    assert corrupt.list_skills() == []


def test_rejects_multiple_manifests_and_files_outside_package_root(tmp_path):
    multi = make_zip(tmp_path / "multi.zip", {
        "manifest.json": manifest(), "nested/manifest.json": manifest(),
    })
    manager = SkillManager(settings(tmp_path))
    with pytest.raises(ValueError, match="exactly one"):
        manager.install_zip(multi)
    mixed = make_zip(tmp_path / "mixed.zip", {
        "package/manifest.json": manifest(), "outside.txt": "not in package",
    })
    with pytest.raises(ValueError, match="outside the manifest"):
        manager.install_zip(mixed)

def test_skill_catalog_write_failures_roll_back_state_and_cleanup(tmp_path, monkeypatch):
    z = make_zip(tmp_path / "skill.zip", {"manifest.json": manifest()})
    manager = SkillManager(settings(tmp_path))
    monkeypatch.setattr(manager, "_save_catalog_locked", lambda: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(OSError):
        manager.install_zip(z)
    assert manager.list_skills() == []
    assert not list(manager.root.glob("pending-*"))


def test_skill_approval_and_rejection_failures_restore_pending_state(tmp_path, monkeypatch):
    z1 = make_zip(tmp_path / "one.zip", {"manifest.json": manifest()})
    second_manifest = manifest().replace("hello-skill", "second-skill")
    z2 = make_zip(tmp_path / "two.zip", {"manifest.json": second_manifest})
    manager = SkillManager(settings(tmp_path))
    first = manager.install_zip(z1)
    second = manager.install_zip(z2)
    original_save = manager._save_catalog_locked
    with pytest.raises(KeyError):
        manager.approve("missing")
    monkeypatch.setattr(manager, "_save_catalog_locked", lambda: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(OSError):
        manager.approve(first.id)
    assert manager.catalog[first.id]["status"] == "pending_review"
    with pytest.raises(OSError):
        manager.reject(second.id)
    assert manager.catalog[second.id]["status"] == "pending_review"
    monkeypatch.setattr(manager, "_save_catalog_locked", original_save)
    manager.approve(first.id)
    with pytest.raises(ValueError, match="pending review"):
        manager.approve(first.id)

def test_directory_entries_are_normalized_and_extracted(tmp_path):
    archive_path = make_zip(tmp_path / "directories.zip", {
        "manifest.json": manifest(), "docs/": "", "docs/readme.txt": "hello",
    })
    destination = tmp_path / "extracted"
    safe_extract(archive_path, destination, settings(tmp_path))
    assert (destination / "docs").is_dir()
    assert (destination / "docs" / "readme.txt").read_text(encoding="utf-8") == "hello"


def test_rejects_encrypted_archive_members(tmp_path):
    archive_path = make_zip(tmp_path / "encrypted.zip", {"manifest.json": manifest()})
    raw = bytearray(archive_path.read_bytes())
    local_header = raw.find(b"PK\x03\x04")
    central_header = raw.find(b"PK\x01\x02")
    assert local_header >= 0 and central_header >= 0
    raw[local_header + 6] |= 0x01
    raw[central_header + 8] |= 0x01
    archive_path.write_bytes(raw)
    with pytest.raises(UnsafeArchive, match="Encrypted ZIP"):
        inspect_zip(archive_path, settings(tmp_path))


def test_extraction_failure_removes_partial_destination(tmp_path, monkeypatch):
    archive_path = make_zip(tmp_path / "partial.zip", {
        "manifest.json": manifest(), "docs/readme.txt": "hello",
    })
    destination = tmp_path / "partial-out"
    def fail_copy(*args, **kwargs):
        raise OSError("simulated disk failure")
    monkeypatch.setattr("app.security.shutil.copyfileobj", fail_copy)
    with pytest.raises(OSError, match="simulated disk failure"):
        safe_extract(archive_path, destination, settings(tmp_path))
    assert not destination.exists()

