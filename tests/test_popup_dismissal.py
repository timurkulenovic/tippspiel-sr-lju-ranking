from tippspiel_crawler.crawl_ranking import _matches_survey_cta


def test_survey_cta_is_detected() -> None:
    assert _matches_survey_cta("Zur Umfrage")
    assert _matches_survey_cta("  ZUR UMFRAGE!  ")
    assert _matches_survey_cta("Jetzt zur Umfrage")


def test_close_button_is_not_treated_as_survey_cta() -> None:
    assert not _matches_survey_cta("")
    assert not _matches_survey_cta("Schließen")
    assert not _matches_survey_cta("Close")
    assert not _matches_survey_cta("×")
    assert not _matches_survey_cta("Accept all")
