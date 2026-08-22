"""Resolve ATS adapters by type."""

from __future__ import annotations

import httpx

from app.models.career_watch import CareerAtsType, WatchedCompany
from app.services.career_watch.ashby import AshbyAdapter
from app.services.career_watch.bamboohr import BambooHrAdapter
from app.services.career_watch.base import AtsAdapter
from app.services.career_watch.breezy import BreezyAdapter
from app.services.career_watch.generic_html import GenericHtmlAdapter
from app.services.career_watch.greenhouse import GreenhouseAdapter
from app.services.career_watch.lever import LeverAdapter
from app.services.career_watch.personio import PersonioAdapter
from app.services.career_watch.recruitee import RecruiteeAdapter
from app.services.career_watch.smartrecruiters import SmartRecruitersAdapter
from app.services.career_watch.types import ParsedJob
from app.services.career_watch.workable import WorkableAdapter
from app.services.career_watch.workday import WorkdayAdapter

_ADAPTERS: dict[CareerAtsType, AtsAdapter] = {
    CareerAtsType.greenhouse: GreenhouseAdapter(),
    CareerAtsType.lever: LeverAdapter(),
    CareerAtsType.ashby: AshbyAdapter(),
    CareerAtsType.workday: WorkdayAdapter(),
    CareerAtsType.smartrecruiters: SmartRecruitersAdapter(),
    CareerAtsType.workable: WorkableAdapter(),
    CareerAtsType.recruitee: RecruiteeAdapter(),
    CareerAtsType.breezy: BreezyAdapter(),
    CareerAtsType.personio: PersonioAdapter(),
    CareerAtsType.bamboohr: BambooHrAdapter(),
    CareerAtsType.generic_html: GenericHtmlAdapter(),
    CareerAtsType.unknown: GenericHtmlAdapter(),
}


def get_adapter(ats_type: CareerAtsType) -> AtsAdapter:
    return _ADAPTERS.get(ats_type, GenericHtmlAdapter())


async def fetch_company_jobs(
    company: WatchedCompany,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[ParsedJob]:
    adapter = get_adapter(company.ats_type)
    if client is None:
        async with httpx.AsyncClient() as owned:
            return await adapter.fetch_jobs(company, client=owned)
    return await adapter.fetch_jobs(company, client=client)


__all__ = ["fetch_company_jobs", "get_adapter"]
