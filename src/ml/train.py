#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import duckdb
from sqlalchemy import select

from src.db.models import ModelRun, Problem
from src.db.repository import upsert_prediction
from src.db.session import session_scope
from src.ml.training_utils import (
    attach_preprocessor,
    build_candidate_models,
    build_model_pipeline,
    build_preprocessor,
    convert_predictions_for_storage,
    infer_feature_columns,
    prepare_training_dataframe,
    regression_metrics,
)
from src.settings import get_settings


def resolve_snapshot_path(snapshot_path: str | None, feature_version: str | None) -> Path:
    settings = get_settings()
    if snapshot_path:
        resolved = Path(snapshot_path)
        if not resolved.is_absolute():
            resolved = (PROJECT_ROOT / resolved).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Snapshot not found: {resolved}")
        return resolved

    if not feature_version:
        raise ValueError("Provide either --snapshot-path or --feature-version")

    candidates = sorted(settings.export_dir.glob(f"training_snapshot_{feature_version}_*.parquet"))
    if not candidates:
        raise FileNotFoundError(
            f"No training snapshot found in {settings.export_dir} for feature version {feature_version!r}"
        )
    return candidates[-1]


def load_snapshot(snapshot_path: Path) -> pd.DataFrame:
    if snapshot_path.suffix.lower() == ".parquet":
        connection = duckdb.connect()
        try:
            return connection.execute(
                f"SELECT * FROM read_parquet('{snapshot_path.as_posix()}')"
            ).df()
        finally:
            connection.close()
    if snapshot_path.suffix.lower() == ".csv":
        return pd.read_csv(snapshot_path)
    raise ValueError(f"Unsupported snapshot format: {snapshot_path.suffix}")


def load_snapshot_manifest(snapshot_path: Path) -> dict:
    manifest_path = snapshot_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def choose_selection_split(df: pd.DataFrame) -> str:
    split_names = set(df["split_name"].dropna().unique().tolist())
    if "validation" in split_names:
        return "validation"
    if "test" in split_names:
        return "test"
    return "train"


