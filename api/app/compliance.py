"""Évaluation de conformité d'une exigence (RAG base interne + jugement LLM sourcé).

Règle absolue : pas de preuve interne = MANQUANT. Aucune invention.
"""
from sqlalchemy.orm import Session

from .config import settings
from .embeddings import embed_query
from .llm import judge_compliance
from .models import Document, DocumentChunk, Requirement


def _search_internal(db: Session, org_id, query: str, k: int):
    """Top-k chunks de la base documentaire INTERNE (kind='internal') de l'org."""
    q_vec = embed_query(query)
    distance = DocumentChunk.embedding.cosine_distance(q_vec)
    return (
        db.query(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            Document.org_id == org_id,
            Document.kind == "internal",
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(distance)
        .limit(k)
        .all()
    )


def assess_requirement(db: Session, org_id, requirement: Requirement) -> dict:
    """Retourne {verdict, rationale, sources} pour une exigence."""
    rows = _search_internal(db, org_id, requirement.text, settings.compliance_top_k)

    sources = [
        {
            "document_id": str(chunk.document_id),
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "excerpt": chunk.content,
            "score": round(1.0 - float(dist), 4),
        }
        for chunk, filename, dist in rows
    ]
    excerpts = [s["excerpt"] for s in sources]

    judgment = judge_compliance(requirement.text, excerpts)
    return {
        "verdict": judgment.verdict,
        "rationale": judgment.rationale,
        "sources": sources,
    }
