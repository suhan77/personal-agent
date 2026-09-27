from pathlib import Path
from typing import Annotated
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed

logger = logging.getLogger(__name__)

MAX_TEXT_BYTES = 200_000


def resolve_workspace_file(working_directory: str, path: str) -> Path:
    if not isinstance(working_directory, str) or not working_directory.strip():
        raise ValueError("Working directory is required")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("File path is required")
    root = Path(working_directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Directory not found: {root}")
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("File path must be relative to the working directory")
    cursor = root
    for component in relative.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError("Symbolic links are not allowed in file paths")
    target = (root / relative).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("File path must stay within the working directory")
    return target


@tool
def read_file(path: str, working_directory: Annotated[str, InjectedState("working_directory")]) -> str:
    """작업 디렉터리 안의 UTF-8 텍스트 파일을 읽는다. path는 상대 경로다."""
    target = resolve_workspace_file(working_directory, path)
    if not target.is_file() or target.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("File is missing or too large")
    return target.read_text(encoding="utf-8")


@tool
def update_file(path: str, old_text: str, new_text: str) -> str:
    """파일의 기존 문구를 새 문구로 바꿀 변경안을 제안한다. 실제 수정은 사용자 승인 후에만 한다."""
    return "변경안 검토 대기"


@tool
@log_timed(LogMessages.DIRECTORY_TOOL)
def list_directory(
    working_directory: Annotated[str, InjectedState("working_directory")],
) -> list[dict[str, str]]:
    """현재 작업 디렉터리의 파일과 하위 디렉터리 목록을 조회한다."""
    directory = Path(working_directory).expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Directory not found: {directory}")

    entries = [
        {"name": entry.name, "type": "directory" if entry.is_dir() else "file"}
        for entry in sorted(directory.iterdir(), key=lambda item: item.name.lower())
    ]
    logger.info(LogMessages.DIRECTORY_LISTING, directory, len(entries))
    return entries


@tool
@log_timed(LogMessages.FILE_CREATION_TOOL)
def create_file(
    path: str,
    working_directory: Annotated[str, InjectedState("working_directory")],
    content: str = "",
) -> str:
    """사용자 승인 후 새 파일을 현재 작업 디렉터리에 만든다.

    path는 현재 작업 디렉터리 기준 상대 경로다. 기존 파일은 덮어쓰지 않는다.
    """
    if not isinstance(working_directory, str) or not working_directory.strip():
        raise ValueError("Working directory is required")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("File path is required")

    directory = Path(working_directory).expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Directory not found: {directory}")

    relative_path = Path(path)
    if relative_path.is_absolute():
        raise ValueError("File path must be relative to the working directory")

    target = (directory / relative_path).resolve()
    if target == directory or not target.is_relative_to(directory):
        raise ValueError("File path must stay within the working directory")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"Parent directory not found: {target.parent}")

    with target.open("x", encoding="utf-8") as file:
        file.write(content)

    logger.info(LogMessages.FILE_CREATED, target, len(content))
    return str(target)
