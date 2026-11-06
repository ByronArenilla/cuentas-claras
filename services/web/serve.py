"""Servidor de desarrollo de la web (spec 011, RF-36 y RF-37).

Solo biblioteca estándar. Sirve los archivos de `public/` y:

- responde `index.html` a las rutas de la app (`/registrar`,
  `/unirse/<token>`…), que no son archivos: la app decide qué mostrar;
- genera `/config.js` con la URL de la API, tomada de `API_URL`
  (principio 11);
- pone en cada respuesta las cabeceras de seguridad, entre ellas la
  Content-Security-Policy que protege el token guardado en el navegador
  (decisión 2).

Es para la fase 1. En la fase 2 lo reemplaza un contenedor con la misma regla
de rutas y las mismas cabeceras (spec 011, requisitos para la 013).

Uso: `API_URL=http://localhost:8000 python3 serve.py --host 127.0.0.1 --port 8080`
"""

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

PUBLIC = Path(__file__).resolve().parent / "public"

# Tipos que `mimetypes` no siempre conoce o que el navegador exige exactos:
# un módulo ES con otro tipo no se ejecuta.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".txt": "text/plain; charset=utf-8",
}


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix, "application/octet-stream")


def origin_of(url: str) -> str:
    """`http://localhost:8000/algo` → `http://localhost:8000`."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def security_headers(api_url: str) -> dict[str, str]:
    """Cabeceras de RF-37. La CSP solo deja cargar lo propio y conectarse a
    la API: un script ajeno o en línea no se ejecuta, así que un XSS no puede
    leer el token de `localStorage` y enviarlo a otro lado.
    https://developer.mozilla.org/es/docs/Web/HTTP/CSP
    """
    csp = "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self'",
            "font-src 'self'",
            "img-src 'self' data:",
            "manifest-src 'self'",
            f"connect-src {origin_of(api_url)}",
            "base-uri 'none'",
            "form-action 'self'",
            # Nadie puede mostrar la web dentro de un <iframe> (clickjacking).
            "frame-ancestors 'none'",
        ]
    )
    return {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        # El token de `/unirse/<token>` no viaja a otra página al seguir un
        # enlace.
        "Referrer-Policy": "no-referrer",
        # Servidor de desarrollo: siempre la última versión de cada archivo.
        "Cache-Control": "no-cache",
    }


def config_module(api_url: str) -> bytes:
    # `json.dumps` escapa comillas y barras: la URL no puede romper el módulo.
    return f"export const API_URL = {json.dumps(api_url)};\n".encode()


def resolve(url_path: str) -> Path | None:
    """Archivo que corresponde a la ruta, `index.html` si es una ruta de la
    app, o `None` (404).

    Nunca sale de `public/`: `/../serve.py` y sus variantes codificadas no se
    sirven.
    """
    candidate = (PUBLIC / unquote(url_path).lstrip("/")).resolve()
    if not candidate.is_relative_to(PUBLIC):
        return None
    if candidate.is_file():
        return candidate
    # Una ruta sin extensión es una pantalla de la app (RF-36).
    if not Path(url_path).suffix:
        return PUBLIC / "index.html"
    return None


def make_handler(api_url: str) -> type[BaseHTTPRequestHandler]:
    headers = security_headers(api_url)
    config = config_module(api_url)

    class Handler(BaseHTTPRequestHandler):
        server_version = "gastito-web"

        def do_GET(self) -> None:
            self.respond(send_body=True)

        def do_HEAD(self) -> None:
            self.respond(send_body=False)

        def respond(self, *, send_body: bool) -> None:
            path = urlsplit(self.path).path
            if path == "/config.js":
                status, kind, body = HTTPStatus.OK, content_type(Path(path)), config
            elif (file := resolve(path)) is not None:
                status, kind, body = (
                    HTTPStatus.OK,
                    content_type(file),
                    file.read_bytes(),
                )
            else:
                status = HTTPStatus.NOT_FOUND
                kind = CONTENT_TYPES[".txt"]
                body = b"No encontrado.\n"

            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor de desarrollo de la web.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    api_url = os.environ.get("API_URL", "").strip()
    if not api_url:
        print(
            "Falta la variable de entorno API_URL (la URL de la API, por ejemplo "
            "http://localhost:8000). Defínela en .env (copia .env.example).",
            file=sys.stderr,
        )
        return 1

    server = ThreadingHTTPServer((args.host, args.port), make_handler(api_url))
    print(
        f"Web en http://{args.host}:{server.server_address[1]} (API: {api_url})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
