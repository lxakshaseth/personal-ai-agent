"""
Tests for filesystem tools.

All file I/O is performed against real temporary directories inside the
project's own temp folder (avoids Windows permission issues with system temp).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.tools.filesystem.tools import (
    CreateFolderTool,
    DeleteFolderTool,
    CreateFileTool,
    DeleteFileTool,
    MoveFileTool,
    CopyFileTool,
    RenameFileTool,
    ListDirectoryTool,
    SearchFilesTool,
    OpenFolderTool,
)


# ── Fixture: temp dir inside the project (avoids system-temp permission issues)

@pytest.fixture
def sandbox():
    """
    A temporary directory created inside the project's own scratch area,
    with allowed_base_paths patched to include it.
    """
    base = Path(__file__).parent.parent / ".pytest_sandbox"
    base.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=base))
    with patch("app.tools.filesystem.tools._allowed", return_value=[str(tmp)]):
        yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


# ── create_folder ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_folder_success(sandbox: Path) -> None:
    target = str(sandbox / "new_folder")
    result = await CreateFolderTool().execute(folder_path=target)
    assert result.success
    assert Path(target).is_dir()
    assert "created" in result.output.lower()


@pytest.mark.asyncio
async def test_create_folder_nested(sandbox: Path) -> None:
    target = str(sandbox / "a" / "b" / "c")
    result = await CreateFolderTool().execute(folder_path=target)
    assert result.success
    assert Path(target).is_dir()


@pytest.mark.asyncio
async def test_create_folder_already_exists_ok(sandbox: Path) -> None:
    target = str(sandbox / "exists")
    Path(target).mkdir()
    result = await CreateFolderTool().execute(folder_path=target, exist_ok=True)
    assert result.success


@pytest.mark.asyncio
async def test_create_folder_protected_path_rejected() -> None:
    result = await CreateFolderTool().execute(folder_path=r"C:\Windows\System32\bad")
    assert not result.success
    assert result.error is not None


# ── delete_folder ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_folder_success(sandbox: Path) -> None:
    target = sandbox / "to_delete"
    target.mkdir()
    (target / "file.txt").write_text("hello")
    result = await DeleteFolderTool().execute(folder_path=str(target))
    assert result.success
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_folder_not_found(sandbox: Path) -> None:
    result = await DeleteFolderTool().execute(folder_path=str(sandbox / "nonexistent"))
    assert not result.success
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_delete_folder_system_dir_rejected() -> None:
    result = await DeleteFolderTool().execute(folder_path=r"C:\Windows")
    assert not result.success


# ── create_file ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_file_success(sandbox: Path) -> None:
    target = str(sandbox / "hello.txt")
    result = await CreateFileTool().execute(file_path=target, content="Hello, World!")
    assert result.success
    assert Path(target).read_text() == "Hello, World!"


@pytest.mark.asyncio
async def test_create_file_no_overwrite_existing(sandbox: Path) -> None:
    target = sandbox / "existing.txt"
    target.write_text("original")
    result = await CreateFileTool().execute(file_path=str(target), content="new", overwrite=False)
    assert not result.success
    assert target.read_text() == "original"


@pytest.mark.asyncio
async def test_create_file_overwrite(sandbox: Path) -> None:
    target = sandbox / "existing.txt"
    target.write_text("original")
    result = await CreateFileTool().execute(file_path=str(target), content="replaced", overwrite=True)
    assert result.success
    assert target.read_text() == "replaced"


# ── delete_file ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_file_success(sandbox: Path) -> None:
    target = sandbox / "to_delete.txt"
    target.write_text("bye")
    result = await DeleteFileTool().execute(file_path=str(target))
    assert result.success
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_file_not_found(sandbox: Path) -> None:
    result = await DeleteFileTool().execute(file_path=str(sandbox / "ghost.txt"))
    assert not result.success


@pytest.mark.asyncio
async def test_delete_file_refuses_directory(sandbox: Path) -> None:
    d = sandbox / "adir"
    d.mkdir()
    result = await DeleteFileTool().execute(file_path=str(d))
    assert not result.success
    assert "directory" in result.error.lower()


# ── move_file ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_move_file_success(sandbox: Path) -> None:
    src = sandbox / "source.txt"
    src.write_text("data")
    dst = sandbox / "subdir" / "moved.txt"
    result = await MoveFileTool().execute(source=str(src), destination=str(dst))
    assert result.success
    assert dst.read_text() == "data"
    assert not src.exists()


# ── copy_file ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_copy_file_success(sandbox: Path) -> None:
    src = sandbox / "original.txt"
    src.write_text("content")
    dst = sandbox / "copy.txt"
    result = await CopyFileTool().execute(source=str(src), destination=str(dst))
    assert result.success
    assert dst.read_text() == "content"
    assert src.exists()


# ── rename_file ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rename_file_success(sandbox: Path) -> None:
    src = sandbox / "old_name.txt"
    src.write_text("data")
    result = await RenameFileTool().execute(path=str(src), new_name="new_name.txt")
    assert result.success
    assert (sandbox / "new_name.txt").exists()
    assert not src.exists()


@pytest.mark.asyncio
async def test_rename_file_rejects_path_in_new_name(sandbox: Path) -> None:
    src = sandbox / "file.txt"
    src.write_text("data")
    result = await RenameFileTool().execute(path=str(src), new_name="sub/another.txt")
    assert not result.success


# ── list_directory ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_directory_success(sandbox: Path) -> None:
    (sandbox / "a.txt").write_text("a")
    (sandbox / "b.txt").write_text("b")
    (sandbox / "subdir").mkdir()
    result = await ListDirectoryTool().execute(folder_path=str(sandbox))
    assert result.success
    assert "a.txt" in result.output
    assert "b.txt" in result.output
    assert "subdir" in result.output


@pytest.mark.asyncio
async def test_list_directory_not_found(sandbox: Path) -> None:
    result = await ListDirectoryTool().execute(folder_path=str(sandbox / "nodir"))
    assert not result.success


@pytest.mark.asyncio
async def test_list_directory_empty(sandbox: Path) -> None:
    empty = sandbox / "empty"
    empty.mkdir()
    result = await ListDirectoryTool().execute(folder_path=str(empty))
    assert result.success
    assert "empty" in result.output.lower()


# ── search_files ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_files_finds_matches(sandbox: Path) -> None:
    (sandbox / "hello.py").write_text("")
    (sandbox / "world.py").write_text("")
    (sandbox / "readme.md").write_text("")
    result = await SearchFilesTool().execute(folder_path=str(sandbox), pattern="*.py")
    assert result.success
    assert "hello.py" in result.output
    assert "readme.md" not in result.output


@pytest.mark.asyncio
async def test_search_files_no_matches(sandbox: Path) -> None:
    result = await SearchFilesTool().execute(folder_path=str(sandbox), pattern="*.xyz")
    assert result.success
    assert "no files" in result.output.lower()


@pytest.mark.asyncio
async def test_search_files_recursive(sandbox: Path) -> None:
    sub = sandbox / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("")
    result = await SearchFilesTool().execute(folder_path=str(sandbox), pattern="*.py", recursive=True)
    assert result.success
    assert "deep.py" in result.output


# ── open_folder ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_open_folder_calls_startfile(sandbox: Path) -> None:
    with patch("app.tools.filesystem.tools.os.startfile") as mock_sf:
        result = await OpenFolderTool().execute(folder_path=str(sandbox))
    assert result.success
    mock_sf.assert_called_once_with(str(sandbox))


@pytest.mark.asyncio
async def test_open_folder_not_found(sandbox: Path) -> None:
    result = await OpenFolderTool().execute(folder_path=str(sandbox / "nope"))
    assert not result.success
