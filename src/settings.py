from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    environment: str
    export_dir: Path
    model_dir: Path
    raw_page_dir: Path
    scrape_run_dir: Path

    def ensure_runtime_dirs(self) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.raw_page_dir.mkdir(parents=True, exist_ok=True)
        self.scrape_run_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/testforge",
    )
    settings = Settings(
        database_url=database_url,
        environment=os.getenv("TESTFORGE_ENV", "development"),
        export_dir=(PROJECT_ROOT / os.getenv("TESTFORGE_EXPORT_DIR", "data/exports")).resolve(),
        model_dir=(PROJECT_ROOT / os.getenv("TESTFORGE_MODEL_DIR", "data/models")).resolve(),
        raw_page_dir=(PROJECT_ROOT / os.getenv("TESTFORGE_RAW_PAGE_DIR", "data/raw_pages")).resolve(),
        scrape_run_dir=(PROJECT_ROOT / os.getenv("TESTFORGE_SCRAPE_RUN_DIR", "data/scrape_runs")).resolve(),
    )
    settings.ensure_runtime_dirs()
    return settings
