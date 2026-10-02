"""Competition metadata and storage scoping.

The API keeps the World Cup as its compatibility default.  A competition is
resolved once at the route boundary and is then used to select provider
identifiers and Mongo collections, so two competitions cannot share mutable
cache or bot state by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


DEFAULT_COMPETITION_ID = "wc2026"


@dataclass(frozen=True)
class Competition:
    id: str
    display_name: str
    short_name: str
    espn_slug: str
    odds_api_sport_key: str
    season: str
    ruleset: str
    archive_collection: str
    cache_collection: str
    custom_bot_collection: str

    @property
    def display(self) -> Mapping[str, str]:
        return MappingProxyType({"name": self.display_name, "short_name": self.short_name})

    @property
    def mongo_collections(self) -> Mapping[str, str]:
        return MappingProxyType({
            "archive": self.archive_collection,
            "cache": self.cache_collection,
            "custom_bot": self.custom_bot_collection,
        })

    @property
    def odds_api_key(self) -> str:
        """Short alias used by provider adapters."""
        return self.odds_api_sport_key

    @property
    def espn_competition(self) -> str:
        """Alias matching ESPN's competition terminology."""
        return self.espn_slug

    @property
    def is_club_competition(self) -> bool:
        return self.id in {"ucl2026", "epl2026"}

    def __getitem__(self, key: str) -> Any:
        """Allow registry consumers to use either attributes or dict syntax."""
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "short_name": self.short_name,
            "display": dict(self.display),
            "espn_slug": self.espn_slug,
            "odds_api_sport_key": self.odds_api_sport_key,
            "season": self.season,
            "ruleset": self.ruleset,
            "archive_collection": self.archive_collection,
            "cache_collection": self.cache_collection,
            "custom_bot_collection": self.custom_bot_collection,
            "mongo_collections": dict(self.mongo_collections),
        }


COMPETITIONS: dict[str, Competition] = {
    "wc2026": Competition(
        id="wc2026",
        display_name="FIFA World Cup 2026",
        short_name="WC 2026",
        espn_slug="fifa.world",
        odds_api_sport_key="soccer_fifa_world_cup",
        season="2026",
        ruleset="srf_tippspiel",
        archive_collection="archive",
        cache_collection="cache",
        custom_bot_collection="custom_bot",
    ),
    "ucl2026": Competition(
        id="ucl2026",
        display_name="UEFA Champions League 2026/27",
        short_name="UCL 2026/27",
        espn_slug="uefa.champions",
        odds_api_sport_key="soccer_uefa_champs_league",
        season="2026/27",
        ruleset="srf_tippspiel",
        archive_collection="archive_ucl2026",
        cache_collection="cache_ucl2026",
        custom_bot_collection="custom_bot_ucl2026",
    ),
    "epl2026": Competition(
        id="epl2026",
        display_name="English Premier League 2026/27",
        short_name="EPL 2026/27",
        espn_slug="eng.1",
        odds_api_sport_key="soccer_epl",
        season="2026/27",
        ruleset="srf_tippspiel",
        archive_collection="archive_epl2026",
        cache_collection="cache_epl2026",
        custom_bot_collection="custom_bot_epl2026",
    ),
}

# Public aliases keep the registry easy to discover without duplicating data.
COMPETITION_REGISTRY = COMPETITIONS
REGISTRY = COMPETITIONS


def get_competition(value: str | Competition | None = None) -> Competition:
    """Resolve a competition ID, defaulting omitted/blank values to WC."""
    if isinstance(value, Competition):
        return value
    if value is None:
        competition_id = DEFAULT_COMPETITION_ID
    elif not isinstance(value, str):
        raise ValueError(f"Unknown competition: {value}")
    elif not value.strip():
        competition_id = DEFAULT_COMPETITION_ID
    else:
        # IDs are protocol values. Do not silently normalize casing or
        # surrounding characters, which can hide client/configuration bugs.
        competition_id = value
    try:
        return COMPETITIONS[competition_id]
    except KeyError as exc:
        raise ValueError(f"Unknown competition: {value}") from exc


def require_competition(value: str | Competition | None = None) -> Competition:
    """Resolve a route value and expose invalid IDs as a client error."""
    from fastapi import HTTPException

    try:
        return get_competition(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Clear aliases make the boundary intent obvious to callers and keep future
# routes from reimplementing defaulting/validation.
parse_competition = get_competition
resolve_competition = get_competition


def list_competitions() -> list[dict[str, Any]]:
    """Return serializable metadata for the public competition selector."""
    return [competition.to_dict() for competition in COMPETITIONS.values()]


def competition_document_id(competition: str | Competition | None, key: str) -> str:
    """Return a collision-resistant Mongo document ID for a logical key."""
    return f"{get_competition(competition).id}:{key}"


def document_ids(competition: str | Competition | None, key: str) -> tuple[str, ...]:
    """Return scoped ID first, plus the old WC ID for read compatibility."""
    comp = get_competition(competition)
    scoped = competition_document_id(comp, key)
    if comp.id == DEFAULT_COMPETITION_ID:
        return scoped, key
    return (scoped,)


def find_competition_document(collection: Any, competition: str | Competition | None, key: str) -> Any:
    """Read a scoped document, falling back to an unscoped WC legacy ID."""
    for doc_id in document_ids(competition, key):
        try:
            document = collection.find_one({"_id": doc_id})
        except Exception:
            document = None
        if document:
            return document
    return None


def collection_for(collections: Any, competition: str | Competition | None) -> Any:
    """Select a competition-specific collection while accepting old callers."""
    comp = get_competition(competition)
    if isinstance(collections, Mapping):
        return collections[comp.id]
    return collections
