"""Extraction des exigences d'un AO via LLM (sortie JSON validée Pydantic).

Règle absolue du produit : ne jamais inventer. On n'extrait que ce qui figure
explicitement dans le texte de l'appel d'offres.
"""
import json
import logging
from functools import lru_cache

from openai import OpenAI

from .config import settings
from .schemas import ExtractedRequirement, RequirementsLLM
from .text_extract import chunk_text

logger = logging.getLogger("ao.llm")

SYSTEM_PROMPT = (
    "Tu analyses un appel d'offres (AO) pour une entreprise qui doit y répondre. "
    "Ta tâche : extraire la liste des EXIGENCES que le répondant doit satisfaire.\n"
    "Règles impératives :\n"
    "1. N'invente JAMAIS une exigence : extrais uniquement ce qui figure "
    "explicitement dans le texte fourni.\n"
    "2. Une exigence = une attente vérifiable (technique, fonctionnelle, juridique, "
    "sécurité, RH, financière, délai, etc.).\n"
    "3. Pour chaque exigence, renseigne :\n"
    "   - text : reformulation concise et fidèle de l'exigence ;\n"
    "   - category : catégorie courte (ex: technique, fonctionnel, juridique, "
    "sécurité, financier, RH, délai) ;\n"
    "   - obligation : 'obligatoire' (doit/exigé/impératif), 'souhaité' "
    "(souhaité/apprécié/recommandé) ou 'optionnel' (peut/facultatif) ;\n"
    "   - code : référence/article de l'AO si présent, sinon null ;\n"
    "   - source_excerpt : court extrait du texte source qui justifie l'exigence.\n"
    "4. Réponds STRICTEMENT en JSON valide, sans texte autour, au format : "
    '{"requirements": [{"text": "...", "category": "...", '
    '"obligation": "...", "code": null, "source_excerpt": "..."}]}\n'
    "Si aucune exigence n'est présente, renvoie {\"requirements\": []}."
)


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _parse(content: str) -> RequirementsLLM:
    try:
        return RequirementsLLM.model_validate_json(content)
    except Exception:
        # Tolérance : certains modèles enrobent le JSON.
        try:
            return RequirementsLLM.model_validate(json.loads(content))
        except Exception:
            logger.warning("Réponse LLM non parsable: %.200s", content)
            return RequirementsLLM()


def extract_requirements(text: str) -> list[ExtractedRequirement]:
    """Extrait et dédoublonne les exigences d'un texte d'AO (multi-segments)."""
    text = (text or "").strip()
    if not text:
        return []

    segments = chunk_text(text, settings.extract_segment_chars, 200)
    segments = segments[: settings.extract_max_segments]

    client = _client()
    seen: set[str] = set()
    results: list[ExtractedRequirement] = []
    for segment in segments:
        if not segment.strip():
            continue
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": segment},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        parsed = _parse(resp.choices[0].message.content or "{}")
        for req in parsed.requirements:
            key = " ".join(req.text.lower().split())
            if key and key not in seen:
                seen.add(key)
                results.append(req)
    return results
