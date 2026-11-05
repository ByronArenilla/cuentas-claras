from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Importar la configuración aquí hace que el servicio falle al arrancar, y no
# en la primera petición, si falta una variable obligatoria (RF-33).
from app.config import settings  # noqa: F401
from app.db import engine, run_migrations
from app.routers import (
    auth,
    budget_items,
    budgets,
    categories,
    expenses,
    incomes,
    invitations,
    spaces,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Aplica las migraciones pendientes antes de atender la primera petición
    (spec 008, RF-31). Si una falla, la API no arranca (RF-37)."""
    run_migrations(engine)
    yield


app = FastAPI(title="gastito API", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(budget_items.router)
app.include_router(budgets.router)
app.include_router(categories.router)
app.include_router(expenses.router)
app.include_router(incomes.router)
app.include_router(invitations.router)
app.include_router(spaces.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Estado del servicio, sin autenticación ni datos de usuarios (RF-34)."""
    return {"status": "ok"}
