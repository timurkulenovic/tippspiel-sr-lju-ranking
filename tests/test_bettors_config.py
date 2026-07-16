from __future__ import annotations

from pathlib import Path

from tippspiel_crawler.export_ranking_html import load_export_settings


def test_load_export_settings_reads_bettors(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[auth]
email = "user@example.com"
password = "secret"
""".strip(),
        encoding="utf-8",
    )

    csv_file = tmp_path / "bettors.csv"
    csv_file.write_text("first_name,initials\nLuka,LF\nEnsar,ED\n", encoding="utf-8")

    settings = load_export_settings(config)

    assert "luka|LF" in settings.bettors
    assert "ensar|ED" in settings.bettors
    assert settings.bettor_labels["luka|LF"] == "Luka (LF)"
    assert settings.bettor_count == 2


def test_load_export_settings_normalizes_diacritics(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[auth]
email = "user@example.com"
password = "secret"
""".strip(),
        encoding="utf-8",
    )

    csv_file = tmp_path / "bettors.csv"
    csv_file.write_text("first_name,initials\nDomen,DJ\nAndraz,AL\n", encoding="utf-8")

    settings = load_export_settings(config)

    assert "domen|DJ" in settings.bettors
    assert "andraz|AL" in settings.bettors


def test_load_export_settings_missing_file_returns_empty_sets(tmp_path: Path) -> None:
    settings = load_export_settings(tmp_path / "missing.toml")

    assert settings.bettors == set()
    assert settings.bettor_labels == {}
    assert settings.exception_players == set()
    assert settings.bettor_count == 0


def test_load_export_settings_reads_bettors_from_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "bettors.csv"
    csv_file.write_text(
        "first_name,initials\nGregor,GR\nTimur,TK\n",
        encoding="utf-8",
    )

    config = tmp_path / "config.toml"
    config.write_text(
        """
[auth]
email = "user@example.com"
password = "secret"
""".strip(),
        encoding="utf-8",
    )

    settings = load_export_settings(config)

    assert settings.bettors == {"gregor|GR", "timur|TK"}
    assert settings.bettor_labels["gregor|GR"] == "Gregor (GR)"
    assert settings.bettor_count == 2


