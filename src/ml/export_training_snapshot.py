#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
import pandas as pd
from sqlalchemy import text

from src.db.session import get_engine
from src.ml.snapshot_utils import (
    DEFAULT_TEST_YEARS,
    DEFAULT_TRAIN_END_YEAR,
    DEFAULT_VALIDATION_YEARS,
    assign_split_name,
    parse_year_set,
)
from src.settings import get_settings


SNAPSHOT_SQL_BASE = """
SELECT
    p.problem_id,
    p.contest_type,
    p.year,
    p.problem_number,
    p.difficulty_estimate,
    p.primary_topic,
    p.secondary_topics,
    p.techniques,
    p.estimated_solve_minutes,
    fs.feature_version,
    fs.has_diagram,
    fs.has_answer_choices,
    fs.problem_length_words,
    fs.problem_length_chars,
    fs.solution_length_words,
    fs.solution_length_chars,
    fs.problem_sentence_count,
    fs.features_json,
    {prediction_columns}
FROM problems AS p
JOIN feature_sets AS fs
    ON fs.problem_id = p.id
{prediction_join}
WHERE fs.feature_version = :feature_version
ORDER BY p.year, p.contest_type, p.problem_number
"""


def write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    connection = duckdb.connect()
    connection.register("snapshot_df", df)
    connection.execute(f"COPY snapshot_df TO '{output_path.as_posix()}' (FORMAT PARQUET)")
    connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a Parquet snapshot from PostgreSQL for ML training")
    parser.add_argument("--feature-version", required=True, help="Feature version to export")
    parser.add_argument("--model-run-id", type=int, default=None, help="Optional model run for prediction columns")
    parser.add_argument("--train-end-year", type=int, default=DEFAULT_TRAIN_END_YEAR)
    parser.add_argument("--validation-years", default=",".join(str(year) for year in sorted(DEFAULT_VALIDATION_YEARS)))
    parser.add_argument("--test-years", default=",".join(str(year) for year in sorted(DEFAULT_TEST_YEARS)))
    parser.add_argument("--output-name", default=None, help="Optional base file name without extension")
    args = parser.parse_args()

    validation_years = parse_year_set(args.validation_years, DEFAULT_VALIDATION_YEARS)
    test_years = parse_year_set(args.test_years, DEFAULT_TEST_YEARS)
    output_name = args.output_name or f"training_snapshot_{args.feature_version}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    engine = get_engine()
    prediction_join = ""
    prediction_columns = "NULL AS predicted_solve_rate, NULL AS predicted_difficulty"
    params = {"feature_version": args.feature_version}
    if args.model_run_id is not None:
        prediction_join = """
LEFT JOIN problem_predictions AS pp
    ON pp.problem_id = p.id
    AND pp.model_run_id = :model_run_id
"""
        prediction_columns = "pp.predicted_solve_rate, pp.predicted_difficulty"
        params["model_run_id"] = args.model_run_id

    snapshot_sql = SNAPSHOT_SQL_BASE.format(
        prediction_columns=prediction_columns,
        prediction_join=prediction_join,
    )
    with engine.connect() as connection:
        df = pd.read_sql(
            text(snapshot_sql),
            connection,
            params=params,
        )

    df["split_name"] = df["year"].apply(
        lambda year: assign_split_name(
            int(year),
            train_end_year=args.train_end_year,
            validation_years=validation_years,
            test_years=test_years,
        )
    )

    settings = get_settings()
    output_path = settings.export_dir / f"{output_name}.parquet"
    manifest_path = settings.export_dir / f"{output_name}.manifest.json"

    write_parquet(df, output_path)

    manifest = {
        "feature_version": args.feature_version,
        "model_run_id": args.model_run_id,
        "snapshot_path": str(output_path),
        "row_count": int(len(df)),
        "split_counts": df["split_name"].value_counts(dropna=False).to_dict(),
        "train_end_year": args.train_end_year,
        "validation_years": sorted(validation_years),
        "test_years": sorted(test_years),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
