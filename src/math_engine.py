import os
import json
import time
import hashlib
import logging
from functools import lru_cache
from datetime import datetime
import pandas as pd
import numpy as np
import scipy.optimize as optimize
import scipy.stats as stats

logger = logging.getLogger(__name__)

HOST_NATIONS = {"United States", "Canada", "Mexico"}
HOST_ELO_BONUS = 80
DEFAULT_ELO = 1500.0
LEGACY_DC_POLICY = "legacy"
CLUB_DC_POLICY = "clubs"


class MathEngine:
    """
    A mathematical engine for betting calculations.
    """

    # How long (seconds) to skip a reload when no new results have come in.
    ELO_RELOAD_DEBOUNCE_SEC = 300  # 5 minutes

    def __init__(self, elo_csv_path: str, name_mapping: dict = None):
        self.elo_csv_path = elo_csv_path
        self.elo_df = pd.read_csv(elo_csv_path)
        self.elo_df['elo_rating'] = self.elo_df['elo_rating'].astype(float)
        self.name_mapping = name_mapping or {}
        self.team_forms = {}
        self._last_elo_reload: float = 0.0

    @staticmethod
    def remove_margin(odds_home: float, odds_draw: float, odds_away: float) -> dict[str, float]:
        """
        Calculates the true probabilities by removing the bookmaker's margin from decimal odds.
        """
        # Calculate implied probabilities
        prob_home = 1.0 / odds_home
        prob_draw = 1.0 / odds_draw
        prob_away = 1.0 / odds_away
        
        # Calculate bookmaker's margin
        margin = prob_home + prob_draw + prob_away
        
        # Calculate true probabilities
        true_prob_home = prob_home / margin
        true_prob_draw = prob_draw / margin
        true_prob_away = prob_away / margin
        
        return {
            "home": true_prob_home,
            "draw": true_prob_draw,
            "away": true_prob_away
        }

    def get_elo_probability(self, rating_a: float, rating_b: float, is_a_host: bool = False, is_b_host: bool = False) -> float:
        """Berechnet die reine Elo-Siegwahrscheinlichkeit für Team A inkl. möglichem Heimvorteil."""
        if is_a_host:
            rating_a += 80
        if is_b_host:
            rating_b += 80
            
        diff = rating_a - rating_b
        return 1 / (10 ** (-diff / 400) + 1)

    def reload_elo_data(self, archive: dict = None, force: bool = False):
        """ Reloads the latest Elo dataframe from the CSV file to ensure global state is up-to-date.
        Skips the expensive I/O if data was reloaded within ELO_RELOAD_DEBOUNCE_SEC unless force=True.
        """
        now = time.time()
        if not force and (now - self._last_elo_reload) < self.ELO_RELOAD_DEBOUNCE_SEC:
            return  # Elo is still fresh — skip disk I/O
        if os.path.exists(self.elo_csv_path):
            self.elo_df = pd.read_csv(self.elo_csv_path)
            self.elo_df['elo_rating'] = self.elo_df['elo_rating'].astype(float)
        self._build_team_forms(archive=archive)
        self._last_elo_reload = now

    def _build_team_forms(self, archive: dict = None):
        """
        Reconstructs the W-D-L visual form chain for all teams based on elo_history.json
        and prediction_archive.json (or an in-memory archive dict from MongoDB).
        """
        import json
        import os
        history_path = os.path.join(os.path.dirname(self.elo_csv_path), 'elo_history.json')

        if archive is None:
            # Fallback: read from file (local dev without MongoDB)
            archive_path = os.path.join(os.path.dirname(self.elo_csv_path), 'prediction_archive.json')
            if not os.path.exists(archive_path):
                self.team_forms = {}
                return
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    archive = json.load(f)
            except Exception:
                self.team_forms = {}
                return

        if not os.path.exists(history_path):
            self.team_forms = {}
            return

        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                elo_hist = json.load(f)
        except Exception:
            self.team_forms = {}
            return

        forms = {}
        for team_name, entries in elo_hist.items():
            team_form = []
            prev_elo = entries[0]['elo'] if entries else 1500.0
            for i in range(1, len(entries)):
                entry = entries[i]
                curr_elo = entry['elo']
                match_id = entry['match_id']
                if match_id == "baseline" or match_id not in archive:
                    prev_elo = curr_elo
                    continue
                
                match = archive[match_id]
                res = match.get("post_match_result", {})
                if res.get("status") != "completed":
                    prev_elo = curr_elo
                    continue
                
                actual_score = res.get("actual_score")
                if not actual_score or actual_score == "N/A":
                    prev_elo = curr_elo
                    continue
                
                try:
                    h_goals, a_goals = map(int, actual_score.split(":"))
                except ValueError:
                    prev_elo = curr_elo
                    continue
                
                home_team = match.get("metadata", {}).get("home_team", "")
                home_norm = self.name_mapping.get(home_team, home_team)
                
                if team_name == home_norm:
                    opp = match.get("metadata", {}).get("away_disp", "Unknown")
                    gf, ga = h_goals, a_goals
                else:
                    opp = match.get("metadata", {}).get("home_disp", "Unknown")
                    gf, ga = a_goals, h_goals
                
                if gf > ga: outcome = "W"
                elif gf < ga: outcome = "L"
                else: outcome = "D"
                
                delta = curr_elo - prev_elo
                
                team_form.append({
                    "result": outcome,
                    "opponent": opp,
                    "score": f"{gf}:{ga}",
                    "delta": round(delta, 1)
                })
                prev_elo = curr_elo
            
            # Keep last 5
            last_5 = team_form[-5:]
            
            # Determine "On Fire"
            on_fire = False
            if len(last_5) >= 3 and all(f["result"] == "W" for f in last_5[-3:]):
                on_fire = True
            elif len(last_5) >= 2 and sum(f["delta"] for f in last_5[-2:]) >= 40:
                on_fire = True
                
            forms[team_name] = {
                "form": last_5,
                "on_fire": on_fire
            }
            
        self.team_forms = forms

    def get_match_elo_probabilities(self, home_team: str, away_team: str) -> tuple[float, float]:
        home_norm = self.name_mapping.get(home_team, home_team)
        away_norm = self.name_mapping.get(away_team, away_team)

        if home_norm in self.elo_df['team_name'].values:
            elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
        else:
            elo_home = 1500.0

        if away_norm in self.elo_df['team_name'].values:
            elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0]
        else:
            elo_away = 1500.0

        # BEWUSST OHNE Gastgeber-Bonus (is_a_host/is_b_host).
        # Dieser Wert wird in /api/predict zu 30% mit den Buchmacher-Quoten geblendet,
        # und die Quoten preisen den Heimvorteil bereits ein. Würden wir hier zusätzlich
        # +80 Elo für USA/Kanada/Mexiko draufgeben, zählten wir den Heimvorteil doppelt
        # ("Double-Dip"). Der +80-Bonus gehört NUR in die reine Elo-Aktualisierung
        # (_calculate_new_elo), wo es keine Markt-Quote zum Gegenrechnen gibt.
        prob_home = self.get_elo_probability(elo_home, elo_away)

        return float(prob_home), float(1.0 - prob_home)

    def ensure_teams_exist(self, *teams: str) -> None:
        """
        Stellt sicher, dass jedes (bereits normalisierte) Team eine Zeile im
        Elo-DataFrame hat — fehlende Teams werden mit Default-Elo 1500 angelegt
        und persistiert. Explizit benannter Side-Effect statt versteckt in einer
        'merge'-Funktion. Keine Rückgabe.
        """
        added = False
        for team in teams:
            if team and team not in self.elo_df['team_name'].values:
                new_row = pd.DataFrame([{
                    "team_code": team[:3].upper(),
                    "team_name": team,
                    "elo_rating": 1500.0,
                }])
                self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                added = True
        if added:
            self.elo_df.to_csv(self.elo_csv_path, index=False)

    @staticmethod
    def derive_xg_from_odds(
        prob_home: float,
        prob_draw: float,
        prob_away: float,
        prob_over25: float = None,
        *,
        dc_policy: str = LEGACY_DC_POLICY,
    ) -> tuple[float, float]:
        """
        Derives Expected Goals (xG) for home and away teams by minimizing the difference
        between bookmaker probabilities and Poisson-derived probabilities.
        prob_over25 is optional — omit when totals market data is unavailable.
        """
        if dc_policy not in {LEGACY_DC_POLICY, CLUB_DC_POLICY}:
            raise ValueError(f"Unknown Dixon-Coles policy: {dc_policy}")

        def cost_function(lambdas):
            l_home, l_away = lambdas

            max_goals = 10
            poisson_home = stats.poisson.pmf(np.arange(max_goals), l_home)
            poisson_away = stats.poisson.pmf(np.arange(max_goals), l_away)

            prob_matrix = np.outer(poisson_home, poisson_away)

            rho = -0.15
            prob_matrix[0, 0] *= 1 - (l_home * l_away * rho)
            if dc_policy == CLUB_DC_POLICY:
                prob_matrix[1, 0] *= 1 + (l_away * rho)
                prob_matrix[0, 1] *= 1 + (l_home * rho)
            else:
                prob_matrix[1, 0] *= 1 + (l_home * rho)
                prob_matrix[0, 1] *= 1 + (l_away * rho)
            prob_matrix[1, 1] *= 1 - rho

            prob_matrix = prob_matrix / np.sum(prob_matrix)

            calc_home = np.sum(np.tril(prob_matrix, -1))
            calc_draw = np.sum(np.diag(prob_matrix))
            calc_away = np.sum(np.triu(prob_matrix, 1))

            error = (
                (calc_home - prob_home) ** 2 +
                (calc_draw - prob_draw) ** 2 +
                (calc_away - prob_away) ** 2
            )

            if prob_over25 is not None:
                goals_h, goals_a = np.indices((max_goals, max_goals))
                calc_over25 = np.sum(prob_matrix[(goals_h + goals_a) > 2])
                error += (calc_over25 - prob_over25) ** 2

            return error

        bounds = ((0.1, 5.0), (0.1, 5.0))

        result = optimize.minimize(cost_function, [1.5, 1.5], bounds=bounds, method='L-BFGS-B')
        if not result.success:
            result = optimize.minimize(cost_function, [prob_home * 3.5, prob_away * 3.5], bounds=bounds, method='L-BFGS-B')

        if not result.success:
            # Proportional fallback: scale world-cup averages by the match's win probability ratio
            l_home = max(0.1, min(5.0, 1.35 * (prob_home / 0.45)))
            l_away = max(0.1, min(5.0, 1.10 * (prob_away / 0.28)))
            return l_home, l_away

        return float(result.x[0]), float(result.x[1])

    @staticmethod
    def generate_exact_score_matrix(
        lambda_home: float,
        lambda_away: float,
        max_goals: int = 5,
        rho: float = -0.15,
        *,
        dc_policy: str = LEGACY_DC_POLICY,
    ) -> pd.DataFrame:
        """
        Generates a matrix of exact score probabilities using independent Poisson distributions,
        adjusted with the Dixon-Coles method for low-scoring draws.
        """
        goals_range = np.arange(max_goals + 1)
        prob_home = stats.poisson.pmf(goals_range, lambda_home)
        prob_away = stats.poisson.pmf(goals_range, lambda_away)
        
        # Joint probability matrix
        prob_matrix = np.outer(prob_home, prob_away)
        
        if dc_policy not in {LEGACY_DC_POLICY, CLUB_DC_POLICY}:
            raise ValueError(f"Unknown Dixon-Coles policy: {dc_policy}")

        # Dixon-Coles adjustment
        tau_00 = 1 - (lambda_home * lambda_away * rho)
        if dc_policy == CLUB_DC_POLICY:
            tau_10 = 1 + (lambda_away * rho)
            tau_01 = 1 + (lambda_home * rho)
        else:
            tau_10 = 1 + (lambda_home * rho)
            tau_01 = 1 + (lambda_away * rho)
        tau_11 = 1 - rho
        
        prob_matrix[0, 0] *= tau_00
        prob_matrix[1, 0] *= tau_10
        prob_matrix[0, 1] *= tau_01
        prob_matrix[1, 1] *= tau_11
        
        # Normalize matrix
        prob_matrix = prob_matrix / np.sum(prob_matrix)
        
        # Create DataFrame
        df = pd.DataFrame(
            prob_matrix,
            index=[f"{g}" for g in goals_range],
            columns=[f"{g}" for g in goals_range]
        )
        df.index.name = "Home Goals"
        df.columns.name = "Away Goals"
        return df

    @staticmethod
    def calculate_actual_points(tipped_score: str, actual_score: str, is_ko_phase: bool = False) -> int:
        """Score a completed tip against an actual result using the SRF Tippspiel ruleset."""
        try:
            t_home, t_away = map(int, tipped_score.split(":"))
            a_home, a_away = map(int, actual_score.split(":"))
        except Exception:
            return 0

        points = 0
        t_tend = np.sign(t_home - t_away)
        a_tend = np.sign(a_home - a_away)
        tendency_correct = t_tend == a_tend

        if tendency_correct:
            points += 5
        if t_home == a_home:
            points += 1
        if t_away == a_away:
            points += 1
        if tendency_correct and (t_home - t_away) == (a_home - a_away):
            points += 3

        return points * 2 if is_ko_phase else points

    @staticmethod
    def _tip_points(tipped_home: int, tipped_away: int, actual_home: int, actual_away: int, is_ko_phase: bool = False) -> int:
        return MathEngine.calculate_actual_points(
            f"{tipped_home}:{tipped_away}", f"{actual_home}:{actual_away}", is_ko_phase
        )

    def _points_distribution(self, t_home: int, t_away: int, score_matrix: pd.DataFrame, is_ko_phase: bool) -> tuple[float, float]:
        """Gibt (Erwartungswert, Standardabweichung) der Punkte eines Tipps über die Resultatverteilung zurück."""
        ev = 0.0
        ev_sq = 0.0
        for a_home_str in score_matrix.index:
            for a_away_str in score_matrix.columns:
                prob = score_matrix.loc[a_home_str, a_away_str]
                if prob > 0:
                    pts = self._tip_points(t_home, t_away, int(a_home_str), int(a_away_str), is_ko_phase)
                    ev += pts * prob
                    ev_sq += (pts ** 2) * prob
        variance = max(0.0, ev_sq - ev ** 2)
        return ev, variance ** 0.5

    def calculate_expected_points(self, score_matrix: pd.DataFrame, is_ko_phase: bool = False, top_n: int = 5) -> pd.DataFrame:
        """
        Calculates the Expected Points (xP) for tips from 0:0 up to 5:5 based on the specific ruleset.
        """
        results = []
        max_tip_goals = 5

        for t_home in range(max_tip_goals + 1):
            for t_away in range(max_tip_goals + 1):
                xp, _ = self._points_distribution(t_home, t_away, score_matrix, is_ko_phase)
                results.append({"Tipp": f"{t_home}:{t_away}", "xP": xp})

        df_xp = pd.DataFrame(results)
        df_xp = df_xp.sort_values(by="xP", ascending=False).head(top_n).reset_index(drop=True)
        return df_xp

    @staticmethod
    @lru_cache(maxsize=32)
    def _expected_points_weights(home_axis: tuple[str, ...], away_axis: tuple[str, ...], is_ko_phase: bool) -> np.ndarray:
        """Return cached SRF point weights for all 0:0..5:5 tips and matrix cells."""
        weights = np.empty((36, len(home_axis) * len(away_axis)), dtype=np.float64)
        candidate = 0
        for tipped_home in range(6):
            for tipped_away in range(6):
                cell = 0
                for actual_home in home_axis:
                    for actual_away in away_axis:
                        weights[candidate, cell] = MathEngine._tip_points(
                            tipped_home, tipped_away, int(actual_home), int(actual_away), is_ko_phase,
                        )
                        cell += 1
                candidate += 1
        return weights

    def calculate_expected_points_vectorized(
        self,
        score_matrix: pd.DataFrame,
        is_ko_phase: bool = False,
        top_n: int = 5,
    ) -> pd.DataFrame:
        """Calculate xP with cached SRF weights and one NumPy matrix product."""
        home_axis = tuple(str(value) for value in score_matrix.index)
        away_axis = tuple(str(value) for value in score_matrix.columns)
        weights = self._expected_points_weights(home_axis, away_axis, is_ko_phase)
        probabilities = score_matrix.to_numpy(dtype=np.float64, copy=False).reshape(-1)
        positive = probabilities > 0
        expected = weights[:, positive] @ probabilities[positive]
        results = [
            {"Tipp": f"{tipped_home}:{tipped_away}", "xP": float(expected[tipped_home * 6 + tipped_away])}
            for tipped_home in range(6)
            for tipped_away in range(6)
        ]
        return pd.DataFrame(results).sort_values(by="xP", ascending=False).head(top_n).reset_index(drop=True)

    def compute_bot_tips(
        self,
        score_matrix: pd.DataFrame,
        base_xp_df: pd.DataFrame,
        true_probs: dict,
        prob_over25: float | None,
        home_team: str,
        away_team: str,
        match_id: str,
        is_ko_phase: bool = False
    ) -> dict:
        bots = {}
        fallback_tip = base_xp_df.iloc[0]["Tipp"] if not base_xp_df.empty else "1:0"

        # 1. The Broker (100% Odds)
        try:
            xg_h_o, xg_a_o = self.derive_xg_from_odds(true_probs["home"], true_probs["draw"], true_probs["away"], prob_over25)
            sm_o = self.generate_exact_score_matrix(xg_h_o, xg_a_o, max_goals=10)
            xp_o = self.calculate_expected_points(sm_o, is_ko_phase)
            bots["broker"] = {"tip": xp_o.iloc[0]["Tipp"] if not xp_o.empty else fallback_tip}
        except Exception as e:
            logger.warning(f"Broker bot failed: {e}")
            bots["broker"] = {"tip": fallback_tip}

        # 2. The Professor (100% Elo + Market Totals to fix unrealistic high scores)
        try:
            p_h_e, p_a_e = self.get_match_elo_probabilities(home_team, away_team)
            p_d_e = max(0.15, 1.0 - p_h_e - p_a_e)
            total_e = p_h_e + p_a_e + p_d_e
            xg_h_e, xg_a_e = self.derive_xg_from_odds(p_h_e / total_e, p_d_e / total_e, p_a_e / total_e, prob_over25)
            sm_e = self.generate_exact_score_matrix(xg_h_e, xg_a_e, max_goals=10)
            xp_e = self.calculate_expected_points(sm_e, is_ko_phase)
            bots["professor"] = {"tip": xp_e.iloc[0]["Tipp"] if not xp_e.empty else fallback_tip}
        except Exception as e:
            logger.warning(f"Professor bot failed: {e}")
            bots["professor"] = {"tip": fallback_tip}

        # 3. The X-Sniper (Always highest xP draw)
        try:
            draw_tip = None
            if not base_xp_df.empty:
                draws = base_xp_df[base_xp_df["Tipp"].apply(lambda x: x.split(":")[0] == x.split(":")[1])]
                if not draws.empty:
                    draw_tip = draws.iloc[0]["Tipp"]
            bots["sniper"] = {"tip": draw_tip if draw_tip else "1:1"}
        except Exception as e:
            logger.warning(f"Sniper bot failed: {e}")
            bots["sniper"] = {"tip": "1:1"}

        # 5. The Gambler (Weighted Random)
        try:
            if not base_xp_df.empty:
                top_10 = base_xp_df.head(10).copy()
                weights = top_10["xP"].values.astype(float)
                sum_w = weights.sum()
                if sum_w > 0:
                    weights /= sum_w
                    seed = int(hashlib.md5(match_id.encode('utf-8')).hexdigest(), 16) % (2**32)
                    rng = np.random.default_rng(seed)
                    bots["gambler"] = {"tip": top_10.iloc[rng.choice(len(top_10), p=weights)]["Tipp"]}
                else: bots["gambler"] = {"tip": fallback_tip}
            else: bots["gambler"] = {"tip": fallback_tip}
        except Exception as e:
            logger.warning(f"Gambler bot failed: {e}")
            bots["gambler"] = {"tip": fallback_tip}

        return bots

    def custom_bot_score_matrix(
        self,
        odds: dict,
        elo_home: float,
        elo_away: float,
        market_weight: float,
        is_ko: bool = False,
    ):
        """
        Build the score-probability matrix for a custom bot at a given market_weight.
        Only depends on (odds, elo, market_weight, is_ko) — risk/draw/underdog biases
        don't change the matrix, so the grid search can memoize this per market_weight
        and skip the expensive scipy xG fit.

        Returns (score_matrix, true_probs).
        """
        true_probs = self.remove_margin(odds["home"], odds["draw"], odds["away"])

        # Elo win/loss shares from the stored ratings. No host bonus here — the
        # blend below mirrors /api/predict, where the market already prices it in.
        p_home_winloss = self.get_elo_probability(float(elo_home), float(elo_away))
        elo_home_share, elo_away_share = p_home_winloss, 1.0 - p_home_winloss

        # market_weight is the share of the *market*; the Elo share is its complement.
        w_elo = max(0.0, min(1.0, 1.0 - float(market_weight)))
        pool = true_probs["home"] + true_probs["away"]
        if pool <= 0:
            pool = 1e-9
        prob_home = (true_probs["home"] / pool * (1 - w_elo) + elo_home_share * w_elo) * pool
        prob_away = (true_probs["away"] / pool * (1 - w_elo) + elo_away_share * w_elo) * pool
        prob_draw = true_probs["draw"]

        prob_over25 = None
        if odds.get("over25") and odds.get("under25"):
            raw_over = 1.0 / odds["over25"]
            raw_under = 1.0 / odds["under25"]
            prob_over25 = raw_over / (raw_over + raw_under)

        xg_h, xg_a = self.derive_xg_from_odds(prob_home, prob_draw, prob_away, prob_over25)

        if is_ko:
            base = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_h *= et_factor
            xg_a *= et_factor

        score_matrix = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        return score_matrix, true_probs

    def pick_tip_from_matrix(
        self,
        score_matrix,
        true_probs: dict,
        risk: float,
        draw_bias: float,
        underdog_bias: float,
        is_ko: bool = False,
    ) -> str:
        """Argmax-Schleife über 0:0 – 5:5 mit den drei Bias-Knöpfen."""
        home_is_underdog = true_probs["home"] < true_probs["away"]
        best_tip, best_score = "1:0", float("-inf")
        for t_home in range(6):
            for t_away in range(6):
                ev, std = self._points_distribution(t_home, t_away, score_matrix, is_ko)
                score = ev + risk * std
                if t_home == t_away:
                    score += draw_bias
                underdog_wins = (t_home > t_away) if home_is_underdog else (t_away > t_home)
                if underdog_wins:
                    score += underdog_bias
                if score > best_score:
                    best_score = score
                    best_tip = f"{t_home}:{t_away}"
        return best_tip

    def compute_custom_bot_tip(
        self,
        odds: dict,
        elo_home: float,
        elo_away: float,
        params: dict,
        is_ko: bool = False,
    ) -> str:
        """
        Tip of a user-designed ("build-a-bot") strategy, parametrised by four knobs:

          market_weight (0..1): blend between market and Elo within the win/loss pool.
                                 1.0 = pure bookmaker odds (like the Broker),
                                 0.0 = pure Elo ratings (like the Professor).
                                 The house Algo uses 0.7.
          risk (-1..1):         weight on the standard deviation of a tip's point
                                 distribution. < 0 favours safe tendency tips,
                                 > 0 gambles on exact high scores.
          draw_bias (>= 0):     xP bonus added to every draw tip (like the X-Sniper).
          underdog_bias (>= 0): xP bonus added to tips where the market underdog
                                 wins (like the Rebel).

        Reconstructs everything from the stored pre-match odds + Elo ratings, so it
        can be evaluated retroactively on any archived match. Returns "H:A".
        """
        sm, true_probs = self.custom_bot_score_matrix(
            odds, elo_home, elo_away,
            market_weight=float(params.get("market_weight", 0.7)),
            is_ko=is_ko,
        )
        return self.pick_tip_from_matrix(
            sm, true_probs,
            risk=float(params.get("risk", 0.0)),
            draw_bias=float(params.get("draw_bias", 0.0)),
            underdog_bias=float(params.get("underdog_bias", 0.0)),
            is_ko=is_ko,
        )

    def _calculate_new_elo(self, rating_a: float, rating_b: float, actual_result_a: float, k_factor: int = 60, is_a_host: bool = False, is_b_host: bool = False, goal_diff: int = 0) -> tuple[float, float]:
        """
        Standard Elo update. K=60 entspricht dem World-Football-Elo-Standard
        für WM-Endrundenspiele; der Margin-of-Victory-Multiplikator ebenso
        (×1.5 bei 2 Toren Differenz, ×1.75 bei 3, +1/8 je weiteres Tor).
        """
        expected_a = self.get_elo_probability(rating_a, rating_b, is_a_host=is_a_host, is_b_host=is_b_host)
        expected_b = 1 - expected_a

        gd = abs(goal_diff)
        if gd <= 1:
            mov_multiplier = 1.0
        elif gd == 2:
            mov_multiplier = 1.5
        else:
            mov_multiplier = 1.75 + (gd - 3) / 8

        k = k_factor * mov_multiplier
        new_rating_a = rating_a + k * (actual_result_a - expected_a)
        new_rating_b = rating_b + k * ((1 - actual_result_a) - expected_b)
        return new_rating_a, new_rating_b

    def update_elo_from_api_scores(self, api_scores: list, processed_matches_file: str = 'data/processed_matches.json') -> int:
        """
        Updates Elo ratings based on completed matches from the API, 
        ensuring idempotency by tracking processed match IDs.
        """
        processed_ids = []
        if os.path.exists(processed_matches_file):
            with open(processed_matches_file, 'r', encoding='utf-8') as f:
                try:
                    processed_ids = json.load(f)
                except json.JSONDecodeError:
                    processed_ids = []
                    
        processed_set = set(processed_ids)
        updates_made = 0
        
        for match in api_scores:
            match_id = match.get("id")
            if not match_id or match_id in processed_set or not match.get("completed"):
                continue
                
            home_team = match.get("home_team")
            away_team = match.get("away_team")
            scores = match.get("scores")
            
            if not scores:
                continue
                
            # Parse scores
            home_score = next((s["score"] for s in scores if s["name"] == home_team), None)
            away_score = next((s["score"] for s in scores if s["name"] == away_team), None)
            
            if home_score is not None and away_score is not None:
                try:
                    home_score = int(home_score)
                    away_score = int(away_score)
                except ValueError:
                    continue
                    
                home_norm = self.name_mapping.get(home_team, home_team)
                away_norm = self.name_mapping.get(away_team, away_team)
                
                for team in [home_norm, away_norm]:
                    if team not in self.elo_df['team_name'].values:
                        new_row = pd.DataFrame([{"team_code": team[:3].upper(), "team_name": team, "elo_rating": 1500}])
                        self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                        
                elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
                elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0]
                    
                hosts = ["United States", "Canada", "Mexico"]
                is_home_host = home_norm in hosts
                is_away_host = away_norm in hosts

                if home_score > away_score:
                    result_home = 1.0
                elif home_score < away_score:
                    result_home = 0.0
                else:
                    result_home = 0.5
                    
                new_elo_home, new_elo_away = self._calculate_new_elo(elo_home, elo_away, result_home, is_a_host=is_home_host, is_b_host=is_away_host, goal_diff=home_score - away_score)
                
                self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'] = float(new_elo_home)
                self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'] = float(new_elo_away)
                
                # Elo History Logging
                history_json_path = os.path.join(os.path.dirname(os.path.abspath(processed_matches_file)), 'elo_history.json')
                history = {}
                if os.path.exists(history_json_path):
                    try:
                        with open(history_json_path, 'r', encoding='utf-8') as hf:
                            history = json.load(hf)
                    except json.JSONDecodeError:
                        history = {}
                
                for team_name, new_elo in [(home_norm, new_elo_home), (away_norm, new_elo_away)]:
                    if team_name not in history:
                        # Insert baseline entry using current CSV value before this update
                        baseline_rows = self.elo_df.loc[self.elo_df['team_name'] == team_name, 'elo_rating']
                        baseline_elo = float(baseline_rows.values[0]) if not baseline_rows.empty else 1500.0
                        history[team_name] = [
                            {"timestamp": 0, "match_id": "baseline", "elo": baseline_elo}
                        ]
                    history[team_name].append({
                        "timestamp": float(time.time()),
                        "match_id": str(match_id),
                        "elo": float(new_elo)
                    })
                
                try:
                    with open(history_json_path, 'w', encoding='utf-8') as hf:
                        json.dump(history, hf, indent=4)
                except Exception as e:
                    print(f"Failed to write Elo history: {e}")
                
                processed_set.add(match_id)
                processed_ids.append(match_id)
                updates_made += 1
                
        if updates_made > 0:
            os.makedirs(os.path.dirname(os.path.abspath(processed_matches_file)), exist_ok=True)
            with open(processed_matches_file, 'w', encoding='utf-8') as f:
                json.dump(processed_ids, f, indent=4)

        return updates_made

    def _get_historical_elo(self, team_name: str, before_ts: float = None) -> float:
        """
        Liefert die Elo eines Teams VOR einem Zeitpunkt.
        Quelle: elo_history.json im selben data/-Ordner wie elo_csv_path.
        Fallback DEFAULT_ELO (1500), wenn das Team nicht in der History steht.
        """
        norm = self.name_mapping.get(team_name, team_name)
        history_path = os.path.join(os.path.dirname(self.elo_csv_path), 'elo_history.json')
        if not os.path.exists(history_path):
            return DEFAULT_ELO
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            return DEFAULT_ELO

        team_history = history.get(norm, [])
        if not team_history:
            return DEFAULT_ELO

        if before_ts is None:
            return float(team_history[0]['elo'])

        valid = [e for e in team_history if e.get('timestamp', 0) < before_ts]
        if not valid:
            return float(team_history[0]['elo'])
        return float(valid[-1]['elo'])

    def _reconstruct_pipeline(
        self,
        home_team: str,
        away_team: str,
        commence_time: str = None,
        is_ko: bool = False,
    ):
        """
        Pipeline: historische Pre-Match-Elo → H/D/A → xG → Score-Matrix → Top-xP-Tipp.
        Returns (score_matrix, p_home, p_draw, p_away, tip, xp) — alle None bei Fehler.
        """
        before_ts = None
        if commence_time:
            try:
                before_ts = datetime.fromisoformat(
                    commence_time.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                before_ts = None

        elo_home = self._get_historical_elo(home_team, before_ts)
        elo_away = self._get_historical_elo(away_team, before_ts)

        home_norm = self.name_mapping.get(home_team, home_team)
        away_norm = self.name_mapping.get(away_team, away_team)
        if home_norm in HOST_NATIONS:
            elo_home += HOST_ELO_BONUS
        if away_norm in HOST_NATIONS:
            elo_away += HOST_ELO_BONUS

        # Elo → Win-Loss-Pool. Draw-Rate heuristisch:
        # 0.28 bei gleicher Elo, sinkt linear mit |ΔElo|, Boden 0.18.
        p_home_winloss = self.get_elo_probability(elo_home, elo_away)
        diff = abs(elo_home - elo_away)
        p_draw = max(0.18, 0.28 - (diff / 1000) * 0.10)
        p_home = p_home_winloss * (1.0 - p_draw)
        p_away = (1.0 - p_home_winloss) * (1.0 - p_draw)

        try:
            xg_h, xg_a = self.derive_xg_from_odds(p_home, p_draw, p_away, prob_over25=None)
        except Exception:
            return None, None, None, None, None, None

        if is_ko:
            base_matrix = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_h *= et_factor
            xg_a *= et_factor

        score_matrix = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        xp_df = self.calculate_expected_points(score_matrix, is_ko_phase=is_ko)

        if xp_df.empty:
            return None, None, None, None, None, None
        return score_matrix, p_home, p_draw, p_away, xp_df.iloc[0]['Tipp'], float(xp_df.iloc[0]['xP'])

    def reconstruct_bot_tips(
        self,
        home_team: str,
        away_team: str,
        match_id: str,
        commence_time: str = None,
        is_ko: bool = False,
    ) -> dict | None:
        """
        Bot-Tipps für ein Match ohne historische Quoten. odds_pure ist
        semantisch nicht definiert ohne Quoten — fällt deshalb auf die
        Elo-Wahrscheinlichkeiten als "true_probs" zurück (was für diese Matches
        odds_pure ≈ elo_pure ≈ chalk macht).
        """
        sm, p_home, p_draw, p_away, tip, xp = self._reconstruct_pipeline(
            home_team, away_team, commence_time, is_ko
        )
        if sm is None:
            return None
        true_probs = {"home": p_home, "draw": p_draw, "away": p_away}
        base_xp_df = self.calculate_expected_points(sm, is_ko_phase=is_ko)
        return self.compute_bot_tips(
            score_matrix=sm,
            base_xp_df=base_xp_df,
            true_probs=true_probs,
            prob_over25=None,
            home_team=home_team,
            away_team=away_team,
            match_id=match_id,
            is_ko_phase=is_ko
        )

    # ── Bonus questions (Weltmeister, 0:0-Anzahl, Torschützenkönig, Schweiz) ──
    # Every bot answer below is derived from the live Elo table and the same
    # Dixon-Coles machinery used for match predictions — nothing is hardcoded
    # per bot. Caveat: this project has no player-level scoring data anywhere,
    # so the goal-count questions are explicitly rough heuristics (documented
    # inline), not modeled predictions the way match xP is.

    _BONUS_ROUND_THRESHOLDS = [
        (4, "Halbfinale", 7), (8, "Viertelfinale", 6),
        (16, "Achtelfinale", 5), (32, "Sechzehntelfinale", 4),
    ]

    def _elo_rank(self, team: str) -> int:
        """1-based rank of `team` in the current Elo table (1 = strongest)."""
        norm = self.name_mapping.get(team, team)
        ranked = self.elo_df.sort_values("elo_rating", ascending=False).reset_index(drop=True)
        idx = ranked.index[ranked["team_name"] == norm]
        return int(idx[0]) + 1 if len(idx) else len(ranked) + 1

    def _seeded_rng(self, key: str) -> np.random.Generator:
        seed = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % (2**32)
        return np.random.default_rng(seed)

    def _round_for_rank(self, rank: int) -> tuple[str, int]:
        """Maps an Elo rank to the furthest round that rank would plausibly
        reach in the 48-team bracket, plus matches played to get there."""
        for cutoff, label, matches in self._BONUS_ROUND_THRESHOLDS:
            if rank <= cutoff:
                return label, matches
        return "Gruppenphase", 3

    def _bonus_champion(self) -> dict[str, str]:
        """Each bot's pick for the tournament winner, from the live Elo table."""
        ranked = self.elo_df.sort_values("elo_rating", ascending=False).reset_index(drop=True)
        on_fire = {t for t, f in self.team_forms.items() if f.get("on_fire")}
        hot = ranked[ranked["team_name"].isin(on_fire)]

        top8 = ranked.head(8)
        weights = top8["elo_rating"].values.astype(float)
        weights = weights - weights.min() + 1.0
        weights /= weights.sum()
        rng = self._seeded_rng("bonus_champion")
        gambler_pick = str(top8.iloc[int(rng.choice(len(top8), p=weights))]["team_name"])

        return {
            "professor": str(ranked.iloc[0]["team_name"]),                                  # pure highest Elo
            "broker": str((hot.iloc[0] if not hot.empty else ranked.iloc[0])["team_name"]),  # highest Elo among in-form teams
            "rebel": str(ranked.iloc[min(4, len(ranked) - 1)]["team_name"]),                 # contrarian mid-pack pick
            "sniper": str(ranked.iloc[min(2, len(ranked) - 1)]["team_name"]),
            "gambler": gambler_pick,
        }

    def _bonus_draws_00(self) -> dict[str, int]:
        """Expected number of 0:0 draws across 64 matches, from the Dixon-Coles
        matrix at the tournament's average scoring rate (λ≈1.2 per team)."""
        def p00(rho: float) -> float:
            m = self.generate_exact_score_matrix(1.2, 1.2, max_goals=5, rho=rho)
            return float(m.loc["0", "0"])

        base_count = p00(-0.15) * 64  # house rho, same as everywhere else
        rng = self._seeded_rng("bonus_draws")
        jitter = int(rng.integers(-2, 3))

        return {
            "professor": int(round(base_count)),
            "broker": int(round(base_count)),
            "rebel": int(np.floor(p00(0.05) * 64)),      # less negative rho → fewer low-score draws
            "sniper": int(round(p00(-0.35) * 64)),        # more negative rho → forces more draws
            "gambler": int(max(0, round(base_count + jitter))),
        }

    def _bonus_switzerland(self) -> tuple[dict[str, str], dict[str, int]]:
        """Round reached + total goals, scaled off Switzerland's Elo rank and
        relative attacking strength vs. the field average."""
        swiss_name = self.name_mapping.get("Switzerland", "Switzerland")
        swiss_rank = self._elo_rank(swiss_name)
        league_avg_elo = float(self.elo_df["elo_rating"].mean())
        swiss_rows = self.elo_df.loc[self.elo_df["team_name"] == swiss_name, "elo_rating"]
        swiss_elo = float(swiss_rows.values[0]) if not swiss_rows.empty else league_avg_elo
        goals_per_game = 1.2 * (swiss_elo / league_avg_elo)

        rng = self._seeded_rng("bonus_switzerland")
        rank_bumps = {
            "professor": 0, "broker": 2, "rebel": -4, "sniper": 1,
            "gambler": int(rng.integers(-4, 5)),
        }

        rounds, goals = {}, {}
        for bot, bump in rank_bumps.items():
            label, matches = self._round_for_rank(max(1, swiss_rank - bump))
            rounds[bot] = label
            goals[bot] = int(round(goals_per_game * matches))
        return rounds, goals

    def _bonus_top_scorer(self) -> dict[str, int]:
        """Rough proxy for the top scorer's goal tally: avg goals/game/team ×
        assumed matches played × the scorer's assumed share of team goals.
        No player-level data exists anywhere in this project, so this is
        explicitly a heuristic, not a modeled prediction."""
        avg_goals_per_game = 1.2
        rng = self._seeded_rng("bonus_top_scorer")
        profiles = {
            "professor": (7, 0.30), "broker": (6, 0.35),
            "rebel": (5, 0.50), "sniper": (7, 0.20),
            "gambler": (int(rng.integers(5, 8)), float(rng.uniform(0.25, 0.45))),
        }
        return {bot: int(round(avg_goals_per_game * matches * share)) for bot, (matches, share) in profiles.items()}

    def compute_bonus_predictions(self, actual_results: dict) -> list[dict]:
        """
        Algorithmically answers the 5 SRF Tippspiel bonus questions per bot
        (Broker, Professor, Rebel, Sniper, Gambler) and grades them against
        `actual_results`. Returns a JSON-serializable list, one entry per
        question, ready for the frontend.
        """
        champion = self._bonus_champion()
        draws_00 = self._bonus_draws_00()
        swiss_round, swiss_goals = self._bonus_switzerland()
        top_scorer = self._bonus_top_scorer()

        def grade(question: str, answers: dict, actual, exact_pts: int, tolerance: int = 0, tolerance_pts: int = 0) -> dict:
            bots = {}
            for bot, answer in answers.items():
                if isinstance(actual, (int, float)) and isinstance(answer, (int, float)):
                    diff = abs(answer - actual)
                    pts = exact_pts if diff == 0 else (tolerance_pts if tolerance and diff <= tolerance else 0)
                else:
                    pts = exact_pts if answer == actual else 0
                bots[bot] = {"answer": answer, "points": pts}
            return {"question": question, "actual": actual, "bots": bots}

        return [
            grade("Weltmeister", champion, actual_results.get("champion"), exact_pts=50),
            grade("Anzahl 0:0-Spiele", draws_00, actual_results.get("draws_00"), exact_pts=20, tolerance=1, tolerance_pts=10),
            grade("Torschützenkönig – Tore", top_scorer, actual_results.get("top_scorer_goals"), exact_pts=15, tolerance=2, tolerance_pts=8),
            grade("Schweiz – Tore", swiss_goals, actual_results.get("switzerland_goals"), exact_pts=15, tolerance=2, tolerance_pts=8),
            grade("Schweiz – wie weit?", swiss_round, actual_results.get("switzerland_round"), exact_pts=15),
        ]
