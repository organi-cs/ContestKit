from src.ml.snapshot_utils import assign_split_name


def test_default_split_assignment() -> None:
    assert assign_split_name(2020) == "train"
    assert assign_split_name(2021) == "validation"
    assert assign_split_name(2023) == "test"


def test_future_years_fall_into_holdout() -> None:
    assert assign_split_name(2025) == "holdout"
