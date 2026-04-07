"""Initial TestForge schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260408_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contest_key", sa.String(length=64), nullable=False),
        sa.Column("contest_type", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("variant", sa.String(length=16), nullable=True),
        sa.Column("num_problems", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("contest_key", name="uq_contests_contest_key"),
    )
    op.create_index("ix_contests_contest_key", "contests", ["contest_key"])
    op.create_index("ix_contests_contest_type", "contests", ["contest_type"])
    op.create_index("ix_contests_year", "contests", ["year"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delay_seconds", sa.Float(), nullable=False),
        sa.Column("contests_attempted", sa.Integer(), nullable=False),
        sa.Column("contests_completed", sa.Integer(), nullable=False),
        sa.Column("problems_seen", sa.Integer(), nullable=False),
        sa.Column("problems_created", sa.Integer(), nullable=False),
        sa.Column("problems_updated", sa.Integer(), nullable=False),
        sa.Column("problems_failed", sa.Integer(), nullable=False),
        sa.Column("args_json", sa.JSON(), nullable=False),
        sa.Column("issues_json", sa.JSON(), nullable=False),
        sa.Column("manifest_path", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("run_key", name="uq_scrape_runs_run_key"),
    )
    op.create_index("ix_scrape_runs_run_key", "scrape_runs", ["run_key"])

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_name", sa.String(length=128), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("target_column", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("split_version", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("training_snapshot_path", sa.String(length=255), nullable=True),
        sa.Column("artifact_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_name", name="uq_model_runs_run_name"),
    )
    op.create_index("ix_model_runs_run_name", "model_runs", ["run_name"])
    op.create_index("ix_model_runs_feature_version", "model_runs", ["feature_version"])
    op.create_index("ix_model_runs_split_version", "model_runs", ["split_version"])

    op.create_table(
        "problems",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("contest_type", sa.String(length=32), nullable=False),
        sa.Column("problem_number", sa.Integer(), nullable=False),
        sa.Column("difficulty_estimate", sa.Float(), nullable=True),
        sa.Column("problem_text", sa.Text(), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=True),
        sa.Column("has_diagram", sa.Boolean(), nullable=False),
        sa.Column("answer_choices", sa.Text(), nullable=True),
        sa.Column("problem_length_words", sa.Integer(), nullable=True),
        sa.Column("problem_length_chars", sa.Integer(), nullable=True),
        sa.Column("solution_length_words", sa.Integer(), nullable=True),
        sa.Column("solution_length_chars", sa.Integer(), nullable=True),
        sa.Column("problem_sentence_count", sa.Integer(), nullable=True),
        sa.Column("primary_topic", sa.String(length=64), nullable=True),
        sa.Column("secondary_topics", sa.JSON(), nullable=False),
        sa.Column("techniques", sa.JSON(), nullable=False),
        sa.Column("estimated_solve_minutes", sa.Float(), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("problem_number > 0", name="ck_problems_problem_number_positive"),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], name="fk_problems_contest_id_contests"),
        sa.UniqueConstraint("contest_id", "problem_number", name="uq_problems_contest_id"),
        sa.UniqueConstraint("problem_id", name="uq_problems_problem_id"),
        sa.UniqueConstraint("url", name="uq_problems_url"),
    )
    op.create_index("ix_problems_contest_id", "problems", ["contest_id"])
    op.create_index("ix_problems_problem_id", "problems", ["problem_id"])
    op.create_index("ix_problems_year", "problems", ["year"])
    op.create_index("ix_problems_contest_type", "problems", ["contest_type"])

    op.create_table(
        "raw_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scrape_run_id", sa.Integer(), nullable=False),
        sa.Column("problem_key", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=255), nullable=False),
        sa.Column("snapshot_path", sa.String(length=255), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("extracted_problem_text", sa.Boolean(), nullable=False),
        sa.Column("extracted_solution_text", sa.Boolean(), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], name="fk_raw_pages_scrape_run_id_scrape_runs"),
    )
    op.create_index("ix_raw_pages_scrape_run_id", "raw_pages", ["scrape_run_id"])
    op.create_index("ix_raw_pages_problem_key", "raw_pages", ["problem_key"])

    op.create_table(
        "feature_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("has_diagram", sa.Boolean(), nullable=False),
        sa.Column("has_answer_choices", sa.Boolean(), nullable=False),
        sa.Column("problem_length_words", sa.Integer(), nullable=True),
        sa.Column("problem_length_chars", sa.Integer(), nullable=True),
        sa.Column("solution_length_words", sa.Integer(), nullable=True),
        sa.Column("solution_length_chars", sa.Integer(), nullable=True),
        sa.Column("problem_sentence_count", sa.Integer(), nullable=True),
        sa.Column("difficulty_estimate", sa.Float(), nullable=True),
        sa.Column("estimated_solve_minutes", sa.Float(), nullable=True),
        sa.Column("features_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_feature_sets_problem_id_problems"),
        sa.UniqueConstraint("problem_id", "feature_version", name="uq_feature_sets_problem_id"),
    )
    op.create_index("ix_feature_sets_problem_id", "feature_sets", ["problem_id"])
    op.create_index("ix_feature_sets_feature_version", "feature_sets", ["feature_version"])

    op.create_table(
        "problem_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("predicted_solve_rate", sa.Float(), nullable=False),
        sa.Column("predicted_difficulty", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_problem_predictions_problem_id_problems"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], name="fk_problem_predictions_model_run_id_model_runs"),
        sa.UniqueConstraint("problem_id", "model_run_id", name="uq_problem_predictions_problem_id"),
    )
    op.create_index("ix_problem_predictions_problem_id", "problem_predictions", ["problem_id"])
    op.create_index("ix_problem_predictions_model_run_id", "problem_predictions", ["model_run_id"])

    op.create_table(
        "assembled_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("solver_name", sa.String(length=64), nullable=False),
        sa.Column("objective_name", sa.String(length=64), nullable=False),
        sa.Column("requested_problem_count", sa.Integer(), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=False),
        sa.Column("source_problem_count", sa.Integer(), nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("constraint_config_json", sa.JSON(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], name="fk_assembled_tests_model_run_id_model_runs"),
        sa.UniqueConstraint("name", name="uq_assembled_tests_name"),
    )
    op.create_index("ix_assembled_tests_name", "assembled_tests", ["name"])
    op.create_index("ix_assembled_tests_model_run_id", "assembled_tests", ["model_run_id"])

    op.create_table(
        "assembled_test_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assembled_test_id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("predicted_solve_rate", sa.Float(), nullable=True),
        sa.Column("predicted_difficulty", sa.Float(), nullable=True),
        sa.Column("estimated_solve_minutes", sa.Float(), nullable=True),
        sa.Column("primary_topic", sa.String(length=64), nullable=True),
        sa.Column("techniques", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["assembled_test_id"], ["assembled_tests.id"], name="fk_assembled_test_items_assembled_test_id_assembled_tests"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_assembled_test_items_problem_id_problems"),
        sa.UniqueConstraint("assembled_test_id", "order_index", name="uq_assembled_test_items_assembled_test_id"),
    )
    op.create_index("ix_assembled_test_items_assembled_test_id", "assembled_test_items", ["assembled_test_id"])
    op.create_index("ix_assembled_test_items_problem_id", "assembled_test_items", ["problem_id"])


def downgrade() -> None:
    op.drop_index("ix_assembled_test_items_problem_id", table_name="assembled_test_items")
    op.drop_index("ix_assembled_test_items_assembled_test_id", table_name="assembled_test_items")
    op.drop_table("assembled_test_items")
    op.drop_index("ix_assembled_tests_model_run_id", table_name="assembled_tests")
    op.drop_index("ix_assembled_tests_name", table_name="assembled_tests")
    op.drop_table("assembled_tests")
    op.drop_index("ix_problem_predictions_model_run_id", table_name="problem_predictions")
    op.drop_index("ix_problem_predictions_problem_id", table_name="problem_predictions")
    op.drop_table("problem_predictions")
    op.drop_index("ix_feature_sets_feature_version", table_name="feature_sets")
    op.drop_index("ix_feature_sets_problem_id", table_name="feature_sets")
    op.drop_table("feature_sets")
    op.drop_index("ix_raw_pages_problem_key", table_name="raw_pages")
    op.drop_index("ix_raw_pages_scrape_run_id", table_name="raw_pages")
    op.drop_table("raw_pages")
    op.drop_index("ix_problems_contest_type", table_name="problems")
    op.drop_index("ix_problems_year", table_name="problems")
    op.drop_index("ix_problems_problem_id", table_name="problems")
    op.drop_index("ix_problems_contest_id", table_name="problems")
    op.drop_table("problems")
    op.drop_index("ix_model_runs_split_version", table_name="model_runs")
    op.drop_index("ix_model_runs_feature_version", table_name="model_runs")
    op.drop_index("ix_model_runs_run_name", table_name="model_runs")
    op.drop_table("model_runs")
    op.drop_index("ix_scrape_runs_run_key", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_index("ix_contests_year", table_name="contests")
    op.drop_index("ix_contests_contest_type", table_name="contests")
    op.drop_index("ix_contests_contest_key", table_name="contests")
    op.drop_table("contests")
