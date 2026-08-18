#!/usr/bin/env python3
"""Generate TalioCV global job corpus seed JSON (500 US tech employers).

Usage (from ``backend/``):

  uv run python scripts/generate_job_corpus_seed.py
  uv run python scripts/generate_job_corpus_seed.py --skip-verify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.services.career_watch.job_corpus_seed import (
    TIER_TARGETS,
    TOTAL_TARGET,
    careers_page_url,
    validate_seed_records,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "job_corpus" / "seed_500.json"

# Ordered tier-1 slugs (first 100 verified matches become tier 1).
TIER1_SLUGS: tuple[str, ...] = (
    "stripe", "openai", "airbnb", "databricks", "coinbase", "figma", "discord",
    "roblox", "reddit", "lyft", "doordash", "instacart", "pinterest", "dropbox",
    "twilio", "block", "asana", "anthropic", "mongodb", "cloudflare", "datadog",
    "brex", "chime", "gusto", "scale-ai", "affirm", "checkr", "flexport", "gitlab",
    "hubspot", "intercom", "klaviyo", "netlify", "okta", "pagerduty", "toast",
    "vercel", "cockroach-labs", "planetscale", "mixpanel", "launchdarkly",
    "amplitude", "nuro", "fivetran", "spotify", "zscaler", "elastic", "notion",
    "linear", "ramp", "mercury", "posthog", "deel", "hightouch", "supabase", "neon",
    "confluent", "temporal", "snowflake", "sentry", "palantir", "plaid", "anduril",
    "spacex", "neuralink", "xai", "waymo", "weave", "webflow", "tailscale", "replit",
    "robinhood", "rubrik", "samsara", "verkada", "oscar-health", "lucid-motors",
    "lucid", "airtable", "sofi", "stripe", "coinbase", "databricks", "figma",
    "discord", "roblox", "reddit", "lyft", "instacart", "pinterest", "dropbox",
    "twilio", "block", "asana", "anthropic", "mongodb", "cloudflare", "datadog",
    "brex", "chime", "gusto", "scale-ai", "affirm", "checkr", "flexport", "gitlab",
)

SLUG_OVERRIDES: dict[str, tuple[str, str]] = {
    "andurilindustries": ("anduril", "Anduril"),
    "doordashusa": ("doordash", "DoorDash"),
    "temporaltechnologies": ("temporal", "Temporal"),
    "lucidsoftware": ("lucid", "Lucid"),
    "lucidmotors": ("lucid-motors", "Lucid Motors"),
    "scaleai": ("scale-ai", "Scale AI"),
    "getscale": ("scale-ai", "Scale AI"),
    "cockroachlabs": ("cockroach-labs", "Cockroach Labs"),
    "grafanalabs": ("grafana", "Grafana Labs"),
    "layerzerolabs": ("layerzero", "LayerZero"),
    "weavehealth": ("weave-health", "Weave"),
    "moderntreasury": ("modern-treasury", "Modern Treasury"),
    "generalatlantic": ("general-atlantic", "General Atlantic"),
    "saasgroup": ("saas-group", "SaaS Group"),
    "insightpartners": ("insight-partners", "Insight Partners"),
    "khoslaventures": ("khosla-ventures", "Khosla Ventures"),
    "indexventures": ("index-ventures", "Index Ventures"),
}

DISPLAY_NAMES: dict[str, str] = {
    "a16z": "a16z",
    "xai": "xAI",
    "n26": "N26",
    "1password": "1Password",
    "openai": "OpenAI",
}

ATS_ORDER = {"greenhouse": 0, "ashby": 1, "lever": 2}

# Verified public board tokens (union of API probes).
GREENHOUSE_TOKENS: tuple[str, ...] = tuple(
    dict.fromkeys(
        """
        AndurilIndustries acuitymd affirm airbnb airtable algolia alloy alphasense amount
        amplitude anaplan apollo appian applovin asana attentive axon betterhelp bigid
        billcom blend block bird braze brex calm carta checkr chime circleci clara clear
        cloudflare cloverhealth cockroachlabs coinbase collectivehealth contentful coreweave
        coursera current databricks datadog diligent discord doordashusa dropbox duolingo
        earnin elastic epicgames esri everlaw exabeam extend faire fairmarkit falconx fastly
        figma fivetran flatironhealth flexport formlabs forward found fox genius getscale ghost
        gitlab glossier gocardless grafanalabs greenhouse grin gusto guild hellofresh hive
        housecall hubspot humaninterest idme incode instacart intercom iterable jfrog justworks
        khanacademy kickstarter klaviyo knowbe4 lattice launchdarkly layerzerolabs liftoff lob
        lucidmotors lucidsoftware lyft magicleap mark43 marqeta medium metronome mixpanel mobility
        modernhealth mongodb monzo motive motional n26 netlify neuralink newsela nextdoor nuro
        okta onetrust orchard oscar pagerduty pandadoc payit pendo philo pinterest planetscale
        platformscience postman postscript pubmatic purestorage qualtrics relativity robinhood
        roblox rubrik samsara scaleai seatgeek sendbird sigmacomputing singlestore smartsheet sofi
        solarwinds solutions spacex spothero squarespace stackadapt starburst stripe sumologic
        super superset taboola tailscale taketwo tanium tastytrade taxbit temporaltechnologies
        thinkific tide toast trumid trustpilot twilio typeface udacity udemy unqork upkeep upstart
        valimail vercel verkada vestwell watershed waymo weave weavehealth webflow wing workato
        workboard workstream xai xometry yext yotpo youcom ziprecruiter zocdoc zoominfo zscaler
        zuora adyen amperity anthropic astranis atbay athena aviatrix biofourmis bitgo bitwarden
        bloomreach bluestone bold branch brandwatch bringg buildkite butlr calendly capitalize
        captify careem caribou cavnue ceros chargepoint classpass cleo clicktherapeutics cloudbeds
        collibra colorado comet corelight cresta cribl crisp crossbeam dataiku deepmind designpickle
        devrev dialpad digimarc digit dispatch doc doppel ebanx edison effectual elite elo emerge
        enboarder ethic ethos eudia eve ever evergreen excel exiger explore fellow fetch fieldwire
        figure finance find firsthand firstprinciples five9 flash fleet flex flexe flip flourish
        focused foundry fourkites fruitful future a16z fireblocks founders general gemini paradigm
        phantomai ripple remote 6sense abacus abcellera accela accuweather affinidi airspace altium
        amwell saasgroup generalatlantic altruist alloy calendly carta ghost medium paradigm remote
        """.split()
    )
)

ASHBY_TOKENS: tuple[str, ...] = tuple(
    dict.fromkeys(
        """
        1password acorns airbyte airtable aleph alchemy amber amplitude ankorstore anyscale aptible
        arlo astra benchling betterup bolt brightwheel buffer capsule carbonhealth catch cedar
        clickup cohere cointracker commure conductor confluent crunchbase dandy deel envoy extend
        found fullstory gainsight guild hightouch hyperscience illumio influxdata insitro iterable
        kustomer launchdarkly lemonade level liftoff linear loom maintainx marqeta mercury miro mural
        mux neon niantic notable notion nutanix nylas openai opensea orchard overjet patreon
        perplexity philo plaid point posthog purestorage qualtrics ramp real reddit redis render
        replicant replit runway sentry sequoia skydio snackpass snowflake sondermind spekit stedi
        strava substack supabase superhuman synthetic talkdesk temporal thumbtack tilt tonal traba
        unify unit valon vanta vercel verkada voxel watershed weave whoop wistia wiz wrapbook zapier
        zefr zip backbone backmarket base baseten benepass bestow bio blockdaemon blockstream bold
        boost braintrust bubble build cadre canopy capchase cardless chalice chariot clarify
        clipboard cloudkitchens clubhouse compound crusoe cryptio curri deepgram deepl deepnote
        deepsource demandbase duffel dune eagle eightsleep electric elevenlabs elliptic ello
        emergence eon equip everbridge evervault evolve exa factory fig fin finch firstround
        firststreet flatfile float flock flowhub flux foam focal folio foresight forma formal formula
        fort foxglove freewill freshpaint frontier fulcrum fundamental fuse insightpartners jump
        kraken ledger lightspeed moderntreasury phantom uniswap cohere opensea sentry airbyte
        benchling khoslaventures fin
        """.split()
    )
)

LEVER_TOKENS: tuple[str, ...] = (
    "spotify", "plaid", "neon", "alltrails", "anchorage", "gopuff", "highspot",
    "indexventures", "maxmind", "metabase", "outreach", "palantir", "peerspace",
    "pipedrive", "prosper", "ro", "zoox",
)


@dataclass
class GenerationResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)
    tier_counts: dict[int, int] = field(default_factory=dict)


def slug_and_name(token: str) -> tuple[str, str]:
    key = token.lower()
    if key in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[key]
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    name = DISPLAY_NAMES.get(slug, slug.replace("-", " ").title())
    return slug, name


async def verify_token(ats_type: str, token: str) -> bool:
    if ats_type == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    elif ats_type == "lever":
        url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    else:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(url)
            return response.status_code == 200
        except httpx.HTTPError:
            return False


async def build_verified_pool(*, skip_verify: bool) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return slug-keyed verified companies and omitted candidate labels."""
    sem = asyncio.Semaphore(40)
    verified_raw: list[tuple[str, str]] = []
    omitted: list[str] = []

    async def probe(ats_type: str, token: str) -> None:
        label = f"{token} ({ats_type})"
        if skip_verify:
            verified_raw.append((ats_type, token))
            return
        async with sem:
            if await verify_token(ats_type, token):
                verified_raw.append((ats_type, token))
            else:
                omitted.append(label)

    tasks = [probe("greenhouse", token) for token in GREENHOUSE_TOKENS]
    tasks += [probe("ashby", token) for token in ASHBY_TOKENS]
    tasks += [probe("lever", token) for token in LEVER_TOKENS]
    await asyncio.gather(*tasks)

    by_slug: dict[str, dict[str, Any]] = {}
    for ats_type, token in verified_raw:
        slug, name = slug_and_name(token)
        existing = by_slug.get(slug)
        if existing is None or ATS_ORDER[ats_type] < ATS_ORDER[existing["ats_type"]]:
            by_slug[slug] = {
                "name": name,
                "slug": slug,
                "ats_type": ats_type,
                "ats_board_token": token,
            }
    return by_slug, omitted


