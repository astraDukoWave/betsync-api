#!/usr/bin/env python3
"""reset_pipeline_data.py — DEV-ONLY: wipe pipeline picks, WC matches, and Redis pipeline keys.

⚠️  WARNING: This permanently deletes data. Never run against production.

Usage:
    python scripts/reset_pipeline_data.py [--dry-run]

What it deletes:
    1. parlay_picks → picks with source='pipeline'
    2. picks with source='pipeline'
    3. parlays (all pipeline-generated)
    4. matches belonging to any "World Cup" competition
    5. Redis keys: pipeline:ran:*, job:*, odds:idempotency:*

What it keeps:
    - sports table
    - competitions table
    - sportsbooks table
    - user_balances, ledger, transactions (financial data untouched)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis as sync_redis
from sqlalchemy import text, select, delete
from app.core.database import SyncSessionLocal
from app.core.config import settings


def reset(db, dry_run: bool = False) -> None:
    tag = "[DRY-RUN] " if dry_run else ""

    # ── 1. Count before ──────────────────────────────────────────────────
    pp_count = db.execute(
        text("""
            SELECT COUNT(*) FROM parlay_picks pp
            JOIN picks p ON p.pick_id = pp.pick_id
            WHERE p.source = 'pipeline'
        """)
    ).scalar()

    pick_count = db.execute(
        text("SELECT COUNT(*) FROM picks WHERE source = 'pipeline'")
    ).scalar()

    parlay_count = db.execute(
        text("SELECT COUNT(*) FROM parlays")
    ).scalar()

    match_count = db.execute(
        text("""
            SELECT COUNT(*) FROM matches m
            JOIN competitions c ON c.competition_id = m.competition_id
            WHERE c.name ILIKE '%World Cup%'
        """)
    ).scalar()

    print(f"\n  Found:")
    print(f"    parlay_picks (pipeline):  {pp_count}")
    print(f"    picks (pipeline):         {pick_count}")
    print(f"    parlays (all):            {parlay_count}")
    print(f"    matches (World Cup):      {match_count}")

    if dry_run:
        print("\n  [DRY-RUN] No changes made.")
        return

    # ── 2. Delete in FK-safe order ────────────────────────────────────────
    # parlay_picks that reference pipeline picks
    r1 = db.execute(
        text("""
            DELETE FROM parlay_picks
            WHERE pick_id IN (
                SELECT pick_id FROM picks WHERE source = 'pipeline'
            )
        """)
    )
    print(f"  Deleted {r1.rowcount} parlay_picks")

    # pipeline picks
    r2 = db.execute(
        text("DELETE FROM picks WHERE source = 'pipeline'")
    )
    print(f"  Deleted {r2.rowcount} picks")

    # all parlays (they're pipeline-generated; no user parlays in dev)
    r3 = db.execute(text("DELETE FROM parlays"))
    print(f"  Deleted {r3.rowcount} parlays")

    # World Cup matches (now safe because picks referencing them are gone)
    r4 = db.execute(
        text("""
            DELETE FROM matches
            WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE name ILIKE '%World Cup%'
            )
        """)
    )
    print(f"  Deleted {r4.rowcount} World Cup matches")

    db.commit()

    # ── 3. Flush Redis pipeline keys ──────────────────────────────────────
    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    patterns = ["pipeline:ran:*", "job:*", "odds:idempotency:*"]
    total_redis_deleted = 0
    for pattern in patterns:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            total_redis_deleted += len(keys)
    print(f"  Deleted {total_redis_deleted} Redis keys ({', '.join(patterns)})")

    print("\n  ✅ Reset complete. Run seed_world_cup.py then the pipeline again.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="DEV-ONLY: Reset pipeline data for BetSync local dev."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting.",
    )
    args = parser.parse_args()

    print("\n⚠️  BetSync — Pipeline Data Reset (DEV-ONLY)\n")

    if not args.dry_run:
        confirm = input("  Type 'yes' to confirm deletion: ").strip().lower()
        if confirm != "yes":
            print("  Aborted.")
            sys.exit(0)

    db = SyncSessionLocal()
    try:
        reset(db, dry_run=args.dry_run)
    except Exception as e:
        db.rollback()
        print(f"\n❌ Reset failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()
