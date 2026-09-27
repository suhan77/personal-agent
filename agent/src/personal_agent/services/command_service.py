"""Safe filesystem commands for the local agent worker."""
from pathlib import Path


class CommandService:
    def __init__(self, working_directory: Path) -> None:
        self._working_directory = self._validate_directory(working_directory)

    @property
    def working_directory(self) -> Path:
        return self._working_directory

    def set_working_directory(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Working directory path is required")
        directory = self._validate_directory(Path(path).expanduser().resolve())
        self._working_directory = directory
        return directory

    @staticmethod
    def _validate_directory(path: Path) -> Path:
        path = path.expanduser().resolve()
        if not path.is_dir():
            raise NotADirectoryError(f"Working directory not found: {path}")
        return path
