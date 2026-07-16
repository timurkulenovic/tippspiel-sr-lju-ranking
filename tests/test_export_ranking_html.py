from __future__ import annotations

from pathlib import Path

from tippspiel_crawler.export_ranking_html import (
    deduplicate_by_player_keep_highest_points,
    load_export_settings,
    load_prepared_report,
    prepare_report_payload,
    write_prepared_report,
)


def test_deduplicate_by_player_keeps_row_with_highest_points() -> None:
    rows = [
        {"rank": 1, "player": "Alice", "office": "Ljubljana", "tips": 10, "points": 50, "winPercent": 20},
        {"rank": 2, "player": "Bob", "office": "Ljubljana", "tips": 11, "points": 60, "winPercent": 30},
        {"rank": 3, "player": "Alice", "office": "Ljubljana", "tips": 12, "points": 75, "winPercent": 40},
    ]

    deduplicated = deduplicate_by_player_keep_highest_points(rows)

    assert deduplicated == [
        {"rank": 3, "player": "Alice", "office": "Ljubljana", "tips": 12, "points": 75, "winPercent": 40},
        {"rank": 2, "player": "Bob", "office": "Ljubljana", "tips": 11, "points": 60, "winPercent": 30},
    ]


def test_prepare_payload_calculates_bettor_flags_and_row_fields(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[auth]
email = "user@example.com"
password = "secret"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "bettors.csv").write_text("first_name,initials\nLuka,LF\n", encoding="utf-8")

    settings = load_export_settings(config)
    rows = [
        {"player": "Luka Ferlan", "office": "Ljubljana", "tips": 10, "points": 50, "winPercent": 20},
        {"player": "Alice Smith", "office": "Ljubljana", "tips": 11, "points": 40, "winPercent": 30},
    ]

    payload = prepare_report_payload(rows, "Ljubljana", "2026-01-15T12:30:00Z", settings)

    assert payload["office"] == "Ljubljana"
    assert payload["bettorsCount"] == 1
    assert payload["bettingPool"] == {
        "entryFee": 15,
        "currency": "EUR",
        "totalAmount": 15,
        "prizes": {"first": 7.5, "second": 4.5, "third": 3.0},
    }
    assert payload["rows"][0]["playerDisplay"] == "Luka"
    assert payload["rows"][0]["isBettor"] is True
    assert payload["rows"][0]["initials"] == "LF"
    assert payload["rows"][0]["pointsInt"] == 50


def test_prepare_payload_missing_bettors_list(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nemail="a"\npassword="b"\n', encoding="utf-8")
    (tmp_path / "bettors.csv").write_text("first_name,initials\nLuka,LF\nKevin,KS\n", encoding="utf-8")

    settings = load_export_settings(config)
    rows = [{"player": "Luka Ferlan", "office": "Ljubljana", "tips": 10, "points": 50, "winPercent": 20}]

    payload = prepare_report_payload(rows, "Ljubljana", None, settings)

    assert payload["missingBettors"] == ["Kevin (KS)"]


def test_prepare_payload_roundtrip_written_json(tmp_path: Path) -> None:
    out = tmp_path / "ljubljana_ranking.json"
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nemail="a"\npassword="b"\n', encoding="utf-8")
    (tmp_path / "bettors.csv").write_text("first_name,initials\nLuka,LF\n", encoding="utf-8")

    settings = load_export_settings(config)
    rows = [{"player": "Luka Ferlan", "office": "Ljubljana", "tips": 10, "points": 50, "winPercent": 20}]
    payload = prepare_report_payload(rows, "Ljubljana", "2026-01-15T12:30:00Z", settings)
    write_prepared_report(payload, out)

    loaded = load_prepared_report(out)
    assert loaded["bettingPool"]["totalAmount"] == 15
    assert loaded["bettingPool"]["prizes"]["first"] == 7.5
    assert loaded["rows"][0]["isBettor"] is True
    assert loaded["rows"][0]["playerDisplay"] == "Luka"
    assert "player" not in loaded["rows"][0]


