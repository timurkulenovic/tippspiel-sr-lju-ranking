from tippspiel_crawler.extractors import (
    parse_bonus_statistics_payload,
    parse_ranking_row,
    sum_bonus_points_by_customer,
    to_int,
)


def test_to_int_extracts_numbers() -> None:
    assert to_int(" 1.234 Punkte") == 1234
    assert to_int("-7") == -7
    assert to_int("--") is None


def test_parse_ranking_row() -> None:
    parsed = parse_ranking_row(["1", "Alice", "Vienna (AT)", "42", "99", "", "67%"], player_id="7909")
    assert parsed == {
        "rank": 1,
        "player": "Alice",
        "office": "Vienna (AT)",
        "tips": 42,
        "points": 99,
        "winPercent": 67,
        "bwinBonusPoints": 0,
        "laolaBonusPoints": 0,
        "playerId": 7909,
    }


def test_parse_ranking_row_legacy_without_office() -> None:
    parsed = parse_ranking_row(["2", "Bob", "12", "88", "", "55%"])
    assert parsed == {
        "rank": 2,
        "player": "Bob",
        "office": "",
        "tips": 12,
        "points": 88,
        "winPercent": 55,
        "bwinBonusPoints": 0,
        "laolaBonusPoints": 0,
    }


def test_sum_bonus_points_by_customer() -> None:
    bwin, laola = sum_bonus_points_by_customer(
        [
            {"customer": "bwin", "earned_points": 5},
            {"customer": "bwin", "earned_points": 0},
            {"customer": None, "earned_points": 10},
            {"customer": "", "earned_points": 5},
            {"customer": "BWIN", "earned_points": "5"},
            {"customer": "other", "earned_points": 99},
        ]
    )
    assert bwin == 10
    assert laola == 15


def test_parse_bonus_statistics_payload() -> None:
    payload = {
        "bonusTipResults": [
            {"customer": "bwin", "earned_points": 5},
            {"customer": None, "earned_points": 10},
        ]
    }
    assert parse_bonus_statistics_payload(payload) == (5, 10)
    assert parse_bonus_statistics_payload(None) == (0, 0)


