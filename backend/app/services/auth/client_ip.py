"""Resolve the client IP behind zero or more trusted reverse proxies."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from app.config import settings


def _normalize_ip(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    if text.count(":") == 1 and text.rsplit(":", 1)[0].count(":") == 0:
        host, _, port = text.rpartition(":")
        if port.isdigit():
            return host
    return text


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse ``TRUSTED_PROXY_IPS`` into networks.

    CIDR entries are accepted because a containerised reverse proxy has no
    stable address: traffic published through Docker arrives from whatever
    gateway address the bridge network happens to hold, so pinning exact
    IPs would silently stop trusting the proxy after a network recreate.
    Bare addresses stay supported and become single-host networks.
    """
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in settings.TRUSTED_PROXY_IPS or ["127.0.0.1", "::1"]:
        text = item.strip()
        if not text:
            continue
        try:
            networks.append(ipaddress.ip_network(_normalize_ip(text), strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _is_trusted_proxy(
    value: str, networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(addr in network for network in networks)


def resolve_client_ip(request: Request) -> str:
    """Return the best-effort client IP for the request.

    ``X-Forwarded-For`` is honoured only when the immediate peer is a
    configured trusted proxy; otherwise the header is ignored so clients
    cannot spoof their address.
    """
    peer = _normalize_ip(request.client.host if request.client else "")
    if not peer:
        return ""

    networks = _trusted_proxy_networks()
    if not _is_trusted_proxy(peer, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer

    hops = [_normalize_ip(part) for part in forwarded.split(",") if part.strip()]
    for hop in reversed(hops):
        if hop and not _is_trusted_proxy(hop, networks):
            return hop
    return hops[0] if hops else peer


def is_private_or_loopback(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


__all__ = ["is_private_or_loopback", "resolve_client_ip"]
