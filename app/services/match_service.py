from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.match import Match
from app.schemas.match import MatchCreate


async def create_match(db: AsyncSession, data: MatchCreate) -> Match:
    match = Match(**data.model_dump())
    db.add(match)
    await db.flush()
    return match


async def get_match(db: AsyncSession, match_id: UUID) -> Match:
    match = await db.get(Match, match_id)
    if not match:
        raise NotFoundError("MATCH_NOT_FOUND", f"Match {match_id} not found")
    return match


async def list_matches(
    db: AsyncSession,
    competition_id: Optional[UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Match]:
    query = select(Match)
    if competition_id:
        query = query.where(Match.competition_id == competition_id)
    result = await db.execute(
        query.order_by(Match.kickoff_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())
