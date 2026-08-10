"""Конфигурация. Всё через окружение, ничего в коде."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT.parent / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str
    admin_id: int | None = None

    # LLM. По умолчанию Anthropic; для OpenAI-совместимого провайдера
    # достаточно задать llm_base_url и llm_api_key.
    llm_provider: str = "anthropic"          # anthropic | openai
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "claude-sonnet-5"
    llm_max_tokens: int = 700
    llm_timeout: float = 60.0

    persona: str = "kolodets"
    personas_dir: Path = ROOT / "personas"
    laws_path: Path = ROOT.parent / "docs" / "LAWS.md"

    # Railway подставляет DATABASE_URL сам, когда в проект добавлен Postgres.
    database_url: str = ""
    db_path: Path = ROOT.parent / "data" / "pdp.sqlite3"
    history_turns: int = 12          # сколько реплик уходит в контекст
    dossier_every: int = 20          # раз во сколько реплик пересобирать досье
    rate_limit_seconds: float = 2.0


try:
    settings = Settings()  # type: ignore[call-arg]
except Exception as exc:  # noqa: BLE001 — новичку нужен понятный текст, а не трейсбек
    raise SystemExit(
        "Не хватает настроек.\n"
        "Скопируй .env.example в .env и заполни BOT_TOKEN и LLM_API_KEY.\n"
        f"Подробности: {exc}"
    ) from exc
