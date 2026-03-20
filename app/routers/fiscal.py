"""Router del Motor Fiscal (Fiscal Engine) de BetSync.

Expone dos endpoints bajo el prefijo /fiscal:
  - GET /summary  → JSON con FiscalSummaryResponse
  - GET /export/csv → StreamingResponse con el CSV para el contador

Tag: fiscal
"""
import csv
import io
from datetime import date

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_redis
from app.schemas.fiscal import CSV_HEADERS, FiscalSummaryResponse
from app.services import fiscal_service

router = APIRouter(prefix="/fiscal")

# ---------------------------------------------------------------------------
# Endpoint 1: Resumen fiscal JSON
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=FiscalSummaryResponse,
    summary="Resumen fiscal anual (SAT/MX)",
    description=(
        "Calcula la base imponible estimada cruzando picks resueltos y "
        "transacciones del año fiscal indicado. "
        "Todos los montos están en MXN. "
        "**No es asesoría fiscal** — consultar con un contador."
    ),
)
async def get_fiscal_summary(
    tax_year: int = Query(
        ...,
        ge=2000,
        le=2100,
        description="Año fiscal a consultar (ej. 2025)",
        example=2025,
    ),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> FiscalSummaryResponse:
    return await fiscal_service.get_fiscal_summary(db, tax_year, redis)


# ---------------------------------------------------------------------------
# Endpoint 2: Export CSV para el contador
# ---------------------------------------------------------------------------


@router.get(
    "/export/csv",
    summary="Exportar reporte fiscal en CSV",
    description=(
        "Genera y descarga un archivo CSV con el detalle de todas las "
        "operaciones contables del año fiscal: picks resueltos y "
        "transacciones, ordenados cronológicamente. "
        "Entregable directo para el contador / declaración SAT."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Archivo CSV descargable",
        }
    },
)
async def export_fiscal_csv(
    tax_year: int = Query(
        ...,
        ge=2000,
        le=2100,
        description="Año fiscal a exportar (ej. 2025)",
        example=2025,
    ),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Genera el CSV fiscal usando la librería estándar `csv` + `io.StringIO`.

    No se usan dependencias externas (pandas, openpyxl, etc.).
    El archivo se escribe en memoria y se retorna como StreamingResponse
    para evitar guardar archivos temporales en disco.
    """
    rows = await fiscal_service.get_fiscal_detail_rows(db, tax_year)

    # Escribir CSV en memoria
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=CSV_HEADERS,
        extrasaction="ignore",   # ignorar claves extra si las hubiera
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

    # Rebobinar el buffer al inicio antes de enviarlo
    output.seek(0)

    filename = f"betsync_fiscal_{tax_year}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Fiscal-Year": str(tax_year),
            "X-Total-Records": str(len(rows)),
        },
    )
