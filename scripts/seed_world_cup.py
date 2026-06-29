#!/usr/bin/env python3
"""seed_world_cup.py — Idempotent seed for Soccer sport + FIFA World Cup 2026 competition.

Run once before the first pipeline execution:
    python scripts/seed_world_cup.py

Safe to re-run: uses SELECT-before-INSERT logic, never creates duplicates.
Requires the DB to be running and migrations applied (alembic upgrade head).
"""
import sys
import os

# Allow running from repo root or scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import SyncSessionLocal
from app.models.sport import Sport
from app.models.competition import Competition


def seed(db) -> None:
    # ── 1. Sport: Soccer ─────────────────────────────────────────────────
    sport = db.execute(
        select(Sport).where(Sport.slug == "soccer")
    ).scalar_one_or_none()

    if sport:
        print(f"  ✓ Sport already exists  — id={sport.sport_id}  slug=soccer")
    else:
        sport = Sport(name="Soccer", slug="soccer", is_active=True)
        db.add(sport)
        db.flush()
        print(f"  ✚ Sport created         — id={sport.sport_id}  slug=soccer")

    # ── 2. Competition: FIFA World Cup 2026 ───────────────────────────────
    competition = db.execute(
        select(Competition).where(
            Competition.sport_id == sport.sport_id,
            Competition.name == "FIFA World Cup 2026",
        )
    ).scalar_one_or_none()

    if competition:
        print(
            f"  ✓ Competition already exists — id={competition.competition_id}"
            f"  name='{competition.name}'"
            f"  tier={competition.tier}"
            f"  active={competition.is_active}"
        )
        # Ensure it is active and tier A
        if not competition.is_active or competition.tier != "A":
            competition.is_active = True
            competition.tier = "A"
            print("    → Updated to active=True, tier=A")
    else:
        competition = Competition(
            sport_id=sport.sport_id,
            name="FIFA World Cup 2026",
            country="World",
            tier="A",
            is_active=True,
        )
        db.add(competition)
        db.flush()
        print(
            f"  ✚ Competition created     — id={competition.competition_id}"
            f"  name='{competition.name}'"
        )

    db.commit()
    print("\n  ✅ Seed complete. Ready to run the pipeline.")


if __name__ == "__main__":
    print("\n🌍 BetSync — FIFA World Cup 2026 Seed\n")
    db = SyncSessionLocal()
    try:
        seed(db)
    except Exception as e:
        db.rollback()
        print(f"\n❌ Seed failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
