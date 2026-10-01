"""Request schemas for Talent ID administration."""

from datetime import time

from pydantic import BaseModel, Field


class CreateSiteRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=32)
    timezone: str = Field(default="America/Bogota", min_length=3, max_length=64)


class CreateScheduleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    start_time: time
    end_time: time
    tolerance_minutes: int = Field(default=0, ge=0, le=180)


class ConfigureEmployeeAttendanceRequest(BaseModel):
    site_id: str
    schedule_id: str
    attendance_eligible: bool = True


class ProvisionKioskRequest(BaseModel):
    site_id: str
    name: str = Field(min_length=2, max_length=120)
