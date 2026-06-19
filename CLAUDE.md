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
  main.py        # app FastAPI + CORS + /health
  config.py      # settings via env (pydantic-settings)
  database.py    # engine + SessionLocal + get_db
  models.py      # Organization, User, Project
  schemas.py     # Pydantic v2 (in/out)
  security.py    # bcrypt + JWT (create/decode token)
  deps.py        # get_current_user (auth)
  routers/auth.py      # register, login
  routers/projects.py  # CRUD projets, scopé par org_id
api/migrations/        # Alembic
```

## État d'avancement
- **Sprint 0 — FAIT** : socle qui tourne. Auth JWT (register + login OAuth2), CRUD projets scopé organisation, schéma Postgres (`organizations`, `users`, `projects`), extension `vector` activée, Docker Compose (db + api). Vérifié : compile, importe, auth round-trip, migration OK.
- **Sprint 1 — À FAIRE (prochain)** : service `worker`, upload de documents vers S3 (MinIO dev / R2 prod), parsing PDF/texte, chunking + embeddings (OpenAI `text-embedding-3-small`), table `document_chunks` avec colonne `VECTOR(1536)`, ingestion de la base interne.
- Sprint 2 : extraction des exigences (LLM, sortie JSON validée Pydantic) + écran de revue.
- Sprint 3 : matrice de conformité (RAG pgvector, jugement LLM sourcé) + ajustement manuel.
- Sprint 4 : génération de sections + éditeur + export DOCX (python-docx).
- Sprint 5 : finition + facturation Stripe avant lancement.

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
