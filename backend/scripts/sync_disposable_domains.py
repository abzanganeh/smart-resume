#!/usr/bin/env python3
"""Refresh the vendored disposable-email domain blocklist.

Source: https://github.com/disposable/disposable-email-domains (MIT)
Run manually or from CI on a schedule; registration never depends on live fetch.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/disposable/disposable-email-domains/"
    "master/domains.txt"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "data" / "disposable_email_domains.txt"
)


def sync(*, output: Path, url: str = SOURCE_URL) -> int:
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    line_count = sum(1 for line in raw.splitlines() if line.strip())
    print(f"Wrote {line_count} domains to {output}")
    return line_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--url", default=SOURCE_URL, help="Upstream domains.txt URL")
    args = parser.parse_args(argv)
    try:
        sync(output=args.output, url=args.url)
    except OSError as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
