"""KnowledgeEntry schemas."""

from datetime import datetime

from pydantic import BaseModel


class KnowledgeCreate(BaseModel):
    department_id: int | None = None
    question: str
    answer: str
    language: str = "en"
    category: str | None = None
    created_by: str | None = None


class KnowledgeUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    language: str | None = None
    category: str | None = None
    is_active: bool | None = None
    department_id: int | None = None


class KnowledgeResponse(BaseModel):
    id: int
    department_id: int | None = None
    question: str
    answer: str
    language: str
    category: str | None = None
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
