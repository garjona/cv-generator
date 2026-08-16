from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    # Prefer .env.local for developer-specific settings, but do not override
    # already exported process env vars.
    load_dotenv(".env.local", override=False)
    load_dotenv(".env", override=False)


@dataclass(slots=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    enable_llm: bool
    database_path: Path
    logs_dir: Path
    default_output_dir: Path
    default_template_style: str
    openai_timeout_seconds: int


def load_settings() -> Settings:
    _load_dotenv_if_available()
    raw_key = os.getenv("OPENAI_API_KEY")
    cleaned_key = raw_key.strip().strip('"').strip("'") if raw_key else None
    return Settings(
        openai_api_key=cleaned_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        enable_llm=os.getenv("ENABLE_LLM", "false").strip().lower() in {"1", "true", "yes", "on"},
        database_path=Path(os.getenv("CVGEN_DB_PATH", "data/master_profile.db")),
        logs_dir=Path(os.getenv("CVGEN_LOGS_DIR", "logs")),
        default_output_dir=Path(os.getenv("CVGEN_OUTPUT_DIR", "outputs")),
        default_template_style=os.getenv("CVGEN_DEFAULT_TEMPLATE", "html_ats"),
        openai_timeout_seconds=int(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
    )
