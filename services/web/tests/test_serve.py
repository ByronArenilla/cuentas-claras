"""Servidor de desarrollo de la web (spec 011, RF-36, RF-37; criterio 3)."""

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import serve

API_URL = "http://api.test:8000"
SERVE_PY = Path(serve.__file__)


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """La web servida en un puerto libre, con un `API_URL` de prueba."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(API_URL))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url: str) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


INDEX = (serve.PUBLIC / "index.html").read_bytes()


@pytest.mark.parametrize("path", ["/", "/registrar", "/gastos/12", "/unirse/abc-_9"])
def test_app_routes_return_the_page(base_url: str, path: str) -> None:
    status, headers, body = get(base_url + path)

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert body == INDEX


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("manifest.webmanifest", "application/manifest+json"),
        ("probe.js", "text/javascript"),
        ("probe.woff2", "font/woff2"),
        ("probe.css", "text/css"),
        ("probe.svg", "image/svg+xml"),
        ("probe.png", "image/png"),
    ],
)
def test_files_are_served_with_their_type(name: str, content_type: str) -> None:
    assert serve.content_type(Path(name)).startswith(content_type)


def test_an_existing_file_is_served(base_url: str) -> None:
    status, headers, body = get(base_url + "/index.html")

    assert status == 200
    assert body == INDEX


@pytest.mark.parametrize(
    "path", ["/css/no-existe.css", "/../serve.py", "/%2e%2e/serve.py", "/js/x.js"]
)
def test_missing_files_and_paths_outside_public_are_not_found(
    base_url: str, path: str
) -> None:
    status, _, _ = get(base_url + path)

    assert status == 404


def test_config_is_a_module_with_the_api_url(base_url: str) -> None:
    status, headers, body = get(base_url + "/config.js")

    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")
    assert body.decode() == 'export const API_URL = "http://api.test:8000";\n'
    assert headers["Cache-Control"] == "no-cache"


@pytest.mark.parametrize("path", ["/", "/config.js", "/no-existe.css"])
def test_every_response_carries_the_security_headers(base_url: str, path: str) -> None:
    _, headers, _ = get(base_url + path)

    csp = headers["Content-Security-Policy"]
    for rule in (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data:",
        "manifest-src 'self'",
        "connect-src http://api.test:8000",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ):
        assert rule in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_without_api_url_the_server_does_not_start() -> None:
    env = {key: value for key, value in os.environ.items() if key != "API_URL"}

    result = subprocess.run(
        [sys.executable, str(SERVE_PY), "--port", "0"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert "API_URL" in result.stderr


# --- Manifiesto (RF-28) ---


def test_the_manifest_lets_the_app_be_pinned() -> None:
    manifest = json.loads((serve.PUBLIC / "manifest.webmanifest").read_text())

    assert manifest["name"] == manifest["short_name"] == "gastito"
    assert manifest["lang"] == "es-CO"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/registrar"
    assert manifest["background_color"].startswith("#")
    assert manifest["theme_color"].startswith("#")
    icons = {(icon["sizes"], icon.get("purpose", "any")) for icon in manifest["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= icons
    for icon in manifest["icons"]:
        assert (serve.PUBLIC / icon["src"].lstrip("/")).is_file(), icon["src"]


def test_the_page_links_the_manifest_and_the_iphone_icon() -> None:
    page = INDEX.decode()

    assert '<link rel="manifest" href="/manifest.webmanifest">' in page
    assert 'rel="apple-touch-icon"' in page
    assert (serve.PUBLIC / "icons" / "apple-touch-icon.png").is_file()
