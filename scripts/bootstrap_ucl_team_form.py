"""Resumable API-Football team-form bootstrap for the 2026/27 Champions League."""

import argparse
import json
import os
import sys
from pathlib import Path

import certifi
from dotenv import load_dotenv

MongoClient = None  # Loaded only after the required credentials are validated.

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.competitions import get_competition
from src.services.team_form import (
    ApiFootballClient,
    EspnTeamFormClient,
    FailoverTeamFormClient,
    TeamFormService,
)


def main(argv=None):
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", type=int, default=int(os.getenv("UCL_TEAM_FORM_LEAGUE", "2")))
    parser.add_argument("--season", type=int, default=int(os.getenv("UCL_TEAM_FORM_SEASON", "2026")))
    args = parser.parse_args(argv)
    uri = os.getenv("MONGO_URI", "").strip()
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not uri:
        raise SystemExit("MONGO_URI is required")
    if not key:
        raise SystemExit("API_FOOTBALL_KEY is required")

    mongo_client = MongoClient
    if mongo_client is None:
        from pymongo import MongoClient as mongo_client
    mongo = mongo_client(uri, tlsCAFile=certifi.where())
    try:
        collection = mongo["wm2026_db"][get_competition("ucl2026").cache_collection]
        client = FailoverTeamFormClient(
            ApiFootballClient(key, cache_collection=collection, competition="ucl2026"),
            EspnTeamFormClient(season=args.season),
        )
        try:
            result = TeamFormService(collection, client).bootstrap(league=args.league, season=args.season)
        except RuntimeError as exc:
            raise SystemExit(f"Team-form bootstrap failed: {exc}") from exc
        print(json.dumps(result, sort_keys=True))
    finally:
        close = getattr(mongo, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
