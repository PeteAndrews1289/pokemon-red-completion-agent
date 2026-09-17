"""Derive three compatible learner targets from one admitted TRAIN contrast.

All targets use the same executed whole-party return. They are not inferred
labels for unplayed alternatives, and sibling choices count as one scenario.
"""

from __future__ import annotations

from collections.abc import Mapping
from statistics import fmean
from typing import cast

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices


class TrainerPracticeTargetError(ValueError):
    """An admitted contrast does not support learner targets."""


def extract_trainer_practice_targets(
    admission: Mapping[str, object], document: Mapping[str, object]
) -> dict[str, object]:
    if (
        admission.get("schema") != "pokemon.red.trainer-practice-admission.v1"
        or admission.get("partition") != "train"
        or admission.get("execution_proof_complete") is not True
        or admission.get("return_proof_complete") is not True
        or admission.get("observation_schema") != OBSERVATION_SCHEMA_V2
        or admission.get("capture_id") != document.get("capture_id")
        or admission.get("manifest_sha256") != document.get("manifest_sha256")
    ):
        raise TrainerPracticeTargetError("training requires execution-proven TRAIN admission")
    rows, branches = admission.get("measured_choices"), document.get("branches")
    if not isinstance(rows, list) or not isinstance(branches, list) or len(rows) != len(branches):
        raise TrainerPracticeTargetError("admitted branch inventory differs")
    refs: list[str] = []
    values: list[float] = []
    kinds: list[str] = []
    initial_observation: object = None
    initial_model_input: object = None
    for row, branch in zip(rows, branches, strict=True):
        if not isinstance(row, Mapping) or not isinstance(branch, Mapping):
            raise TrainerPracticeTargetError("admitted branch differs")
        choice = row.get("first_choice_ref")
        episode = branch.get("episode")
        details = row.get("whole_party_return")
        if (
            not isinstance(choice, str)
            or choice != branch.get("first_choice_ref")
            or not isinstance(episode, Mapping)
            or not isinstance(details, Mapping)
            or details.get("schema") != "pokemon.red.trainer-practice.whole-party-return.v1"
            or not isinstance(details.get("value"), (int, float))
            or isinstance(details.get("value"), bool)
        ):
            raise TrainerPracticeTargetError("admitted return differs")
        decisions = episode.get("decisions")
        if (
            not isinstance(decisions, list)
            or not decisions
            or not isinstance(decisions[0], Mapping)
        ):
            raise TrainerPracticeTargetError("admitted first decision differs")
        first = decisions[0]
        if initial_observation is None:
            initial_observation = first.get("observation")
            initial_model_input = first.get("model_input")
        elif first.get("observation") != initial_observation:
            raise TrainerPracticeTargetError("branches start from different observations")
        kind = first.get("kind")
        if kind not in {"attack", "voluntary_switch", "switch_prompt", "forced_switch"}:
            raise TrainerPracticeTargetError("first action is unsupported")
        refs.append(choice)
        values.append(float(details["value"]))
        kinds.append(kind)
    if not isinstance(initial_observation, Mapping):
        raise TrainerPracticeTargetError("actor observation is missing")
    if all(kind in {"attack", "voluntary_switch"} for kind in kinds):
        context = "main"
    elif all(kind == "switch_prompt" for kind in kinds):
        context = "prompt"
    elif all(kind == "forced_switch" for kind in kinds):
        context = "forced"
    else:
        raise TrainerPracticeTargetError("first-choice contexts are mixed")
    supported = (
        initial_model_input.get("supported_candidate_mask")
        if isinstance(initial_model_input, Mapping) else None
    )
    attack_depleted = (
        context == "main"
        and isinstance(supported, list)
        and bool(supported)
        and all(value is False for value in supported)
    )
    groups: dict[str, tuple[int, ...]] = {}
    attack = tuple(i for i, kind in enumerate(kinds) if kind == "attack")
    switches = tuple(
        i
        for i, kind in enumerate(kinds)
        if kind in {"voluntary_switch", "forced_switch"}
        or kind == "switch_prompt"
        and refs[i] != "pokemon.core:battle:decline-switch"
    )
    decline = tuple(i for i, ref in enumerate(refs) if ref == "pokemon.core:battle:decline-switch")
    if len(attack) >= 2:
        groups["move"] = attack
    if len(switches) >= 2:
        groups["switch"] = switches
    if attack and switches:
        groups["control"] = (*attack, *switches)
    elif decline and switches:
        groups["control"] = (*decline, *switches)
    if not groups:
        raise TrainerPracticeTargetError("contrast has no trainable action comparison")
    heads = {}
    for name, indices in groups.items():
        local_values = tuple(values[index] for index in indices)
        heads[name] = {
            "choice_refs": [refs[index] for index in indices],
            "returns": list(local_values),
            "best_indices": list(tied_best_indices(local_values)),
        }
    return {
        "schema": "pokemon.red.trainer-practice-three-head-targets.v1",
        "capture_id": admission["capture_id"],
        "manifest_sha256": admission["manifest_sha256"],
        "source_commit": admission["source_commit"],
        "admission_sha256": canonical_sha256(admission),
        "choices_sha256": canonical_sha256(document),
        "root_lineage_id": admission["root_lineage_id"],
        "partition": "train",
        "observation_schema": OBSERVATION_SCHEMA_V2,
        "scenario_count": 1,
        "timing_count": 1,
        "decision_context": context,
        "attack_depleted": attack_depleted,
        "timing_offset_frames": admission["opening_idle_frames"],
        "observation": dict(initial_observation),
        "legacy_model_input": initial_model_input,
        "heads": heads,
    }


