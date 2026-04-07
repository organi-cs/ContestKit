#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pulp
from sqlalchemy import desc, select

from src.db.models import AssembledTest, ModelRun, Problem, ProblemPrediction
from src.db.repository import replace_assembled_test_items
from src.db.session import session_scope


@dataclass
class Candidate:
    problem_db_id: int
    problem_id: str
    difficulty: float
    predicted_solve_rate: float | None
    estimated_solve_minutes: float
    primary_topic: str | None
    techniques: tuple[str, ...]


def solve_rate_to_difficulty(predicted_solve_rate: float | None, fallback: float | None) -> float:
    if predicted_solve_rate is not None:
        return round(1.0 - predicted_solve_rate, 4)
    return fallback or 0.0


def discrimination_weight(predicted_solve_rate: float | None, difficulty: float) -> float:
    if predicted_solve_rate is not None:
        return predicted_solve_rate * (1.0 - predicted_solve_rate)

    normalized = max(0.0, min(difficulty / 7.0, 1.0))
    return 1.0 - abs(normalized - 0.5)


def load_topic_bounds(path: str | None) -> dict[str, dict[str, int]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_candidates(session, model_run_id: int | None, contest_type: str | None, year: int | None) -> list[Candidate]:
    stmt = select(Problem).order_by(Problem.year, Problem.contest_type, Problem.problem_number)
    if contest_type:
        stmt = stmt.where(Problem.contest_type == contest_type)
    if year:
        stmt = stmt.where(Problem.year == year)

    problems = session.execute(stmt).scalars().all()
    prediction_map: dict[int, ProblemPrediction] = {}
    if model_run_id is not None:
        predictions = session.execute(
            select(ProblemPrediction).where(ProblemPrediction.model_run_id == model_run_id)
        ).scalars()
        prediction_map = {prediction.problem_id: prediction for prediction in predictions}

    candidates: list[Candidate] = []
    for problem in problems:
        prediction = prediction_map.get(problem.id)
        predicted_solve_rate = prediction.predicted_solve_rate if prediction else None
        difficulty = prediction.predicted_difficulty if prediction and prediction.predicted_difficulty is not None else solve_rate_to_difficulty(
            predicted_solve_rate,
            problem.difficulty_estimate,
        )
        candidates.append(
            Candidate(
                problem_db_id=problem.id,
                problem_id=problem.problem_id,
                difficulty=difficulty,
                predicted_solve_rate=predicted_solve_rate,
                estimated_solve_minutes=problem.estimated_solve_minutes or max((problem.problem_length_words or 0) / 18.0, 2.0),
                primary_topic=problem.primary_topic,
                techniques=tuple(problem.techniques or []),
            )
        )
    return candidates


def assemble_candidates(
    candidates: list[Candidate],
    *,
    name: str,
    n_problems: int,
    time_limit_minutes: int,
    topic_bounds: dict[str, dict[str, int]],
) -> tuple[list[Candidate], float]:
    if len(candidates) < n_problems:
        raise ValueError(f"Not enough candidates ({len(candidates)}) to assemble {n_problems} problems")

    positions = range(n_problems)
    problem = pulp.LpProblem(name=name, sense=pulp.LpMaximize)
    decision = {
        (candidate.problem_db_id, position): pulp.LpVariable(
            f"x_{candidate.problem_db_id}_{position}",
            lowBound=0,
            upBound=1,
            cat="Binary",
        )
        for candidate in candidates
        for position in positions
    }

    problem += pulp.lpSum(
        discrimination_weight(candidate.predicted_solve_rate, candidate.difficulty) * decision[(candidate.problem_db_id, position)]
        for candidate in candidates
        for position in positions
    )

    for position in positions:
        problem += pulp.lpSum(decision[(candidate.problem_db_id, position)] for candidate in candidates) == 1

    for candidate in candidates:
        problem += pulp.lpSum(decision[(candidate.problem_db_id, position)] for position in positions) <= 1

    problem += pulp.lpSum(
        candidate.estimated_solve_minutes * decision[(candidate.problem_db_id, position)]
        for candidate in candidates
        for position in positions
    ) <= time_limit_minutes

    for position in range(n_problems - 1):
        current_difficulty = pulp.lpSum(candidate.difficulty * decision[(candidate.problem_db_id, position)] for candidate in candidates)
        next_difficulty = pulp.lpSum(candidate.difficulty * decision[(candidate.problem_db_id, position + 1)] for candidate in candidates)
        problem += current_difficulty <= next_difficulty

    technique_groups: dict[tuple[str, ...], list[Candidate]] = {}
    for candidate in candidates:
        if candidate.techniques:
            technique_groups.setdefault(candidate.techniques, []).append(candidate)
    for grouped_candidates in technique_groups.values():
        if len(grouped_candidates) < 2:
            continue
        problem += pulp.lpSum(
            decision[(candidate.problem_db_id, position)]
            for candidate in grouped_candidates
            for position in positions
        ) <= 1

    for topic, bounds in topic_bounds.items():
        topic_candidates = [candidate for candidate in candidates if candidate.primary_topic == topic]
        if not topic_candidates:
            continue
        total = pulp.lpSum(
            decision[(candidate.problem_db_id, position)]
            for candidate in topic_candidates
            for position in positions
        )
        if "min" in bounds:
            problem += total >= int(bounds["min"])
        if "max" in bounds:
            problem += total <= int(bounds["max"])

    solver = pulp.PULP_CBC_CMD(msg=False)
    result_status = problem.solve(solver)
    if pulp.LpStatus[result_status] != "Optimal":
        raise ValueError(f"Assembly failed with status {pulp.LpStatus[result_status]}")

    selected: list[tuple[int, Candidate]] = []
    for position in positions:
        for candidate in candidates:
            value = pulp.value(decision[(candidate.problem_db_id, position)])
            if value is not None and math.isclose(value, 1.0, rel_tol=0.0, abs_tol=1e-9):
                selected.append((position, candidate))
                break

    selected.sort(key=lambda entry: entry[0])
    return [candidate for _, candidate in selected], float(pulp.value(problem.objective))


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble a contest paper from PostgreSQL problem data")
    parser.add_argument("--name", required=True, help="Unique assembled test name")
    parser.add_argument("--n-problems", type=int, required=True, help="Number of problems to select")
    parser.add_argument("--time-limit", type=int, required=True, help="Time limit in minutes")
    parser.add_argument("--model-run-id", type=int, default=None, help="Optional model run to pull predictions from")
    parser.add_argument("--contest-type", default=None, help="Optional contest type filter")
    parser.add_argument("--year", type=int, default=None, help="Optional year filter")
    parser.add_argument("--topic-bounds", default=None, help="Path to JSON file of topic min/max bounds")
    args = parser.parse_args()

    topic_bounds = load_topic_bounds(args.topic_bounds)

    with session_scope() as session:
        resolved_model_run_id = args.model_run_id
        if resolved_model_run_id is None:
            resolved_model_run_id = session.execute(
                select(ModelRun.id).order_by(desc(ModelRun.created_at)).limit(1)
            ).scalar_one_or_none()

        candidates = build_candidates(session, resolved_model_run_id, args.contest_type, args.year)
        selected_candidates, objective_value = assemble_candidates(
            candidates,
            name=args.name,
            n_problems=args.n_problems,
            time_limit_minutes=args.time_limit,
            topic_bounds=topic_bounds,
        )

        assembled_test = session.scalar(select(AssembledTest).where(AssembledTest.name == args.name))
        if assembled_test is None:
            assembled_test = AssembledTest(
                name=args.name,
                solver_name="pulp",
                objective_name="discrimination_weight",
                requested_problem_count=args.n_problems,
                time_limit_minutes=args.time_limit,
                source_problem_count=len(candidates),
                objective_value=objective_value,
                status="assembled",
                constraint_config_json={
                    "topic_bounds": topic_bounds,
                    "contest_type": args.contest_type,
                    "year": args.year,
                },
                model_run_id=resolved_model_run_id,
            )
            session.add(assembled_test)
            session.flush()
        else:
            assembled_test.requested_problem_count = args.n_problems
            assembled_test.time_limit_minutes = args.time_limit
            assembled_test.source_problem_count = len(candidates)
            assembled_test.objective_value = objective_value
            assembled_test.constraint_config_json = {
                "topic_bounds": topic_bounds,
                "contest_type": args.contest_type,
                "year": args.year,
            }
            assembled_test.model_run_id = resolved_model_run_id
            session.flush()

        replace_assembled_test_items(
            session,
            assembled_test,
            [
                {
                    "problem_id": candidate.problem_db_id,
                    "order_index": index + 1,
                    "predicted_solve_rate": candidate.predicted_solve_rate,
                    "predicted_difficulty": candidate.difficulty,
                    "estimated_solve_minutes": candidate.estimated_solve_minutes,
                    "primary_topic": candidate.primary_topic,
                    "techniques": list(candidate.techniques),
                }
                for index, candidate in enumerate(selected_candidates)
            ],
        )
        session.commit()

    print(
        json.dumps(
            {
                "name": args.name,
                "selected_problem_ids": [candidate.problem_id for candidate in selected_candidates],
                "objective_value": objective_value,
                "source_problem_count": len(candidates),
                "model_run_id": resolved_model_run_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
