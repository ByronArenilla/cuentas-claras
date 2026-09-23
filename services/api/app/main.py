from fastapi import FastAPI

app = FastAPI(title="budget-ops API")


@app.get("/health")
def health() -> dict[str, str]:
    """Estado del servicio, sin autenticación ni datos de usuarios (RF-34)."""
    return {"status": "ok"}
