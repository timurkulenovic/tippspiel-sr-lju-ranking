from pathlib import Path

import pytest

from tippspiel_crawler.crawl_ranking import AuthCredentials, load_credentials


def test_load_credentials_reads_auth_values(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nemail = "user@example.com"\npassword = "secret"\n', encoding="utf-8")

    creds = load_credentials(config)

    assert creds == AuthCredentials(email="user@example.com", password="secret")


def test_load_credentials_rejects_missing_values(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nemail = ""\npassword = ""\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Credentials missing"):
        load_credentials(config)

