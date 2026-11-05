"""Plan del mes: el resumen y copiar el plan del mes anterior (spec 008,
RF-13 a RF-16 y RF-23 a RF-26).

Las rutas reciben el espacio por `member_space`, nunca consultando por
`space_id` directamente (RF-28; RF-28 y RF-29 de la 001).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.deps import member_space, requested_period
from app.models import Space
from app.plan import NothingToCopy, PlanNotEmpty, copy_previous_plan
from app.schemas import PlanCopyIn, PlanCopyOut, SummaryOut
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


@router.post("/plan/copy", status_code=status.HTTP_201_CREATED)
def copy_plan(
    data: PlanCopyIn,
    space: Annotated[Space, Depends(member_space)],
    db: Annotated[Session, Depends(get_db)],
) -> PlanCopyOut:
    """Copia al mes `period` (por defecto el actual) el plan del mes anterior,
    sin los rubros de categorías eliminadas (RF-13). Nunca mezcla ni
    reemplaza un plan que ya existe (RF-14)."""
    try:
        skipped = copy_previous_plan(db, space.id, data.period)
    except PlanNotEmpty:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{data.period} ya tiene un plan; no se copió nada.",
        ) from None
    except NothingToCopy:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{dates.previous_period(data.period)} no tiene un plan para copiar.",
        ) from None
    return PlanCopyOut(
        summary=build_summary(db, space.id, data.period), skipped=skipped
    )
