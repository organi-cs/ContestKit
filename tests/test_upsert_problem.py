from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import Contest, Problem
from src.db.repository import get_or_create_contest, upsert_problem


def build_problem_values(contest_id: int) -> dict:
    return {
        "contest_id": contest_id,
        "problem_id": "2023_AMC_10A_P1",
        "url": "https://example.com/problem-1",
        "year": 2023,
        "contest_type": "AMC_10A",
        "problem_number": 1,
        "difficulty_estimate": 1.0,
        "problem_text": "Sample problem",
        "solution_text": "Sample solution",
        "has_diagram": False,
        "answer_choices": "(A) 1 (B) 2 (C) 3 (D) 4 (E) 5",
        "problem_length_words": 2,
        "problem_length_chars": 14,
        "solution_length_words": 2,
        "solution_length_chars": 15,
        "problem_sentence_count": 1,
        "estimated_solve_minutes": 2.5,
        "last_scraped_at": datetime.now(timezone.utc),
    }


def test_problem_upsert_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        contest = get_or_create_contest(
            session,
            contest_key="2023_AMC_10A",
            contest_type="AMC_10A",
            year=2023,
            variant=None,
            num_problems=25,
        )
        session.commit()

        values = build_problem_values(contest.id)
        _, created = upsert_problem(session, values)
        session.commit()
        assert created is True

        values["problem_text"] = "Updated sample problem"
        _, created = upsert_problem(session, values)
        session.commit()
        assert created is False

        rows = session.execute(select(Problem)).scalars().all()
        assert len(rows) == 1
        assert rows[0].problem_text == "Updated sample problem"
