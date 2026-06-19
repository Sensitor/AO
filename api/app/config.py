from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aocopilot:aocopilot@db:5432/aocopilot"
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    frontend_origin: str = "http://localhost:3000"

    # --- Sprint 1 : stockage S3 (MinIO en dev, Cloudflare R2 en prod) ---
    s3_endpoint_url: str = "http://minio:9000"  # vide => AWS S3 par défaut
    s3_region: str = "us-east-1"
    s3_access_key: str = "aocopilot"
    s3_secret_key: str = "aocopilot"
    s3_bucket: str = "ao-documents"
    s3_use_path_style: bool = True  # requis par MinIO

    # --- Sprint 1 : embeddings (OpenAI) ---
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- Sprint 1 : découpage en chunks (caractères) ---
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # --- Sprint 2 : extraction des exigences (LLM) ---
    llm_model: str = "gpt-4o-mini"
    extract_segment_chars: int = 12000
    extract_max_segments: int = 8


settings = Settings()
