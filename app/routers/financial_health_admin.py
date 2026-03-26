import hmac
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.schemas.reconciliation import FinancialHealthSummarySchema
from app.services import reconciliation_service

router = APIRouter(prefix="/admin/financial-health")


def _verify_reconciliation_secret(
    x_reconciliation_secret: Annotated[Optional[str], Header()] = None,
) -> None:
    expected = (settings.admin_reconciliation_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Financial health admin is not configured (admin_reconciliation_secret).",
        )
    if not x_reconciliation_secret or not hmac.compare_digest(
        x_reconciliation_secret,
        expected,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Reconciliation-Secret header.",
        )


@router.get(
    "",
    response_model=FinancialHealthSummarySchema,
    dependencies=[Depends(_verify_reconciliation_secret)],
)
async def get_financial_health(
    db: AsyncSession = Depends(get_db),
):
    summary = await reconciliation_service.summarize_financial_health(db)
    return FinancialHealthSummarySchema(
        total_users=summary.total_users,
        ok_users=summary.ok_users,
        warning_users=summary.warning_users,
        critical_users=summary.critical_users,
    )
