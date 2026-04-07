from __future__ import annotations


DEFAULT_TRAIN_END_YEAR = 2020
DEFAULT_VALIDATION_YEARS = {2021, 2022}
DEFAULT_TEST_YEARS = {2023, 2024}


def assign_split_name(
    year: int,
    *,
    train_end_year: int = DEFAULT_TRAIN_END_YEAR,
    validation_years: set[int] | None = None,
    test_years: set[int] | None = None,
) -> str:
    validation_years = validation_years or DEFAULT_VALIDATION_YEARS
    test_years = test_years or DEFAULT_TEST_YEARS

    if year in validation_years:
        return "validation"
    if year in test_years:
        return "test"
    if year <= train_end_year:
        return "train"
    return "holdout"


def parse_year_set(raw_value: str | None, default: set[int]) -> set[int]:
    if not raw_value:
        return set(default)
    return {int(value.strip()) for value in raw_value.split(",") if value.strip()}
