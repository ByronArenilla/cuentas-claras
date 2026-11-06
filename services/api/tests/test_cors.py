"""CORS para la web (spec 011, RF-38).

La web corre en otro origen (`WEB_BASE_URL`, otro puerto) y el navegador solo
le deja leer las respuestas de la API si esta lo permite. Solo ese origen.
"""

from fastapi.testclient import TestClient

from tests.conftest import WEB_BASE_URL

OTHER_ORIGIN = "http://otro.example"


def preflight(client: TestClient, origin: str):
    """La petición `OPTIONS` que el navegador hace antes de un `POST` con
    `Authorization` desde otro origen."""
    return client.options(
        "/spaces",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )


def test_the_web_origin_passes_the_preflight(client: TestClient) -> None:
    response = preflight(client, WEB_BASE_URL)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_BASE_URL
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "access-control-allow-credentials" not in response.headers


def test_another_origin_does_not_pass_the_preflight(client: TestClient) -> None:
    response = preflight(client, OTHER_ORIGIN)

    assert "access-control-allow-origin" not in response.headers


def test_responses_to_the_web_carry_the_header(client: TestClient) -> None:
    to_web = client.get("/health", headers={"Origin": WEB_BASE_URL})
    to_other = client.get("/health", headers={"Origin": OTHER_ORIGIN})

    assert to_web.headers["access-control-allow-origin"] == WEB_BASE_URL
    assert "access-control-allow-origin" not in to_other.headers
