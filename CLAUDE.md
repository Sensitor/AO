# CLAUDE.md — AO Copilot

Contexte de projet pour Claude Code. Lis ce fichier en entier au démarrage de chaque session.

## Le produit
SaaS B2B qui aide une entreprise à répondre plus vite et mieux à des appels d'offres privés.
Pipeline : upload AO → extraction des exigences → matrice de conformité (vs base documentaire interne) → génération de sections → export DOCX.

**Côté répondant uniquement, jamais côté acheteur.** Règle absolue du moteur IA : ne jamais inventer de fait (projet, client, certification, intégration). Pas de preuve interne = exigence marquée `MANQUANT`, et zone non couverte rendue littéralement `[À compléter]`.

## Stack
- API : FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic
- DB : PostgreSQL 16 + pgvector
- Auth : JWT (HS256), mots de passe bcrypt
- Frontend (à venir) : Next.js App Router
- Storage (à venir) : S3-compatible
- LLM : API GPT-class

Principes : MVP-first, simple et robuste, **pas de sur-ingénierie** (pas de multi-agents, pas d'infra ajoutée tant qu'elle n'est pas nécessaire), pensé « vendable vite ».

## Commandes
```bash
docker compose up --build                                   # lance db + api (migrations auto)
docker compose run --rm api alembic upgrade head            # appliquer les migrations
docker compose run --rm api alembic revision --autogenerate -m "msg"  # nouvelle migration
```
- API : http://localhost:8000 · Swagger : /docs · Santé : /health
- Login Swagger : champ `username` = email.

## Architecture des fichiers
```
api/app/
  main.py        # app FastAPI + CORS + /health + lifespan (ensure_bucket)
  config.py      # settings via env (pydantic-settings)
  database.py    # engine + SessionLocal + get_db
  models.py      # Organization, User, Project, Document, DocumentChunk, Requirement, ComplianceEntry, Section
  schemas.py     # Pydantic v2 (in/out)
  security.py    # bcrypt + JWT (create/decode token)
  deps.py        # get_current_user (auth)
  storage.py     # client S3/MinIO (boto3) : upload/download/delete + ensure_bucket
  text_extract.py# extraction PDF/texte (pypdf) + chunking
  embeddings.py  # embeddings OpenAI (text-embedding-3-small)
  pipeline.py    # ingestion async : S3 -> texte -> chunks -> embeddings -> DB
  llm.py         # LLM : extraction exigences + jugement conformité + génération sections
  compliance.py  # RAG base interne (pgvector) + assess_requirement (sourcé)
  export.py      # export DOCX de la réponse (python-docx)
  billing.py     # Stripe : checkout abonnement + vérif webhook (opt-in config)
  deps.py + require_active_subscription  # gating par abonnement (opt-in)
  routers/auth.py         # register, login
  routers/projects.py     # CRUD projets, scopé par org_id
  routers/documents.py    # upload / list / get / delete / search, scopé par org_id
  routers/requirements.py # extract / list / add / edit / delete exigences (revue)
  routers/compliance.py   # build / get / adjust matrice de conformité
  routers/sections.py     # generate / list / edit / export DOCX
  routers/billing.py      # checkout / subscription / webhook (Stripe)
api/migrations/        # Alembic 0001..0006 (initial, docs+chunks, requirements, compliance, sections, subscriptions)
```

## État d'avancement
- **Sprint 0 — FAIT** : socle qui tourne. Auth JWT (register + login OAuth2), CRUD projets scopé organisation, schéma Postgres (`organizations`, `users`, `projects`), extension `vector` activée, Docker Compose (db + api). Vérifié : compile, importe, auth round-trip, migration OK.
- **Sprint 1 — FAIT** : upload de documents vers S3 (MinIO dev / R2 prod via boto3), parsing PDF/texte (pypdf), chunking + embeddings (OpenAI `text-embedding-3-small`), table `document_chunks` avec colonne `VECTOR(1536)` + index HNSW cosine, ingestion async via `BackgroundTasks` (pas de worker séparé : conforme « pas de sur-ingénierie »), recherche sémantique (`POST /documents/search`). Router `documents` scopé par `org_id`. MinIO ajouté au docker-compose.
- **Sprint 2 — FAIT** : extraction des exigences d'un AO via LLM (`gpt-4o-mini`, JSON mode, sortie validée Pydantic, règle « ne jamais inventer » dans le prompt), segmentation du texte long + dédup, modèle `Requirement` (scopé `org_id`/`project_id`, lié au document source), migration `0003`. Backend de l'écran de revue : `POST /projects/{id}/requirements/extract` (ré-extraction idempotente) + `GET`/`POST`/`PATCH`/`DELETE` pour lister/ajouter/éditer (valider/rejeter)/supprimer. Pas de frontend (Next.js à venir). Vérifié e2e sur la stack Docker.
- **Sprint 3 — FAIT** : matrice de conformité. Pour chaque exigence : RAG pgvector sur la base interne (`kind='internal'`, top-k cosine) + jugement LLM **sourcé** (`conforme`/`partiel`/`manquant`) avec règle « pas de preuve interne = MANQUANT, jamais d'invention ». Modèle `ComplianceEntry` (preuves stockées en JSONB), migration `0004`. Endpoints `POST /projects/{id}/compliance/build` (idempotent, préserve les ajustements manuels), `GET` (matrice), `PATCH /{requirement_id}` (ajustement manuel). Vérifié e2e.
- **Sprint 4 — FAIT** : génération de sections de réponse (une par exigence) à partir des preuves internes de la matrice — zone non couverte rendue littéralement `[À compléter]`, jamais d'invention. Modèle `Section`, migration `0005`. Endpoints `POST /projects/{id}/sections/generate` (idempotent, préserve les sections éditées), `GET`/`PATCH`/`DELETE`, et `GET /projects/{id}/sections/export` (DOCX via python-docx). Vérifié e2e (DOCX produit + `[À compléter]` présent).
- **Sprint 5 — FAIT (Stripe, opt-in)** : facturation Stripe par abonnement. Modèle `Subscription` (par org), migration `0006`. `POST /billing/checkout` (session Checkout abonnement), `GET /billing/subscription` (statut), `POST /billing/webhook` (signature vérifiée, synchro `checkout.session.completed` / `customer.subscription.updated|deleted`). Gating `require_active_subscription` sur les actions à valeur (extract, compliance/build, sections/generate, export). **Opt-in** : `STRIPE_SECRET_KEY` vide ⇒ facturation désactivée, tout passe (dev/gratuit). Code vérifié e2e en mode désactivé ; le flux Stripe réel se vérifie en ajoutant les clés test dans `.env`.

## Décisions tranchées (2026-06-18, avant Sprint 1)
1. **Embeddings** : OpenAI `text-embedding-3-small` → colonne `VECTOR(1536)` pour `document_chunks`.
2. **Stockage** : client boto3 sur API S3. MinIO en dev (service docker-compose), Cloudflare R2 en prod.
3. **Auth** : on garde le JWT maison du Sprint 0 (pas de bascule Supabase).

## Conventions
- SQLAlchemy 2.0, Pydantic v2 (`model_config = ConfigDict(from_attributes=True)` pour les schémas de sortie).
- UUID pour toutes les clés primaires ; `org_id` partout (multi-tenant léger, une org/compte au MVP).
- Toute route métier est scopée par `org_id` de l'utilisateur courant.
- Démarrer les jobs async avec `BackgroundTasks` ; n'introduire Redis/RQ que si le volume l'exige.
- Données sensibles jamais en dur ; `JWT_SECRET` via env.
```
