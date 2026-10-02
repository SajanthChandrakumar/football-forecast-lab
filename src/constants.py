TEAM_MAPPING = {
    "United States": "United States", "USA": "United States",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Ivory Coast": "Ivory Coast",
    "Saudi Arabia": "Saudi Arabia", "KSA": "Saudi Arabia",
    "Turkey": "Türkiye", "Türkiye": "Türkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    # Club-name aliases shared by ESPN, The Odds API and ClubElo.
    "Club Brugge": "Brugge",
    "Manchester City": "Man City",
    "FC Porto": "Porto",
    "Borussia Dortmund": "Dortmund",
    "Real Betis": "Betis",
    "Internazionale": "Inter",
    "VfB Stuttgart": "Stuttgart",
    "Feyenoord Rotterdam": "Feyenoord",
    "AEK Athens": "AEK",
    "LASK Linz": "LASK",
    "Viking FK": "Viking",
    "AS Roma": "Roma",
    "Atlético Madrid": "Atlético",
    "Atletico Madrid": "Atlético",
    "Bodo/Glimt": "Bodø/Glimt",
    "Bodø/Glimt": "Bodø/Glimt",
    "Fenerbahce": "Fenerbahçe",
    "Manchester United": "Man United",
    "PSV Eindhoven": "PSV",
    "Shakhtar Donetsk": "Shakhtar",
    "Slavia Prague": "Slavia Praha",
    "Slavia Praha": "Slavia Praha",
    "Slovan Bratislava": "Slovan",
    "Sporting CP": "Sporting",
    "Sporting Lisbon": "Sporting",
    "Paris Saint Germain": "Paris Saint-Germain",
    "ŠK Slovan Bratislava": "Slovan",
    "RC Lens": "Lens",
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Brighton and Hove Albion": "Brighton",
    "Coventry City": "Coventry",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Forest",
    "Tottenham Hotspur": "Tottenham",
}

DISPLAY_MAPPING = {
    "United States": "USA", "USA": "USA",
    "South Korea": "South Korea", "Korea Republic": "South Korea",
    "Iran": "Iran", "IR Iran": "Iran",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "Ivory Coast": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
}

TOTALS_CACHE_TTL = 3600   # 1h per match
SCORES_CACHE_TTL = 1800   # 30 min — avoids burning quota on repeated manual syncs

# "round of" catches both the WC2026 Round of 32 and the Round of 16.
_KO_ROUND_KEYWORDS = {"round of", "quarter", "semi", "final", "3rd place"}


def _is_ko_round(round_str: str) -> bool:
    if not round_str:
        return False
    lower = round_str.lower()
    return any(kw in lower for kw in _KO_ROUND_KEYWORDS)
