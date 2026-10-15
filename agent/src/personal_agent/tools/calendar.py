"""macOS 캘린더 일정 조회·생성·수정 도구."""
from datetime import datetime

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from personal_agent.services.native_tool_bridge import call_native_tool


class EventTimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: datetime = Field(description="시작 시각, 시간대가 포함된 ISO 8601")
    end: datetime = Field(description="종료 시각, 시간대가 포함된 ISO 8601")

    @model_validator(mode="after")
    def validate_range(self):
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("시간대를 포함해야 합니다")
        if self.end <= self.start or (self.end - self.start).days > 366:
            raise ValueError("조회 기간은 0일 초과 366일 이하여야 합니다")
        return self


class EventSearch(EventTimeRange):
    query: str = Field(default="", description="일정 제목에 포함된 검색어. 빈 문자열이면 전체")


class EventCreate(EventTimeRange):
    title: str = Field(min_length=1, description="일정 제목")
    location: str = ""
    notes: str = ""
    calendar_name: str | None = None

    @model_validator(mode="after")
    def validate_title(self):
        if not self.title.strip():
            raise ValueError("제목이 필요합니다")
        return self


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=1, description="find_calendar_events 결과의 identifier")
    revision: str = Field(min_length=1, description="조회 결과의 revision, 변경 감지용")
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        changes = self.model_fields_set - {"identifier", "revision"}
        if not changes or any(getattr(self, key) is None for key in changes):
            raise ValueError("변경할 값만 지정하세요. null은 지원하지 않습니다")
        if self.title is not None and not self.title.strip():
            raise ValueError("제목이 필요합니다")
        for value in (self.start, self.end):
            if value is not None and value.utcoffset() is None:
                raise ValueError("시간대를 포함해야 합니다")
        if self.start and self.end and self.end <= self.start:
            raise ValueError("종료는 시작 이후여야 합니다")
        return self


@tool("find_calendar_events", args_schema=EventSearch)
async def find_calendar_events(**fields) -> dict:
    """macOS 캘린더의 일정 목록 확인과 제목 검색을 위한 조회 도구.

    지정한 기간에 해당하는 일정을 최대 50건 반환한다.
    """
    args = EventSearch.model_validate(fields)
    return await call_native_tool("find_calendar_events", args.model_dump(mode="json"), timeout=120)


@tool("create_calendar_event", args_schema=EventCreate)
async def create_calendar_event(**fields) -> dict:
    """macOS 캘린더에 새 시간 일정을 추가하는 도구.

    제목·시작·종료 시각과 선택적인 장소·메모·캘린더 이름을 지원한다.
    반복·종일 일정 및 참석자 설정은 지원 범위에 포함되지 않는다.
    """
    args = EventCreate.model_validate(fields)
    return await call_native_tool("create_calendar_event", args.model_dump(mode="json"), timeout=120)


@tool("update_calendar_event", args_schema=EventUpdate)
async def update_calendar_event(**fields) -> dict:
    """macOS 캘린더의 기존 일정 제목·시작·종료 시각·장소·메모를 부분 수정하는 도구.

    조회 결과의 식별자와 버전으로 수정 대상을 구분한다.
    반복·종일·참석자가 있는 일정은 수정 지원 범위에 포함되지 않는다.
    """
    args = EventUpdate.model_validate({key: value for key, value in fields.items() if value is not None})
    return await call_native_tool("update_calendar_event", args.model_dump(mode="json", exclude_unset=True), timeout=120)