def aggregate_trainer_timing_targets(
    targets: tuple[Mapping[str, object], ...],
    *,
    expected_offsets: tuple[int, ...],
) -> dict[str, object]:
    """One scenario from five predeclared observation-preserving RNG offsets."""

    if (
        len(targets) != len(expected_offsets)
        or len(targets) < 5
        or len(set(expected_offsets)) != len(expected_offsets)
        or any(type(offset) is not int or not 0 <= offset <= 12 for offset in expected_offsets)
        or tuple(target.get("timing_offset_frames") for target in targets) != expected_offsets
    ):
        raise TrainerPracticeTargetError("timing schedule differs from prospective offsets")
    first = targets[0]
    expected_identity = (
        first.get("capture_id"),
        first.get("manifest_sha256"),
        first.get("root_lineage_id"),
        first.get("observation"),
        first.get("decision_context"),
        first.get("attack_depleted"),
    )
    first_heads = first.get("heads")
    if not isinstance(first_heads, Mapping):
        raise TrainerPracticeTargetError("timed target heads are missing")
    for target in targets:
        if (
            target.get("schema") != "pokemon.red.trainer-practice-three-head-targets.v1"
            or target.get("partition") != "train"
            or target.get("timing_count") != 1
            or (
                target.get("capture_id"),
                target.get("manifest_sha256"),
                target.get("root_lineage_id"),
                target.get("observation"),
                target.get("decision_context"),
                target.get("attack_depleted"),
            )
            != expected_identity
            or not isinstance(target.get("heads"), Mapping)
            or set(cast(Mapping[str, object], target["heads"])) != set(first_heads)
        ):
            raise TrainerPracticeTargetError("timed branches are not one comparable scenario")
    averaged: dict[str, object] = {}
    for name, first_head in first_heads.items():
        if not isinstance(first_head, Mapping):
            raise TrainerPracticeTargetError("timed head differs")
        refs = first_head.get("choice_refs")
        if not isinstance(refs, list) or not refs:
            raise TrainerPracticeTargetError("timed choice inventory differs")
        per_timing: list[list[float]] = []
        for target in targets:
            head = target["heads"][name]  # type: ignore[index]
            if (
                not isinstance(head, Mapping)
                or head.get("choice_refs") != refs
                or not isinstance(head.get("returns"), list)
                or len(head["returns"]) != len(refs)
            ):
                raise TrainerPracticeTargetError("timed choice inventory differs")
            per_timing.append([float(value) for value in head["returns"]])
        means = tuple(
            round(fmean(row[index] for row in per_timing), 9) for index in range(len(refs))
        )
        averaged[name] = {
            "choice_refs": list(refs),
            "returns": list(means),
            "best_indices": list(tied_best_indices(means)),
            "timing_returns": per_timing,
            "return_spread": [
                round(
                    max(row[index] for row in per_timing) - min(row[index] for row in per_timing), 9
                )
                for index in range(len(refs))
            ],
        }
    return {
        **{
            key: first[key]
            for key in (
                "schema",
                "capture_id",
                "manifest_sha256",
                "source_commit",
                "root_lineage_id",
                "partition",
                "scenario_count",
                "observation",
                "legacy_model_input",
                "observation_schema",
                "decision_context",
                "attack_depleted",
            )
        },
        "timing_count": len(targets),
        "timing_offsets": list(expected_offsets),
        "timing_target_sha256s": [canonical_sha256(target) for target in targets],
        "heads": averaged,
    }
