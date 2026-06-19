import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..embeddings import embed_query
from ..models import Document, DocumentChunk, Project, User
from ..pipeline import process_document
from ..schemas import ChunkMatch, DocumentOut, SearchIn
from ..storage import delete_object, upload_fileobj

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_KINDS = {"internal", "tender"}  # base documentaire interne / AO à analyser


def _get_owned_document(document_id: uuid.UUID, db: Session, user: User) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.org_id == user.org_id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return doc


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form("internal"),
    project_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind doit être l'un de {sorted(ALLOWED_KINDS)}",
        )
    if project_id is not None:
        owns = (
            db.query(Project)
            .filter(Project.id == project_id, Project.org_id == user.org_id)
            .first()
        )
        if not owns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

    document_id = uuid.uuid4()
    key = f"{user.org_id}/{document_id}/{file.filename}"
    upload_fileobj(file.file, key, file.content_type)

    doc = Document(
        id=document_id,
        org_id=user.org_id,
        project_id=project_id,
        kind=kind,
        filename=file.filename,
        content_type=file.content_type,
        s3_key=key,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Ingestion asynchrone (parsing + chunking + embeddings).
    background.add_task(process_document, doc.id)
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return (
        db.query(Document)
        .filter(Document.org_id == user.org_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_owned_document(document_id, db, user)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, user)
    try:
        delete_object(doc.s3_key)
    except Exception:  # noqa: BLE001 — best effort, on supprime la ligne quand même
        pass
    db.delete(doc)  # chunks supprimés en cascade (ondelete=CASCADE)
    db.commit()


@router.post("/search", response_model=list[ChunkMatch])
def search_documents(
    body: SearchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recherche sémantique dans les chunks de l'organisation (RAG, base Sprint 3)."""
    if not body.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query vide"
        )
    k = max(1, min(body.k, 50))
    q_vec = embed_query(body.query)
    distance = DocumentChunk.embedding.cosine_distance(q_vec)
    rows = (
        db.query(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            DocumentChunk.org_id == user.org_id,
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(distance)
        .limit(k)
        .all()
    )
    return [
        ChunkMatch(
            document_id=chunk.document_id,
            filename=filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=1.0 - float(dist),
        )
        for chunk, filename, dist in rows
    ]
