import pandas as pd

from src.ml.training_utils import (
    convert_predictions_for_storage,
    infer_feature_columns,
    prepare_training_dataframe,
)


def test_prepare_training_dataframe_flattens_feature_payload() -> None:
    raw_df = pd.DataFrame(
        {
            "features_json": ['{"contest_position_ratio": 0.5, "has_solution": true}'],
            "secondary_topics": ['["geometry", "algebra"]'],
            "techniques": ['["invariant"]'],
            "has_diagram": [True],
            "has_answer_choices": [False],
            "contest_type": ["AMC_10A"],
            "primary_topic": ["geometry"],
            "difficulty_estimate": [2.5],
        }
    )

    prepared = prepare_training_dataframe(raw_df)

    assert prepared.loc[0, "secondary_topics_count"] == 2
    assert prepared.loc[0, "techniques_count"] == 1
    assert prepared.loc[0, "feature__contest_position_ratio"] == 0.5
    assert prepared.loc[0, "feature__has_solution"] == 1.0


def test_infer_feature_columns_excludes_target() -> None:
    prepared = pd.DataFrame(
        {
            "year": [2023],
            "problem_number": [1],
            "difficulty_estimate": [2.0],
            "contest_type": ["AMC_10A"],
            "primary_topic": ["number theory"],
            "feature__contest_position_ratio": [0.1],
            "secondary_topics_count": [0],
            "techniques_count": [1],
        }
    )

    numeric_columns, categorical_columns = infer_feature_columns(
        prepared,
        target_column="difficulty_estimate",
    )

    assert "difficulty_estimate" not in numeric_columns
    assert "feature__contest_position_ratio" in numeric_columns
    assert "contest_type" in categorical_columns


def test_convert_predictions_for_storage_from_difficulty_target() -> None:
    predictions = pd.Series([1.0, 4.0, 7.0], dtype="float64")
    reference = pd.Series([1.0, 4.0, 7.0], dtype="float64")

    predicted_difficulty, predicted_solve_rate = convert_predictions_for_storage(
        predictions=predictions,
        target_column="difficulty_estimate",
        reference_series=reference,
    )

    assert predicted_difficulty.tolist() == [1.0, 4.0, 7.0]
    assert predicted_solve_rate.tolist() == [1.0, 0.5, 0.0]
