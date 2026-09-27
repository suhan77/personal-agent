"""미리 알림 등록 전에 사용자에게 보여줄 제안 데이터."""

from datetime import date, time
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepeatFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ReminderPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReminderProposal(BaseModel):
    """승인 전에 검증할 미리 알림 내용. 이 모델은 저장을 수행하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="필수. 미리 알림 제목")
    due_date: date = Field(description="필수. YYYY-MM-DD 형식의 날짜")
    due_time: time | None = Field(default=None, description="선택. HH:MM 형식의 시간. 없으면 종일")
    notes: str | None = Field(default=None, max_length=10_000, description="선택. 메모")
    url: str | None = Field(default=None, description="선택. 관련 웹 주소(http 또는 https)")
    list_name: str | None = Field(default=None, description="선택. 저장할 목록 이름. 없으면 기본 목록")
    repeat: RepeatFrequency | None = Field(default=None, description="선택. 매일·매주·매월·매년 반복")
    priority: ReminderPriority | None = Field(default=None, description="선택. 낮음·보통·높음 우선순위")
    unsupported_options: list[str] = Field(default_factory=list, description="요청받았지만 자동 저장이 확인되지 않은 옵션. 있으면 제안을 진행하지 않는다")

    @field_validator("title", "list_name")
    @classmethod
    def nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip() if value is not None else None

    @field_validator("url")
    @classmethod
    def web_url_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must be an HTTP(S) web address")
        return value
