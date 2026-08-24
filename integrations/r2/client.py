"""Cliente de Cloudflare R2 — almacena el catálogo real (audio + artwork)
fuera del volumen de Railway (25GB+ no entra en un volumen barato, y R2
es ~10x más económico por GB que el storage de volúmenes de Railway,
sin costo de salida de datos).

R2 es compatible con la API de S3, así que se usa boto3 apuntado al
endpoint de Cloudflare. Este módulo es deliberadamente delgado — solo
sube/baja/lista objetos, la lógica de qué cachear y cuándo vive en
agents/capabilities/catalogue_cache.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.config import Config

_client = None


def _get_client():
    global _client
    if _client is None:
        account_id = os.environ["R2_ACCOUNT_ID"]
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def _bucket() -> str:
    return os.environ["R2_BUCKET_NAME"]


def upload_file(local_path: Path, key: str) -> None:
    """Sube un archivo local a R2 bajo `key` (ruta relativa dentro del
    bucket, ej. "528 HZ vol 1/wav/Solar Pulse (10).wav")."""
    _get_client().upload_file(str(local_path), _bucket(), key)


def download_file(key: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _get_client().download_file(_bucket(), key, str(local_path))


def object_exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _get_client().head_object(Bucket=_bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def list_keys(prefix: str = "") -> set[str]:
    """Todas las keys existentes bajo un prefijo — usado por la sincronización
    para no resubir lo que ya está en R2."""
    keys: set[str] = set()
    paginator = _get_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys
