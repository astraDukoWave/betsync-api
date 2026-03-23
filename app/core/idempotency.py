"""Atomic idempotency for mutating endpoints using Redis SET NX + cached JSON responses."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

_IDEM_PREFIX = "idem:v1:picks:create"


@dataclass(frozen=True)
class IdempotencyProceed:
    redis_key: str
    kind: Literal["proceed"] = "proceed"


@dataclass(frozen=True)
class IdempotencyCached:
    status_code: int
    body: dict[str, Any]
    kind: Literal["cached"] = "cached"


@dataclass(frozen=True)
class IdempotencyConflictProcessing:
    kind: Literal["conflict_processing"] = "conflict_processing"


@dataclass(frozen=True)
class IdempotencyConflictMismatch:
    kind: Literal["conflict_mismatch"] = "conflict_mismatch"


IdempotencyOutcome = Union[
    IdempotencyProceed,
    IdempotencyCached,
    IdempotencyConflictProcessing,
    IdempotencyConflictMismatch,
]


def pick_create_body_fingerprint(data: BaseModel) -> str:
    canonical = json.dumps(
        data.model_dump(mode="json", round_trip=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redis_key(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"{_IDEM_PREFIX}:{digest}"


async def begin_pick_create(
    redis,
    idempotency_key: str,
    body_fingerprint: str,
) -> IdempotencyOutcome:
    """
    Try to acquire an exclusive processing lock. If the key already exists, return cached
    outcome or a conflict when another request is still processing / body mismatch.
    """
    key = _redis_key(idempotency_key)
    proc_ttl = settings.idempotency_processing_ttl_seconds

    acquired = await redis.set(key, "processing", nx=True, ex=proc_ttl)
    if acquired:
        return IdempotencyProceed(redis_key=key)

    raw: Optional[str] = await redis.get(key)
    if raw is None:
        acquired = await redis.set(key, "processing", nx=True, ex=proc_ttl)
        if acquired:
            return IdempotencyProceed(redis_key=key)
        raw = await redis.get(key)

    if raw is None:
        return IdempotencyConflictProcessing()

    if raw == "processing":
        return IdempotencyConflictProcessing()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("idempotency corrupt payload for key %s", key)
        return IdempotencyConflictProcessing()

    if payload.get("fingerprint") != body_fingerprint:
        return IdempotencyConflictMismatch()

    return IdempotencyCached(
        status_code=int(payload["status_code"]),
        body=payload["body"],
    )


async def complete_pick_create(
    redis,
    redis_key: str,
    body_fingerprint: str,
    status_code: int,
    response_body: dict[str, Any],
) -> None:
    value = json.dumps(
        {
            "status_code": status_code,
            "body": response_body,
            "fingerprint": body_fingerprint,
        },
        separators=(",", ":"),
    )
    await redis.set(
        redis_key,
        value,
        ex=settings.idempotency_result_ttl_seconds,
    )


async def abort_pick_create_if_processing(redis, redis_key: str) -> None:
    raw = await redis.get(redis_key)
    if raw == "processing":
        await redis.delete(redis_key)
