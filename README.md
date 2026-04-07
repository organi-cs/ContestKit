# ContestKit

TestForge is an automated math competition assembly system that combines:

- `PostgreSQL` as the source of truth for scraped problems, features, model runs, and assembled papers
- `DuckDB` and `Parquet` for reproducible ML snapshots and notebook workflows
- `FastAPI` for serving curated data and optimizer outputs
- `PuLP` for integer-programming-based paper assembly

## Quick Start

1. Create a PostgreSQL database and copy `.env.example` to `.env`.
2. Install dependencies:

```bash
pip install -e .
```

3. Run the first migration:

```bash
alembic upgrade head
```

4. Scrape problems into the database:

```bash
python src/scraper/scraper.py --test
```

5. Generate versioned features and export a Parquet training snapshot:

```bash
python src/ml/generate_features.py --feature-version baseline_v1
python src/ml/export_training_snapshot.py --feature-version baseline_v1
```

6. Train a baseline model and write predictions back into PostgreSQL:

```bash
python src/ml/train.py --feature-version baseline_v1
```

7. Start the API:

```bash
uvicorn src.api.main:app --reload
```

## Data Layout

- `data/raw_pages/`: HTML snapshots fetched during scraping
- `data/scrape_runs/`: JSON manifests for each scrape run
- `data/exports/`: Parquet training snapshots and split manifests

## Main Commands

```bash
python src/scraper/scraper.py --contest AMC_10A --years 2023-2024
python src/ml/generate_features.py --feature-version baseline_v1
python src/ml/export_training_snapshot.py --feature-version baseline_v1
python src/ml/train.py --feature-version baseline_v1
python src/optimizer/assemble.py --name "demo-paper" --n-problems 15 --time-limit 90
```
