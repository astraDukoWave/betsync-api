from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError, ConflictError
from app.models.sportsbook import Sportsbook
from app.schemas.sportsbook import SportsbookCreate, SportsbookUpdate, SportsbookResponse

router = APIRouter(prefix="/sportsbooks")


@router.get("/", response_model=list[SportsbookResponse])
async def list_sportsbooks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Sportsbook).order_by(Sportsbook.name))
    return list(result.scalars().all())


@router.post("/", response_model=SportsbookResponse, status_code=status.HTTP_201_CREATED)
async def create_sportsbook(
    data: SportsbookCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(Sportsbook).where(Sportsbook.name == data.name)
    )
    if existing:
        raise ConflictError("SPORTSBOOK_EXISTS", f"Sportsbook '{data.name}' already exists")

    sportsbook = Sportsbook(**data.model_dump())
    db.add(sportsbook)
    await db.flush()
    return sportsbook


@router.patch("/{sportsbook_id}", response_model=SportsbookResponse)
async def update_sportsbook(
    sportsbook_id: UUID,
    data: SportsbookUpdate,
    db: AsyncSession = Depends(get_db),
):
    sportsbook = await db.get(Sportsbook, sportsbook_id)
    if not sportsbook:
        raise NotFoundError("SPORTSBOOK_NOT_FOUND", f"Sportsbook {sportsbook_id} not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sportsbook, field, value)

    await db.flush()
    return sportsbook
