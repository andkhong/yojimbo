from datetime import datetime

from pydantic import BaseModel


class ContactBase(BaseModel):
    phone_number: str
    name: str | None = None
    preferred_language: str = "en"
    email: str | None = None
    notes: str | None = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = None
    preferred_language: str | None = None
    email: str | None = None
    notes: str | None = None


class ContactResponse(ContactBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
