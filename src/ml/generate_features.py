#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from src.db.models import Contest, Problem
from src.db.repository import upsert_feature_set
from src.db.session import session_scope


def latex_token_count(text: str | None) -> int:
    if not text:
        return 0
    return text.count("$")


def answer_choice_count(answer_choices: str | None) -> int:
    if not answer_choices:
        return 0
    return len(re.findall(r"\([A-E]\)", answer_choices))


def build_feature_payload(problem: Problem, contest: Contest, feature_version: str) -> dict:
    problem_length_words = problem.problem_length_words or 0
    solution_length_words = problem.solution_length_words or 0
    estimated_solve_minutes = problem.estimated_solve_minutes or round(max(problem_length_words / 18.0, 2.0), 2)
    features_json = {
        "contest_position_ratio": round(problem.problem_number / contest.num_problems, 4),
        "has_solution": bool(problem.solution_text),
        "has_answer_choices": bool(problem.answer_choices),
        "answer_choice_count": answer_choice_count(problem.answer_choices),
        "problem_latex_token_count": latex_token_count(problem.problem_text),
        "solution_latex_token_count": latex_token_count(problem.solution_text),
        "solution_to_problem_word_ratio": round(solution_length_words / problem_length_words, 4) if problem_length_words else None,
        "topic_count": len(problem.secondary_topics or []),
        "technique_count": len(problem.techniques or []),
        "year": problem.year,
        "contest_type": problem.contest_type,
    }
    return {
        "problem_id": problem.id,
        "feature_version": feature_version,
        "has_diagram": problem.has_diagram,
        "has_answer_choices": bool(problem.answer_choices),
        "problem_length_words": problem.problem_length_words,
        "problem_length_chars": problem.problem_length_chars,
        "solution_length_words": problem.solution_length_words,
        "solution_length_chars": problem.solution_length_chars,
        "problem_sentence_count": problem.problem_sentence_count,
        "difficulty_estimate": problem.difficulty_estimate,
        "estimated_solve_minutes": estimated_solve_minutes,
        "features_json": features_json,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate versioned feature sets from curated problems")
    parser.add_argument("--feature-version", required=True, help="Feature version label, e.g. baseline_v1")
    parser.add_argument("--contest-type", default=None, help="Optional contest type filter")
    parser.add_argument("--year", type=int, default=None, help="Optional year filter")
    args = parser.parse_args()

    with session_scope() as session:
        stmt = (
            select(Problem, Contest)
            .join(Contest, Contest.id == Problem.contest_id)
            .order_by(Problem.year, Problem.contest_type, Problem.problem_number)
        )
        if args.contest_type:
            stmt = stmt.where(Problem.contest_type == args.contest_type)
        if args.year:
            stmt = stmt.where(Problem.year == args.year)

        rows = session.execute(stmt).all()
        created = 0
        updated = 0
        for problem, contest in rows:
            payload = build_feature_payload(problem, contest, args.feature_version)
            _, was_created = upsert_feature_set(session, payload)
            if was_created:
                created += 1
            else:
                updated += 1
        session.commit()

    summary = {
        "feature_version": args.feature_version,
        "rows_processed": len(rows),
        "created": created,
        "updated": updated,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
