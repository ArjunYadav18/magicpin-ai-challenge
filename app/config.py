from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings:
    def __init__(self) -> None:
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8080"))
        self.team_name: str = os.getenv("TEAM_NAME", "Vera Local")
        self.team_members: list[str] = _csv(os.getenv("TEAM_MEMBERS", "You"))
        self.contact_email: str = os.getenv("CONTACT_EMAIL", "you@example.com")
        self.bot_version: str = os.getenv("BOT_VERSION", "1.0.0")
        self.submitted_at: str = os.getenv("SUBMITTED_AT", "2026-04-26T08:00:00Z")
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower()
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
        self.llm_model: str = os.getenv("LLM_MODEL", "").strip()
        self.llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
        self.max_actions_per_tick: int = int(os.getenv("MAX_ACTIONS_PER_TICK", "8"))
        self.send_score_threshold: float = float(os.getenv("SEND_SCORE_THRESHOLD", "0.42"))

    @property
    def llm_enabled(self) -> bool:
        if not self.llm_provider:
            return False
        if self.llm_provider == "ollama":
            return True
        return bool(self.llm_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
