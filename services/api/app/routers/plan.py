"""Plan del mes: el resumen (spec 008, RF-23 a RF-26).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-28; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import member_space, requested_period
from app.models import Space
from app.schemas import SummaryOut
from app.summary import build_summary

router = APIRouter(prefix="/spaces/{space_id}", tags=["plan"])


@router.get("/summary")
def read_summary(
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
    period: Annotated[str, Depends(requested_period)],
) -> SummaryOut:
    """Resumen del periodo, por defecto el actual en `TZ`: ingresos, rubros,
    categorías y totales (RF-23 a RF-26). El cálculo vive en
    `app/summary.py` (principio 10)."""
    return build_summary(db, space.id, period)
