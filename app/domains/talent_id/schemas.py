"""Request schemas for Talent ID administration."""

from datetime import time
from typing import Literal

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


class UpdateKioskRequest(BaseModel):
    site_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    active: bool | None = None



class RequestBiometricConsentOtp(BaseModel):
    decision: Literal["AUTHORIZED", "DENIED", "REVOKED"]
    document_version: str = Field(min_length=1, max_length=32)


class SignBiometricConsentRequest(BaseModel):
    decision: Literal["AUTHORIZED", "DENIED", "REVOKED"]
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    document_version: str = Field(min_length=1, max_length=32)



class RegisterMobileDeviceRequest(BaseModel):
    label: str = Field(default="Mi celular", min_length=2, max_length=80)
    public_key_jwk: dict
    link_challenge_id: str = Field(min_length=8, max_length=80)
    link_otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class IssueMobileQrRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=80)
    challenge_id: str = Field(min_length=8, max_length=80)
    nonce: str = Field(min_length=16, max_length=256)
    signature: str = Field(min_length=32, max_length=256)


class KioskQrAttendanceRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    event_type: Literal["check_in", "check_out"]
