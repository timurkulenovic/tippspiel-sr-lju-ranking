from tippspiel_crawler.extractors import parse_ranking_row, to_int


def test_to_int_extracts_numbers() -> None:
    assert to_int(" 1.234 Punkte") == 1234
    assert to_int("-7") == -7
    assert to_int("--") is None


def test_parse_ranking_row() -> None:
    parsed = parse_ranking_row(["1", "Alice", "Vienna (AT)", "42", "99", "", "67%"])
    assert parsed == {
        "rank": 1,
        "player": "Alice",
        "office": "Vienna (AT)",
        "tips": 42,
        "points": 99,
        "winPercent": 67,
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
    }


