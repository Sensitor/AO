import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    org_name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    org_id: uuid.UUID
    role: str


class ProjectIn(BaseModel):
    name: str
    buyer_name: str | None = None
    deadline: date | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    buyer_name: str | None = None
    deadline: date | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    buyer_name: str | None
    status: str
    deadline: date | None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID | None
    kind: str
    filename: str
    content_type: str | None
    status: str
    chunk_count: int
    error: str | None
    created_at: datetime


class SearchIn(BaseModel):
    query: str
    k: int = 5


class ChunkMatch(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    score: float
