from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, utc_now


class Contest(TimestampMixin, Base):
    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contest_type: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    variant: Mapped[str | None] = mapped_column(String(16), nullable=True)
    num_problems: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64), default="AoPS Wiki")

    problems: Mapped[list["Problem"]] = relationship(back_populates="contest")


class Problem(TimestampMixin, Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("contest_id", "problem_number"),
        CheckConstraint("problem_number > 0", name="problem_number_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id"), index=True)
    problem_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(255), unique=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    contest_type: Mapped[str] = mapped_column(String(32), index=True)
    problem_number: Mapped[int] = mapped_column(Integer)
    difficulty_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    problem_text: Mapped[str] = mapped_column(Text)
    solution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_diagram: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_choices: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_length_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_length_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution_length_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution_length_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_sentence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secondary_topics: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    techniques: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    estimated_solve_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    contest: Mapped["Contest"] = relationship(back_populates="problems")
    feature_sets: Mapped[list["FeatureSet"]] = relationship(back_populates="problem")
    predictions: Mapped[list["ProblemPrediction"]] = relationship(back_populates="problem")
    assembled_items: Mapped[list["AssembledTestItem"]] = relationship(back_populates="problem")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_seconds: Mapped[float] = mapped_column(Float, default=1.5)
    contests_attempted: Mapped[int] = mapped_column(Integer, default=0)
    contests_completed: Mapped[int] = mapped_column(Integer, default=0)
    problems_seen: Mapped[int] = mapped_column(Integer, default=0)
    problems_created: Mapped[int] = mapped_column(Integer, default=0)
    problems_updated: Mapped[int] = mapped_column(Integer, default=0)
    problems_failed: Mapped[int] = mapped_column(Integer, default=0)
    args_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    issues_json: Mapped[list[dict]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    manifest_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raw_pages: Mapped[list["RawPage"]] = relationship(back_populates="scrape_run")


class RawPage(Base):
    __tablename__ = "raw_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scrape_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), index=True)
    problem_key: Mapped[str] = mapped_column(String(80), index=True)
    url: Mapped[str] = mapped_column(String(255))
    snapshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_problem_text: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_solution_text: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    scrape_run: Mapped["ScrapeRun"] = relationship(back_populates="raw_pages")


class FeatureSet(Base):
    __tablename__ = "feature_sets"
    __table_args__ = (
        UniqueConstraint("problem_id", "feature_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    feature_version: Mapped[str] = mapped_column(String(64), index=True)
    has_diagram: Mapped[bool] = mapped_column(Boolean, default=False)
    has_answer_choices: Mapped[bool] = mapped_column(Boolean, default=False)
    problem_length_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_length_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution_length_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution_length_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_sentence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_solve_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    features_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="feature_sets")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    model_family: Mapped[str] = mapped_column(String(64))
    target_column: Mapped[str] = mapped_column(String(64), default="solve_rate")
    feature_version: Mapped[str] = mapped_column(String(64), index=True)
    split_version: Mapped[str] = mapped_column(String(64), index=True)
    params_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    metrics_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    training_snapshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    predictions: Mapped[list["ProblemPrediction"]] = relationship(back_populates="model_run")
    assembled_tests: Mapped[list["AssembledTest"]] = relationship(back_populates="model_run")


class ProblemPrediction(Base):
    __tablename__ = "problem_predictions"
    __table_args__ = (
        UniqueConstraint("problem_id", "model_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"), index=True)
    predicted_solve_rate: Mapped[float] = mapped_column(Float)
    predicted_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="predictions")
    model_run: Mapped["ModelRun"] = relationship(back_populates="predictions")


class AssembledTest(Base):
    __tablename__ = "assembled_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    solver_name: Mapped[str] = mapped_column(String(64), default="pulp")
    objective_name: Mapped[str] = mapped_column(String(64), default="solve_rate_variance")
    requested_problem_count: Mapped[int] = mapped_column(Integer)
    time_limit_minutes: Mapped[int] = mapped_column(Integer)
    source_problem_count: Mapped[int] = mapped_column(Integer)
    objective_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="assembled")
    constraint_config_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    model_run_id: Mapped[int | None] = mapped_column(ForeignKey("model_runs.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    model_run: Mapped["ModelRun | None"] = relationship(back_populates="assembled_tests")
    items: Mapped[list["AssembledTestItem"]] = relationship(
        back_populates="assembled_test",
        cascade="all, delete-orphan",
    )


class AssembledTestItem(Base):
    __tablename__ = "assembled_test_items"
    __table_args__ = (
        UniqueConstraint("assembled_test_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assembled_test_id: Mapped[int] = mapped_column(ForeignKey("assembled_tests.id"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    predicted_solve_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_solve_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    techniques: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)

    assembled_test: Mapped["AssembledTest"] = relationship(back_populates="items")
    problem: Mapped["Problem"] = relationship(back_populates="assembled_items")
