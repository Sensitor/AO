"""Ingestion d'un document : S3 -> texte -> chunks -> embeddings -> document_chunks.

Lancé en tâche de fond via BackgroundTasks. Conformément aux conventions, on reste
sur BackgroundTasks tant que le volume ne justifie pas un worker/Redis dédié.
"""
import logging
import uuid

from .config import settings
from .database import SessionLocal
from .embeddings import embed_texts
from .models import Document, DocumentChunk
from .storage import download_bytes
from .text_extract import chunk_text, extract_text

logger = logging.getLogger("ao.ingestion")


def process_document(document_id: uuid.UUID) -> None:
    """Pipeline complet pour un document. Crée sa propre session DB (tâche de fond)."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = "processing"
        doc.error = None
        db.commit()

        raw = download_bytes(doc.s3_key)
        text = extract_text(raw, doc.content_type, doc.filename)
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)

        # Réingestion idempotente : on repart d'une table de chunks propre.
        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

        if chunks:
            vectors = embed_texts(chunks)
            for idx, (content, vector) in enumerate(zip(chunks, vectors)):
                db.add(
                    DocumentChunk(
                        org_id=doc.org_id,
                        document_id=doc.id,
                        chunk_index=idx,
                        content=content,
                        embedding=vector,
                    )
                )

        doc.chunk_count = len(chunks)
        doc.status = "ready"
        db.commit()
        logger.info("Document %s ingéré: %d chunks", doc.id, len(chunks))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Échec ingestion document %s", document_id)
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
