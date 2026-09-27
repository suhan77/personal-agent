"""Swift EventKit을 통해 실제 미리 알림을 검색하는 읽기 전용 도구."""

from datetime import date

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from personal_agent.services.native_tool_bridge import call_native_tool


class ReminderSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="필수. 제목에 포함된 검색어")
    due_date: date | None = Field(default=None, description="선택. YYYY-MM-DD 형식의 예정일")
    list_name: str | None = Field(default=None, description="선택. 미리 알림 목록 이름")
    include_completed: bool = Field(default=False, description="선택. 완료된 미리 알림도 포함할지 여부")

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search query must not be blank")
        return value.strip()


@tool("find_reminders", args_schema=ReminderSearchInput)
async def find_reminders(query: str, due_date: date | None = None,
                         list_name: str | None = None, include_completed: bool = False) -> dict:
    """
    macOS 미리 알림에서 제목 검색어와 선택한 날짜·목록에 맞는 항목을 조회한다.
    수정·삭제 대상을 찾을 때 사용하며, 미리 알림을 변경하지 않는다.
    최대 10건을 반환한다. truncated가 참이면 날짜·목록으로 검색을 좁힌다.
    """
    arguments = ReminderSearchInput.model_validate({"query": query, "due_date": due_date,
                                                    "list_name": list_name,
                                                    "include_completed": include_completed})
    result = await call_native_tool("find_reminders", arguments.model_dump(mode="json"), timeout=120)
    if (not isinstance(result, dict) or not isinstance(result.get("items"), list)
            or not isinstance(result.get("truncated"), bool)):
        raise ValueError("Invalid reminder search result")
    return result
