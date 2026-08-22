#!/usr/bin/env python3
"""Build candidate slug list for corpus expansion probes."""

from __future__ import annotations

import json
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = BACKEND_ROOT / "data" / "job_corpus" / "candidate_slugs.json"
SEED_500 = BACKEND_ROOT / "data" / "job_corpus" / "seed_500.json"

# Additional public-company slug guesses (lower-case, hyphenated).
EXTRA_SLUGS: tuple[str, ...] = tuple(
    dict.fromkeys(
        slug
        for raw in """
        apple microsoft amazon google alphabet meta netflix tesla adobe salesforce
        oracle intel amd nvidia qualcomm broadcom ibm cisco dell hp hp-enterprise
        uber lyft snap pinterest twitter x corp square block shopify spotify
        zoom slack atlassian monday freshworks zendesk servicenow workday sap
        paypal visa mastercard american-express capital-one chase wells-fargo
        goldman-sachs morgan-stanley jpmorgan citi bank-of-america
        walmart target costco home-depot lowes best-buy kroger albertsons
        nike adidas lululemon under-armour gap old-navy
        boeing lockheed raytheon northrop general-dynamics
        johnson-and-johnson pfizer merck abbvie bristol-myers moderna
        chevron exxon shell bp conoco
        disney comcast warner-bros paramount
        ford gm stellantis rivian lucid-motors
        delta united american-airlines southwest
        marriott hilton hyatt airbnb booking
        procter-gamble unilever colgate kraft heinz
        3m caterpillar deere honeywell ge siemens
        accenture deloitte kpmg pwc ey
        mckinsey bcg bain
        canva figma notion airtable monday
        rippling justworks gusto deel remote oyster
        retool airtable coda clickup asana
        hashicorp terraform docker confluent databricks snowflake
        mongodb redis elastic datadog new-relic splunk
        crowdstrike palo-alto-networks zscaler fortinet
        okta auth0 duo ping-identity
        twilio sendgrid mailchimp hubspot marketo
        stripe adyen square block affirm klarna
        robinhood coinbase kraken gemini
        epic-games unity roblox take-two ea activision
        riot-games blizzard bungie
        spacex blue-origin rocket-lab
        anduril shield-ai skydio
        openai anthropic cohere huggingface stability-ai
        scale-ai labelbox weights-and-biases
        waymo cruise aurora zoox nuro
        flexport convoy project44
        instacart go-puff gopuff
        doordash grubhub uber-eats
        chime current varo
        brex ramp mercury arc
        plaid finix marqeta
        checkr goodhire
        gusto rippling justworks
        lattice culture-amp 15five
        greenhouse lever ashby smartrecruiters workable recruitee
        """.split()
        for slug in [re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")]
        if slug
    )
)


def main() -> None:
    slugs: set[str] = set(EXTRA_SLUGS)
    if SEED_500.is_file():
        rows = json.loads(SEED_500.read_text(encoding="utf-8"))
        for row in rows:
            slugs.add(str(row["slug"]))
    ordered = sorted(slugs)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(ordered)} candidate slugs to {OUTPUT}")


if __name__ == "__main__":
    main()
