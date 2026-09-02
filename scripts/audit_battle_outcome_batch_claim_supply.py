#!/usr/bin/env python3
"""Audit claim availability for one frozen battle batch without gameplay."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import freeze_battle_outcome_batch as freezer  # noqa: E402

from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    BattleOutcomePressureCandidate,
    parse_battle_outcome_batch_freeze,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstAvailabilitySnapshot,
    claim_first_availability_snapshot_lease,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)


class BattleOutcomeBatchClaimSupplyAuditError(RuntimeError):
    """Raised when a batch cannot support an action-free claim census."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--expected-freeze-sha256", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    payload = freezer._read_bounded_private_file(  # noqa: SLF001
        args.freeze,
        maximum_bytes=freezer._MAXIMUM_FREEZE_BYTES,  # noqa: SLF001
        subject="batch freeze",
    )
    freeze_sha256 = hashlib.sha256(payload).hexdigest()
    if freeze_sha256 != freezer._sha256(  # noqa: SLF001
        args.expected_freeze_sha256,
        "batch freeze",
    ):
        raise BattleOutcomeBatchClaimSupplyAuditError("batch freeze digest differs")
    freeze = parse_battle_outcome_batch_freeze(payload)
    candidates = (*freeze.roster.fresh_train, *freeze.roster.development)
    if not candidates:
        raise BattleOutcomeBatchClaimSupplyAuditError("batch has no fresh roots")
    pairs = tuple(
        (item.binding.logical_root_sha256, item.binding.physical_root_sha256)
        for item in candidates
    )
    if len(set(pairs)) != len(pairs):
        raise BattleOutcomeBatchClaimSupplyAuditError("batch repeats a root pair")
    with claim_first_availability_snapshot_lease(
        open_fixed_account_claim_registry()
    ) as lease:
        snapshot = lease.observe(pairs)
        counts = _availability_counts(candidates, snapshot)
    return {
        "schema": "pokemon-red-battle-outcome-batch-claim-supply-audit-v1",
        "status": (
            "complete_batch_supply_available"
            if counts["fresh_train_available"] == counts["fresh_train_total"]
            and counts["development_available"] == counts["development_total"]
            else "fresh_batch_supply_unavailable"
        ),
        "source": source.public_dict(),
        "source_bundle_sha256": working_source_bundle_sha256(PROJECT_ROOT),
        "freeze_sha256": freeze_sha256,
        "roster_sha256": freeze.roster.roster_sha256,
        "availability_snapshot_sha256": snapshot.snapshot_sha256,
        **counts,
        "state_files_opened": 0,
        "rom_files_opened": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "root_claims_created": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _availability_counts(
    candidates: Sequence[BattleOutcomePressureCandidate],
    snapshot: ClaimFirstAvailabilitySnapshot,
) -> dict[str, int]:
    totals: Counter[str] = Counter()
    available: Counter[str] = Counter()
    for candidate in candidates:
        partition = candidate.partition.value
        totals[partition] += 1
        available[partition] += int(
            snapshot.availability_for(
                candidate.binding.logical_root_sha256,
                candidate.binding.physical_root_sha256,
            )
        )
    return {
        "fresh_train_total": totals["train"],
        "fresh_train_available": available["train"],
        "fresh_train_claimed": totals["train"] - available["train"],
        "development_total": totals["development"],
        "development_available": available["development"],
        "development_claimed": totals["development"] - available["development"],
    }


def main() -> int:
    try:
        receipt = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"battle batch claim-supply audit failed: {error}") from None
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
