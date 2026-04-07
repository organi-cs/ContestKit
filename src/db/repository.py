from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import (
    AssembledTest,
    AssembledTestItem,
    Contest,
    FeatureSet,
    Problem,
    ProblemPrediction,
    RawPage,
)


def get_or_create_contest(
    session: Session,
    *,
    contest_key: str,
    contest_type: str,
    year: int,
    variant: str | None,
    num_problems: int,
) -> Contest:
    contest = session.scalar(select(Contest).where(Contest.contest_key == contest_key))
    if contest is None:
        contest = Contest(
            contest_key=contest_key,
            contest_type=contest_type,
            year=year,
            variant=variant,
            num_problems=num_problems,
        )
        session.add(contest)
        session.flush()
        return contest

    contest.contest_type = contest_type
    contest.year = year
    contest.variant = variant
    contest.num_problems = num_problems
    session.flush()
    return contest


def _generic_upsert(session: Session, model: type, unique_filter: Select, values: dict):
    instance = session.scalar(unique_filter)
    if instance is None:
        instance = model(**values)
        session.add(instance)
        session.flush()
        return instance, True

    for key, value in values.items():
        setattr(instance, key, value)
    session.flush()
    return instance, False


def upsert_problem(session: Session, values: dict) -> tuple[Problem, bool]:
    created = session.scalar(select(Problem.id).where(Problem.problem_id == values["problem_id"])) is None
    engine = session.get_bind()
    if engine is not None and engine.dialect.name == "postgresql":
        stmt = (
            pg_insert(Problem)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Problem.problem_id],
                set_={key: value for key, value in values.items() if key != "problem_id"},
            )
            .returning(Problem.id)
        )
        problem_id = session.execute(stmt).scalar_one()
        problem = session.get(Problem, problem_id)
        return problem, created

    problem, _ = _generic_upsert(
        session,
        Problem,
        select(Problem).where(Problem.problem_id == values["problem_id"]),
        values,
    )
    return problem, created


def upsert_feature_set(session: Session, values: dict) -> tuple[FeatureSet, bool]:
    return _generic_upsert(
        session,
        FeatureSet,
        select(FeatureSet).where(
            FeatureSet.problem_id == values["problem_id"],
            FeatureSet.feature_version == values["feature_version"],
        ),
        values,
    )


def upsert_prediction(session: Session, values: dict) -> tuple[ProblemPrediction, bool]:
    return _generic_upsert(
        session,
        ProblemPrediction,
        select(ProblemPrediction).where(
            ProblemPrediction.problem_id == values["problem_id"],
            ProblemPrediction.model_run_id == values["model_run_id"],
        ),
        values,
    )


def record_raw_page(session: Session, values: dict) -> RawPage:
    raw_page = RawPage(**values)
    session.add(raw_page)
    session.flush()
    return raw_page


def replace_assembled_test_items(
    session: Session,
    assembled_test: AssembledTest,
    items: Iterable[dict],
) -> None:
    for existing in list(assembled_test.items):
        session.delete(existing)
    session.flush()
    for item in items:
        assembled_test.items.append(AssembledTestItem(**item))
    session.flush()
