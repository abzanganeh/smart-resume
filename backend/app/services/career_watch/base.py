"""ATS adapter protocol."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.models.career_watch import WatchedCompany
from app.services.career_watch.types import ParsedJob


class AtsAdapter(Protocol):
    async def fetch_jobs(
        self,
        company: WatchedCompany,
        *,
        client: httpx.AsyncClient,
    ) -> list[ParsedJob]:
        """Return open roles for ``company``."""


__all__ = ["AtsAdapter"]
