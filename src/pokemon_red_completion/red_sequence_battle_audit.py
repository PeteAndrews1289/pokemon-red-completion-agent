"""Attribute authenticated scoped battle results to existing sequence decisions.

Does not prove that no other combat actor ran. That requires the separate whole-
player authority audit; these measured losses alone cannot enable a target mask.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from .post_battle_strategy import BattleResult
from .provenance import canonical_sha256
from .red_scoped_training_battlers import ScopedBattleOutcome, ScopedTrainingBattlers
from .red_sequence_receipts import read_sequence_receipts


@dataclass(frozen=True)
class ScopedSequenceLossAudit:
    native_plan_sha256: str
    scope_sha256: str
    source_sha256: str
    top_level_losses: tuple[int, ...]
    model_losses: tuple[int, ...]
    leading_support_losses: int
    battles: tuple[ScopedBattleOutcome, ...]
    complete_actor_coverage_verified: bool = False
    training_eligible: bool = False


def audit_scoped_sequence_losses(
    root: Path, *, pool: ScopedTrainingBattlers, expected_native_plan_sha256: str,
    expected_scope_sha256: str, expected_actor_plan_sha256: str,
    expected_actor_result_sha256: str, source_sha256: str,
) -> ScopedSequenceLossAudit:
    """Every declared battle must fit exactly one top-level input interval."""
    plan = json.loads((root / "native-plan.json").read_bytes())
    declaration = json.loads((pool.output / "declaration.json").read_bytes())
    if (canonical_sha256(plan) != expected_native_plan_sha256
        or plan["source"]["state_sha256"] != source_sha256
        or plan["source"]["partition"] != "train"
        or declaration["source_commit"] != plan["source"]["source_commit"]):
        raise ValueError("scoped sequence loss source differs")
    projection = read_sequence_receipts(
        root / "episode", expected_plan_sha256=expected_actor_plan_sha256,
        expected_result_sha256=expected_actor_result_sha256, source_sha256=source_sha256,
    )
    battles = pool.verified_outcomes(
        expected_native_plan_sha256=expected_native_plan_sha256,
        expected_declaration_sha256=expected_scope_sha256, source_sha256=source_sha256,
    )
    rows = json.loads((root / "episode/result.json").read_bytes())["outcomes"]
    losses = [0] * len(rows)
    previous = 0
    for ordinal, battle in enumerate(battles):
        if (battle.ordinal != ordinal or battle.before_frame < previous
            or battle.after_frame <= battle.before_frame):
            raise ValueError("scoped sequence battle order differs")
        owners = [i for i, row in enumerate(rows)
                  if row["before"]["frames"] <= battle.before_frame
                  and battle.after_frame <= row["after"]["frames"]]
        if len(owners) != 1:
            raise ValueError("scoped battle has no unique top-level cost owner")
        losses[owners[0]] += int(battle.result is BattleResult.LOST)
        previous = battle.after_frame
    model_losses: list[int] = []
    leading = 0
    for row, count in zip(rows, losses, strict=True):
        if row["learning_eligible"]:
            model_losses.append(count)
        elif model_losses:
            model_losses[-1] += count
        else:
            leading += count
    if len(model_losses) != len(projection.choices):
        raise ValueError("scoped sequence battle ownership census differs")
    return ScopedSequenceLossAudit(
        expected_native_plan_sha256, expected_scope_sha256, source_sha256,
        tuple(losses), tuple(model_losses), leading, battles,
    )