def validate_training_frame(df: pd.DataFrame, target_column: str) -> None:
    required_columns = {"problem_id", "split_name", target_column}
    missing = required_columns - set(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Snapshot is missing required columns: {missing_text}")

    labeled = df[df[target_column].notna()]
    if labeled.empty:
        raise ValueError(f"No labeled rows found for target column {target_column!r}")
    if "train" not in set(labeled["split_name"]):
        raise ValueError("Snapshot does not contain any labeled train rows")


def fit_candidate_models(
    df: pd.DataFrame,
    *,
    target_column: str,
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> tuple[str, dict, dict[str, object]]:
    train_df = df[(df["split_name"] == "train") & df[target_column].notna()].copy()
    selection_split = choose_selection_split(df[df[target_column].notna()].copy())
    selection_df = df[(df["split_name"] == selection_split) & df[target_column].notna()].copy()
    test_df = df[(df["split_name"] == "test") & df[target_column].notna()].copy()

    candidate_models = build_candidate_models()
    metrics_by_model: dict[str, dict] = {}
    fitted_pipelines: dict[str, object] = {}

    feature_columns = numeric_columns + categorical_columns
    x_train = train_df[feature_columns]
    y_train = train_df[target_column].astype(float)

    for model_name, (model, model_params) in candidate_models.items():
        preprocessor = build_preprocessor(numeric_columns, categorical_columns)
        pipeline = attach_preprocessor(build_model_pipeline(model), preprocessor)
        pipeline.fit(x_train, y_train)

        model_metrics = {
            "params": model_params,
            "selection_split": selection_split,
            "train": regression_metrics(y_train, pipeline.predict(x_train)),
        }

        if not selection_df.empty:
            x_selection = selection_df[feature_columns]
            y_selection = selection_df[target_column].astype(float)
            model_metrics[selection_split] = regression_metrics(
                y_selection,
                pipeline.predict(x_selection),
            )

        if not test_df.empty:
            x_test = test_df[feature_columns]
            y_test = test_df[target_column].astype(float)
            model_metrics["test"] = regression_metrics(y_test, pipeline.predict(x_test))

        metrics_by_model[model_name] = model_metrics
        fitted_pipelines[model_name] = pipeline

    best_model_name = min(
        metrics_by_model.keys(),
        key=lambda model_name: metrics_by_model[model_name][selection_split]["rmse"],
    )
    return best_model_name, metrics_by_model, fitted_pipelines


def refit_selected_model(
    *,
    model_name: str,
    df: pd.DataFrame,
    target_column: str,
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> object:
    candidate_models = build_candidate_models()
    model, _ = candidate_models[model_name]
    preprocessor = build_preprocessor(numeric_columns, categorical_columns)
    pipeline = attach_preprocessor(build_model_pipeline(model), preprocessor)

    labeled_df = df[df[target_column].notna()].copy()
    feature_columns = numeric_columns + categorical_columns
    pipeline.fit(
        labeled_df[feature_columns],
        labeled_df[target_column].astype(float),
    )
    return pipeline


def persist_model_run(
    *,
    run_name: str,
    feature_version: str,
    target_column: str,
    split_version: str,
    model_name: str,
    metrics_by_model: dict,
    snapshot_path: Path,
    artifact_path: Path,
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> int:
    with session_scope() as session:
        model_run = session.scalar(select(ModelRun).where(ModelRun.run_name == run_name))
        if model_run is None:
            model_run = ModelRun(run_name=run_name)
            session.add(model_run)

        model_run.model_family = model_name
        model_run.target_column = target_column
        model_run.feature_version = feature_version
        model_run.split_version = split_version
        model_run.params_json = {
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
        }
        model_run.metrics_json = {
            "selected_model": model_name,
            "models": metrics_by_model,
        }
        model_run.training_snapshot_path = str(snapshot_path)
        model_run.artifact_path = str(artifact_path)
        session.flush()
        model_run_id = model_run.id
    return model_run_id


def persist_predictions(
    *,
    model_run_id: int,
    predictions_df: pd.DataFrame,
) -> dict[str, int]:
    with session_scope() as session:
        rows = session.execute(select(Problem.problem_id, Problem.id)).all()
        problem_id_map = {problem_id: db_id for problem_id, db_id in rows}
        created = 0
        updated = 0

        for row in predictions_df.itertuples(index=False):
            problem_db_id = problem_id_map.get(row.problem_id)
            if problem_db_id is None:
                continue
            _, was_created = upsert_prediction(
                session,
                {
                    "problem_id": problem_db_id,
                    "model_run_id": model_run_id,
                    "predicted_solve_rate": float(row.predicted_solve_rate) if pd.notna(row.predicted_solve_rate) else 0.0,
                    "predicted_difficulty": float(row.predicted_difficulty) if pd.notna(row.predicted_difficulty) else None,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        session.commit()
    return {"created": created, "updated": updated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TestForge difficulty models from a frozen snapshot")
    parser.add_argument("--snapshot-path", default=None, help="Path to a Parquet or CSV snapshot")
    parser.add_argument("--feature-version", default=None, help="Feature version, used to locate the latest snapshot if needed")
    parser.add_argument(
        "--target-column",
        default="difficulty_estimate",
        help="Target column present in the snapshot. Defaults to difficulty_estimate until solve_rate is added.",
    )
    parser.add_argument("--run-name", default=None, help="Unique model run name. Defaults to a timestamped name.")
    args = parser.parse_args()

    snapshot_path = resolve_snapshot_path(args.snapshot_path, args.feature_version)
    snapshot_manifest = load_snapshot_manifest(snapshot_path)
    raw_df = load_snapshot(snapshot_path)
    df = prepare_training_dataframe(raw_df)
    validate_training_frame(df, args.target_column)

    feature_version = args.feature_version or str(df["feature_version"].dropna().iloc[0])
    split_version = (
        f"train_end_year={snapshot_manifest.get('train_end_year', 'unknown')};"
        f"validation_years={','.join(str(value) for value in snapshot_manifest.get('validation_years', []))};"
        f"test_years={','.join(str(value) for value in snapshot_manifest.get('test_years', []))}"
    )

    numeric_columns, categorical_columns = infer_feature_columns(df, target_column=args.target_column)
    best_model_name, metrics_by_model, _ = fit_candidate_models(
        df,
        target_column=args.target_column,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
    )

    final_pipeline = refit_selected_model(
        model_name=best_model_name,
        df=df,
        target_column=args.target_column,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
    )

    feature_columns = numeric_columns + categorical_columns
    all_predictions = pd.Series(
        final_pipeline.predict(df[feature_columns]),
        index=df.index,
        dtype="float64",
    )
    labeled_reference = df[df[args.target_column].notna()][args.target_column].astype(float)
    predicted_difficulty, predicted_solve_rate = convert_predictions_for_storage(
        predictions=all_predictions,
        target_column=args.target_column,
        reference_series=labeled_reference,
    )

    run_name = args.run_name or f"{best_model_name}_{feature_version}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    settings = get_settings()
    artifact_path = settings.model_dir / f"{run_name}.pkl"
    metadata_path = settings.model_dir / f"{run_name}.json"

    with artifact_path.open("wb") as handle:
        pickle.dump(
            {
                "pipeline": final_pipeline,
                "target_column": args.target_column,
                "feature_columns": feature_columns,
                "numeric_columns": numeric_columns,
                "categorical_columns": categorical_columns,
            },
            handle,
        )

    metadata = {
        "run_name": run_name,
        "selected_model": best_model_name,
        "feature_version": feature_version,
        "target_column": args.target_column,
        "snapshot_path": str(snapshot_path),
        "artifact_path": str(artifact_path),
        "metrics": metrics_by_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    model_run_id = persist_model_run(
        run_name=run_name,
        feature_version=feature_version,
        target_column=args.target_column,
        split_version=split_version,
        model_name=best_model_name,
        metrics_by_model=metrics_by_model,
        snapshot_path=snapshot_path,
        artifact_path=artifact_path,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
    )

    predictions_df = pd.DataFrame(
        {
            "problem_id": df["problem_id"],
            "predicted_difficulty": predicted_difficulty,
            "predicted_solve_rate": predicted_solve_rate,
        }
    )
    prediction_counts = persist_predictions(model_run_id=model_run_id, predictions_df=predictions_df)

    summary = {
        "run_name": run_name,
        "model_run_id": model_run_id,
        "selected_model": best_model_name,
        "target_column": args.target_column,
        "snapshot_path": str(snapshot_path),
        "artifact_path": str(artifact_path),
        "prediction_counts": prediction_counts,
        "selection_metrics": metrics_by_model[best_model_name],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
