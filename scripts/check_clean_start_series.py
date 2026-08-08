#!/usr/bin/env python3
"""Independently evaluate one frozen ten-root learned clean-start series."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.clean_start_campaign import (
    CleanStartCampaignError,
    evaluate_clean_start_series,
    parse_clean_start_campaign,
    parse_clean_start_outcome,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        campaign = parse_clean_start_campaign(args.campaign.read_bytes())
        outcomes = tuple(parse_clean_start_outcome(path.read_bytes()) for path in args.outcome)
        result = evaluate_clean_start_series(campaign, outcomes)
        payload = json.dumps(result.public_dict(), indent=2, sort_keys=True) + "\n"
    except (OSError, CleanStartCampaignError) as error:
        parser.error(str(error))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="ascii")
    print(payload, end="")
    return 0 if result.promotion_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