def select_seed_records(pool: dict[str, dict[str, Any]]) -> GenerationResult:
    """Select exactly 500 rows with tier distribution 100/175/225."""
    if len(pool) < TOTAL_TARGET:
        raise RuntimeError(
            f"only {len(pool)} verified unique companies available; need {TOTAL_TARGET}"
        )

    tier1_used: set[str] = set()
    tier1: list[dict[str, Any]] = []
    tier2: list[dict[str, Any]] = []
    tier3: list[dict[str, Any]] = []

    # Tier 1: explicit priority order first, then remaining by slug.
    priority = [pool[s] for s in TIER1_SLUGS if s in pool]
    remaining = sorted(
        (row for slug, row in pool.items() if slug not in TIER1_SLUGS),
        key=lambda row: row["slug"],
    )
    ordered = priority + remaining

    for row in ordered:
        slug = row["slug"]
        if slug in tier1_used:
            continue
        if len(tier1) < TIER_TARGETS[1]:
            tier1_used.add(slug)
            tier1.append({**row, "poll_priority_tier": 1})
        elif len(tier2) < TIER_TARGETS[2]:
            tier2.append({**row, "poll_priority_tier": 2})
        elif len(tier3) < TIER_TARGETS[3]:
            tier3.append({**row, "poll_priority_tier": 3})
        else:
            break

    records = tier1 + tier2 + tier3
    if len(records) != TOTAL_TARGET:
        raise RuntimeError(
            f"selected {len(records)} rows; expected {TOTAL_TARGET} "
            f"(tier1={len(tier1)}, tier2={len(tier2)}, tier3={len(tier3)})"
        )

    for row in records:
        row["careers_page_url"] = careers_page_url(
            row["ats_type"], row["ats_board_token"]
        )

    counts = {1: len(tier1), 2: len(tier2), 3: len(tier3)}
    omitted_overflow = sorted(
        slug
        for slug in pool
        if slug not in {row["slug"] for row in records}
    )
    return GenerationResult(
        records=records,
        omitted=omitted_overflow,
        tier_counts=counts,
    )


async def generate_seed(*, skip_verify: bool) -> GenerationResult:
    pool, verify_omitted = await build_verified_pool(skip_verify=skip_verify)
    result = select_seed_records(pool)
    result.omitted = verify_omitted + [
        f"{slug} (verified overflow)" for slug in result.omitted
    ]
    validate_seed_records(result.records)
    return result


def write_seed(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip live ATS token verification (not recommended).",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    result = await generate_seed(skip_verify=args.skip_verify)
    write_seed(args.output, result.records)

    print(f"Wrote {len(result.records)} rows to {args.output}")
    print(f"Tier counts: tier1={result.tier_counts[1]}, tier2={result.tier_counts[2]}, tier3={result.tier_counts[3]}")
    if result.omitted:
        print(f"Omitted ({len(result.omitted)}) due to token uncertainty or overflow:")
        for item in result.omitted:
            print(f"  - {item}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
