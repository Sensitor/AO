"""Stockage objet S3-compatible (MinIO en dev, Cloudflare R2 en prod).

Le client ne parle que l'API S3 : changer d'endpoint suffit pour passer de MinIO
à R2/S3 sans toucher au code applicatif.
"""
import io
import time
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import settings


@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"},
        ),
    )


def ensure_bucket(retries: int = 5, delay: float = 2.0) -> None:
    """Crée le bucket s'il n'existe pas. Réessaie tant que le storage démarre."""
    client = _client()
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            try:
                client.head_bucket(Bucket=settings.s3_bucket)
            except ClientError:
                client.create_bucket(Bucket=settings.s3_bucket)
            return
        except Exception as exc:  # storage pas encore prêt au démarrage
            last_exc = exc
            time.sleep(delay)
    raise RuntimeError(f"Storage S3 indisponible: {last_exc}")


def upload_fileobj(fileobj, key: str, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_fileobj(fileobj, settings.s3_bucket, key, ExtraArgs=extra)


def download_bytes(key: str) -> bytes:
    buf = io.BytesIO()
    _client().download_fileobj(settings.s3_bucket, key, buf)
    return buf.getvalue()


def delete_object(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)
