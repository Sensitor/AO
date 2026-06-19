"""Embeddings via l'API OpenAI (text-embedding-3-small par défaut, 1536 dims)."""
from functools import lru_cache

from openai import OpenAI

from .config import settings

_BATCH = 100


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        resp = client.embeddings.create(
            model=settings.embedding_model, input=texts[i : i + _BATCH]
        )
        out.extend(item.embedding for item in resp.data)
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
