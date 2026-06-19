import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .config import settings
from .database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="org")
    projects = relationship("Project", back_populates="org")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="owner")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Organization", back_populates="users")


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    buyer_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="draft")
    deadline = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    org = relationship("Organization", back_populates="projects")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    # "internal" = base documentaire interne, "tender" = AO à analyser
    kind = Column(String, nullable=False, default="internal")
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    s3_key = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=True)
    # pending -> processing -> ready | failed
    status = Column(String, nullable=False, default="pending")
    error = Column(String, nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.embedding_dim), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Document AO source (null si exigence ajoutée manuellement).
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    code = Column(String, nullable=True)  # référence/article dans l'AO si présent
    text = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    # obligatoire | souhaité | optionnel
    obligation = Column(String, nullable=False, default="obligatoire")
    source_excerpt = Column(Text, nullable=True)  # passage source (pour la revue)
    # extracted | validated | rejected | edited | manual
    status = Column(String, nullable=False, default="extracted")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ComplianceEntry(Base):
    __tablename__ = "compliance_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # conforme | partiel | manquant
    verdict = Column(String, nullable=False, default="manquant")
    rationale = Column(Text, nullable=True)
    # preuves internes citées : [{document_id, filename, chunk_index, excerpt, score}]
    sources = Column(JSONB, nullable=False, server_default="[]")
    # auto (jugement LLM) | adjusted (override manuel, préservé au rebuild)
    status = Column(String, nullable=False, default="auto")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Section(Base):
    __tablename__ = "sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="[À compléter]")
    # generated (rédigé sourcé) | empty ([À compléter]) | edited (modifié à la main)
    status = Column(String, nullable=False, default="generated")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True
    )
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    plan = Column(String, nullable=True)
    # none | trialing | active | past_due | canceled | incomplete | unpaid
    status = Column(String, nullable=False, default="none")
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
