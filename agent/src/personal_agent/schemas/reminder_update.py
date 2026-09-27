"""기존 미리 알림을 부분 변경하기 위한 검증 모델."""

from datetime import date, time
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from personal_agent.schemas.reminder import ReminderPriority, RepeatFrequency


ClearableField = Literal["due_time", "notes", "url", "repeat", "priority"]


class ReminderUpdateFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    due_time: time | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    url: str | None = None
    list_name: str | None = None
    repeat: RepeatFrequency | None = None
    priority: ReminderPriority | None = None

    @model_validator(mode="after")
    def require_nonnull_values(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("설정할 값은 null일 수 없습니다. 제거하려면 clear를 사용하세요")
        return self

    @field_validator("title", "list_name")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("빈 문자열은 사용할 수 없습니다")
        return value.strip() if value is not None else None

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("HTTP(S) URL만 사용할 수 있습니다")
        return value


class ReminderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, description="find_reminders 결과의 정확한 identifier")
    set: ReminderUpdateFields = Field(default_factory=ReminderUpdateFields, description="새 값으로 설정할 필드만 포함")
    clear: list[ClearableField] = Field(default_factory=list, description="값을 제거할 필드")

    @model_validator(mode="after")
    def validate_patch(self):
        selected = self.set.model_fields_set
        if not selected and not self.clear:
            raise ValueError("변경할 필드가 없습니다")
        if len(set(self.clear)) != len(self.clear) or selected.intersection(self.clear):
            raise ValueError("같은 필드를 중복 변경할 수 없습니다")
        return self
