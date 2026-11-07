"""Loads configuration from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # project root
load_dotenv(ROOT / ".env")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_reader_url: str
    db_writer_url: str
    ollama_host: str
    ollama_model: str
    ollama_think: bool
    contracts_dir: Path
    log_dir: Path
    max_agent_steps: int
    slack_webhook_url: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    alert_email_from: str | None
    alert_email_to: str | None


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        db_reader_url=env("DB_READER_URL", "postgresql://agent_reader:reader_pw@localhost:5432/supplier_demo"),
        db_writer_url=env("DB_WRITER_URL", "postgresql://agent_writer:writer_pw@localhost:5432/supplier_demo"),
        ollama_host=env("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=env("OLLAMA_MODEL", "qwen3.5:4b"),
        ollama_think=_bool(env("OLLAMA_THINK"), False),
        contracts_dir=_path(env("CONTRACTS_DIR", "data/contracts")),
        log_dir=_path(env("LOG_DIR", "logs")),
        max_agent_steps=int(env("MAX_AGENT_STEPS", "12")),
        slack_webhook_url=env("SLACK_WEBHOOK_URL") or None,
        smtp_host=env("SMTP_HOST") or None,
        smtp_port=int(env("SMTP_PORT", "587")),
        smtp_user=env("SMTP_USER") or None,
        smtp_password=env("SMTP_PASSWORD") or None,
        alert_email_from=env("ALERT_EMAIL_FROM") or None,
        alert_email_to=env("ALERT_EMAIL_TO") or None,
    )


settings = load_settings()
