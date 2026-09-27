"""Small, credit-free UCL provider adapters.

The adapters return data plus provenance.  They intentionally do not invent a
rating for a club which ClubElo did not publish.
"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from html.parser import HTMLParser
from datetime import datetime, timezone

import requests

from src.competitions import competition_document_id, find_competition_document, get_competition
from src.constants import TEAM_MAPPING
from src.services.snapshots import normalize_status


CLUBELO_URL = os.getenv("CLUBELO_URL", "https://clubelo.com/Ranking")
CLUBELO_TEAM_SLUGS = {
    "AEK": "AEK",
    "Feyenoord": "Feyenoord",
    "LASK": "lask",
    "Sabah FK": "",
    "Shakhtar": "Shakhtar",
    "Slovan": "SlovanBratislava",
    "Viking": "Viking",
}

# Keep aliases at the provider boundary; callers use the names from their
# fixture/provider payloads and never have to guess which spelling is canonical.
CLUBELO_ALIASES = {
    "Bayern Munich": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "Paris Saint-Germain": "Paris Saint-Germain",
    "Paris SG": "Paris Saint-Germain",
    "Inter Milan": "Inter",
    "Internazionale": "Inter",
    "Atlético Madrid": "Atlético",
}


class _RankingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _canonical_club(name: str) -> str:
    clean = " ".join((name or "").split())
    return CLUBELO_ALIASES.get(clean, clean)


def parse_clubelo_html(html: str) -> list[dict]:
    """Parse the ranking table into ``team``/``elo`` rows."""
    parser = _RankingParser()
    parser.feed(html or "")
    rows = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        try:
            # Ranking is currently [rank, club, elo].  Looking at the last
            # numeric cell also tolerates an extra coefficient column.
            rank = int(float(cells[0].replace(",", "")))
            elo_index = next(i for i in range(len(cells) - 1, 0, -1) if _is_number(cells[i]))
            elo = float(cells[elo_index].replace(",", ""))
        except (ValueError, StopIteration):
            continue
        team = _canonical_club(cells[1])
        if team:
            rows.append({"rank": rank, "team": team, "team_name": team, "elo": elo, "elo_rating": elo})
    if rows:
        return rows

    marker = "var vegaJson ="
    marker_index = (html or "").find(marker)
    if marker_index < 0:
        return []
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[marker_index + len(marker):].lstrip())
    except (json.JSONDecodeError, TypeError):
        return []
    for dataset in (payload.get("datasets") or {}).values():
        if not isinstance(dataset, list):
            continue
        live_rows = []
        for item in dataset:
            if not isinstance(item, dict) or "Name" not in item or "Elo" not in item:
                continue
            try:
                elo = float(item["Elo"])
            except (TypeError, ValueError):
                continue
            team = _canonical_club(str(item["Name"]))
            if team:
                rank = len(live_rows) + 1
                live_rows.append({"rank": rank, "team": team, "team_name": team, "elo": elo, "elo_rating": elo})
        if live_rows:
            return live_rows
    return []


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_team_page(html: str, team: str) -> dict | None:
    json_match = re.search(
        rf'"Name"\s*:\s*"{re.escape(team)}".{{0,240}}?"Elo"\s*:\s*([0-9]{{3,4}}(?:\.[0-9]+)?)',
        html or "",
        re.IGNORECASE | re.DOTALL,
    )
    text = " ".join(unescape(re.sub(r"<[^>]+>", " ", html or "")).split())
    team_match = re.search(rf"{re.escape(team)}\s+([0-9]{{3,4}}(?:\.[0-9]+)?)", text, re.IGNORECASE)
    match = team_match or json_match or re.search(
        r"(?:Current\s+)?Elo\s*:?\s*([0-9]{3,4}(?:\.[0-9]+)?)", text, re.IGNORECASE
    )
    if not match:
        return None
    elo = float(match.group(1))
    return {"rank": None, "team": team, "team_name": team, "elo": elo, "elo_rating": elo}


def _required_ucl_clubs(cache_collection, competition) -> set[str]:
    fixtures = find_competition_document(cache_collection, competition, "matches_cache") or {}
    return {
        TEAM_MAPPING.get(str(match.get(field) or ""), str(match.get(field) or ""))
        for match in fixtures.get("data", [])
        if isinstance(match, dict)
        for field in ("home_team", "away_team")
        if match.get(field)
    }


def _rating_teams(rows: list[dict]) -> set[str]:
    return {
        TEAM_MAPPING.get(str(row.get("team") or row.get("team_name") or ""), str(row.get("team") or row.get("team_name") or ""))
        for row in rows
        if isinstance(row, dict) and (row.get("team") or row.get("team_name"))
    }


def _persist_clubelo(cache_collection, document: dict) -> None:
    comp = get_competition(document.get("competition"))
    provider_id = competition_document_id(comp, "clubelo_ratings")
    compatibility_id = competition_document_id(comp, "elo_ratings")
    provider_values = {key: value for key, value in document.items() if key != "_id"}
    compatibility_values = {
        key: document.get(key)
        for key in ("competition", "status", "source", "observed_at", "error", "rows", "coverage", "provenance")
    }
    for document_id, values in ((provider_id, provider_values), (compatibility_id, compatibility_values)):
        cache_collection.update_one(
            {"_id": document_id},
            {"$set": values, "$setOnInsert": {"_id": document_id}},
            upsert=True,
        )


def ingest_clubelo(
    cache_collection,
    competition=None,
    *,
    observed_at: datetime | None = None,
    request_get=None,
    url: str | None = None,
) -> dict:
    """Fetch ClubElo and persist its cache document with provenance.

    A failed refresh returns the previous rows as ``stale`` when available;
    otherwise it returns ``failed`` with no fabricated ratings.
    """
    comp = get_competition(competition)
    key = "clubelo_ratings"
    cache_id = competition_document_id(comp, key)
    previous = find_competition_document(cache_collection, comp, key) or find_competition_document(
        cache_collection, comp, "elo_ratings"
    ) or {}
    required = _required_ucl_clubs(cache_collection, comp) if comp.id == "ucl2026" else set()
    previous_rows = [dict(row) for row in previous.get("rows", []) if isinstance(row, dict)]
    previous_complete = bool(required) and required.issubset(_rating_teams(previous_rows))
    observed = (observed_at or datetime.now(timezone.utc)).isoformat()
    source_url = url or CLUBELO_URL
    getter = request_get or requests.get
    try:
        if comp.id == "ucl2026" and not required:
            raise ValueError("UCL fixture coverage is unavailable; ClubElo ratings cannot be validated")
        response = getter(source_url, timeout=10, headers=_conditional_headers(previous))
        response.raise_for_status()
        not_modified = getattr(response, "status_code", None) == 304 and previous.get("rows")
        rows = previous_rows if not_modified else parse_clubelo_html(getattr(response, "text", ""))
        if not rows:
            raise ValueError("ClubElo ranking page contained no ratings")
        present = _rating_teams(rows)
        page_errors = {}
        base_url = source_url.rsplit("/", 1)[0]
        for team in sorted(required - present):
            slug = CLUBELO_TEAM_SLUGS.get(team)
            if slug is None:
                page_errors[team] = "ClubElo team page is not mapped"
                continue
            team_url = f"{base_url}/{slug}"
            try:
                team_response = getter(team_url, timeout=10, headers={})
                team_response.raise_for_status()
                row = _parse_team_page(getattr(team_response, "text", ""), team)
                if row is None:
                    raise ValueError("ClubElo team page contained no current rating")
                row["provenance"] = {"source": "clubelo", "url": team_url, "observed_at": observed}
                rows.append(row)
                present.add(team)
            except Exception as exc:
                page_errors[team] = str(exc)
        present = _rating_teams(rows)
        missing = sorted(required - present)
        coverage = {
            "required": len(required),
            "available": len(required & present),
            "missing": missing,
            "errors": page_errors,
        }
        if missing:
            error = f"ClubElo snapshot is incomplete; missing current ratings for: {', '.join(missing)}"
            if previous_complete:
                status = "stale"
                rows = previous_rows
                provenance = previous.get("provenance") or {
                    "source": "clubelo", "url": source_url, "observed_at": previous.get("observed_at"),
                }
            else:
                status = "failed"
                rows = []
                provenance = {"source": "clubelo", "url": source_url, "observed_at": observed}
        else:
            status = "fresh"
            error = None
            provenance = {
                "source": "clubelo",
                "url": source_url,
                "observed_at": observed,
                "etag": _header(response, "etag") or previous.get("etag"),
                "last_modified": _header(response, "last-modified") or (previous.get("provenance") or {}).get("last_modified"),
            }
        document = {
            "_id": cache_id,
            "competition": comp.id,
            "status": status,
            "source": "clubelo",
            "observed_at": observed,
            "error": error,
            "rows": rows,
            "coverage": coverage,
            "provenance": provenance,
            "etag": _header(response, "etag") or previous.get("etag"),
        }
        _persist_clubelo(cache_collection, document)
        return document
    except Exception as exc:
        if previous_complete:
            rows = previous_rows
            status = "stale"
            coverage = previous.get("coverage") or {
                "required": len(required), "available": len(required), "missing": [], "errors": {},
            }
            provenance = previous.get("provenance") or {
                "source": "clubelo", "url": source_url, "observed_at": previous.get("observed_at"),
            }
        else:
            rows = []
            status = "failed"
            known = _rating_teams(previous_rows)
            coverage = {
                "required": len(required),
                "available": len(required & known),
                "missing": sorted(required - known),
                "errors": {"provider": str(exc)},
            }
            provenance = {"source": "clubelo", "url": source_url, "observed_at": observed}
        document = {
            "_id": cache_id,
            "competition": comp.id,
            "status": status,
            "source": "clubelo",
            "observed_at": observed,
            "rows": rows,
            "error": str(exc),
            "coverage": coverage,
            "provenance": provenance,
            "etag": previous.get("etag"),
        }

        # Keep both the provider contract and the compatibility Elo document
        # truthful after a failed refresh; enrichment reads the latter.
        _persist_clubelo(cache_collection, document)
        return document


def _conditional_headers(previous: dict) -> dict:
    headers = {}
    if previous.get("etag"):
        headers["If-None-Match"] = previous["etag"]
    last_modified = (previous.get("provenance") or {}).get("last_modified")
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _header(response, name: str):
    headers = getattr(response, "headers", {}) or {}
    return headers.get(name) or headers.get(name.title())


def compose_match_sources(
    odds: dict | None,
    elo: dict | None,
    *,
    observed_at: str | None = None,
    odds_status: str = "fresh",
    elo_status: str = "fresh",
    errors: dict | None = None,
) -> dict:
    """Combine source payloads without filling missing data with defaults."""
    odds_status = normalize_status(odds_status)
    elo_status = normalize_status(elo_status)
    has_odds = _source_available(odds)
    has_elo = _source_available(elo)
    if has_odds and has_elo:
        mode = "odds+elo"
    elif has_odds:
        mode = "odds-only"
    elif has_elo:
        mode = "elo-only"
    else:
        mode = "unavailable"
    source_statuses = [
        _source_status(odds, odds_status) if has_odds else None,
        _source_status(elo, elo_status) if has_elo else None,
    ]
    if mode == "unavailable":
        status = "unavailable"
    elif "failed" in source_statuses:
        status = "failed"
    elif "stale" in source_statuses:
        status = "stale"
    else:
        status = "fresh"
    source_names = [name for present, name in ((has_odds, "odds_api"), (has_elo, "clubelo")) if present]
    result = {
        "status": status,
        "source_mode": mode,
        "source": "+".join(source_names) or "none",
        "odds": odds,
        "elo": elo,
        "observed_at": observed_at,
        "provenance": {
            "odds": {"source": "odds_api", "status": odds_status, "observed_at": observed_at},
            "elo": {"source": "clubelo", "status": elo_status, "observed_at": observed_at},
        },
    }
    source_errors = dict(errors or {})
    for name, payload in (("odds", odds), ("elo", elo)):
        if isinstance(payload, dict) and payload.get("error"):
            source_errors.setdefault(name, payload["error"])
    if source_errors:
        result["errors"] = source_errors
    return result


def _source_available(payload) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    status = payload.get("status")
    if status in {"failed", "unavailable"}:
        return False
    if "rows" in payload:
        return bool(payload.get("rows"))
    if "odds" in payload:
        return bool(payload.get("odds"))
    return True


def _source_status(payload, fallback: str) -> str:
    value = payload.get("status", fallback) if isinstance(payload, dict) else fallback
    return normalize_status(value, default=fallback)


# Names used by small integrations/readers can stay descriptive and stable.
fetch_clubelo = ingest_clubelo
normalize_sources = compose_match_sources
