from __future__ import annotations

import json
import math
from collections.abc import Iterable

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


CORE_NUMERIC_COLUMNS = [
    "year",
    "problem_number",
    "difficulty_estimate",
    "estimated_solve_minutes",
    "problem_length_words",
    "problem_length_chars",
    "solution_length_words",
    "solution_length_chars",
    "problem_sentence_count",
]
CORE_BOOLEAN_COLUMNS = [
    "has_diagram",
    "has_answer_choices",
]
CORE_CATEGORICAL_COLUMNS = [
    "contest_type",
    "primary_topic",
]
LIST_LIKE_COLUMNS = [
    "secondary_topics",
    "techniques",
]


def parse_jsonish(value):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return value
    return value


def prepare_training_dataframe(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    df = snapshot_df.copy()

    for column in LIST_LIKE_COLUMNS:
        if column in df.columns:
            df[column] = df[column].apply(parse_jsonish)
            df[f"{column}_count"] = df[column].apply(
                lambda value: len(value) if isinstance(value, list) else 0
            )

    if "features_json" in df.columns:
        parsed_features = df["features_json"].apply(parse_jsonish).apply(
            lambda value: value if isinstance(value, dict) else {}
        )
        feature_columns = sorted({key for payload in parsed_features for key in payload.keys()})
        for column in feature_columns:
            df[f"feature__{column}"] = parsed_features.apply(lambda payload: payload.get(column))

    for column in CORE_BOOLEAN_COLUMNS:
        if column in df.columns:
            df[column] = df[column].astype(object).apply(
                lambda v: float(v) if v is not None and v is not pd.NA else float("nan")
            )

    for column in df.columns:
        if column.startswith("feature__"):
            valid = df[column].dropna()
            if not valid.empty and valid.map(lambda value: isinstance(value, bool)).all():
                df[column] = df[column].astype(object).apply(
                    lambda v: float(v) if v is not None and v is not pd.NA else float("nan")
                )

    # Universal cleanup: convert any remaining pandas nullable types to numpy
    # types so scikit-learn never encounters pd.NA
    import numpy as np
    for column in df.columns:
        if pd.api.types.is_extension_array_dtype(df[column].dtype):
            if pd.api.types.is_numeric_dtype(df[column]) or pd.api.types.is_bool_dtype(df[column]):
                df[column] = df[column].to_numpy(dtype="float64", na_value=np.nan)

    return df


def infer_feature_columns(df: pd.DataFrame, *, target_column: str) -> tuple[list[str], list[str]]:
    feature_columns = sorted(column for column in df.columns if column.startswith("feature__"))
    numeric_feature_cols = [c for c in feature_columns if pd.api.types.is_numeric_dtype(df[c])]

    numeric_columns = [
        column
        for column in (
            CORE_NUMERIC_COLUMNS
            + CORE_BOOLEAN_COLUMNS
            + [f"{column}_count" for column in LIST_LIKE_COLUMNS]
            + numeric_feature_cols
        )
        if column in df.columns and column != target_column
    ]

    categorical_columns = [
        column
        for column in CORE_CATEGORICAL_COLUMNS
        if column in df.columns and column != target_column
    ]
    return numeric_columns, categorical_columns


def build_preprocessor(
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> ColumnTransformer:
    transformers = []
    if numeric_columns:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                numeric_columns,
            )
        )
    if categorical_columns:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                categorical_columns,
            )
        )

    return ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0.0)


def build_candidate_models() -> dict[str, tuple[object, dict]]:
    return {
        "dummy_median": (
            DummyRegressor(strategy="median"),
            {"strategy": "median"},
        ),
        "random_forest": (
            RandomForestRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=1,
            ),
            {
                "n_estimators": 300,
                "min_samples_leaf": 2,
                "random_state": 42,
                "n_jobs": 1,
            },
        ),
        "gradient_boosting": (
            GradientBoostingRegressor(
                learning_rate=0.05,
                n_estimators=250,
                max_depth=None,
                min_samples_leaf=2,
                random_state=42,
            ),
            {
                "learning_rate": 0.05,
                "n_estimators": 250,
                "min_samples_leaf": 2,
                "random_state": 42,
            },
        ),
    }


def build_model_pipeline(model) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", "passthrough"),
            ("model", model),
        ]
    )


def attach_preprocessor(pipeline: Pipeline, preprocessor: ColumnTransformer) -> Pipeline:
    pipeline.steps[0] = ("preprocessor", preprocessor)
    return pipeline


def regression_metrics(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float]:
    y_true_series = pd.Series(list(y_true), dtype="float64")
    y_pred_series = pd.Series(list(y_pred), dtype="float64")
    rmse = math.sqrt(mean_squared_error(y_true_series, y_pred_series))
    mae = mean_absolute_error(y_true_series, y_pred_series)
    r2 = r2_score(y_true_series, y_pred_series) if len(y_true_series) >= 2 else 0.0
    return {
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2),
    }


def convert_predictions_for_storage(
    *,
    predictions: pd.Series,
    target_column: str,
    reference_series: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    predicted_difficulty = pd.Series([None] * len(predictions), index=predictions.index, dtype="float64")
    predicted_solve_rate = pd.Series([None] * len(predictions), index=predictions.index, dtype="float64")

    difficulty_targets = {"difficulty_estimate", "predicted_difficulty"}
    solve_rate_targets = {"solve_rate", "predicted_solve_rate"}

    if target_column in difficulty_targets:
        predicted_difficulty = predictions.astype(float)
        ref_min = float(reference_series.min())
        ref_max = float(reference_series.max())
        span = max(ref_max - ref_min, 1e-9)
        normalized = (predictions - ref_min) / span
        predicted_solve_rate = (1.0 - normalized).clip(lower=0.0, upper=1.0)
    elif target_column in solve_rate_targets:
        predicted_solve_rate = predictions.clip(lower=0.0, upper=1.0).astype(float)
        predicted_difficulty = (1.0 - predicted_solve_rate).astype(float)
    else:
        predicted_difficulty = predictions.astype(float)

    return predicted_difficulty, predicted_solve_rate
