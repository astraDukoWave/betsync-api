"""Pipeline runner — synchronous, runs inside a Celery task.

Key design decisions:
- A single Odds API call fetches events and is reused for both match upsert
  and odds indexing (no double-spend of API quota).
- `_upsert_world_cup_matches` is idempotent: SELECT before INSERT, update
  kickoff_at if it drifted.
- `_bulk_insert_picks` back-fills `pick_id` into each pick dict so the parlay
  builder can reference them (fixes a silent KeyError bug).
- The World Cup sport slug is read from `settings.world_cup_sport_slug` so it
  can be changed via env var without a code deploy.
"""
import hashlib
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import redis as sync_redis
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.config import SystemConfig
from app.models.match import Match, MatchStatus
from app.models.parlay import Parlay, ParlayStatus, ParlayType
from app.models.parlay_pick import ParlayPick
from app.models.pick import Pick, PickGrade, PickSource, PickStatus
from app.worker.pipeline.calculator import (
    american_to_decimal, calc_implied_prob, build_parlay_suggestions,
)
from app.services.pick_service import DomainValidator
from app.worker.pipeline.odds_client import OddsApiClient, OddsAPIError

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Synchronous pipeline runner for Celery tasks."""

    def __init__(self, db: Session, settings):
        self.db = db
        self.settings = settings
        self._redis = sync_redis.from_url(settings.redis_url, decode_responses=True)
        self.client = OddsApiClient(
            api_key=settings.odds_api_key,
            base_url=settings.odds_api_base_url,
            max_requests_per_minute=settings.odds_api_max_requests_per_minute,
            idempotency_ttl_seconds=settings.odds_api_idempotency_ttl_seconds,
            max_retry_attempts=settings.odds_api_retry_attempts,
            redis_client=self._redis,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────

    def run(self, run_date: str) -> dict[str, Any]:
        run_dt = date.fromisoformat(run_date)
        config = self._load_config()

        # Step 1: fetch events ONCE from Odds API (single API call)
        sport_slug = self.settings.world_cup_sport_slug
        events = self._fetch_world_cup_events(sport_slug, run_dt)

        if not events:
            logger.warning(
                "No events returned from Odds API for slug=%s on %s. "
                "Check ODDS_API_KEY and WORLD_CUP_SPORT_SLUG.",
                sport_slug, run_date,
            )
            return {"picks_suggested": 0, "parlays_suggested": 0}

        # Step 2: upsert matches into DB from the events we already fetched
        self._upsert_world_cup_matches(events)

        # Step 3: load scheduled matches that match pipeline criteria
        matches = self._load_scheduled_matches(run_dt, config)
        if not matches:
            logger.info(
                "No scheduled matches found for pipeline on %s. "
                "Ensure seed_world_cup.py has been run and the competition "
                "is active with tier in %s.",
                run_date, config["active_tiers"],
            )
            return {"picks_suggested": 0, "parlays_suggested": 0}

        # Step 4: build odds index from already-fetched events (no second API call)
        odds_data = self._build_odds_index(events)

        # Step 5: generate picks
        picks = self._process_odds(matches, odds_data, config)
        self._bulk_insert_picks(picks, run_dt)

        # Step 6: generate parlay suggestions from grade-A picks
        parlays_count = self._bulk_insert_parlays(picks, config, run_dt)

        return {
            "picks_suggested": len(picks),
            "parlays_suggested": parlays_count,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Config
    # ──────────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        result = self.db.execute(select(SystemConfig))
        entries = result.scalars().all()
        cfg = {}
        for e in entries:
            cfg[e.key] = e.value
        return {
            "min_implied_prob_class_a": float(cfg.get("min_implied_prob_class_a", "0.55")),
            "min_implied_prob_class_b": float(cfg.get("min_implied_prob_class_b", "0.50")),
            "min_parlay_odds_total": float(cfg.get("min_parlay_odds_total", "1.80")),
            "active_tiers": cfg.get("active_competition_tiers", "A,B").split(","),
            "min_grade": cfg.get("pipeline_min_grade", "B"),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Odds API — single fetch, dual use
    # ──────────────────────────────────────────────────────────────────────

    def _fetch_world_cup_events(
        self, sport_slug: str, run_dt: date
    ) -> list[dict]:
        """Fetch upcoming events for the given sport slug.

        Uses idempotency cache so retries on the same day don't re-hit the API.
        Returns an empty list on error (pipeline continues gracefully).
        """
        idempotency_key = hashlib.sha256(
            f"v1|{run_dt.isoformat()}|{sport_slug}|h2h|us".encode(),
        ).hexdigest()
        try:
            events = self.client.get_odds(
                sport=sport_slug,
                markets="h2h",
                regions="us",
                idempotency_key=idempotency_key,
            )
            logger.info(
                "Fetched %d events from Odds API for slug=%s",
                len(events), sport_slug,
            )
            return events
        except OddsAPIError as e:
            logger.error(
                "Odds API error fetching slug=%s: %s. "
                "Verify ODDS_API_KEY and WORLD_CUP_SPORT_SLUG.",
                sport_slug, e,
            )
        except Exception as e:
            logger.error("Unexpected error fetching events for slug=%s: %s", sport_slug, e)
        return []

    @staticmethod
    def _build_odds_index(events: list[dict]) -> dict:
        """Index events by (home_team.lower(), away_team.lower()) for O(1) lookup."""
        index = {}
        for event in events:
            key = (
                event.get("home_team", "").lower(),
                event.get("away_team", "").lower(),
            )
            index[key] = event
        return index

    # ──────────────────────────────────────────────────────────────────────
    # Match upsert — idempotent, uses Odds API team names as source of truth
    # ──────────────────────────────────────────────────────────────────────

    def _upsert_world_cup_matches(self, events: list[dict]) -> int:
        """Upsert Match rows for all events returned by Odds API.

        Uses the active World Cup competition from the DB. Idempotent:
        if a match (home_team, away_team, competition_id) already exists,
        only kickoff_at is updated if it drifted.

        Returns the count of newly inserted matches.
        """
        competition = self.db.execute(
            select(Competition).where(
                Competition.name.ilike("%World Cup%"),
                Competition.is_active.is_(True),
            ).limit(1)
        ).scalar_one_or_none()

        if not competition:
            logger.warning(
                "No active World Cup competition in DB. "
                "Run `python scripts/seed_world_cup.py` first."
            )
            return 0

        inserted = 0
        for event in events:
            home = event.get("home_team", "").strip()
            away = event.get("away_team", "").strip()
            commence_time = event.get("commence_time", "")

            if not home or not away or not commence_time:
                logger.debug("Skipping incomplete event: %s", event.get("id"))
                continue

            try:
                kickoff_at = datetime.fromisoformat(
                    commence_time.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                logger.warning(
                    "Cannot parse commence_time=%r for %s vs %s",
                    commence_time, home, away,
                )
                continue

            existing = self.db.execute(
                select(Match).where(
                    Match.competition_id == competition.competition_id,
                    Match.home_team == home,
                    Match.away_team == away,
                )
            ).scalar_one_or_none()

            if existing:
                # Only update kickoff if it drifted (schedule changes happen)
                if existing.kickoff_at != kickoff_at:
                    logger.debug(
                        "Updating kickoff_at for %s vs %s: %s → %s",
                        home, away, existing.kickoff_at, kickoff_at,
                    )
                    existing.kickoff_at = kickoff_at
            else:
                match = Match(
                    competition_id=competition.competition_id,
                    home_team=home,
                    away_team=away,
                    kickoff_at=kickoff_at,
                    status=MatchStatus.scheduled,
                )
                self.db.add(match)
                inserted += 1

        self.db.flush()
        logger.info(
            "Match upsert complete: %d new, %d already existed",
            inserted, len(events) - inserted,
        )
        return inserted

    # ──────────────────────────────────────────────────────────────────────
    # Match loading
    # ──────────────────────────────────────────────────────────────────────

    def _load_scheduled_matches(self, run_dt: date, config: dict) -> list[Match]:
        """Load all active scheduled matches from active competitions of the right tier."""
        now_utc = datetime.now(timezone.utc)
        result = self.db.execute(
            select(Match)
            .join(Competition, Match.competition_id == Competition.competition_id)
            .where(
                Match.status == MatchStatus.scheduled,
                Match.kickoff_at >= now_utc,  # only future matches
                Competition.is_active.is_(True),
                Competition.tier.in_(config["active_tiers"]),
            )
        )
        matches = list(result.scalars().all())
        logger.info("Found %d scheduled upcoming matches for pipeline", len(matches))
        return matches

    # ──────────────────────────────────────────────────────────────────────
    # Odds processing → picks
    # ──────────────────────────────────────────────────────────────────────

    def _process_odds(
        self, matches: list[Match], odds_data: dict, config: dict,
    ) -> list[dict]:
        picks = []
        for match in matches:
            key = (match.home_team.lower(), match.away_team.lower())
            event = odds_data.get(key)
            if not event:
                logger.debug(
                    "No odds found for %s vs %s — skipping",
                    match.home_team, match.away_team,
                )
                continue

            bookmakers = event.get("bookmakers", [])
            if not bookmakers:
                continue

            best = self._find_best_odds(bookmakers)
            for market_key, outcomes in best.items():
                for outcome in outcomes:
                    odds_am = outcome.get("price", 0)
                    if odds_am == 0 or -100 < odds_am < 100:
                        continue

                    try:
                        odds_dec = american_to_decimal(odds_am)
                        imp_prob = calc_implied_prob(odds_dec)
                    except ValueError:
                        continue

                    if imp_prob >= config["min_implied_prob_class_a"]:
                        grade = "A"
                    elif imp_prob >= config["min_implied_prob_class_b"]:
                        grade = "B"
                    else:
                        grade = "C"

                    if grade > config["min_grade"]:
                        continue

                    picks.append({
                        "match_id": match.match_id,
                        "sportsbook_id": None,
                        "market": market_key,
                        "selection": outcome.get("name", ""),
                        "odds_american": odds_am,
                        "odds_decimal": odds_dec,
                        "implied_prob": imp_prob,
                        "grade": grade,
                        # pick_id populated in _bulk_insert_picks after flush
                    })

        logger.info("Processed %d potential picks from odds data", len(picks))
        return picks

    def _find_best_odds(self, bookmakers: list[dict]) -> dict:
        """Aggregate per outcome: best (highest) price across bookmakers, plus
        the full per-bookmaker price list (book_prices) needed for Sprint 1c
        consensus/breadth scoring.

        `price` remains the best price — required for backward compatibility
        with _process_odds (grade calculation). Do not remove or rename it.

        In American odds the numerically highest value is best for the bettor
        (e.g. -122 > -127 > -130), so the existing ``price > existing["price"]``
        comparison is the correct criterion and is preserved unchanged.
        """
        best: dict[str, list[dict]] = {}
        for bm in bookmakers:
            bookmaker_key = bm.get("key", "unknown")
            for mkt in bm.get("markets", []):
                mkt_key = mkt.get("key", "h2h")
                if mkt_key not in best:
                    best[mkt_key] = []
                for outcome in mkt.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price", 0)
                    existing = next(
                        (o for o in best[mkt_key] if o["name"] == name), None
                    )
                    if existing:
                        existing["book_prices"].append(
                            {"bookmaker": bookmaker_key, "price": price}
                        )
                        if price > existing["price"]:
                            existing["price"] = price
                    else:
                        best[mkt_key].append({
                            "name": name,
                            "price": price,
                            "book_prices": [
                                {"bookmaker": bookmaker_key, "price": price}
                            ],
                        })
        return best

    # ──────────────────────────────────────────────────────────────────────
    # DB writes
    # ──────────────────────────────────────────────────────────────────────

    def _bulk_insert_picks(self, picks: list[dict], run_dt: date) -> None:
        """Insert Pick rows and back-fill `pick_id` into each dict.

        The pick_id back-fill is required so _bulk_insert_parlays can reference
        the newly created picks (build_parlay_suggestions uses p["pick_id"]).
        """
        default_sb = self._get_default_sportsbook_id()
        objs: list[Pick] = []

        for p in picks:
            obj = Pick(
                match_id=p["match_id"],
                sportsbook_id=p.get("sportsbook_id") or default_sb,
                run_date=run_dt,
                market=p["market"],
                selection=p["selection"],
                odds_american=p["odds_american"],
                odds_decimal=Decimal(str(p["odds_decimal"])),
                implied_prob=Decimal(str(p["implied_prob"])),
                grade=PickGrade(p["grade"]),
                status=PickStatus.pending,
                source=PickSource.pipeline,
            )
            DomainValidator.validate(
                obj,
                None,
                profit_tolerance=self.settings.pick_profit_tolerance,
            )
            self.db.add(obj)
            objs.append(obj)

        # Single flush → all PKs assigned by DB
        self.db.flush()

        # Back-fill pick_id so parlay builder can reference them
        for p, obj in zip(picks, objs):
            p["pick_id"] = obj.pick_id

        logger.info("Inserted %d pipeline picks", len(picks))

    def _get_default_sportsbook_id(self) -> uuid.UUID:
        from app.models.sportsbook import Sportsbook
        result = self.db.execute(
            select(Sportsbook.sportsbook_id).limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        sb = Sportsbook(name="Default", currency="USD", odds_format_default="american")
        self.db.add(sb)
        self.db.flush()
        return sb.sportsbook_id

    def _bulk_insert_parlays(
        self, picks: list[dict], config: dict, run_dt: date
    ) -> int:
        grade_a_picks = [p for p in picks if p["grade"] == "A"]
        if len(grade_a_picks) < 2:
            return 0

        suggestions = build_parlay_suggestions(
            grade_a_picks,
            min_odds_total=config["min_parlay_odds_total"],
        )

        default_sb = self._get_default_sportsbook_id()
        count = 0
        for s in suggestions[:5]:
            parlay = Parlay(
                sportsbook_id=default_sb,
                run_date=run_dt,
                type=ParlayType.regular,
                stake=Decimal("1.00"),
                odds_total=Decimal(str(s["odds_total"])),
                potential_return=Decimal(str(s["odds_total"])),
                status=ParlayStatus.pending,
            )
            self.db.add(parlay)
            self.db.flush()

            # Link picks to parlay
            for pick_dict in s["picks"]:
                pp = ParlayPick(
                    parlay_id=parlay.parlay_id,
                    pick_id=pick_dict["pick_id"],
                )
                self.db.add(pp)
            count += 1

        self.db.flush()
        logger.info("Inserted %d parlay suggestions", count)
        return count
