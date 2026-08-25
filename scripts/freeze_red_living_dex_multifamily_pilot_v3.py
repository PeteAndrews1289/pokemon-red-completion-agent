#!/usr/bin/env python3
"""Freeze one new-identity V3 multi-family Red curriculum without acting."""

from __future__ import annotations

from freeze_red_living_dex_multifamily_pilot import MultifamilyFreezeProtocol
from freeze_red_living_dex_multifamily_pilot import main as _run_freeze

PROTOCOL = MultifamilyFreezeProtocol(
    lane_id="red-living-dex-multifamily-option-value-curriculum-v3",
    plan_schema="pokemon.red.private-living-dex-multifamily-pilot-plan.v3",
    result_schema="pokemon.red.living-dex-multifamily-pilot-freeze-result.v3",
    failure_schema="pokemon.red.living-dex-multifamily-pilot-freeze-failure.v3",
    success_status="two_family_root_disjoint_pilot_frozen_v3",
    plan_record_id="red-living-dex-multifamily-pilot-plan-v3",
    plan_record_kind="red-living-dex-multifamily-pilot-plan-v3",
)

LANE_ID = PROTOCOL.lane_id
PLAN_SCHEMA = PROTOCOL.plan_schema
RESULT_SCHEMA = PROTOCOL.result_schema
FAILURE_SCHEMA = PROTOCOL.failure_schema
PLAN_RECORD_ID = PROTOCOL.plan_record_id
PLAN_RECORD_KIND = PROTOCOL.plan_record_kind


def main(argv: list[str] | None = None) -> int:
    return _run_freeze(argv, protocol=PROTOCOL)


if __name__ == "__main__":
    raise SystemExit(main())
