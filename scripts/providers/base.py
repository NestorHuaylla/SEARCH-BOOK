"""Provider interface and resilient HTTP helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.config import Settings


class ProviderError(RuntimeError):
    """A provider failed without invalidating other provider results."""


class BaseProvider(ABC):
    """Contract implemented by every external catalog provider."""

    name = "Base"

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.session = session or self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": self.settings.user_agent,
            }
        )
        return session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.settings.request_timeout)
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise ProviderError(f"{self.name}: request failed: {exc}") from exc

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name}: invalid JSON response") from exc

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Fetch and normalize this provider's current catalog slice."""

