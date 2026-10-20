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
        "version": "1.0.0", "description": "test skill", "languages": ["pt"],
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
    manager.approve("hello-skill")
    assert len(manager.active_tools(["hello-skill"], "pt")) == 1

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

