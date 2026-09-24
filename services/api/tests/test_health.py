from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_responds_without_auth() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_exposes_no_user_or_space_data() -> None:
    body = client.get("/health").text.lower()

    for word in ("user", "email", "space", "member", "token", "password"):
        assert word not in body
