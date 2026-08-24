"""Herramienta de un solo uso: genera un SPOTIFY_REFRESH_TOKEN nuevo.

Corre un flujo OAuth local (abre el navegador, apruebas el acceso) y
imprime el refresh_token para pegar en .env. Usa el redirect_uri ya
registrado en la app de Spotify Developer (http://127.0.0.1:8888/callback).

Uso:
    python -m integrations.spotify.get_refresh_token
"""

from __future__ import annotations

import base64
import os
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

SCOPES = "playlist-read-private playlist-modify-private playlist-modify-public ugc-image-upload"
REDIRECT_URI = "http://127.0.0.1:8888/callback"

_captured_code: dict[str, str] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _captured_code["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("Listo. Ya puedes cerrar esta pestaña.".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
        }
    )
    print(f"Abriendo navegador — apruebas con la cuenta NØBØĐ¥ de Spotify:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", 8888), _Handler)
    while "code" not in _captured_code:
        server.handle_request()

    code = _captured_code["code"]
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        timeout=20,
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\nListo. Pega esto en .env (reemplaza la línea existente):\n")
    print(f"SPOTIFY_REFRESH_TOKEN={tokens['refresh_token']}\n")


if __name__ == "__main__":
    main()
