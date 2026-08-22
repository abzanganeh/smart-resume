"""Client-IP trust boundary (OWASP A01/A09, LLM06 rate limiting).

Threat model
------------

Three controls key on "who is calling": the slowapi rate limits that bound
anonymous LLM spend, the IP an admin session is bound to, and the address
written into audit rows. All three are only as good as the function that
decides a request's address, and that function sits on a trust boundary
with two failure modes, both of which have shipped in this codebase:

1. **Too trusting.** Reading ``X-Forwarded-For`` without checking who the
   immediate peer is lets any caller name its own address. Rate limits
   become bypassable one header at a time, and an admin session's IP
   binding is pinned to a value the attacker picked.

2. **Too suspicious.** Reading the socket peer and ignoring the header
   makes every visitor behind the reverse proxy look like the proxy. That
   is worse than no limit: a handful of logins would 429 the entire site,
   and audit rows would record a single meaningless address.

``resolve_client_ip`` is the one place allowed to make this decision.
The tests below pin its behaviour at both edges and assert that no
request handler quietly grows a second, weaker copy of it.

CI note
-------

Nothing here needs Postgres, so the whole module runs anywhere.
"""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import Mock

import pytest

from app.config import settings
from app.services.auth.client_ip import resolve_client_ip

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"

# The proxy sits inside a Docker bridge range in every containerised
# deployment, so CIDR trust is the realistic configuration to test.
DOCKER_BRIDGE = ["172.16.0.0/12", "127.0.0.1", "::1"]


def _request(*, peer: str, xff: str | None = None) -> Mock:
    request = Mock()
    request.client = Mock(host=peer)
    request.headers = {"x-forwarded-for": xff} if xff else {}
    return request


@pytest.fixture()
def trust_docker_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", DOCKER_BRIDGE)


# ---------------------------------------------------------------------------
# 1. Too trusting — a client must not be able to name its own address
# ---------------------------------------------------------------------------


def test_untrusted_peer_cannot_spoof_its_address(
    trust_docker_bridge: None,
) -> None:
    """The header is ignored entirely when the peer is not a proxy.

    This is the case that matters for a directly reachable backend: the
    compose stack publishes port 8001 on the host, so anything that can
    route to the VM can attempt this.
    """
    ip = resolve_client_ip(
        _request(peer="203.0.113.10", xff="8.8.8.8, 198.51.100.20")
    )
    assert ip == "203.0.113.10"


def test_spoofed_hops_behind_a_trusted_proxy_do_not_win(
    trust_docker_bridge: None,
) -> None:
    """A client-supplied hop is prepended, not appended, so read from the right.

    The proxy appends the peer it saw. Taking the *first* hop would return
    whatever the client wrote; taking the last untrusted one returns the
    address the proxy actually observed.
    """
    ip = resolve_client_ip(
        _request(peer="172.18.0.1", xff="8.8.8.8, 203.0.113.10")
    )
    assert ip == "203.0.113.10"


def test_an_all_trusted_chain_never_returns_empty(
    trust_docker_bridge: None,
) -> None:
    """A degenerate chain must still yield a key, or every caller shares one.

    slowapi buckets on the returned string, so an empty result would put
    every such request into a single counter.
    """
    ip = resolve_client_ip(_request(peer="172.18.0.1", xff="127.0.0.1"))
    assert ip


# ---------------------------------------------------------------------------
# 2. Too suspicious — the proxy must not become everyone's identity
# ---------------------------------------------------------------------------


def test_cidr_trust_resolves_the_real_client(trust_docker_bridge: None) -> None:
    """A containerised proxy has no stable address, so CIDR must work.

    Docker assigns the bridge gateway on network create. Pinning exact
    IPs means the proxy silently stops being trusted after a recreate,
    at which point every visitor collapses onto the gateway address.
    """
    ip = resolve_client_ip(
        _request(peer="172.18.0.1", xff="198.51.100.20, 172.18.0.1")
    )
    assert ip == "198.51.100.20"


