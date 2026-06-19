"""Extraction des exigences d'un AO via LLM (sortie JSON validée Pydantic).

Règle absolue du produit : ne jamais inventer. On n'extrait que ce qui figure
explicitement dans le texte de l'appel d'offres.
"""
import json
import logging
from functools import lru_cache

from openai import OpenAI

from .config import settings
from .schemas import ComplianceLLM, ExtractedRequirement, RequirementsLLM
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


COMPLIANCE_SYSTEM_PROMPT = (
    "Tu évalues si une entreprise répond à une EXIGENCE d'appel d'offres, "
    "UNIQUEMENT à partir des extraits de sa base documentaire interne fournis.\n"
    "Règles impératives :\n"
    "1. N'invente JAMAIS : ne te fie qu'aux extraits fournis. N'utilise aucune "
    "connaissance externe.\n"
    "2. verdict :\n"
    "   - 'conforme' : les extraits prouvent clairement que l'exigence est satisfaite ;\n"
    "   - 'partiel' : les extraits couvrent partiellement l'exigence ;\n"
    "   - 'manquant' : les extraits ne prouvent pas la conformité (ou hors sujet).\n"
    "3. En cas de doute ou d'absence de preuve, réponds 'manquant'.\n"
    "4. rationale : justification courte citant les éléments des extraits (jamais de fait inventé).\n"
    '5. Réponds STRICTEMENT en JSON : {"verdict": "...", "rationale": "..."}'
)


def judge_compliance(requirement_text: str, excerpts: list[str]) -> ComplianceLLM:
    """Juge la conformité d'une exigence au vu d'extraits internes (sourcé, sans invention)."""
    if not excerpts:
        return ComplianceLLM(
            verdict="manquant",
            rationale="Aucune preuve dans la base documentaire interne.",
        )
    context = "\n\n".join(f"[Extrait {i + 1}] {e}" for i, e in enumerate(excerpts))
    user = f"EXIGENCE :\n{requirement_text}\n\nEXTRAITS INTERNES :\n{context}"
    resp = _client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": COMPLIANCE_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return ComplianceLLM.model_validate_json(content)
    except Exception:
        try:
            return ComplianceLLM.model_validate(json.loads(content))
        except Exception:
            logger.warning("Jugement LLM non parsable: %.200s", content)
            return ComplianceLLM(
                verdict="manquant", rationale="Réponse du modèle illisible."
            )


PLACEHOLDER = "[À compléter]"

SECTION_SYSTEM_PROMPT = (
    "Tu rédiges la réponse d'une entreprise à une exigence d'appel d'offres, "
    "à partir UNIQUEMENT des extraits de sa base documentaire interne.\n"
    "Règles impératives :\n"
    "1. N'invente JAMAIS un fait (projet, client, certification, chiffre, "
    "intégration) qui n'est pas présent dans les extraits.\n"
    f"2. Si un aspect de l'exigence n'est pas couvert par les extraits, écris "
    f"littéralement {PLACEHOLDER} à cet endroit.\n"
    "3. Style professionnel et concis, à la première personne du pluriel (« nous »).\n"
    "4. Réponds uniquement par le texte de la réponse, sans titre ni préambule."
)


def generate_section(requirement_text: str, obligation: str, excerpts: list[str]) -> str:
    """Rédige un paragraphe de réponse sourcé. Renvoie [À compléter] si non couvert."""
    if not excerpts:
        return PLACEHOLDER
    context = "\n\n".join(f"[Extrait {i + 1}] {e}" for i, e in enumerate(excerpts))
    user = (
        f"EXIGENCE :\n{requirement_text}\n\n"
        f"NIVEAU : {obligation}\n\n"
        f"EXTRAITS INTERNES :\n{context}"
    )
    resp = _client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text or PLACEHOLDER
