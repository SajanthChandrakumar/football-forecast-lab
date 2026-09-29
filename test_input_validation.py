import pytest

from src.services.input_validation import bounded_match_id, bounded_score, bounded_tip_counts


def test_shared_write_fields_accept_normal_match_data():
    assert bounded_match_id("401915418") == "401915418"
    assert bounded_score("2:1") == "2:1"
    assert bounded_tip_counts({"0:0": 4, "2:1": 11}) == {"0:0": 4, "2:1": 11}


@pytest.mark.parametrize("value", ["", "x" * 129, "bad\nmatch"])
def test_match_id_rejects_empty_oversized_or_control_character_values(value):
    with pytest.raises(ValueError):
        bounded_match_id(value)


@pytest.mark.parametrize("value", ["21:0", "1:-1", "1:2:3", "x:1"])
def test_score_rejects_impossible_or_malformed_values(value):
    with pytest.raises(ValueError):
        bounded_score(value)


@pytest.mark.parametrize("value", [
    {"21:0": 1},
    {"1:0": -1},
    {"1:0": True},
    {"1:0": 1_000_001},
])
def test_tip_counts_rejects_unbounded_or_invalid_entries(value):
    with pytest.raises(ValueError):
        bounded_tip_counts(value)
