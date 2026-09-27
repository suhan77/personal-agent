from pathlib import Path
from typing import Annotated
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed

logger = logging.getLogger(__name__)


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
