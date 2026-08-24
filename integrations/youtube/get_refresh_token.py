"""Herramienta de un solo uso: genera un YOUTUBE_REFRESH_TOKEN de solo lectura.

Corre un flujo OAuth local (abre el navegador, apruebas el acceso) y
imprime el refresh_token para pegar en .env. No es parte del sistema en
marcha — es una utilidad de setup que se corre una vez, a mano, desde una
terminal donde puedas completar el login en el navegador.

Requiere que YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET ya estén en .env,
tomados de un cliente OAuth tipo "Desktop app" en Google Cloud Console
con YouTube Data API v3 + YouTube Analytics API habilitadas.

Uso:
    python -m integrations.youtube.get_refresh_token
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # necesario para comentar
]


def main() -> None:
    load_dotenv()
    client_config = {
        "installed": {
            "client_id": os.environ["YOUTUBE_CLIENT_ID"],
            "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nListo. Pega esto en .env (reemplaza la línea existente):\n")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    main()
