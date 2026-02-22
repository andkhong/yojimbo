import re
from datetime import datetime

from pydantic import BaseModel, field_validator

# E.164 phone format: +[country code][number], 7-15 digits total
_PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")
# Simplified email regex (RFC 5322 compliant enough for our use)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SUPPORTED_LANGUAGES = {
    "en",
    "es",
    "zh",
    "vi",
    "ko",
    "tl",
    "ar",
    "fr",
    "de",
    "ja",
    "pt",
    "hi",
    "ru",
    "it",
    "pl",
    "fa",
    "uk",
    "tr",
    "he",
    "th",
}


class ContactBase(BaseModel):
    phone_number: str
    name: str | None = None
    preferred_language: str = "en"
    email: str | None = None
    notes: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Require E.164 format: +<country><number>, 8-15 chars total."""
        v = v.strip()
        if not _PHONE_RE.match(v):
            raise ValueError(
                f"Phone number must be in E.164 format (e.g. +15551234567). Got: {v!r}"
            )
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email address: {v!r}")
        return v

    @field_validator("preferred_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in SUPPORTED_LANGUAGES:
            # Accept but warn — don't hard-reject unknown languages
            # (governments may serve languages not in our list)
            pass
        if len(v) > 10:
            raise ValueError(f"Language code too long: {v!r}")
        return v


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = None
    preferred_language: str | None = None
    email: str | None = None
    notes: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email address: {v!r}")
        return v


class ContactResponse(ContactBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
