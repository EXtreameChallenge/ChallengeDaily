"""请求参数校验框架（基于 pydantic）"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from datetime import date
from typing import Optional, Literal


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    context_id: Optional[str] = Field(None, max_length=100)
    image_base64: Optional[str] = None


class SettingsUpdate(BaseModel):
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = Field(None, min_length=10, max_length=500)
    ai_model: Optional[str] = None
    screenshot_interval_sec: Optional[int] = Field(None, ge=10, le=600)
    auto_report_enabled: Optional[bool] = None
    auto_report_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[Literal["low", "medium", "high"]] = "medium"
    due_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class HabitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=50)
    target_count: int = Field(1, ge=1, le=100)
    frequency: Literal["daily", "weekly", "monthly"] = "daily"


class DateRangeRequest(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class WeekPlanCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    week_start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


def validate_json(payload: dict, model_cls):
    """校验 JSON payload，返回 (data, error)"""
    try:
        return model_cls(**payload).model_dump(exclude_none=True), None
    except Exception as e:
        return None, str(e)
