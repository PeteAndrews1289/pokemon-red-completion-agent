"""Train-only supply of model-directed, naturally encountered battle decisions.

This collects actual choices and outcomes, not complete move-value labels. A
separate, isolated train-side counterfactual collector must measure alternatives
before any trace can enter a battle fit. Repeated turns inherit one source root.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from .battle_outcome_capture_authentication import BattleScenarioSourceBinding
from .battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleActionExecutor,
    BattleRuntimeTiming,
    BattleStateReader,
)
from .red_autonomous_player import _record, _write
from .red_learned_battle import FrozenBattleRanker, run_learned_battle
from .red_trajectory import PokemonRedObservationEncoder
from .scenario_lab import ScenarioPartition

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _completed_observation_hashes(value: object) -> tuple[str, ...]:
    """Count only settled choices, never a query or interrupted attack alone."""

    if not isinstance(value, list):
        raise ValueError("child decisions differ")
    hashes: list[str] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("child decision differs")
        if "immediate_outcome" not in row or "settled_facts" not in row:
            continue
        choice = row.get("choice")
        digest = choice.get("observation_sha256") if isinstance(choice, dict) else None
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError("completed decision observation differs")
        hashes.append(digest)
    return tuple(hashes)


def _require_durable_child(
    directory: Path,
    child: Mapping[str, object],
    *,
    source: BattleScenarioSourceBinding,
    snapshot: Callable[[], bytes],
) -> None:
    """Reopen the exact selected-action trace before another setup can run."""

    plan = json.loads((directory / "plan.json").read_text())
    if (
        plan.get("partition") != ScenarioPartition.TRAIN.value
        or plan.get("fit_allowed") is not False
        or plan.get("provenance", {}).get("root_lineage_id") != source.root_lineage_id
        or plan.get("provenance", {}).get("source_state_sha256")
        != source.source_state_sha256
    ):
        raise ValueError("child train provenance differs")
    if json.loads((directory / "outcome.json").read_text()) != json.loads(json.dumps(child)):
        raise ValueError("child retained outcome differs")
    terminal = (directory / "terminal.state").read_bytes()
    digest = hashlib.sha256(terminal).hexdigest()
    if digest != child.get("terminal_state_sha256") or snapshot() != terminal:
        raise ValueError("child terminal state differs")
    decisions = child.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("child decisions differ")
    for index, row in enumerate(decisions):
        step = directory / f"step-{index:03d}"
        query = json.loads((step / "query-started.json").read_text())
        choice = json.loads((step / "execution-started.json").read_text())
        before = (step / "before.state").read_bytes()
        if (
            hashlib.sha256(before).hexdigest() != query.get("state_sha256")
            or choice.get("observation_sha256") != query.get("observation_sha256")
            or choice != row.get("choice")
        ):
            raise ValueError("child durable choice differs")
        if "immediate_outcome" in row and "settled_facts" in row:
            if json.loads((step / "outcome.json").read_text()) != json.loads(json.dumps(row)):
                raise ValueError("child durable turn outcome differs")
        elif child.get("stop_reason") == "battle_exited":
            raise ValueError("child exited without a settled decision")


def run_model_battle_train_episode(
    *,
    output: Path,
    source: BattleScenarioSourceBinding,
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    encoder: PokemonRedObservationEncoder,
    model: FrozenBattleRanker,
    snapshot: Callable[[], bytes],
    costs: Callable[[], Mapping[str, int]],
    setup_encounter: Callable[[int], None],
    expected_map: int,
    maximum_encounters: int = 3,
    maximum_decisions: int = 12,
    maximum_decisions_per_encounter: int = 8,
    maximum_actions: int,
    maximum_frames: int,
    timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
) -> dict[str, object]:
    """Run one non-retryable root, stopping on the first unsafe child terminal.

    The caller must bind a hard action/frame limiter around ``executor`` and
    use a setup function that only reaches a natural encounter. No teacher
    battle decision is available here. This function never fits a model.
    """

    if (
        not isinstance(source, BattleScenarioSourceBinding)
        or source.partition is not ScenarioPartition.TRAIN
    ):
        raise ValueError("battle training episode requires an authenticated train source")
    for label, value, ceiling in (
        ("encounters", maximum_encounters, 4),
        ("decisions", maximum_decisions, 16),
        ("decisions per encounter", maximum_decisions_per_encounter, 8),
        ("actions", maximum_actions, 1600),
        ("frames", maximum_frames, 150000),
    ):
        if type(value) is not int or not 1 <= value <= ceiling:  # noqa: E721
            raise ValueError(f"battle episode {label} bound differs")
    origin = snapshot()
    if hashlib.sha256(origin).hexdigest() != source.source_state_sha256:
        raise ValueError("battle episode origin differs from authenticated source")
    initial_costs = dict(costs())
    if any(type(initial_costs.get(key)) is not int for key in ("actions", "frames")):
        raise ValueError("battle episode costs differ")

    def within_cost_bound() -> bool:
        current = costs()
        return all(
            type(current.get(key)) is int
            and 0 <= current[key] - initial_costs[key] <= limit
            for key, limit in (("actions", maximum_actions), ("frames", maximum_frames))
        )

    output.mkdir(mode=0o700, exist_ok=False)
    _write(output / "origin.state", origin)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.model-battle-train-episode.v1",
            "source": source.public_dict(),
            "model_sha256": hashlib.sha256(model.to_json().encode("ascii")).hexdigest(),
            "expected_map": expected_map,
            "maximum_encounters": maximum_encounters,
            "maximum_decisions": maximum_decisions,
            "maximum_decisions_per_encounter": maximum_decisions_per_encounter,
            "maximum_actions": maximum_actions,
            "maximum_frames": maximum_frames,
            "teacher_battle_fallback": False,
            "fit_allowed": False,
            "authority_promoted": False,
        },
    )
    rows: list[dict[str, object]] = []
    semantic_hashes: set[str] = set()
    model_queries = 0
    completed_decisions = 0
    reason = "encounter_limit"
    error: dict[str, str] | None = None
    try:
        for index in range(maximum_encounters):
            if not within_cost_bound():
                reason = "cost_bound_exceeded"
                break
            remaining = maximum_decisions - model_queries
            if remaining <= 0:
                reason = "decision_limit"
                break
            if index:
                state = reader.read()
                if state.map_id != expected_map or state.battle_state != 0:
                    reason = "unsafe_field_boundary"
                    break
                if not reader.read_input_readiness().ready:
                    reason = "field_not_ready"
                    break
            def setup_child(ordinal: int = index) -> None:
                setup_encounter(ordinal)

            child = run_learned_battle(
                output=output / f"encounter-{index:03d}",
                reader=reader,
                executor=executor,
                encoder=encoder,
                model=model,
                snapshot=snapshot,
                costs=costs,
                setup=setup_child,
                provenance={
                    "partition": ScenarioPartition.TRAIN.value,
                    "root_lineage_id": source.root_lineage_id,
                    "source_state_sha256": source.source_state_sha256,
                    "encounter_index": index,
                    "teacher_battle_fallback": False,
                },
                expected_map=expected_map,
                maximum_decisions=min(maximum_decisions_per_encounter, remaining),
                timing=timing,
                evidence_partition=ScenarioPartition.TRAIN,
            )
            queries = child["model_queries"]
            if type(queries) is not int or not 0 <= queries <= remaining:  # noqa: E721
                raise ValueError("child model query count differs")
            model_queries += queries
            _require_durable_child(
                output / f"encounter-{index:03d}",
                child,
                source=source,
                snapshot=snapshot,
            )
            if not within_cost_bound():
                reason = "cost_bound_exceeded"
                break
            completed_hashes = _completed_observation_hashes(child["decisions"])
            hashes = set(completed_hashes)
            completed = len(completed_hashes)
            completed_decisions += completed
            rows.append(
                {
                    "encounter_index": index,
                    "stop_reason": child["stop_reason"],
                    "model_queries": queries,
                    "completed_decisions": completed,
                    "distinct_semantic_decisions": len(hashes),
                    "terminal_state_sha256": child["terminal_state_sha256"],
                }
            )
            new_hashes = hashes.difference(semantic_hashes)
            semantic_hashes.update(hashes)
            if child["stop_reason"] != "battle_exited":
                reason = str(child["stop_reason"])
                break
            if not new_hashes:
                reason = "no_new_semantic_decision"
                break
        else:
            reason = "encounter_limit"
    except Exception as failure:
        reason = "failed"
        error = {"type": type(failure).__name__, "message": str(failure)}

    terminal = snapshot()
    _write(output / "terminal.state", terminal)
    report: dict[str, object] = {
        "schema": "pokemon.red.model-battle-train-episode-outcome.v1",
        "root_lineage_id": source.root_lineage_id,
        "source_state_sha256": source.source_state_sha256,
        "stop_reason": reason,
        "error": error,
        "encounters": rows,
        "model_queries": model_queries,
        "completed_decisions": completed_decisions,
        "distinct_semantic_decisions": len(semantic_hashes),
        "terminal_state_sha256": hashlib.sha256(terminal).hexdigest(),
        "costs": dict(costs()),
        "teacher_battle_fallbacks": 0,
        "fit_eligible_examples": 0,
        "authority_promoted": False,
    }
    _record(output / "outcome.json", report)
    return report
