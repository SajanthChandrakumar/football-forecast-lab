"""Small validation boundary for values written from the public UI."""

MAX_GOALS = 20
MAX_MATCH_ID_LENGTH = 128
MAX_TIP_COUNT = 1_000_000
MAX_TIP_COUNT_ENTRIES = (MAX_GOALS + 1) ** 2


def bounded_match_id(value) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_MATCH_ID_LENGTH or not value.isprintable():
        raise ValueError("match_id must be a printable string of at most 128 characters")
    return value


def bounded_score(value) -> str:
    if not isinstance(value, str):
        raise ValueError("score must use H:A format")
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("score must use H:A format")
    home, away = map(int, parts)
    if home > MAX_GOALS or away > MAX_GOALS:
        raise ValueError(f"score goals must be between 0 and {MAX_GOALS}")
    return f"{home}:{away}"


def bounded_tip_counts(value) -> dict[str, int]:
    if not isinstance(value, dict) or len(value) > MAX_TIP_COUNT_ENTRIES:
        raise ValueError("tip_counts must be a bounded score-count object")
    cleaned = {}
    for score, count in value.items():
        normalized = bounded_score(score)
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_TIP_COUNT:
            raise ValueError(f"tip count must be between 0 and {MAX_TIP_COUNT}")
        cleaned[normalized] = count
    return cleaned
