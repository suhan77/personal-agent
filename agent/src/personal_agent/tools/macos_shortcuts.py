from pathlib import Path

from langchain_core.tools import tool


_CATALOG_DIR = Path(__file__).resolve().parents[1] / "data" / "macos_shortcuts"
_APP_FILES = {
    "finder": "finder.md",
    "파인더": "finder.md",
    "spotlight": "spotlight.md",
    "스포트라이트": "spotlight.md",
    "text": "text_editing.md",
    "text editing": "text_editing.md",
    "텍스트": "text_editing.md",
    "텍스트 편집": "text_editing.md",
}


@tool("get_macos_shortcuts")
def get_macos_shortcuts(app: str = "all") -> str:
    """선택한 범위의 macOS 단축키 문서를 반환한다.

    Args:
        app: finder, spotlight, text 또는 all. 앱이 지정된 질문은 해당 앱을 선택하고,
            특정 앱이 없는 일반 질문은 all을 사용한다. 앱별 문서에는 공통 단축키도 포함된다.
    """
    normalized_app = app.strip().casefold()
    if normalized_app in {"all", "전체", "모두", "macos", "mac os", ""}:
        files = ["common.md", "finder.md", "spotlight.md", "text_editing.md"]
    elif normalized_app in _APP_FILES:
        files = ["common.md", _APP_FILES[normalized_app]]
    else:
        supported = "finder, spotlight, text, all"
        raise ValueError(f"Unsupported macOS shortcut catalog '{app}'. Choose one of: {supported}.")

    documents = []
    for filename in files:
        path = _CATALOG_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"macOS shortcut catalog not found: {path}")
        documents.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(documents)
