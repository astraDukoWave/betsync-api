# claude-progress.md — betsync-api

Last verified: 2026-07-03, against real GitHub state (not agent reports).

## Current verified state

- **betsync-web `main`**: `e2253b2` — Radar UI no longer uses "edge" terminology.
- **betsync-api `main`**: `bf897f1` — `_find_best_odds()` retains per-bookmaker
  price data (`book_prices[]`). `world_cup_sport_slug` = `"soccer_fifa_world_cup"`
  (correct value, matches `c848e1b`).
- Full pipeline test suite (`tests/test_pipeline.py` + `tests/test_picks.py`):
  12/12 passing as of `bf897f1`, run via
  `docker compose run --rm api pytest tests/test_pipeline.py tests/test_picks.py -v`.

## What changed and why (chronological)

1. **Root cause investigation** (pre-sprint): the Radar's "edge" field was
   traced to `implied_prob` (market-implied probability from American odds),
   not a statistical edge. `predictor.py` (real EV formula) exists but is
   never imported by `runner.py` — orphaned code, covered only by
   `TestPredictor` in `tests/test_pipeline.py`.
2. **Sprint 1a** (betsync-web): renamed `edge_pct` → `market_prob` across
   `types.ts`, `RadarKPIBar.tsx`, `RadarFilters.tsx`, `RadarGrid.tsx`,
   `app/radar/page.tsx`. Removed a duplicate `confidence` field that computed
   the exact same value as `edge_pct` (dead redundancy, also caused a sort
   dropdown with two options that produced identical ordering).
   `AIConfig.min_edge_pct` and `app/settings/page.tsx` explicitly excluded.
3. **Settings audit** (discovered during 1a, not yet fixed): none of the 5
   keys the Settings UI writes (`min_edge_pct`, `min_grade`,
   `max_picks_per_day`, `unit_size_usd`, `ai_model`) match any key
   `runner.py._load_config()` reads. The panel is currently non-functional —
   tracked as `sprint-1-bis-settings-keys` in `feature_list.json`.
4. **Sprint 1b** (betsync-api): rewrote `_find_best_odds()` to keep a
   `book_prices[]` list per outcome (bookmaker key + price) instead of
   collapsing immediately to the single best price. `price` field kept
   unchanged for backward compatibility with `_process_odds()` (grade
   calculation untouched). Added 8 new unit tests (`TestFindBestOdds`) —
   the function had zero prior coverage.
   - Mid-sprint incident: the PR branch picked up an unrelated,
     unreported change to `app/core/config.py`
     (`world_cup_sport_slug`) from a stale local `main` on the Codespace
     that had never pulled `origin/main`'s `c848e1b` fix. Caught by
     independent re-cloning and diffing against `origin/main` before merge
     (not by trusting the agent's `git diff --stat` report). Resolved by
     syncing local `main` and re-checking out `config.py` from it before
     the final push.

## Known orphaned / unresolved items

- `predictor.py`: real EV logic exists, has its own tests, but is not wired
  into `runner.py`. Wiring it requires an Alembic migration — `Pick` model
  has no `expected_value` column today (verified directly, not inherited
  from a prior report).
- Settings panel key mismatch — see item 3 above.
- Grade thresholds (`min_implied_prob_class_a/b`) are still fixed values in
  `runner.py`, not yet driven by the confidence score planned for Sprint 1c.

## Next step

**Sprint 1c**: consume `book_prices[]` to compute `consensus_std`,
`best_vs_avg`, `breadth_count`, and use those to assign grade instead of the
fixed `implied_prob` threshold. Open decision before starting: persist the
score on `Pick` (new column + migration) or compute it at read time only.

## Working agreements established this session

- Every sprint closes with an independent re-clone + diff against the real
  `origin/main` before merge — never trust "✅ mergeado" from an agent
  report alone.
- PRs, not direct pushes to `main`, even for zero-risk or docs-only changes.
- Docker/Codespaces split: this Mac (2017 Air) cannot run Docker locally.
  Any prompt asking an agent to run tests or docker compose must target
  Codespaces, not local Cursor.
