from tippspiel_crawler.crawl_ranking import (
    attach_bonus_points,
    parse_group_id,
    statistics_api_url,
    tipps_page_url,
)


def test_parse_group_id_from_ranking_url() -> None:
    assert parse_group_id("https://tippspiel.laola1.at/gruppe/80/ranking") == 80
    assert parse_group_id("https://tippspiel.laola1.at/gruppe/12/7909/tipps") == 12
    assert parse_group_id("https://example.com/nope") is None


def test_statistics_urls() -> None:
    assert statistics_api_url(80, 7257) == (
        "https://tippspiel.laola1.at/api/tippspiel/groups/80/user/7257/statistics"
    )
    assert tipps_page_url(80, 7257) == "https://tippspiel.laola1.at/gruppe/80/7257/tipps"


def test_attach_bonus_points_updates_matching_players() -> None:
    ranking = [
        {"player": "Alice", "playerId": 1, "points": 100, "bwinBonusPoints": 0, "laolaBonusPoints": 0},
        {"player": "Bob", "playerId": 2, "points": 90, "bwinBonusPoints": 0, "laolaBonusPoints": 0},
        {"player": "No Id", "points": 80, "bwinBonusPoints": 0, "laolaBonusPoints": 0},
    ]

    attach_bonus_points(ranking, {1: (5, 10), 2: (0, 15)})

    assert ranking[0]["bwinBonusPoints"] == 5
    assert ranking[0]["laolaBonusPoints"] == 10
    assert ranking[1]["bwinBonusPoints"] == 0
    assert ranking[1]["laolaBonusPoints"] == 15
    assert ranking[2]["bwinBonusPoints"] == 0
    assert ranking[2]["laolaBonusPoints"] == 0
