#!/usr/bin/env python3
"""
TestForge AoPS scraper.

This version treats PostgreSQL as the source of truth:
- each run is logged in `scrape_runs`
- problems are upserted by `problem_id`
- raw HTML snapshots are written to disk and indexed in `raw_pages`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup, Tag
from sqlalchemy import func, select

from src.db.models import Problem, ScrapeRun
from src.db.repository import get_or_create_contest, record_raw_page, upsert_problem
from src.db.session import session_scope
from src.settings import get_settings


BASE_URL = "https://artofproblemsolving.com/wiki/index.php/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

CONTEST_DEFS = {
    "AMC_8": {"problems": 25, "diff_min": 0.5, "diff_max": 3.0},
    "AMC_10A": {"problems": 25, "diff_min": 1.0, "diff_max": 4.0},
    "AMC_10B": {"problems": 25, "diff_min": 1.0, "diff_max": 4.0},
    "AMC_12A": {"problems": 25, "diff_min": 1.5, "diff_max": 5.0},
    "AMC_12B": {"problems": 25, "diff_min": 1.5, "diff_max": 5.0},
    "AIME_I": {"problems": 15, "diff_min": 3.0, "diff_max": 7.0},
    "AIME_II": {"problems": 15, "diff_min": 3.0, "diff_max": 7.0},
}
DEFAULT_YEARS = range(2010, 2025)
FALL_2021_CONTESTS = {"AMC_8", "AMC_10A", "AMC_10B", "AMC_12A", "AMC_12B"}
DEFAULT_DELAY = 1.5
MAX_RETRIES = 3


def get_page_title(year: int, contest_type: str, problem_num: int) -> str:
    return f"{_contest_prefix(year, contest_type)}_Problems/Problem_{problem_num}"


def _contest_prefix(year: int, contest_type: str) -> str:
    if year == 2021 and contest_type in FALL_2021_CONTESTS:
        return f"2021_Fall_{contest_type}"
    return f"{year}_{contest_type}"


def contest_variant(year: int, contest_type: str) -> str | None:
    if year == 2021 and contest_type in FALL_2021_CONTESTS:
        return "FALL"
    return None


def problem_url(year: int, contest_type: str, problem_num: int) -> str:
    return BASE_URL + get_page_title(year, contest_type, problem_num)


def fetch_page(url: str, delay: float = DEFAULT_DELAY) -> tuple[requests.Response | None, int | None, str | None]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(delay)
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp, resp.status_code, None
            if resp.status_code == 404:
                return None, 404, "http_404"
            print(f"  HTTP {resp.status_code} on attempt {attempt}/{MAX_RETRIES}: {url}")
        except requests.RequestException as exc:
            print(f"  Request error on attempt {attempt}/{MAX_RETRIES}: {exc}")
            if attempt == MAX_RETRIES:
                return None, None, str(exc)
        if attempt < MAX_RETRIES:
            backoff = delay * (2 ** attempt)
            print(f"    Retrying in {backoff:.1f}s...")
            time.sleep(backoff)
    return None, None, "request_failed"


def get_content_div(soup: BeautifulSoup) -> Tag | None:
    return soup.find("div", class_="mw-parser-output")


def _element_to_text(el: Tag) -> str:
    clone = BeautifulSoup(str(el), "html.parser")
    for img in clone.find_all("img"):
        alt = img.get("alt", "")
        if alt:
            img.replace_with(f" {alt} ")
    text = clone.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _find_section(content_div: Tag, header_patterns: list[str]) -> str:
    headers = content_div.find_all("h2")
    target_header = None
    for h2 in headers:
        header_text = h2.get_text(strip=True)
        for pattern in header_patterns:
            if re.search(pattern, header_text, re.IGNORECASE):
                target_header = h2
                break
        if target_header:
            break

    if target_header is None:
        return ""

    parts: list[str] = []
    for sibling in target_header.find_next_siblings():
        if sibling.name == "h2":
            break
        if isinstance(sibling, Tag):
            parts.append(_element_to_text(sibling))
    return " ".join(part for part in parts if part)


def extract_problem_text(content_div: Tag) -> str:
    return _find_section(content_div, [r"^Problem(\s+\d+)?$"])


def extract_solution_text(content_div: Tag) -> str:
    headers = content_div.find_all(["h2", "h3"])
    target_header = None
    for header in headers:
        header_text = header.get_text(strip=True)
        if re.match(r"^Solution(\s+1)?(\s*\(.+\))?$", header_text, re.IGNORECASE):
            target_header = header
            break

    if target_header is None:
        return ""

    parts: list[str] = []
    for sibling in target_header.find_next_siblings():
        if sibling.name in ("h2", "h3"):
            break
        if isinstance(sibling, Tag):
            parts.append(_element_to_text(sibling))
    return " ".join(part for part in parts if part)


def check_has_diagram(content_div: Tag) -> bool:
    headers = content_div.find_all(["h2", "h3"])
    problem_header = None
    for header in headers:
        if re.match(r"^Problem(\s+\d+)?$", header.get_text(strip=True), re.IGNORECASE):
            problem_header = header
            break

    tags_to_check = [content_div]
    if problem_header is not None:
        siblings = []
        for sibling in problem_header.find_next_siblings():
            if sibling.name in ("h2", "h3"):
                break
            siblings.append(sibling)
        if siblings:
            tags_to_check = siblings

    for tag in tags_to_check:
        if not isinstance(tag, Tag):
            continue
        images = [tag] if tag.name == "img" else tag.find_all("img")
        for img in images:
            alt = img.get("alt", "")
            src = img.get("src", "")
            classes = img.get("class", [])
            if isinstance(classes, str):
                classes = [classes]

            if "latex" not in src.lower() and not any("latex" in value.lower() for value in classes):
                if "AMC_Logo" not in src:
                    return True

            if "[asy]" in alt.lower() or "asymptote" in alt.lower():
                return True

            width = img.get("width")
            height = img.get("height")
            if width and height and width.isdigit() and height.isdigit():
                if int(width) > 100 and int(height) > 100:
                    return True
    return False


def extract_answer_choices(content_div: Tag, problem_text: str) -> str:
    inline_match = re.search(
        r"\(A\)\s*.+?\(B\)\s*.+?\(C\)\s*.+?\(D\)\s*.+?\(E\)\s*.+",
        problem_text,
        re.DOTALL,
    )
    if inline_match:
        return inline_match.group(0).strip()

    full_text = _element_to_text(content_div)
    text_match = re.search(
        r"\$\\textbf\{?\(A\)\}?\$.+?\$\\textbf\{?\(E\)\}?\$[^\n]*",
        full_text,
        re.DOTALL,
    )
    if text_match:
        return text_match.group(0).strip()

    return ""


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


def count_chars(text: str) -> int:
    return len(text) if text else 0


def count_sentences(text: str) -> int:
    if not text:
        return 0
    cleaned = re.sub(r"\b(Mr|Mrs|Ms|Dr|vs|etc|e\.g|i\.e)\.", "", text)
    return len(re.findall(r"[.?!]+", cleaned))


def difficulty_estimate(contest_type: str, problem_number: int) -> float:
    info = CONTEST_DEFS[contest_type]
    num_problems = info["problems"]
    diff_min = info["diff_min"]
    diff_max = info["diff_max"]
    return round(diff_min + (diff_max - diff_min) * (problem_number - 1) / (num_problems - 1), 3)


def parse_years(year_str: str) -> range:
    if "-" in year_str:
        start, end = year_str.split("-", maxsplit=1)
        return range(int(start), int(end) + 1)
    year = int(year_str)
    return range(year, year + 1)


def build_contest_list(contest_filter: str | None, years: range) -> list[tuple[int, str]]:
    contest_types = list(CONTEST_DEFS.keys())
    if contest_filter:
        contest_filter = contest_filter.upper().replace(" ", "_")
        if contest_filter not in CONTEST_DEFS:
            available = ", ".join(CONTEST_DEFS.keys())
            raise SystemExit(f"Unknown contest type: {contest_filter}. Available: {available}")
        contest_types = [contest_filter]
    return [(year, contest_type) for year in years for contest_type in contest_types]


def serialize_args(args: argparse.Namespace) -> dict:
    return {
        "test": args.test,
        "contest": args.contest,
        "years": args.years,
        "delay": args.delay,
    }


def append_issue(issues: list[dict], *, level: str, problem_key: str, url: str, message: str) -> None:
    issues.append(
        {
            "level": level,
            "problem_key": problem_key,
            "url": url,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def save_html_snapshot(run_key: str, contest_name: str, problem_num: int, html: str) -> Path:
    settings = get_settings()
    output_dir = settings.raw_page_dir / run_key / contest_name
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / f"problem_{problem_num}.html"
    snapshot_path.write_text(html, encoding="utf-8")
    return snapshot_path


def write_run_manifest(run: ScrapeRun) -> Path:
    settings = get_settings()
    manifest = {
        "run_key": run.run_key,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "delay_seconds": run.delay_seconds,
        "contests_attempted": run.contests_attempted,
        "contests_completed": run.contests_completed,
        "problems_seen": run.problems_seen,
        "problems_created": run.problems_created,
        "problems_updated": run.problems_updated,
        "problems_failed": run.problems_failed,
        "arguments": run.args_json,
        "issues": run.issues_json,
    }
    manifest_path = settings.scrape_run_dir / f"{run.run_key}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def scrape_problem(
    session,
    run: ScrapeRun,
    *,
    contest_id: int,
    year: int,
    contest_type: str,
    problem_num: int,
    delay: float,
) -> None:
    contest_name = _contest_prefix(year, contest_type)
    problem_key = f"{contest_name}_P{problem_num}"
    url = problem_url(year, contest_type, problem_num)
    run.problems_seen += 1

    response, http_status, fetch_error = fetch_page(url, delay=delay)
    if response is None:
        run.problems_failed += 1
        append_issue(
            run.issues_json,
            level="error",
            problem_key=problem_key,
            url=url,
            message=fetch_error or "page_unavailable",
        )
        record_raw_page(
            session,
            {
                "scrape_run_id": run.id,
                "problem_key": problem_key,
                "url": url,
                "snapshot_path": None,
                "http_status": http_status,
                "extracted_problem_text": False,
                "extracted_solution_text": False,
                "parse_error": fetch_error,
            },
        )
        return

    snapshot_path = save_html_snapshot(run.run_key, contest_name, problem_num, response.text)
    parse_error: str | None = None
    extracted_problem_text = False
    extracted_solution_text = False

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        content_div = get_content_div(soup)
        if content_div is None:
            raise ValueError("missing_content_div")

        has_diagram = check_has_diagram(content_div)
        problem_text = extract_problem_text(content_div)
        solution_text = extract_solution_text(content_div)
        answer_choices = extract_answer_choices(content_div, problem_text)

        extracted_problem_text = bool(problem_text)
        extracted_solution_text = bool(solution_text)

        if not problem_text:
            raise ValueError("empty_problem_text")

        if not solution_text:
            append_issue(
                run.issues_json,
                level="warning",
                problem_key=problem_key,
                url=url,
                message="empty_solution_text",
            )

        estimated_minutes = round(max(count_words(problem_text) / 18.0, 2.0), 2)
        values = {
            "contest_id": contest_id,
            "problem_id": problem_key,
            "url": url,
            "year": year,
            "contest_type": contest_type,
            "problem_number": problem_num,
            "difficulty_estimate": difficulty_estimate(contest_type, problem_num),
            "problem_text": problem_text,
            "solution_text": solution_text,
            "has_diagram": has_diagram,
            "answer_choices": answer_choices or None,
            "problem_length_words": count_words(problem_text),
            "problem_length_chars": count_chars(problem_text),
            "solution_length_words": count_words(solution_text),
            "solution_length_chars": count_chars(solution_text),
            "problem_sentence_count": count_sentences(problem_text),
            "estimated_solve_minutes": estimated_minutes,
            "last_scraped_at": datetime.now(timezone.utc),
        }
        _, created = upsert_problem(session, values)
        if created:
            run.problems_created += 1
        else:
            run.problems_updated += 1
    except Exception as exc:
        parse_error = str(exc)
        run.problems_failed += 1
        append_issue(
            run.issues_json,
            level="error",
            problem_key=problem_key,
            url=url,
            message=parse_error,
        )
    finally:
        record_raw_page(
            session,
            {
                "scrape_run_id": run.id,
                "problem_key": problem_key,
                "url": url,
                "snapshot_path": str(snapshot_path),
                "http_status": http_status,
                "extracted_problem_text": extracted_problem_text,
                "extracted_solution_text": extracted_solution_text,
                "parse_error": parse_error,
            },
        )


def scrape_contest(session, run: ScrapeRun, *, year: int, contest_type: str, delay: float) -> None:
    contest_name = _contest_prefix(year, contest_type)
    num_problems = CONTEST_DEFS[contest_type]["problems"]
    contest = get_or_create_contest(
        session,
        contest_key=contest_name,
        contest_type=contest_type,
        year=year,
        variant=contest_variant(year, contest_type),
        num_problems=num_problems,
    )
    print(f"\nScraping {contest_name} ({num_problems} problems)...")

    for problem_num in range(1, num_problems + 1):
        problem_key = f"{contest_name}_P{problem_num}"
        sys.stdout.write(f"  [{problem_num:2d}/{num_problems}] {problem_key}...")
        sys.stdout.flush()
        before_created = run.problems_created
        before_updated = run.problems_updated
        before_failed = run.problems_failed

        scrape_problem(
            session,
            run,
            contest_id=contest.id,
            year=year,
            contest_type=contest_type,
            problem_num=problem_num,
            delay=delay,
        )
        session.commit()

        if run.problems_created > before_created:
            sys.stdout.write(" created\n")
        elif run.problems_updated > before_updated:
            sys.stdout.write(" updated\n")
        elif run.problems_failed > before_failed:
            sys.stdout.write(" failed\n")
        else:
            sys.stdout.write(" skipped\n")

    run.contests_completed += 1


def print_summary(session, run: ScrapeRun) -> None:
    total_problems = session.scalar(select(func.count(Problem.id))) or 0
    print("\n" + "=" * 60)
    print("TESTFORGE SCRAPE SUMMARY")
    print("=" * 60)
    print(f"Run key:           {run.run_key}")
    print(f"Status:            {run.status}")
    print(f"Contests complete: {run.contests_completed}/{run.contests_attempted}")
    print(f"Problems seen:     {run.problems_seen}")
    print(f"Problems created:  {run.problems_created}")
    print(f"Problems updated:  {run.problems_updated}")
    print(f"Problems failed:   {run.problems_failed}")
    print(f"Canonical rows:    {total_problems}")
    print("-" * 60)
    rows = session.execute(
        select(Problem.contest_type, func.count(Problem.id))
        .group_by(Problem.contest_type)
        .order_by(Problem.contest_type)
    ).all()
    for contest_type, count in rows:
        print(f"{contest_type:12s} {count:4d}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="TestForge AoPS problem scraper")
    parser.add_argument("--test", action="store_true", help="Scrape only 2023 AMC 10A")
    parser.add_argument("--contest", type=str, default=None, help="Contest filter, e.g. AMC_10A")
    parser.add_argument("--years", type=str, default=None, help="Year or year range, e.g. 2020-2024")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests in seconds")
    args = parser.parse_args()

    if args.test:
        contests = [(2023, "AMC_10A")]
    else:
        years = parse_years(args.years) if args.years else DEFAULT_YEARS
        contests = build_contest_list(args.contest, years)

    run_key = datetime.now(timezone.utc).strftime("scrape_%Y%m%dT%H%M%SZ")

    with session_scope() as session:
        run = ScrapeRun(
            run_key=run_key,
            status="running",
            delay_seconds=args.delay,
            contests_attempted=len(contests),
            contests_completed=0,
            problems_seen=0,
            problems_created=0,
            problems_updated=0,
            problems_failed=0,
            args_json=serialize_args(args),
            issues_json=[],
        )
        session.add(run)
        session.commit()

        print(f"Starting scrape run {run.run_key}")
        print(f"Database: {get_settings().database_url}")
        print(f"Contests: {len(contests)}")

        try:
            for year, contest_type in contests:
                scrape_contest(session, run, year=year, contest_type=contest_type, delay=args.delay)
            run.status = "completed"
        except KeyboardInterrupt:
            run.status = "interrupted"
            append_issue(run.issues_json, level="error", problem_key="run", url="", message="keyboard_interrupt")
            raise
        except Exception as exc:
            run.status = "failed"
            append_issue(run.issues_json, level="error", problem_key="run", url="", message=str(exc))
            raise
        finally:
            run.completed_at = datetime.now(timezone.utc)
            manifest_path = write_run_manifest(run)
            run.manifest_path = str(manifest_path)
            session.commit()
            print_summary(session, run)


if __name__ == "__main__":
    main()
