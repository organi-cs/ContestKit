from src.scraper.scraper import _contest_prefix


def test_2021_fall_contest_prefix_is_canonical() -> None:
    assert _contest_prefix(2021, "AMC_10A") == "2021_Fall_AMC_10A"


def test_regular_contest_prefix_stays_unchanged() -> None:
    assert _contest_prefix(2023, "AMC_10A") == "2023_AMC_10A"
