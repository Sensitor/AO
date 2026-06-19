import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_active_subscription
from ..export import build_response_docx
from ..llm import PLACEHOLDER, generate_section
from ..models import ComplianceEntry, Project, Requirement, Section, User
from ..schemas import SectionOut, SectionUpdate

router = APIRouter(prefix="/projects/{project_id}/sections", tags=["sections"])


def _owned_project(project_id: uuid.UUID, db: Session, user: User) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.org_id == user.org_id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


def _section_for(
    project_id: uuid.UUID, requirement_id: uuid.UUID, db: Session, user: User
) -> Section:
    section = (
        db.query(Section)
        .filter(
            Section.project_id == project_id,
            Section.org_id == user.org_id,
            Section.requirement_id == requirement_id,
        )
        .first()
    )
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Section not found"
        )
    return section


@router.post("/generate", response_model=list[SectionOut])
def generate_sections(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_subscription),
):
    """Rédige une section par exigence à partir des preuves internes de la matrice.

    Zones non couvertes => [À compléter]. Idempotent : préserve les sections
    éditées manuellement (status='edited').
    """
    _owned_project(project_id, db, user)
    requirements = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            Requirement.org_id == user.org_id,
            Requirement.status != "rejected",
        )
        .order_by(Requirement.created_at.asc())
        .all()
    )
    compliance = {
        e.requirement_id: e
        for e in db.query(ComplianceEntry)
        .filter(
            ComplianceEntry.project_id == project_id,
            ComplianceEntry.org_id == user.org_id,
        )
        .all()
    }
    existing = {
        s.requirement_id: s
        for s in db.query(Section)
        .filter(Section.project_id == project_id, Section.org_id == user.org_id)
        .all()
    }

    try:
        for req in requirements:
            section = existing.get(req.id)
            if section is not None and section.status == "edited":
                continue  # on préserve l'édition manuelle
            entry = compliance.get(req.id)
            excerpts = []
            if entry is not None and entry.verdict != "manquant":
                excerpts = [s["excerpt"] for s in (entry.sources or []) if s.get("excerpt")]
            content = generate_section(req.text, req.obligation, excerpts)
            title = f"{req.code} — {req.text}" if req.code else req.text
            if section is None:
                section = Section(
                    org_id=user.org_id,
                    project_id=project_id,
                    requirement_id=req.id,
                    title=title,
                    content=content,
                )
                db.add(section)
            else:
                section.title = title
                section.content = content
            section.status = "generated" if content != PLACEHOLDER else "empty"
        db.commit()
    except Exception as exc:  # noqa: BLE001 — erreur LLM
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec génération des sections: {exc}",
        )

    return (
        db.query(Section)
        .join(Requirement, Section.requirement_id == Requirement.id)
        .filter(Section.project_id == project_id, Section.org_id == user.org_id)
        .order_by(Requirement.created_at.asc())
        .all()
    )


@router.get("", response_model=list[SectionOut])
def list_sections(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    return (
        db.query(Section)
        .join(Requirement, Section.requirement_id == Requirement.id)
        .filter(Section.project_id == project_id, Section.org_id == user.org_id)
        .order_by(Requirement.created_at.asc())
        .all()
    )


@router.get("/export")
def export_docx(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_subscription),
):
    """Exporte la réponse assemblée en .docx."""
    project = _owned_project(project_id, db, user)
    rows = (
        db.query(Section, Requirement, ComplianceEntry)
        .join(Requirement, Section.requirement_id == Requirement.id)
        .outerjoin(
            ComplianceEntry, ComplianceEntry.requirement_id == Requirement.id
        )
        .filter(Section.project_id == project_id, Section.org_id == user.org_id)
        .order_by(Requirement.created_at.asc())
        .all()
    )
    items = [
        {
            "title": section.title,
            "content": section.content,
            "obligation": req.obligation,
            "verdict": entry.verdict if entry else None,
        }
        for section, req, entry in rows
    ]
    data = build_response_docx(project.name, items)
    filename = f"reponse_{project_id}.docx"
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{requirement_id}", response_model=SectionOut)
def get_section(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    return _section_for(project_id, requirement_id, db, user)


@router.patch("/{requirement_id}", response_model=SectionOut)
def update_section(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: SectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Édition manuelle d'une section (passe en status='edited', préservé au regénérer)."""
    _owned_project(project_id, db, user)
    section = _section_for(project_id, requirement_id, db, user)
    fields = data.model_dump(exclude_unset=True)
    for field in ("title", "content"):
        if fields.get(field) is not None:
            setattr(section, field, fields[field])
    section.status = fields.get("status") or "edited"
    db.commit()
    db.refresh(section)
    return section


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    section = _section_for(project_id, requirement_id, db, user)
    db.delete(section)
    db.commit()
