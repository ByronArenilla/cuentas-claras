from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importar la configuración aquí hace que el servicio falle al arrancar, y no
# en la primera petición, si falta una variable obligatoria (RF-33).
from app.config import settings
from app.db import engine, run_migrations
from app.routers import (
    auth,
    budget_items,
    cards,
    categories,
    expenses,
    incomes,
    invitations,
    plan,
    prepayments,
    spaces,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Aplica las migraciones pendientes antes de atender la primera petición
    (spec 008, RF-31). Si una falla, la API no arranca (RF-37)."""
    run_migrations(engine)
    yield


app = FastAPI(title="gastito API", lifespan=lifespan)

# La web corre en otro origen (otro puerto en local) y el navegador solo le
# deja leer las respuestas si la API lo permite (spec 011, RF-38). Solo el
# origen de la web: es la misma URL de los enlaces de invitación. Sin
# credenciales, porque el token viaja en `Authorization` y no en una cookie.
# https://developer.mozilla.org/es/docs/Web/HTTP/CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_base_url],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(budget_items.router)
app.include_router(cards.router)
app.include_router(categories.router)
app.include_router(expenses.router)
app.include_router(incomes.router)
app.include_router(invitations.router)
app.include_router(plan.router)
app.include_router(prepayments.router)
app.include_router(spaces.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Estado del servicio, sin autenticación ni datos de usuarios (RF-34)."""
    return {"status": "ok"}
