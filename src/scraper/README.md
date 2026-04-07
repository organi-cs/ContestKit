# TestForge Scraper

The scraper now writes into PostgreSQL instead of treating `data/problems.csv` as the canonical dataset.

## What Gets Written

- `scrape_runs`: one row per scraper execution with counts, args, and issue logs
- `problems`: canonical problem rows keyed by `problem_id`
- `contests`: normalized contest metadata, including the 2021 Fall variants
- `raw_pages`: one row per fetched page, linked to an HTML snapshot on disk

## Disk Snapshots

- `data/raw_pages/<run_key>/<contest>/problem_<n>.html`
- `data/scrape_runs/<run_key>.json`

These snapshots make the scrape reproducible even if the upstream page changes later.

## Usage

```bash
# Quick test: 2023 AMC 10A only
python src/scraper/scraper.py --test

# Full scrape
python src/scraper/scraper.py

# Filter by contest type
python src/scraper/scraper.py --contest AMC_10A

# Filter by year range
python src/scraper/scraper.py --years 2020-2024
```

## Guarantees

- Re-running the scraper is idempotent: rows are upserted by `problem_id`
- Missing `problem_text`, empty `solution_text`, and fetch or parse errors are logged to the scrape run
- Contest keys remain canonical, including `2021_Fall_*` variants
