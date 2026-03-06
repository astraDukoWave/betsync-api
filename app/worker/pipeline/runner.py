import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
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
from app.worker.pipeline.odds_client import OddsApiClient, OddsAPIError

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Synchronous pipeline runner for Celery tasks."""

    def __init__(self, db: Session, settings):
        self.db = db
        self.settings = settings
        self.client = OddsApiClient(
            api_key=settings.odds_api_key,
            base_url=settings.odds_api_base_url,
        )

    def run(self, run_date: str) -> dict[str, Any]:
        run_dt = date.fromisoformat(run_date)
        config = self._load_config()
        matches = self._load_scheduled_matches(run_dt, config)

        if not matches:
            logger.info("No scheduled matches for %s", run_date)
            return {"picks_suggested": 0, "parlays_suggested": 0}

        odds_data = self._fetch_all_odds()
        picks = self._process_odds(matches, odds_data, config)
        self._bulk_insert_picks(picks, run_dt)
        parlays_count = self._bulk_insert_parlays(picks, config, run_dt)

        return {
            "picks_suggested": len(picks),
            "parlays_suggested": parlays_count,
        }

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

    def _load_scheduled_matches(self, run_dt: date, config: dict) -> list[Match]:
        result = self.db.execute(
            select(Match)
            .join(Competition, Match.competition_id == Competition.competition_id)
            .where(
                Match.status == MatchStatus.scheduled,
                Competition.is_active.is_(True),
                Competition.tier.in_(config["active_tiers"]),
            )
        )
        matches = list(result.scalars().all())
        logger.info("Found %d scheduled matches for pipeline", len(matches))
        return matches

    def _fetch_all_odds(self) -> dict:
        odds_index = {}
        try:
            data = self.client.get_odds(sport="soccer", markets="h2h")
            for event in data:
                key = (
                    event.get("home_team", "").lower(),
                    event.get("away_team", "").lower(),
                )
                odds_index[key] = event
        except OddsAPIError as e:
            logger.error("Odds API error: %s", e)
        except Exception as e:
            logger.error("Unexpected error fetching odds: %s", e)
        return odds_index

    def _process_odds(
        self, matches: list[Match], odds_data: dict, config: dict,
    ) -> list[dict]:
        picks = []
        for match in matches:
            key = (match.home_team.lower(), match.away_team.lower())
            event = odds_data.get(key)
            if not event:
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
                    })

        logger.info("Processed %d potential picks from odds data", len(picks))
        return picks

    def _find_best_odds(self, bookmakers: list[dict]) -> dict:
        best = {}
        for bm in bookmakers:
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
                        if price > existing["price"]:
                            existing["price"] = price
                    else:
                        best[mkt_key].append({"name": name, "price": price})
        return best

    def _bulk_insert_picks(self, picks: list[dict], run_dt: date):
        for p in picks:
            obj = Pick(
                match_id=p["match_id"],
                sportsbook_id=p.get("sportsbook_id") or self._get_default_sportsbook_id(),
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
            self.db.add(obj)

        self.db.flush()
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

    def _bulk_insert_parlays(self, picks: list[dict], config: dict, run_dt: date) -> int:
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
            count += 1

        logger.info("Inserted %d parlay suggestions", count)
        return count
