from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from src.db.models import AssembledTest, AssembledTestItem, Contest, ModelRun, Problem
from src.db.session import get_db_session


app = FastAPI(title="TestForge API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/contests")
def list_contests(session: Session = Depends(get_db_session)) -> list[dict]:
    contests = session.execute(select(Contest).order_by(desc(Contest.year), Contest.contest_type)).scalars().all()
    return [
        {
            "contest_key": contest.contest_key,
            "contest_type": contest.contest_type,
            "year": contest.year,
            "variant": contest.variant,
            "num_problems": contest.num_problems,
        }
        for contest in contests
    ]


@app.get("/problems")
def list_problems(
    contest_type: str | None = None,
    year: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[dict]:
    stmt = select(Problem).order_by(Problem.year.desc(), Problem.contest_type, Problem.problem_number).offset(offset).limit(limit)
    if contest_type:
        stmt = stmt.where(Problem.contest_type == contest_type)
    if year:
        stmt = stmt.where(Problem.year == year)
    problems = session.execute(stmt).scalars().all()
    return [
        {
            "problem_id": problem.problem_id,
            "contest_type": problem.contest_type,
            "year": problem.year,
            "problem_number": problem.problem_number,
            "difficulty_estimate": problem.difficulty_estimate,
            "has_diagram": problem.has_diagram,
            "primary_topic": problem.primary_topic,
            "techniques": problem.techniques,
        }
        for problem in problems
    ]


@app.get("/model-runs")
def list_model_runs(session: Session = Depends(get_db_session)) -> list[dict]:
    runs = session.execute(select(ModelRun).order_by(ModelRun.created_at.desc())).scalars().all()
    return [
        {
            "id": run.id,
            "run_name": run.run_name,
            "model_family": run.model_family,
            "feature_version": run.feature_version,
            "split_version": run.split_version,
            "metrics": run.metrics_json,
            "snapshot_path": run.training_snapshot_path,
        }
        for run in runs
    ]


@app.get("/assembled-tests")
def list_assembled_tests(session: Session = Depends(get_db_session)) -> list[dict]:
    tests = session.execute(select(AssembledTest).order_by(AssembledTest.created_at.desc())).scalars().all()
    return [
        {
            "name": test.name,
            "solver_name": test.solver_name,
            "objective_name": test.objective_name,
            "requested_problem_count": test.requested_problem_count,
            "time_limit_minutes": test.time_limit_minutes,
            "objective_value": test.objective_value,
            "status": test.status,
            "created_at": test.created_at.isoformat(),
        }
        for test in tests
    ]


@app.get("/assembled-tests/{name}")
def get_assembled_test(name: str, session: Session = Depends(get_db_session)) -> dict:
    assembled_test = session.execute(
        select(AssembledTest)
        .where(AssembledTest.name == name)
        .options(joinedload(AssembledTest.items).joinedload(AssembledTestItem.problem))
    ).unique().scalar_one_or_none()
    if assembled_test is None:
        raise HTTPException(status_code=404, detail="assembled_test_not_found")

    return {
        "name": assembled_test.name,
        "solver_name": assembled_test.solver_name,
        "objective_name": assembled_test.objective_name,
        "objective_value": assembled_test.objective_value,
        "constraints": assembled_test.constraint_config_json,
        "items": [
            {
                "order_index": item.order_index,
                "problem_id": item.problem.problem_id,
                "problem_text": item.problem.problem_text,   # <-- Added this so the text is returned!
                "has_diagram": item.problem.has_diagram,     # <-- Added this as well
                "predicted_solve_rate": item.predicted_solve_rate,
                "predicted_difficulty": item.predicted_difficulty,
                "estimated_solve_minutes": item.estimated_solve_minutes,
                "primary_topic": item.primary_topic,
                "techniques": item.techniques,
            }
            for item in sorted(assembled_test.items, key=lambda value: value.order_index)
        ],
    }
