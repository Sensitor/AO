# AO Copilot — Backend (Sprint 1)

API FastAPI + PostgreSQL/pgvector + Docker. Auth JWT, CRUD projets, et ingestion
de documents (upload S3 → parsing → chunking → embeddings) avec recherche sémantique.

## Stack
- **API** : FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic
- **DB** : PostgreSQL 16 + pgvector (colonne `VECTOR(1536)` sur `document_chunks`)
- **Auth** : JWT (HS256), mots de passe hachés bcrypt
- **Storage** : S3 via boto3 — MinIO en dev, Cloudflare R2 en prod
- **Embeddings** : OpenAI `text-embedding-3-small` (1536 dims)

## Lancer en local

```bash
cp .env.example .env          # ajuste JWT_SECRET + renseigne OPENAI_API_KEY
docker compose up --build
```

Au démarrage, le conteneur `api` applique les migrations (`alembic upgrade head`),
crée le bucket MinIO si besoin, puis lance Uvicorn.

> ⚠️ L'ingestion (chunking + embeddings) nécessite un `OPENAI_API_KEY` valide.
> Sans clé, l'upload réussit mais le document passera en statut `failed`.

- API : http://localhost:8000
- Docs interactives (Swagger) : http://localhost:8000/docs
- Santé : http://localhost:8000/health
- Console MinIO : http://localhost:9001 (login `aocopilot` / `aocopilot`)

## Smoke test

```bash
# 1. Créer un compte (+ son organisation)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"nico@exemple.fr","password":"motdepasse","org_name":"Ma Boite"}'

# 2. Login (form OAuth2 : username = email)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=nico@exemple.fr&password=motdepasse" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 3. Créer un projet
curl -X POST http://localhost:8000/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"AO Mairie X","buyer_name":"Mairie X","deadline":"2026-09-30"}'

# 4. Lister les projets
curl http://localhost:8000/projects -H "Authorization: Bearer $TOKEN"
```

Dans Swagger : clique **Authorize**, saisis l'email dans le champ `username` et le mot de passe, puis teste les routes `/projects`.

### Documents (Sprint 1)

```bash
# 5. Uploader un document de la base interne (PDF ou texte)
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./mon_doc.pdf" \
  -F "kind=internal"

# 6. Suivre l'ingestion (status: pending -> processing -> ready)
curl http://localhost:8000/documents -H "Authorization: Bearer $TOKEN"

# 7. Recherche sémantique sur la base documentaire
curl -X POST http://localhost:8000/documents/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"certification ISO 27001","k":5}'
```

`kind` vaut `internal` (base documentaire) ou `tender` (AO à analyser) ; `project_id`
est optionnel pour rattacher le document à un projet.

## Structure

```
ao-copilot/
├── docker-compose.yml       # db (pgvector) + minio + api
├── .env.example
└── api/
    ├── Dockerfile
    ├── requirements.txt
    ├── alembic.ini
    ├── migrations/
    │   ├── env.py
    │   └── versions/
    │       ├── 0001_initial.py     # organizations, users, projects
    │       └── 0002_documents.py   # documents, document_chunks (VECTOR 1536)
    └── app/
        ├── main.py          # app FastAPI + CORS + /health + lifespan (bucket)
        ├── config.py        # settings (env)
        ├── database.py      # engine + session
        ├── models.py        # Organization, User, Project, Document, DocumentChunk
        ├── schemas.py       # Pydantic v2
        ├── security.py      # JWT + bcrypt
        ├── deps.py          # get_current_user
        ├── storage.py       # client S3/MinIO (boto3)
        ├── text_extract.py  # extraction PDF/texte + chunking
        ├── embeddings.py    # embeddings OpenAI
        ├── pipeline.py      # ingestion async (BackgroundTasks)
        └── routers/
            ├── auth.py      # register / login
            ├── projects.py  # CRUD projets (scopé org)
            └── documents.py # upload / list / delete / search (scopé org)
```

## Migrations

```bash
docker compose run --rm api alembic revision --autogenerate -m "message"
docker compose run --rm api alembic upgrade head
```

## Prochaine étape — Sprint 2 (Extraction des exigences)
Extraction des exigences d'un AO via LLM (sortie JSON validée Pydantic) + écran de revue.
