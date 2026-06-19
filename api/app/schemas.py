import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

OBLIGATIONS = {"obligatoire", "souhaité", "optionnel"}

_OBLIGATION_SYNONYMS = {
    "obligatoire": "obligatoire", "obligation": "obligatoire", "obligatoires": "obligatoire",
    "required": "obligatoire", "mandatory": "obligatoire", "must": "obligatoire",
    "doit": "obligatoire", "impératif": "obligatoire", "imperatif": "obligatoire",
    "exigé": "obligatoire", "exige": "obligatoire", "exigée": "obligatoire",
    "souhaité": "souhaité", "souhaite": "souhaité", "souhaitée": "souhaité",
    "souhaitable": "souhaité", "recommandé": "souhaité", "recommande": "souhaité",
    "apprécié": "souhaité", "apprecie": "souhaité", "preferred": "souhaité",
    "optionnel": "optionnel", "optionnelle": "optionnel", "optional": "optionnel",
    "facultatif": "optionnel", "facultative": "optionnel", "peut": "optionnel",
}


def _normalize_obligation(value) -> str:
    if not value:
        return "obligatoire"
    s = str(value).strip().lower()
    if s in OBLIGATIONS:
        return s
    return _OBLIGATION_SYNONYMS.get(s, "obligatoire")


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


# --- Sprint 2 : exigences ---

class ExtractedRequirement(BaseModel):
    """Élément renvoyé par le LLM (validé avant insertion)."""

    text: str
    category: str | None = None
    obligation: str = "obligatoire"
    code: str | None = None
    source_excerpt: str | None = None

    @field_validator("obligation", mode="before")
    @classmethod
    def _norm(cls, v):
        return _normalize_obligation(v)


class RequirementsLLM(BaseModel):
    requirements: list[ExtractedRequirement] = []


class ExtractIn(BaseModel):
    document_id: uuid.UUID


class RequirementCreate(BaseModel):
    text: str
    category: str | None = None
    obligation: str = "obligatoire"
    code: str | None = None
    source_excerpt: str | None = None
    document_id: uuid.UUID | None = None

    @field_validator("obligation", mode="before")
    @classmethod
    def _norm(cls, v):
        return _normalize_obligation(v)


class RequirementUpdate(BaseModel):
    text: str | None = None
    category: str | None = None
    obligation: str | None = None
    code: str | None = None
    source_excerpt: str | None = None
    status: str | None = None


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID | None
    code: str | None
    text: str
    category: str | None
    obligation: str
    source_excerpt: str | None
    status: str
    created_at: datetime
