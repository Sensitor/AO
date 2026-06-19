# AO Copilot — Backend (Sprint 5)

API FastAPI + PostgreSQL/pgvector + Docker. Pipeline complet : ingestion de
documents (S3 → parsing → chunking → embeddings + recherche sémantique),
extraction des exigences d'un AO (LLM, JSON validé Pydantic), matrice de
conformité (RAG base interne + jugement LLM sourcé), génération des sections de
réponse, export DOCX, et facturation Stripe (abonnement, opt-in). Règle absolue :
aucune invention, zones non couvertes rendues `[À compléter]`.

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

### Exigences (Sprint 2)

Extraction des exigences d'un document AO via LLM (le LLM n'invente jamais : il
n'extrait que ce qui est présent), puis revue manuelle.

```bash
# Uploader l'AO en kind=tender (récupère son id), puis extraire les exigences
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/requirements/extract" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_id":"<id_du_doc_AO>"}'

# Lister les exigences extraites
curl "http://localhost:8000/projects/$PROJECT_ID/requirements" \
  -H "Authorization: Bearer $TOKEN"

# Revue : éditer / valider / rejeter une exigence
curl -X PATCH "http://localhost:8000/projects/$PROJECT_ID/requirements/$REQ_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"validated","obligation":"obligatoire"}'

# Revue : ajouter une exigence manquée par le LLM
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/requirements" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Disposer d'\''une certification ISO 27001","category":"sécurité"}'
```

`obligation` ∈ `{obligatoire, souhaité, optionnel}` (normalisée automatiquement) ;
`status` suit la revue : `extracted` → `validated` / `rejected` / `edited` (ou `manual`).
La ré-extraction sur un même document est idempotente (remplace ses exigences).

### Matrice de conformité (Sprint 3)

Pour chaque exigence : recherche RAG dans la base interne (`kind=internal`) +
jugement LLM **sourcé**. Règle absolue : pas de preuve interne ⇒ `manquant`.

```bash
# Construire la matrice (un verdict sourcé par exigence non rejetée)
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/compliance/build" \
  -H "Authorization: Bearer $TOKEN"

# Consulter la matrice
curl "http://localhost:8000/projects/$PROJECT_ID/compliance" \
  -H "Authorization: Bearer $TOKEN"

# Ajuster manuellement un verdict (passe en status=adjusted, préservé au rebuild)
curl -X PATCH "http://localhost:8000/projects/$PROJECT_ID/compliance/$REQ_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"verdict":"partiel","rationale":"Couverture partielle confirmée manuellement"}'
```

`verdict` ∈ `{conforme, partiel, manquant}`. Chaque entrée porte ses `sources`
(document, extrait, score) pour tracer le jugement. `build` est idempotent et ne
réécrit pas les entrées ajustées manuellement.

### Sections de réponse + export DOCX (Sprint 4)

Génération d'une section par exigence à partir des preuves internes de la matrice ;
toute zone non couverte est rendue littéralement `[À compléter]` (jamais d'invention).

```bash
# Générer les sections (s'appuie sur la matrice de conformité)
curl -X POST "http://localhost:8000/projects/$PROJECT_ID/sections/generate" \
  -H "Authorization: Bearer $TOKEN"

# Éditer une section (passe en status=edited, préservé au regénérer)
curl -X PATCH "http://localhost:8000/projects/$PROJECT_ID/sections/$REQ_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"content":"Notre réponse révisée..."}'

# Exporter la réponse assemblée en DOCX
curl -L "http://localhost:8000/projects/$PROJECT_ID/sections/export" \
  -H "Authorization: Bearer $TOKEN" -o reponse.docx
```

### Facturation Stripe (Sprint 5, opt-in)

Abonnement mensuel. **Opt-in** : tant que `STRIPE_SECRET_KEY` est vide, la
facturation est désactivée et toutes les actions passent (mode dev/gratuit).
Une fois les clés Stripe (test) renseignées dans `.env`, un abonnement actif
devient requis pour les actions à valeur (extraction, matrice, génération, export).

```bash
# Statut d'abonnement de l'organisation
curl "http://localhost:8000/billing/subscription" -H "Authorization: Bearer $TOKEN"

# Démarrer un abonnement (renvoie une URL Stripe Checkout)
curl -X POST "http://localhost:8000/billing/checkout" -H "Authorization: Bearer $TOKEN"

# Webhook (appelé par Stripe, hors auth, signature vérifiée) :
#   stripe listen --forward-to localhost:8000/billing/webhook
```

Config requise (`.env`) : `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` (prix de
l'abonnement), `STRIPE_WEBHOOK_SECRET`. Événements traités :
`checkout.session.completed`, `customer.subscription.updated|deleted`.

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
    │       ├── 0001_initial.py       # organizations, users, projects
    │       ├── 0002_documents.py     # documents, document_chunks (VECTOR 1536)
    │       ├── 0003_requirements.py  # requirements (exigences AO)
    │       ├── 0004_compliance.py    # compliance_entries (matrice)
    │       ├── 0005_sections.py      # sections (réponses + export DOCX)
    │       └── 0006_subscriptions.py # subscriptions (facturation Stripe)
    └── app/
        ├── main.py          # app FastAPI + CORS + /health + lifespan (bucket)
        ├── config.py        # settings (env)
        ├── database.py      # engine + session
        ├── models.py        # Organization, User, Project, Document, DocumentChunk, Requirement
        ├── schemas.py       # Pydantic v2
        ├── security.py      # JWT + bcrypt
        ├── deps.py          # get_current_user
        ├── storage.py       # client S3/MinIO (boto3)
        ├── text_extract.py  # extraction PDF/texte + chunking
        ├── embeddings.py    # embeddings OpenAI
        ├── pipeline.py      # ingestion async (BackgroundTasks)
        ├── llm.py           # LLM : extraction + jugement conformité + génération sections
        ├── compliance.py    # RAG base interne (pgvector) + assess_requirement
        ├── export.py        # export DOCX (python-docx)
        ├── billing.py       # Stripe : checkout + webhook (opt-in)
        └── routers/
            ├── auth.py         # register / login
            ├── projects.py     # CRUD projets (scopé org)
            ├── documents.py    # upload / list / delete / search (scopé org)
            ├── requirements.py # extract / list / add / edit / delete (scopé org)
            ├── compliance.py   # build / get / adjust matrice (scopé org)
            ├── sections.py     # generate / list / edit / export DOCX (scopé org)
            └── billing.py      # checkout / subscription / webhook (Stripe)
```

## Migrations

```bash
docker compose run --rm api alembic revision --autogenerate -m "message"
docker compose run --rm api alembic upgrade head
```

## État
Sprints 0→5 livrés. Le pipeline produit complet tourne (auth → projets → ingestion
→ recherche → exigences → matrice de conformité → sections → DOCX → facturation
Stripe opt-in). Frontend Next.js à venir.
