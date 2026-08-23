"""Sincroniza el catálogo local con NOBODY_BRAIN y con el volumen de
Railway en un solo paso. Corre en la máquina de Santiago — es la única
que ve D:\\Users\\Santiago\\Desktop\\NOBODY; el bot en Railway no puede
leer esa carpeta.

Uso (después de agregar álbumes/tracks nuevos a la carpeta):

    python -m agents.capabilities.sync_catalogue --root "D:\\Users\\Santiago\\Desktop\\NOBODY"

Requiere el CLI de railway instalado y logueado (railway login). Si se
corre desde Git Bash, ya se encarga de desactivar la conversión de rutas
de MSYS internamente — no hace falta anteponer MSYS_NO_PATHCONV=1 a mano.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import requests

from agents.capabilities.catalogue import ingest, render_markdown

RAILWAY_SERVICE = os.environ.get("NOBODY_RAILWAY_SERVICE", "nobody-ceo")
RAILWAY_VOLUME = os.environ.get("NOBODY_RAILWAY_VOLUME", "nobody-ceo-volume")


def _notify_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_FOUNDER_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception:
        pass


def sync(root: Path) -> None:
    report = ingest(root, dry_run=False)
    Path("CATALOGUE_REPORT.md").write_text(render_markdown(report), encoding="utf-8")

    railway_bin = shutil.which("railway")
    if railway_bin is None:
        ok = False
        result = None
    else:
        env = os.environ.copy()
        env["MSYS_NO_PATHCONV"] = "1"
        result = subprocess.run(
            [
                railway_bin, "volume", "--service", RAILWAY_SERVICE,
                "files", "--volume", RAILWAY_VOLUME,
                "upload", "data/nobody.db", "/nobody.db", "--overwrite", "--json",
            ],
            capture_output=True, text=True, env=env,
        )
        ok = result.returncode == 0

    msg = (
        f"Catálogo sincronizado: {report['totals']['albums']} álbumes, "
        f"{report['totals']['tracks']} tracks. "
        f"Subida a Railway: {'OK' if ok else 'FALLÓ — revisar manualmente'}."
    )
    print(msg)
    if not ok:
        print("railway CLI no encontrado en PATH" if result is None else result.stderr)
    _notify_telegram(msg)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Sincroniza el catálogo local con NOBODY_BRAIN y Railway")
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()

    if not args.root.exists():
        raise SystemExit(f"No existe la ruta del catálogo: {args.root}")

    sync(args.root)
