from __future__ import annotations

"""Financial reconciliation (Phase 6.2.2).

Aggregates on ``picks`` here are confined to admin/audit tooling and batched jobs — not dashboard
request paths (DECISION-001). Callers should run via ``POST /api/v1/admin/reconciliation/run``
or future Celery schedules, not user-facing synchronous APIs.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import UserBalance
from app.models.ledger import LedgerEntry
from app.models.pick import Pick, PickStatus
from app.models.reconciliation_audit import ReconciliationAudit

logger = logging.getLogger(__name__)

TOLERANCE = Decimal("0.01")

ReconciliationSeverity = Literal["OK", "WARNING", "CRITICAL"]


@dataclass(frozen=True)
class ReconciliationResult:
    user_id: UUID
    escrow_expected: Decimal
    escrow_actual: Decimal
    ledger_expected: Decimal
    ledger_actual: Decimal
    escrow_drift: Decimal
    ledger_drift: Decimal
    severity: ReconciliationSeverity


@dataclass
class ReconciliationSummary:
    total_users: int
    ok_users: int
    warning_users: int
    critical_users: int
    anomalies: list[ReconciliationResult]
    duration_seconds: float


def _classify_severity(escrow_drift: Decimal, ledger_drift: Decimal) -> ReconciliationSeverity:
    if ledger_drift > TOLERANCE:
        return "CRITICAL"
    if escrow_drift > TOLERANCE:
        return "WARNING"
    return "OK"


def _log_reconciliation_line(
    *,
    user_id: UUID,
    severity: ReconciliationSeverity,
    escrow_drift: Decimal,
    ledger_drift: Decimal,
) -> None:
    logger.info(
        "[RECONCILIATION] user_id=%s severity=%s escrow_drift=%s ledger_drift=%s",
        user_id,
        severity,
        escrow_drift,
        ledger_drift,
    )


async def reconcile_user(db: AsyncSession, user_id: UUID) -> ReconciliationResult:
    """Read-only reconciliation for one wallet row (aggregates on picks/ledger for this user only)."""
    bal_row = await db.execute(
        select(UserBalance.available_balance, UserBalance.locked_balance).where(
            UserBalance.user_id == user_id
        )
    )
    bal = bal_row.one_or_none()
    if bal is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError(
            "USER_BALANCE_NOT_FOUND",
            f"No user_balances row for user_id={user_id}",
        )

    available_balance, locked_balance = bal
    escrow_actual = locked_balance

    exp_escrow = await db.execute(
        select(func.coalesce(func.sum(Pick.stake), 0)).where(
            Pick.user_id == user_id,
            Pick.status == PickStatus.pending,
        )
    )
    escrow_expected = Decimal(exp_escrow.scalar_one())

    # Ledger integrity: running balance from the latest line (SUM(amount) is wrong for internal moves).
    last_ledger = await db.execute(
        select(LedgerEntry.balance_after, LedgerEntry.locked_after)
        .where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(1)
    )
    last_row = last_ledger.one_or_none()
    if last_row is None:
        ledger_expected_total = Decimal("0")
    else:
        balance_after, locked_after = last_row
        ledger_expected_total = balance_after + locked_after

    actual_total = available_balance + locked_balance

    escrow_drift = abs(escrow_expected - escrow_actual)
    ledger_drift = abs(ledger_expected_total - actual_total)
    severity = _classify_severity(escrow_drift, ledger_drift)

    return ReconciliationResult(
        user_id=user_id,
        escrow_expected=escrow_expected,
        escrow_actual=escrow_actual,
        ledger_expected=ledger_expected_total,
        ledger_actual=actual_total,
        escrow_drift=escrow_drift,
        ledger_drift=ledger_drift,
        severity=severity,
    )


async def _persist_if_anomaly(db: AsyncSession, result: ReconciliationResult) -> None:
    if result.severity == "OK":
        return
    db.add(
        ReconciliationAudit(
            id=uuid.uuid4(),
            user_id=result.user_id,
            escrow_drift=result.escrow_drift,
            ledger_drift=result.ledger_drift,
            severity=result.severity,
        )
    )
    await db.flush()


async def reconcile_all_users(
    db: AsyncSession,
    *,
    batch_size: int = 500,
    redis: Any = None,
) -> ReconciliationSummary:
    """Paginate ``user_balances`` by ``user_id`` without loading all IDs into memory."""
    from app.services.operational_metrics import (
        incr_reconciliation_critical,
        incr_reconciliation_drift_detected,
        incr_reconciliation_run,
    )

    started = time.perf_counter()
    await incr_reconciliation_run(redis)

    total_users = 0
    ok_users = 0
    warning_users = 0
    critical_users = 0
    anomalies: list[ReconciliationResult] = []

    last_user_id: UUID | None = None

    while True:
        q = select(UserBalance.user_id).order_by(UserBalance.user_id.asc()).limit(batch_size)
        if last_user_id is not None:
            q = q.where(UserBalance.user_id > last_user_id)

        batch_ids: Sequence[UUID] = (await db.execute(q)).scalars().all()
        if not batch_ids:
            break

        for uid in batch_ids:
            total_users += 1
            result = await reconcile_user(db, uid)

            if result.severity == "OK":
                ok_users += 1
                continue

            anomalies.append(result)
            await incr_reconciliation_drift_detected(redis)
            if result.severity == "CRITICAL":
                critical_users += 1
                await incr_reconciliation_critical(redis)
            else:
                warning_users += 1

            _log_reconciliation_line(
                user_id=result.user_id,
                severity=result.severity,
                escrow_drift=result.escrow_drift,
                ledger_drift=result.ledger_drift,
            )
            await _persist_if_anomaly(db, result)

        last_user_id = batch_ids[-1]

    duration_seconds = time.perf_counter() - started
    return ReconciliationSummary(
        total_users=total_users,
        ok_users=ok_users,
        warning_users=warning_users,
        critical_users=critical_users,
        anomalies=anomalies,
        duration_seconds=duration_seconds,
    )


async def list_recent_anomalies(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> list[ReconciliationAudit]:
    rows = await db.execute(
        select(ReconciliationAudit)
        .order_by(ReconciliationAudit.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())
