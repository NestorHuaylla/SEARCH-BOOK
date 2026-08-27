"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SHARDS_DIR = DATA_DIR / "shards"


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    """Settings shared by the synchronizer and providers."""

    contact_email: str = os.getenv("OPENBOOK_CONTACT_EMAIL", "")
    request_timeout: int = _positive_int("OPENBOOK_REQUEST_TIMEOUT", 30)
    shard_size: int = _positive_int("OPENBOOK_SHARD_SIZE", 1000)
    inline_catalog_limit: int = _positive_int("OPENBOOK_INLINE_CATALOG_LIMIT", 5000)
    openalex_api_key: str = os.getenv("OPENALEX_API_KEY", "")
    root_dir: Path = ROOT_DIR

    @property
    def user_agent(self) -> str:
        contact = self.contact_email.strip()
        suffix = f" ({contact})" if contact else ""
        return f"OpenBookSearch/1.0{suffix}"
