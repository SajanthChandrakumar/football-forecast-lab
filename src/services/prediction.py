"""Shared, competition-aware prediction pipeline.

The public routes used to each carry a slightly different copy of the odds,
Elo, score-matrix, and knockout logic.  This module is the single boundary for
those calculations.  It deliberately keeps provider I/O outside the service:
callers pass the latest trusted inputs and receive a serialisable prediction.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.competitions import competition_document_id, get_competition
from src.math_engine import MathEngine
from src.services.snapshots import normalize_status, select_t15_snapshot, parse_time
from src.services.ucl_providers import compose_match_sources


VALID_STAGES = {"league", "playoff", "round_of_16", "quarterfinal", "semifinal", "final"}
VALID_LEGS = {"single", "first", "second"}
SCORE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
MODEL_VERSION = "prediction-v1"


def infer_stage(round_name: Any) -> str:
    """Map provider round labels onto the stable prediction context enum."""
    text = str(round_name or "").lower().replace("-", " ")
    if "round of 16" in text or "r16" in text:
        return "round_of_16"
    if "quarter" in text:
        return "quarterfinal"
    if "semi" in text:
        return "semifinal"
    if text.strip() == "final" or text.endswith(" final"):
        return "final"
    if "playoff" in text or "knockout" in text:
        return "playoff"
    return "league"


def _score_pair(value: Any) -> tuple[int, int] | None:
    if isinstance(value, str):
        match = SCORE_RE.fullmatch(value)
        if match:
            return int(match.group(1)), int(match.group(2))
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            home, away = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        if home >= 0 and away >= 0:
            return home, away
    if isinstance(value, Mapping):
        for keys in (("home", "away"), ("home_score", "away_score")):
            if all(key in value for key in keys):
                try:
                    home, away = int(value[keys[0]]), int(value[keys[1]])
                except (TypeError, ValueError):
                    return None
                if home >= 0 and away >= 0:
                    return home, away
    return None


@dataclass(frozen=True)
class MatchContext:
    competition: str = "wc2026"
    stage: str = "league"
    tie_id: str | None = None
    leg: str = "single"
    first_leg_score: str | None = None
    first_leg_home_score: int | None = None
    first_leg_away_score: int | None = None
    score_90: str | None = None
    score_aet: str | None = None
    shootout_winner: str | None = None
    extra_time_eligible: bool = False
    commence_time: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_match_context(value: Mapping[str, Any] | MatchContext | None = None, *, competition=None) -> MatchContext:
    """Normalize provider/archive context and reject unknown stage/leg values."""
    if isinstance(value, MatchContext):
        return value
    raw = dict(value or {})
    nested = raw.get("match_context")
    if isinstance(nested, Mapping):
        merged = dict(nested)
        merged.update({key: val for key, val in raw.items() if key != "match_context"})
        raw = merged
    comp = get_competition(competition or raw.get("competition")).id
    stage = raw.get("stage") or infer_stage(raw.get("round"))
    if stage == "league" and raw.get("is_ko_phase"):
        stage = "playoff"
    leg = raw.get("leg") or "single"
    if stage not in VALID_STAGES:
        raise ValueError(f"Unknown match stage: {stage}")
    if leg not in VALID_LEGS:
        raise ValueError(f"Unknown match leg: {leg}")

    first = _score_pair(raw.get("first_leg_score"))
    if first is None:
        first_home = raw.get("first_leg_home_score", raw.get("first_leg_home"))
        first_away = raw.get("first_leg_away_score", raw.get("first_leg_away"))
        if first_home is not None and first_away is not None:
            first = _score_pair((first_home, first_away))
    first_score = raw.get("first_leg_score")
    if first is not None:
        first_score = f"{first[0]}:{first[1]}"
    return MatchContext(
        competition=comp,
        stage=stage,
        tie_id=str(raw["tie_id"]) if raw.get("tie_id") is not None else None,
        leg=leg,
        first_leg_score=first_score,
        first_leg_home_score=first[0] if first else None,
        first_leg_away_score=first[1] if first else None,
        score_90=raw.get("score_90"),
        score_aet=raw.get("score_aet"),
        shootout_winner=raw.get("shootout_winner"),
        extra_time_eligible=bool(raw.get("extra_time_eligible", raw.get("is_ko", False))),
        commence_time=raw.get("commence_time"),
    )


def extra_time_eligible_for_score(context: MatchContext | Mapping[str, Any], home_score: int, away_score: int) -> bool:
    """Return whether a 90-minute cell advances to extra time."""
    ctx = build_match_context(context)
    if ctx.leg == "first":
        return False
    if ctx.competition == "wc2026" and ctx.extra_time_eligible:
        return home_score == away_score
    if ctx.stage == "final":
        return home_score == away_score
    if ctx.leg != "second" or ctx.first_leg_home_score is None or ctx.first_leg_away_score is None:
        return False
    return ctx.first_leg_home_score + home_score == ctx.first_leg_away_score + away_score


def _matrix_copy(matrix: pd.DataFrame) -> pd.DataFrame:
    result = matrix.astype(float).copy()
    total = float(result.to_numpy().sum())
    if total <= 0:
        raise ValueError("Score matrix has no probability mass")
    return result / total


def build_aet_distribution(
    score_matrix: pd.DataFrame,
    xg_home: float,
    xg_away: float,
    context: MatchContext | Mapping[str, Any],
) -> pd.DataFrame:
    """Conditionally convolve aggregate-tie cells with independent 30-minute Poisson increments.

    The returned matrix keeps the 90-minute dimensions.  Poisson tails outside
    those dimensions are folded out by conditioning each triggered cell on the
    representable score range; this preserves an exactly normalized matrix and
    leaves every non-trigger 90-minute cell untouched.
    """
    base = _matrix_copy(score_matrix)
    ctx = build_match_context(context)
    labels_home = list(base.index)
    labels_away = list(base.columns)
    try:
        home_values = [int(label) for label in labels_home]
        away_values = [int(label) for label in labels_away]
    except (TypeError, ValueError) as exc:
        raise ValueError("Score matrix labels must be integer goals") from exc
    output = np.zeros_like(base.to_numpy(dtype=float))
    max_home = len(labels_home) - 1
    max_away = len(labels_away) - 1
    inc_home = np.asarray(poisson.pmf(np.arange(max_home + 1), max(0.0, float(xg_home) / 3.0)))
    inc_away = np.asarray(poisson.pmf(np.arange(max_away + 1), max(0.0, float(xg_away) / 3.0)))
    for row, home in enumerate(home_values):
        for col, away in enumerate(away_values):
            probability = float(base.iloc[row, col])
            if probability <= 0:
                continue
            if not extra_time_eligible_for_score(ctx, home, away):
                output[row, col] += probability
                continue
            weights = []
            cells = []
            for add_home, p_home in enumerate(inc_home):
                for add_away, p_away in enumerate(inc_away):
                    target_home, target_away = home + add_home, away + add_away
                    if target_home <= max_home and target_away <= max_away:
                        cells.append((target_home, target_away))
                        weights.append(float(p_home * p_away))
            total = sum(weights)
            if total <= 0:
                output[row, col] += probability
                continue
            for (target_home, target_away), weight in zip(cells, weights):
                output[target_home, target_away] += probability * weight / total
    result = pd.DataFrame(output, index=base.index, columns=base.columns)
    result.index.name = base.index.name
    result.columns.name = base.columns.name
    return result / float(result.to_numpy().sum())


def advancement_probabilities(context: MatchContext | Mapping[str, Any], home_score: int, away_score: int) -> dict[str, float]:
    """Return advancement probabilities; penalties are never put into SRF scores."""
    ctx = build_match_context(context)
    if extra_time_eligible_for_score(ctx, home_score, away_score):
        return {"home": 0.5, "away": 0.5}
    if ctx.stage == "league":
        return {"home": 0.0, "away": 0.0}
    if home_score > away_score:
        return {"home": 1.0, "away": 0.0}
    if away_score > home_score:
        return {"home": 0.0, "away": 1.0}
    return {"home": 0.5, "away": 0.5}


def pool_lambda(user_points: int, leader_points: int, remaining_srf_max_points: int) -> float:
    remaining = max(1, int(remaining_srf_max_points))
    return min(0.6, 0.6 * max(0, int(leader_points) - int(user_points)) / remaining)


def _field_counts(value: Mapping[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(value, Mapping) or not value:
        return None
    clean: dict[str, int] = {}
    for tip, count in value.items():
        if not isinstance(tip, str) or SCORE_RE.fullmatch(tip) is None:
            return None
        if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or int(count) < 0:
            return None
        clean[tip.strip()] = int(count)
    return clean if sum(clean.values()) > 0 else None


def pool_tip_from_field(
    score_matrix: pd.DataFrame,
    field_counts: Mapping[str, Any] | None,
    user_points: int,
    leader_points: int,
    remaining_srf_max_points: int,
    *,
    is_ko_phase: bool = False,
) -> dict[str, Any]:
    """Choose the pool tip from a manually entered opponent field."""
    counts = _field_counts(field_counts)
    if counts is None:
        return {"tip": None, "status": "unavailable", "field_count": 0, "lambda": None}
    matrix = _matrix_copy(score_matrix)
    lam = pool_lambda(user_points, leader_points, remaining_srf_max_points)
    total_count = sum(counts.values())
    opponent_tips = [(tip, count) for tip, count in counts.items() if count]
    candidates = []
    for home in range(6):
        for away in range(6):
            candidate = f"{home}:{away}"
            expected = 0.0
            expected_sq = 0.0
            for row_label in matrix.index:
                for col_label in matrix.columns:
                    probability = float(matrix.loc[row_label, col_label])
                    actual_home, actual_away = int(row_label), int(col_label)
                    candidate_points = MathEngine.calculate_actual_points(candidate, f"{actual_home}:{actual_away}", is_ko_phase)
                    opponents = sum(
                        count * MathEngine.calculate_actual_points(tip, f"{actual_home}:{actual_away}", is_ko_phase)
                        for tip, count in opponent_tips
                    ) / total_count
                    advantage = candidate_points - opponents
                    expected += probability * advantage
                    expected_sq += probability * advantage * advantage
            std = math.sqrt(max(0.0, expected_sq - expected * expected))
            candidates.append({
                "tip": candidate,
                "expected_advantage": expected,
                "std_advantage": std,
                "pool_score": expected + lam * std,
            })
    best = max(candidates, key=lambda item: (item["pool_score"], -int(item["tip"].split(":")[0]), -int(item["tip"].split(":")[1])))
    return {
        **best,
        "status": "available",
        "field_count": total_count,
        "lambda": lam,
        "candidates": candidates,
    }


def _safe_odds(value: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("status") in {"failed", "unavailable"}:
        return None
    source = value.get("odds") if isinstance(value.get("odds"), Mapping) else value
    try:
        result = {key: float(source[key]) for key in ("home", "draw", "away")}
        if any(not math.isfinite(item) or item <= 1.0 for item in result.values()):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    for key in ("over25", "under25"):
        if key in source:
            try:
                value_float = float(source[key])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value_float) and value_float > 1.0:
                result[key] = value_float
    return result


def _safe_elo(value: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("status") in {"failed", "unavailable"}:
        return None
    source = value.get("elo") if isinstance(value.get("elo"), Mapping) else value
    keys = (("home_rating", "away_rating"), ("home", "away"))
    for home_key, away_key in keys:
        if home_key in source and away_key in source:
            try:
                home, away = float(source[home_key]), float(source[away_key])
            except (TypeError, ValueError):
                continue
            if all(math.isfinite(item) for item in (home, away)):
                return {"home_rating": home, "away_rating": away}
    return None


def _source_metadata(
    value: Mapping[str, Any] | None,
    *,
    default_source: str,
    default_observed_at: str | None,
) -> tuple[str, str, Any, dict[str, Any]]:
    """Read source metadata without letting numeric input cleaning discard it."""
    if not isinstance(value, Mapping):
        return default_source, "fresh", default_observed_at, {}
    nested = value.get("provenance")
    provenance = dict(nested) if isinstance(nested, Mapping) else {}
    source = value.get("source") or provenance.get("source") or default_source
    status = normalize_status(value.get("status"), default="fresh")
    observed_at = value.get("observed_at") or default_observed_at
    return str(source), str(status), observed_at, provenance


def _matrix_dict(matrix: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        str(row): {str(col): float(matrix.loc[row, col]) for col in matrix.columns}
        for row in matrix.index
    }


class PredictionService:
    """Build model and pool predictions from already-collected inputs."""

    def __init__(self, math_engine, *, model_version: str = MODEL_VERSION):
        self.math_engine = math_engine
        self.model_version = model_version

    def _probabilities(self, odds: dict[str, float] | None, elo: dict[str, float] | None) -> tuple[dict[str, float], dict[str, Any]] | None:
        if odds is not None:
            true_probs = self.math_engine.remove_margin(odds["home"], odds["draw"], odds["away"])
            if elo is not None:
                elo_share = self.math_engine.get_elo_probability(elo["home_rating"], elo["away_rating"])
                win_loss = true_probs["home"] + true_probs["away"]
                if win_loss <= 0:
                    return None
                probabilities = {
                    "home": (true_probs["home"] / win_loss * 0.7 + elo_share * 0.3) * win_loss,
                    "draw": true_probs["draw"],
                    "away": (true_probs["away"] / win_loss * 0.7 + (1.0 - elo_share) * 0.3) * win_loss,
                }
                return probabilities, {"true_probs": true_probs, "elo_share": elo_share}
            return true_probs, {"true_probs": true_probs}
        if elo is not None:
            elo_share = self.math_engine.get_elo_probability(elo["home_rating"], elo["away_rating"])
            difference = abs(elo["home_rating"] - elo["away_rating"])
            draw = max(0.18, 0.28 - difference / 10000.0)
            return {
                "home": elo_share * (1.0 - draw),
                "draw": draw,
                "away": (1.0 - elo_share) * (1.0 - draw),
            }, {"true_probs": None, "elo_share": elo_share}
        return None

    def evaluation_probabilities(
        self,
        odds: Mapping[str, Any] | None,
        elo: Mapping[str, Any] | None,
    ) -> dict[str, dict[str, float]] | None:
        """Return model, no-margin market, and pure Elo 1X2 vectors."""
        clean_odds, clean_elo = _safe_odds(odds), _safe_elo(elo)
        if clean_odds is None or clean_elo is None:
            return None
        model = self._probabilities(clean_odds, clean_elo)
        market = self._probabilities(clean_odds, None)
        elo_only = self._probabilities(None, clean_elo)
        if model is None or market is None or elo_only is None:
            return None
        return {
            "model": model[0],
            "market": market[0],
            "elo": elo_only[0],
        }

    def predict(
        self,
        *,
        odds: Mapping[str, Any] | None,
        elo: Mapping[str, Any] | None,
        competition=None,
        context: Mapping[str, Any] | MatchContext | None = None,
        field_counts: Mapping[str, Any] | None = None,
        user_points: int = 0,
        leader_points: int = 0,
        remaining_srf_max_points: int = 1,
        observed_at: str | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        comp = get_competition(competition or (context or {}).get("competition") if isinstance(context, Mapping) else competition)
        ctx = build_match_context(context, competition=comp)
        clean_odds, clean_elo = _safe_odds(odds), _safe_elo(elo)
        odds_source, odds_status, odds_observed_at, odds_provenance = _source_metadata(
            odds,
            default_source="odds_api",
            default_observed_at=observed_at,
        )
        elo_source, elo_status, elo_observed_at, elo_provenance = _source_metadata(
            elo,
            default_source="clubelo",
            default_observed_at=observed_at,
        )
        effective_observed_at = observed_at or odds_observed_at or elo_observed_at
        if effective_observed_at is None:
            effective_observed_at = datetime.now(timezone.utc).isoformat()
        source_errors = {}
        for label, payload in (("odds", odds), ("elo", elo)):
            if isinstance(payload, Mapping) and payload.get("error"):
                source_errors[label] = payload["error"]
        sources = compose_match_sources(
            clean_odds,
            clean_elo,
            observed_at=effective_observed_at,
            odds_status=odds_status,
            elo_status=elo_status,
            errors=source_errors,
        )
        source_metadata = {
            "odds": (odds_source, odds_status, odds_observed_at, odds_provenance),
            "elo": (elo_source, elo_status, elo_observed_at, elo_provenance),
        }
        source_provenance = {}
        for label, (source, status, source_observed_at, payload_provenance) in source_metadata.items():
            details = dict((sources.get("provenance") or {}).get(label) or {})
            details.update(payload_provenance)
            details.update({
                "source": source,
                "status": status,
                "observed_at": source_observed_at,
            })
            source_provenance[label] = details
        sources["provenance"] = source_provenance
        available_sources = [
            source for payload, (source, *_rest) in source_metadata.items()
            if (clean_odds if payload == "odds" else clean_elo) is not None
        ]
        sources["source"] = "+".join(available_sources) or "none"
        sources["observed_at"] = effective_observed_at
        supplied_provenance = dict(provenance or {})
        for label in source_provenance:
            extra = supplied_provenance.get(label)
            if isinstance(extra, Mapping):
                source_provenance[label].update(extra)
                source_provenance[label].update({
                    "source": source_metadata[label][0],
                    "status": source_metadata[label][1],
                    "observed_at": source_metadata[label][2],
                })
        input_provenance = {
            key: value for key, value in supplied_provenance.items()
            if key not in source_provenance
        }
        input_provenance.update(source_provenance)
        output: dict[str, Any] = {
            "status": sources["status"],
            "source_status": sources["status"],
            "source_mode": sources["source_mode"],
            "source": sources["source"],
            "observed_at": sources.get("observed_at"),
            "model_version": self.model_version,
            "context": ctx.as_dict(),
            "input_provenance": input_provenance,
            "provenance": input_provenance,
            "source_inputs": {"odds": clean_odds, "elo": clean_elo},
            "model_tip": None,
            "top_tip": None,
            "pool_tip": None,
            "pool_status": "unavailable",
            "matrix": {},
            "score_matrix": {},
            "xp_tips": [],
            "xg_home": None,
            "xg_away": None,
            "xg": {"home": None, "away": None},
            "max_xp": 0.0,
        }
        score_90_pair = _score_pair(ctx.score_90)
        eligible = (
            extra_time_eligible_for_score(ctx, *score_90_pair)
            if score_90_pair is not None
            else ctx.extra_time_eligible
        )
        context_dict = ctx.as_dict()
        context_dict["extra_time_eligible"] = eligible
        output["context"] = context_dict
        output.update({
            "stage": ctx.stage,
            "tie_id": ctx.tie_id,
            "leg": ctx.leg,
            "first_leg_score": ctx.first_leg_score,
            "score_90": ctx.score_90,
            "score_aet": ctx.score_aet,
            "shootout_winner": ctx.shootout_winner,
            "extra_time_eligible": eligible,
        })
        probabilities = self._probabilities(clean_odds, clean_elo)
        if probabilities is None:
            return output
        probs, details = probabilities
        prob_over25 = None
        if clean_odds and "over25" in clean_odds and "under25" in clean_odds:
            raw_over, raw_under = 1.0 / clean_odds["over25"], 1.0 / clean_odds["under25"]
            prob_over25 = raw_over / (raw_over + raw_under)
        xg_home, xg_away = self.math_engine.derive_xg_from_odds(
            probs["home"], probs["draw"], probs["away"], prob_over25
        )
        base_matrix = self.math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=10)
        matrix = build_aet_distribution(base_matrix, xg_home, xg_away, ctx)
        is_ko = ctx.stage != "league" or (ctx.competition == "wc2026" and ctx.extra_time_eligible)
        xp = self.math_engine.calculate_expected_points(matrix, is_ko_phase=is_ko)
        model_tip = str(xp.iloc[0]["Tipp"]) if not xp.empty else None
        output.update({
            "xg_home": float(xg_home),
            "xg_away": float(xg_away),
            "xg": {"home": float(xg_home), "away": float(xg_away)},
            "matrix": _matrix_dict(matrix),
            "score_matrix": _matrix_dict(matrix),
            "score_matrix_df": matrix,
            "xp_tips": xp.to_dict(orient="records"),
            "model_tip": model_tip,
            "top_tip": model_tip,
            "max_xp": float(xp.iloc[0]["xP"]) if not xp.empty else 0.0,
            "is_ko_phase": is_ko,
            "probabilities": probs,
            "base_probabilities": details.get("true_probs"),
        })
        pool = pool_tip_from_field(
            matrix,
            field_counts,
            user_points,
            leader_points,
            remaining_srf_max_points,
            is_ko_phase=is_ko,
        )
        output.update({
            "pool_tip": pool.get("tip"),
            "pool_status": pool.get("status", "unavailable"),
            "pool_lambda": pool.get("lambda"),
            "pool_score": pool.get("pool_score"),
            "expected_advantage": pool.get("expected_advantage"),
            "std_advantage": pool.get("std_advantage"),
            # Keep the short metric name for old consumers; never copy the
            # pool result's generic `status` over the source status above.
            "lambda": pool.get("lambda"),
        })
        return output

    def reconstruct(
        self,
        home_team: str,
        away_team: str,
        *,
        commence_time: str | None = None,
        competition=None,
        is_ko: bool = False,
        context: Mapping[str, Any] | MatchContext | None = None,
    ) -> dict[str, Any]:
        """Rebuild a model prediction from ratings without reimplementing it.

        World Cup reconstruction retains its historical-rating fallback.  UCL
        reconstruction requires both clubs to be present in the real rating
        frame, so an absent ClubElo row remains explicitly unavailable.
        """
        comp = get_competition(competition)
        prediction_context = dict(context.as_dict() if isinstance(context, MatchContext) else (context or {}))
        prediction_context.setdefault("competition", comp.id)
        prediction_context.setdefault("stage", "playoff" if is_ko else "league")
        prediction_context.setdefault("leg", "single")
        prediction_context.setdefault("commence_time", commence_time)
        if comp.id == "wc2026":
            prediction_context.setdefault("is_ko", is_ko)
        if comp.id == "ucl2026":
            frame = getattr(self.math_engine, "elo_df", None)
            try:
                names = set(frame["team_name"].tolist())
            except Exception:
                names = set()
            home_norm = getattr(self.math_engine, "name_mapping", {}).get(home_team, home_team)
            away_norm = getattr(self.math_engine, "name_mapping", {}).get(away_team, away_team)
            if home_norm not in names or away_norm not in names:
                return self.predict(
                    odds=None,
                    elo=None,
                    competition=comp,
                    context=prediction_context,
                )
            home_rating = float(frame.loc[frame["team_name"] == home_norm, "elo_rating"].iloc[0])
            away_rating = float(frame.loc[frame["team_name"] == away_norm, "elo_rating"].iloc[0])
        else:
            home_rating = self.math_engine._get_historical_elo(home_team, self._timestamp(commence_time))
            away_rating = self.math_engine._get_historical_elo(away_team, self._timestamp(commence_time))
        result = self.predict(
            odds=None,
            elo={"home_rating": home_rating, "away_rating": away_rating},
            competition=comp,
            context=prediction_context,
        )
        matrix = result.get("score_matrix_df")
        xp = pd.DataFrame(result.get("xp_tips") or [])
        if matrix is not None and not xp.empty:
            try:
                result["bots"] = self.math_engine.compute_bot_tips(
                    score_matrix=matrix,
                    base_xp_df=xp,
                    true_probs=result.get("probabilities") or {},
                    prob_over25=None,
                    home_team=home_team,
                    away_team=away_team,
                    match_id=f"{home_team}:{away_team}:{commence_time or ''}",
                    is_ko_phase=bool(result.get("is_ko_phase")),
                )
            except Exception:
                result["bots"] = {}
        return result

    @staticmethod
    def _timestamp(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return parse_time(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None


def _all_snapshots(cache_collection, event_id: str, competition) -> list[dict]:
    try:
        docs = list(cache_collection.find())
    except Exception:
        docs = []
    comp_id = get_competition(competition).id
    return [
        doc for doc in docs
        if str(doc.get("event_id")) == str(event_id)
        and doc.get("competition", comp_id) == comp_id
        and ("odds_snapshot" in str(doc.get("_id", "")) or doc.get("bucket"))
    ]


def freeze_prediction(
    cache_collection,
    archive_collection,
    service: PredictionService,
    match_id: str,
    *,
    competition=None,
    now: datetime | None = None,
    field_counts: Mapping[str, Any] | None = None,
    user_points: int = 0,
    leader_points: int = 0,
    remaining_srf_max_points: int = 1,
    visible_tip: str | None = None,
) -> dict[str, Any]:
    """Freeze model/pool inputs from the latest eligible T-15 snapshot once."""
    comp = get_competition(competition)
    entry = archive_collection.find_one({"_id": match_id})
    if not entry:
        raise ValueError("Match not in archive")
    prediction = entry.get("prediction") or {}
    if prediction.get("frozen_at"):
        return entry
    metadata = entry.get("metadata") or {}
    pool_document = None
    try:
        pool_document = cache_collection.find_one({"_id": competition_document_id(comp, f"pool_context:{match_id}")})
    except Exception:
        pool_document = None
    if pool_document:
        if field_counts is None:
            field_counts = pool_document.get("tip_counts")
        user_points = pool_document.get("user_points", user_points)
        leader_points = pool_document.get("leader_points", leader_points)
        remaining_srf_max_points = pool_document.get("remaining_srf_max_points", remaining_srf_max_points)
    kickoff_value = metadata.get("commence_time")
    if not kickoff_value:
        raise ValueError("Match kickoff required for freeze")
    kickoff = parse_time(kickoff_value)
    current = parse_time(now or datetime.now(timezone.utc))
    if current < kickoff - timedelta(minutes=15):
        raise ValueError("Prediction freeze is available at T-15")
    if current >= kickoff - timedelta(minutes=5):
        raise ValueError("Prediction freeze must happen before the tip deadline (T-5)")
    snapshot = select_t15_snapshot(_all_snapshots(cache_collection, match_id, comp), kickoff)
    if not snapshot:
        raise ValueError("No eligible T-15 snapshot")
    elo = (entry.get("pre_match_snapshot") or {}).get("elo_state")
    snapshot_provenance = snapshot.get("provenance") if isinstance(snapshot.get("provenance"), Mapping) else {}
    result = service.predict(
        odds=snapshot,
        elo=elo,
        competition=comp,
        context=metadata,
        field_counts=field_counts,
        user_points=user_points,
        leader_points=leader_points,
        remaining_srf_max_points=remaining_srf_max_points,
        observed_at=snapshot.get("observed_at"),
        provenance={
            **snapshot_provenance,
            "snapshot_id": snapshot.get("_id"),
            "snapshot_bucket": snapshot.get("bucket"),
        },
    )
    frozen_at = current.isoformat()
    freeze_fields = {
        "model_tip": result.get("model_tip"),
        "top_tip": result.get("top_tip"),
        "pool_tip": result.get("pool_tip"),
        "pool_status": result.get("pool_status"),
        "status": result.get("status"),
        "source_status": result.get("source_status", result.get("status")),
        "source": result.get("source"),
        "observed_at": result.get("observed_at"),
        "source_mode": result.get("source_mode"),
        "model_version": result.get("model_version"),
        "context": result.get("context"),
        "input_provenance": result.get("input_provenance"),
        "provenance": result.get("provenance"),
        "source_inputs": result.get("source_inputs"),
        "probabilities": result.get("probabilities"),
        "base_probabilities": result.get("base_probabilities"),
        "score_inputs": {
            "xg_home": result.get("xg_home"),
            "xg_away": result.get("xg_away"),
            "score_90": metadata.get("score_90"),
            "score_aet": metadata.get("score_aet"),
        },
        "frozen_at": frozen_at,
    }
    if current < kickoff and result.get("probabilities"):
        baselines = {}

        odds = _safe_odds(snapshot)
        if odds is not None:
            bookmaker_source = snapshot.get("source")
            if not bookmaker_source and isinstance(snapshot.get("provenance"), Mapping):
                bookmaker_source = snapshot["provenance"].get("source")
            bookmaker = _evaluation_baseline(
                service.math_engine.remove_margin(odds["home"], odds["draw"], odds["away"]),
                bookmaker_source,
                snapshot.get("observed_at") or snapshot.get("captured_at"),
                current,
                kickoff,
            )
            if bookmaker:
                baselines["bookmaker"] = bookmaker

        elo_baseline = _capture_elo_baseline(service, elo, entry.get("pre_match_snapshot"), current, kickoff)
        if elo_baseline:
            baselines["elo"] = elo_baseline
        freeze_fields["evaluation_baselines"] = baselines

    capture = {
        **freeze_fields,
        "visible_tip": visible_tip or prediction.get("top_tip") or prediction.get("model_tip") or result.get("top_tip"),
        "visible_tip_source": "matches_cache" if visible_tip else ("archive" if prediction.get("top_tip") or prediction.get("model_tip") else "frozen_forecast"),
    }
    if prediction.get("top_tip") or prediction.get("model_tip"):
        # A forecast observation must not replace the tip already shown to users.
        freeze_fields = {
            "frozen_at": frozen_at,
            **({"evaluation_baselines": freeze_fields["evaluation_baselines"]} if "evaluation_baselines" in freeze_fields else {}),
        }
    if "evaluation_forecast" not in prediction:
        freeze_fields["evaluation_forecast"] = capture
    update = {"$set": {f"prediction.{key}": value for key, value in freeze_fields.items()}}
    result_write = archive_collection.update_one(
        {"_id": match_id, "prediction.frozen_at": {"$exists": False},
         **({"prediction.evaluation_forecast": {"$exists": False}} if "evaluation_forecast" in freeze_fields else {})},
        update,
        upsert=False,
    )
    if getattr(result_write, "matched_count", 0):
        return archive_collection.find_one({"_id": match_id})
    # Another writer won the compare-and-set.  Reload its complete document so
    # a concurrent user-tip/archive update is preserved for the caller.
    winner = archive_collection.find_one({"_id": match_id})
    if winner and "evaluation_forecast" in (winner.get("prediction") or {}) and not (winner.get("prediction") or {}).get("frozen_at"):
        freeze_fields.pop("evaluation_forecast", None)
        retry = archive_collection.update_one(
            {"_id": match_id, "prediction.frozen_at": {"$exists": False}},
            {"$set": {f"prediction.{key}": value for key, value in freeze_fields.items()}},
            upsert=False,
        )
        if getattr(retry, "matched_count", 0):
            return archive_collection.find_one({"_id": match_id})
        winner = archive_collection.find_one({"_id": match_id})
    if winner and (winner.get("prediction") or {}).get("frozen_at"):
        return winner
    raise ValueError("Prediction freeze was concurrently replaced")


def _evaluation_baseline(probabilities, source, observed_at, frozen_at, kickoff) -> dict[str, Any] | None:
    if not isinstance(probabilities, Mapping):
        return None
    try:
        values = {key: float(probabilities[key]) for key in ("home", "draw", "away")}
        observed = parse_time(observed_at)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if (
        any(not math.isfinite(value) or value < 0 or value > 1 for value in values.values())
        or abs(sum(values.values()) - 1.0) > 0.01
        or observed > frozen_at
        or observed >= kickoff
        or not isinstance(source, str)
        or not source.strip()
        or source.strip().lower() in {"unknown", "none", "unavailable"}
        or any(term in source.strip().lower() for term in ("reconstruct", "legacy"))
    ):
        return None
    return {"probabilities": values, "observed_at": observed.isoformat(), "source": source.strip()}


def _capture_elo_baseline(service, elo, pre_match_snapshot, frozen_at, kickoff) -> dict[str, Any] | None:
    clean_elo = _safe_elo(elo)
    if clean_elo is None:
        return None
    snapshot = pre_match_snapshot if isinstance(pre_match_snapshot, Mapping) else {}
    raw_provenance = elo.get("provenance") if isinstance(elo, Mapping) else None
    raw_provenance = raw_provenance if isinstance(raw_provenance, Mapping) else {}
    snapshot_provenance = snapshot.get("input_provenance") or snapshot.get("provenance") or {}
    snapshot_provenance = snapshot_provenance if isinstance(snapshot_provenance, Mapping) else {}
    elo_provenance = snapshot_provenance.get("elo") or {}
    elo_provenance = elo_provenance if isinstance(elo_provenance, Mapping) else {}

    source = (
        (elo.get("source") if isinstance(elo, Mapping) else None)
        or raw_provenance.get("source")
        or elo_provenance.get("source")
    )
    status = (
        (elo.get("status") if isinstance(elo, Mapping) else None)
        or raw_provenance.get("status")
        or elo_provenance.get("status")
    )
    if str(status or "").lower() in {"failed", "unavailable"}:
        return None

    observed_at = (
        (elo.get("observed_at") if isinstance(elo, Mapping) else None)
        or raw_provenance.get("observed_at")
    )
    if observed_at is None:
        # A known pre-match archive recording time is valid evidence that these
        # exact ratings were captured before kickoff. Never invent an Elo time.
        if str(status or "").lower() == "stale":
            return None
        observed_at = snapshot.get("timestamp_recorded")
    result = service._probabilities(None, clean_elo)
    if not result:
        return None
    probabilities, _details = result
    return _evaluation_baseline(probabilities, source, observed_at, frozen_at, kickoff)


def rebuild_prediction(
    service: PredictionService,
    entry: dict[str, Any],
    *,
    competition=None,
) -> dict[str, Any] | None:
    """Rebuild an archived tip through the same service as live predictions."""
    snapshot = entry.get("pre_match_snapshot") or {}
    odds = snapshot.get("odds") or {}
    elo = snapshot.get("elo_state") or {}
    if not all(key in odds for key in ("home", "draw", "away")):
        return None
    if not all(key in elo for key in ("home_rating", "away_rating")):
        return None
    metadata = dict(entry.get("metadata") or {})
    result = service.predict(
        odds=odds,
        elo=elo,
        competition=competition,
        context=metadata,
        observed_at=snapshot.get("timestamp_recorded"),
        provenance=snapshot.get("input_provenance") or {},
    )
    if not result.get("model_tip"):
        return None
    prediction = dict(entry.get("prediction") or {})
    prediction.update({
        "model_tip": result.get("model_tip"),
        "top_tip": result.get("top_tip"),
        "pool_tip": result.get("pool_tip"),
        "pool_status": result.get("pool_status"),
        "context": result.get("context"),
        "status": result.get("status"),
        "source_status": result.get("source_status", result.get("status")),
        "source": result.get("source"),
        "observed_at": result.get("observed_at"),
        "source_mode": result.get("source_mode"),
        "model_version": result.get("model_version"),
        "input_provenance": result.get("input_provenance"),
        "provenance": result.get("provenance"),
        "source_inputs": result.get("source_inputs"),
        "max_xp": result.get("max_xp", 0.0),
        "algo_reconstructed": False,
        "tip_source": "pre_match_snapshot",
    })
    updated = dict(entry)
    updated["prediction"] = prediction
    actual = (updated.get("post_match_result") or {}).get("actual_score")
    if actual:
        is_ko = bool(result.get("is_ko_phase"))
        updated.setdefault("post_match_result", {})["algo_points"] = MathEngine.calculate_actual_points(
            prediction["model_tip"], actual, is_ko
        )
    return updated


def user_tip_is_open(commence_time: Any, now: datetime | None = None, *, competition=None) -> bool:
    """T-5 closure with compatibility for legacy undated WC entries."""
    comp = get_competition(competition)
    try:
        kickoff = parse_time(commence_time)
    except (TypeError, ValueError, OverflowError):
        return comp.id == "wc2026"
    current = parse_time(now or datetime.now(timezone.utc))
    return current < kickoff - timedelta(minutes=5)


def predict_match(math_engine, *, odds=None, elo=None, competition=None, context=None, **kwargs):
    """Small functional adapter for callers that do not retain a service instance."""
    return PredictionService(math_engine).predict(
        odds=odds,
        elo=elo,
        competition=competition,
        context=context,
        **kwargs,
    )


# Compatibility aliases for integrations that used singular/plural naming.
Prediction = PredictionService
build_prediction = PredictionService.predict
apply_extra_time = build_aet_distribution
calculate_pool_lambda = pool_lambda
optimize_pool_tip = pool_tip_from_field
build_context = build_match_context
aet_distribution = build_aet_distribution
compute_pool_tip = pool_tip_from_field
