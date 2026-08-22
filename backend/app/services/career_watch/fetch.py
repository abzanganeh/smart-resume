"""HTTP fetch helpers for Career Watch pollers."""

from __future__ import annotations

import time
from collections import defaultdict

import httpx
import structlog

log = structlog.get_logger("career_watch.fetch")

CAREER_WATCH_USER_AGENT = "FlintResume-CareerWatch/1.0 (+https://flintresume.com)"
FETCH_TIMEOUT_SECONDS = 10.0
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 300

_failures: dict[str, list[float]] = defaultdict(list)


class FetchCircuitOpenError(RuntimeError):
    """Raised when a host exceeded consecutive fetch failures."""


class CareerWatchFetchError(RuntimeError):
    """Non-retryable fetch failure."""


def _host_key(url: str) -> str:
    return httpx.URL(url).host or url


def _circuit_open(host: str) -> bool:
    now = time.monotonic()
    recent = [
        ts
        for ts in _failures[host]
        if now - ts <= CIRCUIT_COOLDOWN_SECONDS
    ]
    _failures[host] = recent
    return len(recent) >= CIRCUIT_FAILURE_THRESHOLD


def reset_fetch_circuits_for_tests() -> None:
    _failures.clear()


def record_fetch_failure(url: str) -> None:
    _failures[_host_key(url)].append(time.monotonic())


def record_fetch_success(url: str) -> None:
    _failures.pop(_host_key(url), None)


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    accept: str = "*/*",
) -> str:
    host = _host_key(url)
    if _circuit_open(host):
        raise FetchCircuitOpenError(f"circuit open for {host}")

    try:
        response = await client.get(
            url,
            headers={
                "User-Agent": CAREER_WATCH_USER_AGENT,
                "Accept": accept,
            },
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        record_fetch_failure(url)
        raise CareerWatchFetchError(str(exc)) from exc

    record_fetch_success(url)
    return response.text


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> object:
    host = _host_key(url)
    if _circuit_open(host):
        raise FetchCircuitOpenError(f"circuit open for {host}")

    request_headers = {
        "User-Agent": CAREER_WATCH_USER_AGENT,
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    try:
        response = await client.get(
            url,
            headers=request_headers,
            params=params,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        record_fetch_failure(url)
        raise CareerWatchFetchError(str(exc)) from exc

    record_fetch_success(url)
    return response.json()


__all__ = [
    "CAREER_WATCH_USER_AGENT",
    "CareerWatchFetchError",
    "FETCH_TIMEOUT_SECONDS",
    "FetchCircuitOpenError",
    "fetch_json",
    "fetch_text",
    "record_fetch_failure",
    "record_fetch_success",
    "reset_fetch_circuits_for_tests",
]
