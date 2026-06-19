import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..compliance import assess_requirement
from ..database import get_db
from ..deps import get_current_user
from ..models import ComplianceEntry, Project, Requirement, User
from ..schemas import ComplianceAdjust, ComplianceOut
from ..schemas import _normalize_verdict

router = APIRouter(prefix="/projects/{project_id}/compliance", tags=["compliance"])


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


def _to_out(entry: ComplianceEntry, req: Requirement | None) -> ComplianceOut:
    return ComplianceOut(
        id=entry.id,
        project_id=entry.project_id,
        requirement_id=entry.requirement_id,
        requirement_text=req.text if req else None,
        obligation=req.obligation if req else None,
        verdict=entry.verdict,
        rationale=entry.rationale,
        sources=entry.sources or [],
        status=entry.status,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _matrix(project_id: uuid.UUID, org_id, db: Session) -> list[ComplianceOut]:
    rows = (
        db.query(ComplianceEntry, Requirement)
        .join(Requirement, ComplianceEntry.requirement_id == Requirement.id)
        .filter(
            ComplianceEntry.project_id == project_id,
            ComplianceEntry.org_id == org_id,
        )
        .order_by(Requirement.created_at.asc())
        .all()
    )
    return [_to_out(entry, req) for entry, req in rows]


@router.post("/build", response_model=list[ComplianceOut])
def build_matrix(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Construit la matrice de conformité (RAG interne + jugement LLM sourcé).

    Idempotent : les entrées ajustées manuellement (`status='adjusted'`) sont
    préservées. Les exigences rejetées sont ignorées.
    """
    _owned_project(project_id, db, user)
    requirements = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            Requirement.org_id == user.org_id,
            Requirement.status != "rejected",
        )
        .all()
    )
    existing = {
        e.requirement_id: e
        for e in db.query(ComplianceEntry)
        .filter(
            ComplianceEntry.project_id == project_id,
            ComplianceEntry.org_id == user.org_id,
        )
        .all()
    }

    try:
        for req in requirements:
            entry = existing.get(req.id)
            if entry is not None and entry.status == "adjusted":
                continue  # on ne clobbere pas un ajustement humain
            result = assess_requirement(db, user.org_id, req)
            if entry is None:
                entry = ComplianceEntry(
                    org_id=user.org_id,
                    project_id=project_id,
                    requirement_id=req.id,
                )
                db.add(entry)
            entry.verdict = result["verdict"]
            entry.rationale = result["rationale"]
            entry.sources = result["sources"]
            entry.status = "auto"
        db.commit()
    except Exception as exc:  # noqa: BLE001 — erreur LLM / embeddings
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec construction de la matrice: {exc}",
        )

    return _matrix(project_id, user.org_id, db)


@router.get("", response_model=list[ComplianceOut])
def get_matrix(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    return _matrix(project_id, user.org_id, db)


@router.get("/{requirement_id}", response_model=ComplianceOut)
def get_entry(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    entry = (
        db.query(ComplianceEntry)
        .filter(
            ComplianceEntry.project_id == project_id,
            ComplianceEntry.org_id == user.org_id,
            ComplianceEntry.requirement_id == requirement_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance entry not found"
        )
    req = db.get(Requirement, requirement_id)
    return _to_out(entry, req)


@router.patch("/{requirement_id}", response_model=ComplianceOut)
def adjust_entry(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: ComplianceAdjust,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ajustement manuel du verdict / de la justification (passe en status='adjusted')."""
    _owned_project(project_id, db, user)
    entry = (
        db.query(ComplianceEntry)
        .filter(
            ComplianceEntry.project_id == project_id,
            ComplianceEntry.org_id == user.org_id,
            ComplianceEntry.requirement_id == requirement_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance entry not found"
        )
    fields = data.model_dump(exclude_unset=True)
    if fields.get("verdict") is not None:
        entry.verdict = _normalize_verdict(fields["verdict"])
    if "rationale" in fields and fields["rationale"] is not None:
        entry.rationale = fields["rationale"]
    entry.status = fields.get("status") or "adjusted"
    db.commit()
    db.refresh(entry)
    req = db.get(Requirement, requirement_id)
    return _to_out(entry, req)
