from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.config import DEFAULT_USER_ID
from app.core.dependencies import get_db, get_redis
from app.core.exceptions import ConflictError
from app.core.idempotency import (
    abort_pick_create_if_processing,
    begin_pick_create,
    complete_pick_create,
    pick_create_body_fingerprint,
)
from app.models.pick import PickGrade, PickSource, PickStatus
from app.schemas.pick import (
    PickCreate, PickUpdate, PickResolve, PickConfirm,
    PickResponse, PickListResponse,
)
from app.services import pick_service, parlay_service
from app.services.cache_service import invalidate_dashboard_cache

router = APIRouter(prefix="/picks")


@router.post("/", response_model=PickResponse, status_code=status.HTTP_201_CREATED)
async def create_pick(
    request: Request,
    data: PickCreate,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    redis_key: Optional[str] = None
    fingerprint: Optional[str] = None

    if idempotency_key:
        fingerprint = pick_create_body_fingerprint(data)
        outcome = await begin_pick_create(redis, idempotency_key, fingerprint)
        if outcome.kind == "cached":
            return JSONResponse(
                status_code=outcome.status_code,
                content=outcome.body,
                headers={
                    "X-Idempotent-Replay": "true",
                    "X-Idempotency-Key": outcome.idempotency_key,
                },
            )
        if outcome.kind == "conflict_processing":
            raise ConflictError(
                "IDEMPOTENCY_IN_PROGRESS",
                "An identical request is still being processed for this idempotency key",
            )
        if outcome.kind == "conflict_mismatch":
            raise ConflictError(
                "IDEMPOTENCY_BODY_MISMATCH",
                "Idempotency-Key was already used with a different request body",
            )
        redis_key = outcome.redis_key

    try:
        pick = await pick_service.create_pick(db, data)
        await invalidate_dashboard_cache(redis)
        if idempotency_key and redis_key and fingerprint is not None:
            payload = PickResponse.model_validate(pick).model_dump(mode="json")

            async def _store_idempotent_result() -> None:
                await complete_pick_create(
                    redis,
                    redis_key,
                    fingerprint,
                    status.HTTP_201_CREATED,
                    payload,
                )

            hooks = getattr(request.state, "post_commit_hooks", None)
            if hooks is None:
                request.state.post_commit_hooks = [_store_idempotent_result]
            else:
                hooks.append(_store_idempotent_result)
        headers = {"X-Idempotent-Replay": "false"}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=PickResponse.model_validate(pick).model_dump(mode="json"),
            headers=headers,
        )
    except Exception:
        if redis_key is not None:
            await abort_pick_create_if_processing(redis, redis_key)
        raise


@router.get("/", response_model=PickListResponse)
async def list_picks(
    run_date: Optional[date] = None,
    pick_status: Optional[PickStatus] = None,
    sport_id: Optional[UUID] = None,
    competition_id: Optional[UUID] = None,
    market: Optional[str] = None,
    grade: Optional[PickGrade] = None,
    source: Optional[PickSource] = None,
    user_id: UUID = Query(default=DEFAULT_USER_ID),
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    items, total = await pick_service.list_picks(
        db,
        run_date=run_date,
        status=pick_status,
        sport_id=sport_id,
        competition_id=competition_id,
        market=market,
        grade=grade,
        source=source,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return PickListResponse(
        items=items, total=total, limit=limit, offset=offset,
    )


@router.get("/{pick_id}", response_model=PickResponse)
async def get_pick(
    pick_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.get_pick(db, pick_id)


@router.patch("/{pick_id}", response_model=PickResponse)
async def update_pick(
    pick_id: UUID,
    data: PickUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.update_pick(db, pick_id, data)


@router.patch("/{pick_id}/result", response_model=PickResponse)
async def resolve_pick(
    pick_id: UUID,
    data: PickResolve,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    pick = await pick_service.resolve_pick(db, pick_id, data)
    await parlay_service.auto_resolve_parlays_for_pick(db, pick_id)
    await invalidate_dashboard_cache(redis)
    return pick


@router.delete("/{pick_id}", response_model=PickResponse)
async def delete_pick(
    pick_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.delete_pick(db, pick_id)


@router.patch("/{pick_id}/confirm", response_model=PickResponse)
async def confirm_pick(
    pick_id: UUID,
    data: PickConfirm,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.confirm_pick(db, pick_id, data)
