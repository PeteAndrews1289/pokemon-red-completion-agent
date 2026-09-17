"""Fit a TRAIN-only three-head challenger from five-timing admitted scenarios.

The private corpus plan lists exact state, manifest, report and prospective
choice-plan hashes. Every branch log must be complete and match the declared
source/model/choice/timing identity. No DEVELOPMENT input is opened here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_trainer_practice_admission import inspect_trainer_practice_choices
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads
from pokemon_red_completion.red_trainer_practice_targets import (
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-fit-corpus-plan.v1"
OFFSETS = (0, 2, 4, 6, 8)
SHA256 = re.compile(r"[0-9a-f]{64}")
# Distinct slot IDs and state hashes from this historical catalog do not prove
# independent play. Keep the aliases mutually exclusive until ancestry is audited.
UNRESOLVED_CELADON_ANCESTRY = frozenset({
    "red-lab-rival-train-20260917-offset137",
    "red-goal-v1-001-advance_story-train-01",
    "red-goal-v1-002-advance_story-train-02",
    "red-goal-v1-003-advance_story-train-03",
})


def _validate_root_source_provenance(
    receipts: Sequence[Mapping[str, object]],
) -> None:
    """Reject duplicate or inconsistent upstream states before counting roots.

    Distinct hashes are necessary, but not by themselves proof that captures
    came from independent play. That provenance must still be audited.
    """
    source_by_root: dict[str, str] = {}
    root_by_source: dict[str, str] = {}
    for receipt in receipts:
        root = receipt.get("root_lineage_id")
        source = receipt.get("source_state_sha256")
        if (
            not isinstance(root, str)
            or not root
            or not isinstance(source, str)
            or SHA256.fullmatch(source) is None
        ):
            raise ValueError("trainer root source identity is missing")
        if root in source_by_root and source_by_root[root] != source:
            raise ValueError("trainer root maps to multiple upstream states")
        if source in root_by_source and root_by_source[source] != root:
            raise ValueError("one trainer source was relabeled as multiple roots")
        source_by_root[root] = source
        root_by_source[source] = root
    if len(source_by_root.keys() & UNRESOLVED_CELADON_ANCESTRY) > 1:
        raise ValueError("trainer roots have unresolved shared Celadon ancestry")


def _validate_exploratory_supply(
    targets: Sequence[Mapping[str, object]],
    receipts: Sequence[Mapping[str, object]],
) -> None:
    """A bounded correlated TRAIN fit, never an independent-root qualification."""
    if len(targets) not in {4, 8} or len(receipts) != len(targets):
        raise ValueError("exploratory fit requires exactly four or eight declared scenarios")
    if len({row.get("root_lineage_id") for row in receipts}) != 1:
        raise ValueError("exploratory fit requires one disclosed upstream TRAIN root")
    if len({row.get("capture_id") for row in receipts}) != len(targets):
        raise ValueError("exploratory fit requires distinct captures")
    matchups: set[tuple[str, str]] = set()
    for target in targets:
        observation = target.get("observation")
        if not isinstance(observation, Mapping):
            raise ValueError("exploratory actor observation is missing")
        features = observation.get("features")
        if not isinstance(features, Mapping):
            raise ValueError("exploratory actor features are missing")
        party = features.get("party")
        battle = features.get("battle")
        if not isinstance(party, Mapping) or not isinstance(battle, Mapping):
            raise ValueError("exploratory matchup is missing")
        lead = party.get("lead")
        if not isinstance(lead, Mapping):
            raise ValueError("exploratory active party member is missing")
        actor, opponent = lead.get("species_ref"), battle.get("opponent_species_ref")
        if not isinstance(actor, str) or not isinstance(opponent, str):
            raise ValueError("exploratory species references are missing")
        matchups.add((actor, opponent))
    minimum_matchups = 3 if len(targets) == 4 else 6
    if len(matchups) < minimum_matchups:
        raise ValueError(
            f"exploratory fit requires {minimum_matchups} prospective matchup profiles"
        )


def _bound_path(value: object, label: str) -> Path:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} identity differs")
    location = Path(path)
    if hashlib.sha256(location.read_bytes()).hexdigest() != digest:
        raise ValueError(f"{label} content differs")
    return location


def run(
    plan_path: Path, *, check_only: bool = False, probe_only: bool = False,
    exploratory_fit: bool = False,
) -> dict[str, object]:
    plan = json.loads(plan_path.read_bytes())
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("trainer fit corpus plan differs")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if (
        plan.get("source_commit") != revision
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("trainer fit requires its committed source")
    cases = plan.get("scenarios")
    seed = plan.get("seed")
    output = plan.get("output")
    if (
        not isinstance(cases, list)
        or len(cases) < (1 if probe_only else 4 if exploratory_fit else 16)
        or type(seed) is not int or seed < 0  # noqa: E721
        or not isinstance(output, str) or Path(output).exists()
    ):
        raise ValueError("trainer corpus size, seed, or output differs")
    scenario_targets = []
    scenario_receipts = []
    for scenario_index, scenario in enumerate(cases):
        if (
            not isinstance(scenario, dict)
            or scenario.get("timing_offsets") != list(OFFSETS)
            or not isinstance(scenario.get("trials"), list)
            or len(scenario["trials"]) != len(OFFSETS)
        ):
            raise ValueError("trainer timing inventory differs from five-offset schedule")
        state_path = _bound_path(scenario.get("state"), "trainer state")
        manifest_path = _bound_path(scenario.get("manifest"), "trainer manifest")
        capture = open_battle_scenario_capture(state_path, manifest_path)
        targets = []
        for offset, trial in zip(OFFSETS, scenario["trials"], strict=True):
            if not isinstance(trial, dict):
                raise ValueError("trainer timing trial differs")
            choices_path = _bound_path(trial.get("choices"), "trainer choices")
            choice_plan_path = _bound_path(trial.get("plan"), "trainer choice plan")
            document = json.loads(choices_path.read_bytes())
            choice_plan = json.loads(choice_plan_path.read_bytes())
            if (
                choice_plan.get("schema") != "pokemon.red.trainer-practice-choice-plan.v1"
                or choice_plan.get("capture_manifest_sha256") != capture.manifest_sha256
                or choice_plan.get("source_commit") != capture.manifest.source_commit
                or choice_plan.get("opening_idle_frames") != offset
                or choice_plan.get("player_turn_horizon") != document.get("player_turn_horizon")
                or choice_plan.get("first_choice_refs") != [
                    branch.get("first_choice_ref") for branch in document.get("branches", [])
                ]
                or not isinstance(choice_plan.get("model_sha256"), str)
                or type(choice_plan.get("max_decisions")) is not int  # noqa: E721
            ):
                raise ValueError("trainer timing choice plan differs")
            prefix = trial.get("branch_log_prefix")
            if not isinstance(prefix, str) or prefix not in {
                "matched-branch", "prompt-branch"
            }:
                raise ValueError("trainer branch log prefix differs")
            logs = {
                ref: choices_path.parent / f"{prefix}-{index:02d}-events"
                for index, ref in enumerate(choice_plan["first_choice_refs"])
            }
            admitted = inspect_trainer_practice_choices(
                capture, document,
                expected_choice_refs=tuple(choice_plan["first_choice_refs"]),
                continuation_policy_id=choice_plan["continuation_policy_id"],
                branch_event_logs=logs,
                plan_sha256=hashlib.sha256(choice_plan_path.read_bytes()).hexdigest(),
                model_sha256=choice_plan["model_sha256"],
                max_decisions=choice_plan["max_decisions"],
                expected_opening_idle_frames=offset,
            )
            targets.append(extract_trainer_practice_targets(admitted, document))
        aggregate = aggregate_trainer_timing_targets(
            tuple(targets), expected_offsets=OFFSETS
        )
        heads = aggregate["heads"]
        if not isinstance(heads, dict):
            raise ValueError("trainer scenario heads differ")
        scenario_targets.append(aggregate)
        scenario_receipts.append({
            "scenario_index": scenario_index,
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "source_state_sha256": capture.manifest.source_state_sha256,
            "timing_count": len(OFFSETS),
            "decision_context": aggregate["decision_context"],
            "attack_depleted": aggregate["attack_depleted"],
            "head_kinds": sorted(heads),
        })
    _validate_root_source_provenance(scenario_receipts)
    root_counts = Counter(row["root_lineage_id"] for row in scenario_receipts)
    if probe_only:
        return {
            "status": "diagnostic_corpus_admitted_not_fit_eligible",
            "scenario_count": len(scenario_targets),
            "root_count": len(root_counts),
            "head_kinds": sorted({
                head
                for row in scenario_receipts
                if isinstance(row["head_kinds"], list)
                for head in row["head_kinds"]
            }),
            "model_updates": 0,
            "authority_promotions": 0,
        }
    if exploratory_fit:
        _validate_exploratory_supply(scenario_targets, scenario_receipts)
    elif (
        len(root_counts) < 4
        or any(count < 4 for count in root_counts.values())
        or len(set(root_counts.values())) != 1
    ):
        raise ValueError(
            "balanced independent TRAIN roots with at least four scenarios each required"
        )
    if not all(
        any(
            isinstance(row["head_kinds"], list) and head in row["head_kinds"]
            for row in scenario_receipts
        )
        for head in ("move", "control", "switch")
    ):
        raise ValueError("trainer corpus lacks one or more learnable heads")
    if not exploratory_fit and (
        {row["decision_context"] for row in scenario_receipts}
        != {"main", "prompt", "forced"}
        or not any(row["attack_depleted"] is True for row in scenario_receipts)
    ):
        raise ValueError("trainer corpus lacks required decision contexts")
    if check_only:
        return {
            "status": (
                "correlated_exploratory_train_corpus_admitted_no_fit"
                if exploratory_fit else "train_only_corpus_admitted_no_fit"
            ),
            "scenario_count": len(scenario_targets),
            "root_count": len(root_counts),
            "model_updates": 0,
        }
    model = fit_trainer_practice_three_heads(
        scenario_targets, seed=seed, require_corpus_floor=not exploratory_fit
    )
    destination = Path(output)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(destination / "model.json", model.to_dict())
    report = {
        "schema": "pokemon.red.trainer-practice-fit-receipt.v1",
        "qualification_tier": (
            "correlated_exploratory_train_only"
            if exploratory_fit else "independent_root_train"
        ),
        "promotion_eligible": False,
        "independent_train_supply_gate_passed": not exploratory_fit,
        "source_commit": revision,
        "corpus_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "scenario_count": len(scenario_targets),
        "distinct_upstream_train_roots": len(model.train_root_ids),
        "timing_trials_per_scenario": len(OFFSETS),
        "head_example_counts": {
            head: sum(
                isinstance(target["heads"], dict) and head in target["heads"]
                for target in scenario_targets
            )
            for head in ("move", "control", "switch")
        },
        "model_sha256": hashlib.sha256((destination / "model.json").read_bytes()).hexdigest(),
        "model_updates": 1,
        "development_evaluations": 0,
        "authority_promotions": 0,
        "scenarios": scenario_receipts,
    }
    _record(destination / "receipt.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--exploratory-fit", action="store_true")
    args = parser.parse_args()
    if args.check_only and args.probe_only:
        parser.error("choose one of --check-only or --probe-only")
    if args.probe_only and args.exploratory_fit:
        parser.error("probe-only cannot also fit")
    print(json.dumps(run(args.plan, check_only=args.check_only,
                         probe_only=args.probe_only,
                         exploratory_fit=args.exploratory_fit), sort_keys=True))


if __name__ == "__main__":
    main()
