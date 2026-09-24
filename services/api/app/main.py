from fastapi import FastAPI

# Importar la configuración aquí hace que el servicio falle al arrancar, y no
# en la primera petición, si falta una variable obligatoria (RF-33).
from app.config import settings  # noqa: F401

app = FastAPI(title="budget-ops API")


@app.get("/health")
def health() -> dict[str, str]:
    """Estado del servicio, sin autenticación ni datos de usuarios (RF-34)."""
    return {"status": "ok"}
