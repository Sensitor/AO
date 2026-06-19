import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_active_subscription
from ..llm import extract_requirements
from ..models import Document, Project, Requirement, User
from ..schemas import (
    ExtractIn,
    RequirementCreate,
    RequirementOut,
    RequirementUpdate,
)
from ..storage import download_bytes
from ..text_extract import extract_text

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


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


def _owned_requirement(
    project_id: uuid.UUID, req_id: uuid.UUID, db: Session, user: User
) -> Requirement:
    req = (
        db.query(Requirement)
        .filter(
            Requirement.id == req_id,
            Requirement.project_id == project_id,
            Requirement.org_id == user.org_id,
        )
        .first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found"
        )
    return req


@router.post(
    "/extract",
    response_model=list[RequirementOut],
    status_code=status.HTTP_201_CREATED,
)
def extract_project_requirements(
    project_id: uuid.UUID,
    body: ExtractIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_subscription),
):
    """Extrait les exigences d'un document AO via LLM et les stocke (ré-extraction idempotente)."""
    _owned_project(project_id, db, user)
    document = (
        db.query(Document)
        .filter(Document.id == body.document_id, Document.org_id == user.org_id)
        .first()
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    raw = download_bytes(document.s3_key)
    try:
        text = extract_text(raw, document.content_type, document.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    try:
        extracted = extract_requirements(text)
    except Exception as exc:  # noqa: BLE001 — erreur LLM/réseau
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec extraction LLM: {exc}",
        )

    # Ré-extraction idempotente pour ce document dans ce projet.
    db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.document_id == document.id,
    ).delete()

    created: list[Requirement] = []
    for item in extracted:
        req = Requirement(
            org_id=user.org_id,
            project_id=project_id,
            document_id=document.id,
            code=item.code,
            text=item.text,
            category=item.category,
            obligation=item.obligation,
            source_excerpt=item.source_excerpt,
            status="extracted",
        )
        db.add(req)
        created.append(req)
    db.commit()
    for req in created:
        db.refresh(req)
    return created


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_project(project_id, db, user)
    return (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            Requirement.org_id == user.org_id,
        )
        .order_by(Requirement.created_at.asc())
        .all()
    )


@router.post("", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def add_requirement(
    project_id: uuid.UUID,
    data: RequirementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ajout manuel d'une exigence (l'écran de revue peut compléter ce que le LLM a manqué)."""
    _owned_project(project_id, db, user)
    if data.document_id is not None:
        owns_doc = (
            db.query(Document)
            .filter(Document.id == data.document_id, Document.org_id == user.org_id)
            .first()
        )
        if not owns_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
    req = Requirement(
        org_id=user.org_id,
        project_id=project_id,
        document_id=data.document_id,
        code=data.code,
        text=data.text,
        category=data.category,
        obligation=data.obligation,
        source_excerpt=data.source_excerpt,
        status="manual",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/{req_id}", response_model=RequirementOut)
def get_requirement(
    project_id: uuid.UUID,
    req_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _owned_requirement(project_id, req_id, db, user)


@router.patch("/{req_id}", response_model=RequirementOut)
def update_requirement(
    project_id: uuid.UUID,
    req_id: uuid.UUID,
    data: RequirementUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Revue manuelle : éditer le texte/catégorie/obligation ou valider/rejeter."""
    req = _owned_requirement(project_id, req_id, db, user)
    fields = data.model_dump(exclude_unset=True)
    if "obligation" in fields and fields["obligation"] is not None:
        from ..schemas import _normalize_obligation

        fields["obligation"] = _normalize_obligation(fields["obligation"])
    for field, value in fields.items():
        setattr(req, field, value)
    db.commit()
    db.refresh(req)
    return req


@router.delete("/{req_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(
    project_id: uuid.UUID,
    req_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    req = _owned_requirement(project_id, req_id, db, user)
    db.delete(req)
    db.commit()
