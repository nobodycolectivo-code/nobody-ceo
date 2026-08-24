"""Sube a Cloudflare R2 los archivos de audio/artwork que el catálogo local
(NOBODY_BRAIN) referencia — no la carpeta NOBODY entera, solo lo que
agents.capabilities.catalogue efectivamente ingirió como track/artwork.

Corre en la máquina de Santiago (la única con acceso a
D:\\Users\\Santiago\\Desktop\\NOBODY). Railway nunca ve esa carpeta —
content.py resuelve los archivos vía agents.capabilities.catalogue_cache,
que descarga de R2 bajo demanda.

Idempotente: no resube lo que ya existe en el bucket (chequea las keys
una sola vez al inicio, no un HEAD por archivo).

Uso:
    python -m agents.capabilities.sync_catalogue_r2
    python -m agents.capabilities.sync_catalogue_r2 --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from brain.db import connect
from integrations.r2.client import list_keys, upload_file


def sync(dry_run: bool = False) -> dict:
    local_root = os.environ.get("NOBODY_CATALOGUE_ROOT")
    if not local_root:
        raise SystemExit("NOBODY_CATALOGUE_ROOT no está configurado en .env")
    root = Path(local_root)

    conn = connect()
    audio_keys = {r["audio_path"] for r in conn.execute("SELECT audio_path FROM tracks")}
    artwork_keys = {
        r["artwork_path"]
        for r in conn.execute("SELECT artwork_path FROM albums WHERE artwork_path IS NOT NULL")
    }
    conn.close()

    wanted = audio_keys | artwork_keys
    already_in_r2 = list_keys() if not dry_run else set()
    missing_locally: list[str] = []
    to_upload: list[str] = []

    for key in sorted(wanted):
        local_path = root / key
        if not local_path.exists():
            missing_locally.append(key)
            continue
        if key in already_in_r2:
            continue
        to_upload.append(key)

    if not dry_run:
        for i, key in enumerate(to_upload, start=1):
            upload_file(root / key, key)
            print(f"[{i}/{len(to_upload)}] subido: {key}")

    return {
        "wanted_total": len(wanted),
        "already_in_r2": len(wanted) - len(to_upload) - len(missing_locally),
        "uploaded": 0 if dry_run else len(to_upload),
        "would_upload": len(to_upload) if dry_run else 0,
        "missing_locally": missing_locally,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza audio/artwork del catálogo hacia Cloudflare R2")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = sync(dry_run=args.dry_run)
    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