def test_two_visitors_behind_the_proxy_get_distinct_keys(
    trust_docker_bridge: None,
) -> None:
    """The property every rate limit depends on.

    If these collapsed to one value, ``login`` at 10/minute would lock
    out the whole site once eleven people signed in.
    """
    first = resolve_client_ip(_request(peer="172.18.0.1", xff="198.51.100.20"))
    second = resolve_client_ip(_request(peer="172.18.0.1", xff="203.0.113.77"))
    assert first != second


def test_malformed_trust_entries_do_not_widen_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in the env var must fail closed, not trust everything."""
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["not-an-ip", "127.0.0.1"])
    ip = resolve_client_ip(_request(peer="203.0.113.10", xff="8.8.8.8"))
    assert ip == "203.0.113.10"


# ---------------------------------------------------------------------------
# 3. No handler may grow a second, weaker copy of this decision
# ---------------------------------------------------------------------------


def _docstring_constants(tree: ast.AST) -> set[int]:
    """Ids of ``Constant`` nodes that are docstrings rather than code."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def _modules_reading_forwarded_for() -> list[str]:
    """Modules with the header name as a live string literal.

    Matching on raw text would flag prose — this module and ``limiter.py``
    both discuss the header at length — so the scan parses each file and
    skips docstrings, leaving only literals the code actually evaluates.
    """
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "client_ip.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_constants(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.lower() == "x-forwarded-for"
                and id(node) not in docstrings
            ):
                offenders.append(str(path.relative_to(APP_DIR)))
                break
    return offenders


def test_only_the_resolver_reads_the_forwarded_header() -> None:
    """``admin.py``, ``admin_auth.py`` and ``extension_auth.py`` each had their own.

    Two took the first hop unconditionally (spoofable) and one ignored the
    header entirely (proxy-blind). Centralising is the fix; this test is
    what keeps the next handler from reintroducing a fourth variant.
    """
    offenders = _modules_reading_forwarded_for()
    assert not offenders, (
        "these modules parse X-Forwarded-For directly instead of calling "
        f"resolve_client_ip(): {offenders}"
    )


def _modules_reading_the_socket_peer() -> list[str]:
    """Modules evaluating ``request.client.host`` outside the resolver."""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "client_ip.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "host"
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "client"
            ):
                offenders.append(str(path.relative_to(APP_DIR)))
                break
    return offenders


def test_no_handler_reads_the_socket_peer_directly() -> None:
    """The proxy-blind half of the bug, which the header scan cannot see.

    Nine call sites used to read the peer and ignore ``X-Forwarded-For``
    entirely: admin audit rows, the refund fraud signal, and the Flint
    handoff redemption limit — which meant that limit was one bucket of
    ten per minute for every visitor rather than per client.
    """
    offenders = _modules_reading_the_socket_peer()
    assert not offenders, (
        "these modules read request.client.host instead of calling "
        f"resolve_client_ip(), so they see the proxy: {offenders}"
    )


def test_the_rate_limiter_does_not_key_on_the_socket_peer() -> None:
    """slowapi's default key function is wrong for a proxied deployment.

    ``get_remote_address`` returns the peer, which is the proxy. It may
    only appear as a fallback for requests that have no client at all,
    never as the limiter's ``key_func``.
    """
    source = (APP_DIR / "limiter.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "Limiter":
            continue
        key_func = next(
            (kw.value for kw in node.keywords if kw.arg == "key_func"), None
        )
        assert isinstance(key_func, ast.Name), (
            "Limiter(key_func=...) must name a module-level function"
        )
        assert key_func.id != "get_remote_address", (
            "the limiter must not key on the socket peer; behind the reverse "
            "proxy that is one shared bucket for every visitor"
        )
        return
    pytest.fail("no Limiter(...) construction found in app/limiter.py")
