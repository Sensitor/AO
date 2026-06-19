# AO Copilot — Backend (Sprint 0)

Socle de l'API : FastAPI + PostgreSQL/pgvector + Docker. Auth JWT + CRUD projets.

## Stack
- **API** : FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic
- **DB** : PostgreSQL 16 + pgvector (extension activée, prête pour le Sprint 1)
- **Auth** : JWT (HS256), mots de passe hachés bcrypt

## Lancer en local

```bash
cp .env.example .env          # ajuste JWT_SECRET avant la prod
docker compose up --build
```

Au démarrage, le conteneur `api` applique les migrations (`alembic upgrade head`) puis lance Uvicorn.

- API : http://localhost:8000
- Docs interactives (Swagger) : http://localhost:8000/docs
- Santé : http://localhost:8000/health

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

## Structure

```
ao-copilot/
├── docker-compose.yml
├── .env.example
└── api/
    ├── Dockerfile
    ├── requirements.txt
    ├── alembic.ini
    ├── migrations/
    │   ├── env.py
    │   └── versions/0001_initial.py
    └── app/
        ├── main.py          # app FastAPI + CORS + /health
        ├── config.py        # settings (env)
        ├── database.py      # engine + session
        ├── models.py        # Organization, User, Project
        ├── schemas.py       # Pydantic v2
        ├── security.py      # JWT + bcrypt
        ├── deps.py          # get_current_user
        └── routers/
            ├── auth.py      # register / login
            └── projects.py  # CRUD projets (scopé org)
```

## Migrations

```bash
docker compose run --rm api alembic revision --autogenerate -m "message"
docker compose run --rm api alembic upgrade head
```

## Prochaine étape — Sprint 1 (Documents)
Ajout du service `worker`, upload S3, parsing PDF/texte, chunking + embeddings (`document_chunks` avec colonne `VECTOR`), ingestion de la base interne.
