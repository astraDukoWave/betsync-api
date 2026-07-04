#!/usr/bin/env bash
# init.sh — betsync-api standard startup + verification path

# IMPORTANT: This project's Docker stack only runs in GitHub Codespaces.
# astraDuko's local machine (MacBook Air 2017) cannot run Docker — do not
# attempt to run this script outside Codespaces. If `docker` is not found,
# stop and hand off to a Codespaces session instead of improvising a local
# venv (this has already wasted a full debugging cycle once — see
# claude-progress.md, Sprint 1b incident notes).

set -euo pipefail

echo "== init.sh: betsync-api =="

if ! command -v docker &> /dev/null; then
  echo "ERROR: docker not found in PATH."
  echo "This environment cannot run the project stack."
  echo "Switch to a GitHub Codespace for this repo and re-run init.sh there."
  exit 1
fi

echo "-- Confirming working directory --"
pwd
if [ ! -f "docker-compose.yml" ]; then
  echo "ERROR: docker-compose.yml not found. Run this from the repo root."
  exit 1
fi

echo "-- Reading current state (claude-progress.md, feature_list.json) --"
if [ -f "claude-progress.md" ]; then
  echo "Found claude-progress.md — read it before starting new work."
else
  echo "WARNING: claude-progress.md not found. Proceeding without prior state context."
fi

echo "-- Bringing up postgres + redis (healthchecked) --"
docker compose up -d postgres redis

echo "-- Waiting for healthy postgres + redis --"
for svc in postgres redis; do
  echo " waiting on $svc..."
  timeout 60 bash -c "until [ \"\$(docker compose ps -q $svc | xargs docker inspect -f '{{.State.Health.Status}}')\" = 'healthy' ]; do sleep 2; done"
done

echo "-- Running migrations + starting api (applies alembic upgrade head) --"
docker compose up -d api

echo "-- Smoke check: api container is up --"
sleep 3
docker compose ps api

echo "-- Running baseline verification (fast test subset) --"
docker compose run --rm api pytest tests/test_pipeline.py tests/test_picks.py -v

echo ""
echo "== init.sh complete =="
echo "If baseline verification above failed, fix that BEFORE starting new"
echo "feature work — do not stack changes on a broken starting state."
echo ""
echo "Optional next steps depending on task:"
echo "  python scripts/seed_world_cup.py   # seed World Cup 2026 fixtures"
echo "  docker compose up -d worker        # start Celery worker (pipeline queue)"
echo "  docker compose run --rm api pytest tests/ -v  # full suite"
