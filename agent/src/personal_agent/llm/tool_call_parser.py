import json
import re
from typing import Any
from uuid import uuid4

_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*<function=([^>\s]+)>\s*(.*?)\s*</function>\s*</tool_call>",
    re.DOTALL,
)
_PARAMETER_PATTERN = re.compile(
    r"<parameter=([^>\s]+)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)


def parse_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    """Granite의 XML tool 호출 출력을 LangChain 형식으로 변환한다."""
    tool_calls: list[dict[str, Any]] = []

    for match in _TOOL_CALL_PATTERN.finditer(content):
        arguments = {
            name: _parse_argument(value)
            for name, value in _PARAMETER_PATTERN.findall(match.group(2))
        }
        tool_calls.append(
            {
                "name": match.group(1),
                "args": arguments,
                "id": f"call_{uuid4().hex}",
            }
        )

    return _TOOL_CALL_PATTERN.sub("", content).strip(), tool_calls


def _parse_argument(value: str) -> Any:
    value = value.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
