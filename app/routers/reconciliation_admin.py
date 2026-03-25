import hmac
from typing import Annotated, Optional

import redis.asyncio as aioredis
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, get_redis
from app.schemas.reconciliation import (
    ReconciliationAnomaliesResponse,
    ReconciliationAuditRowSchema,
    ReconciliationFixResponse,
    ReconciliationResultSchema,
    ReconciliationSummarySchema,
)
from app.services import reconciliation_service

router = APIRouter(prefix="/admin/reconciliation")


def _verify_reconciliation_secret(
    x_reconciliation_secret: Annotated[Optional[str], Header()] = None,
) -> None:
    expected = (settings.admin_reconciliation_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reconciliation admin is not configured (admin_reconciliation_secret).",
        )
    if not x_reconciliation_secret or not hmac.compare_digest(
        x_reconciliation_secret,
        expected,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Reconciliation-Secret header.",
        )


@router.post(
    "/run",
    response_model=ReconciliationSummarySchema,
    dependencies=[Depends(_verify_reconciliation_secret)],
)
async def run_reconciliation(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    summary = await reconciliation_service.reconcile_all_users(db, redis=redis)
    return ReconciliationSummarySchema(
        total_users=summary.total_users,
        ok_users=summary.ok_users,
        warning_users=summary.warning_users,
        critical_users=summary.critical_users,
        anomalies=[ReconciliationResultSchema.model_validate(a) for a in summary.anomalies],
        duration_seconds=summary.duration_seconds,
    )


@router.get(
    "/anomalies",
    response_model=ReconciliationAnomaliesResponse,
    dependencies=[Depends(_verify_reconciliation_secret)],
)
async def list_reconciliation_anomalies(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = await reconciliation_service.list_recent_anomalies(db, limit=limit)
    return ReconciliationAnomaliesResponse(
        items=[ReconciliationAuditRowSchema.model_validate(r) for r in rows],
    )


@router.post(
    "/{user_id}/fix",
    response_model=ReconciliationFixResponse,
    dependencies=[Depends(_verify_reconciliation_secret)],
)
async def fix_user_balance_admin(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await reconciliation_service.fix_user_balance(db, user_id)
    return ReconciliationFixResponse.model_validate(
        {
            "user_id": result.user_id,
            "drift_type_before": result.drift_type_before.value,
            "repaired": result.repaired,
            "previous_available": result.previous_available,
            "previous_locked": result.previous_locked,
            "new_available": result.new_available,
            "new_locked": result.new_locked,
        }
    )
