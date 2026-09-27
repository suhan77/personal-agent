from pathlib import Path
from typing import Annotated
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timing

logger = logging.getLogger(__name__)


@tool
def list_directory(
    working_directory: Annotated[str, InjectedState("working_directory")],
) -> list[dict[str, str]]:
    """현재 작업 디렉터리의 파일과 하위 디렉터리 목록을 조회한다."""
    with log_timing(LogMessages.DIRECTORY_TOOL):
        directory = Path(working_directory).expanduser().resolve()
        if not directory.is_dir():
            raise NotADirectoryError(f"Directory not found: {directory}")

        entries = [
            {"name": entry.name, "type": "directory" if entry.is_dir() else "file"}
            for entry in sorted(directory.iterdir(), key=lambda item: item.name.lower())
        ]
    logger.info(LogMessages.DIRECTORY_LISTING, directory, len(entries))
    return entries
