"""Read-only admission of executed TRAIN choice contrasts before model fitting.

This emits measured branch outcomes, not a teacher preference or an inferred
label for an unplayed action. Every sibling remains one upstream root.
"""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.scenario_lab import ScenarioPartition


class TrainerPracticeAdmissionError(ValueError):
    """The proposed choice contrast is unsafe to use as training evidence."""


def inspect_trainer_practice_choices(
    capture: BattleScenarioCapture, document: Mapping[str, object]
) -> dict[str, object]:
    """Verify a complete equal-horizon TRAIN set and expose raw outcomes only."""
    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.partition is not ScenarioPartition.TRAIN
        or document.get("schema") != "pokemon.red.trainer-practice-counterfactual-set.v1"
        or document.get("partition") != "train"
        or document.get("capture_id") != capture.manifest.capture_id
        or document.get("manifest_sha256") != capture.manifest_sha256
        or document.get("root_lineage_id") != capture.manifest.root_lineage_id
    ):
        raise TrainerPracticeAdmissionError("TRAIN capture binding differs")
    horizon = document.get("player_turn_horizon")
    branches = document.get("branches")
    if (
        type(horizon) is not int  # noqa: E721
        or not 1 <= horizon <= 80
        or not isinstance(branches, list)
        or not 2 <= len(branches) <= 10
        or document.get("branch_count") != len(branches)
    ):
        raise TrainerPracticeAdmissionError("choice inventory or horizon differs")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    first_resources: object = None
    for branch in branches:
        if not isinstance(branch, dict):
            raise TrainerPracticeAdmissionError("choice branch differs")
        choice = branch.get("first_choice_ref")
        episode = branch.get("episode")
        if not isinstance(choice, str) or choice in seen or not isinstance(episode, dict):
            raise TrainerPracticeAdmissionError("choice identity is missing or repeated")
        seen.add(choice)
        decisions = episode.get("decisions")
        policy_id = episode.get("policy_id")
        if (
            episode.get("schema") != "pokemon.red.trainer-practice-model-episode.v4"
            or episode.get("capture_id") != capture.manifest.capture_id
            or episode.get("manifest_sha256") != capture.manifest_sha256
            or not isinstance(policy_id, str)
            or not policy_id.endswith(f":first={choice}")
            or not isinstance(decisions, list)
            or not decisions
            or episode.get("decision_count") != len(decisions)
            or episode.get("teacher_queries") != 0
            or episode.get("memory_write_actions") != 0
            or episode.get("authority_promotions") != 0
            or type(episode.get("battle_won")) is not bool
        ):
            raise TrainerPracticeAdmissionError("choice episode binding differs")
        first = decisions[0]
        if (
            not isinstance(first, dict)
            or first.get("observation_sha256")
            != capture.manifest.initial_observation_sha256
            or not _matches_first_choice(first, choice)
        ):
            raise TrainerPracticeAdmissionError("first executed action differs")
        if first_resources is None:
            first_resources = first.get("state_before")
        elif first.get("state_before") != first_resources:
            raise TrainerPracticeAdmissionError("choice branches differ at their starting state")
        for decision in decisions:
            if not isinstance(decision, dict):
                raise TrainerPracticeAdmissionError("choice decision differs")
            for name in ("state_before", "state_after"):
                if not _plausible_resources(decision.get(name)):
                    raise TrainerPracticeAdmissionError("choice has impossible HP resources")
        stop = episode.get("stop_reason")
        turns = episode.get("player_turn_count")
        if type(turns) is not int or not 0 <= turns <= horizon:  # noqa: E721
            raise TrainerPracticeAdmissionError("choice player-turn count differs")
        if stop == "player_turn_budget":
            if turns != horizon:
                raise TrainerPracticeAdmissionError("choice missed its equal-turn horizon")
        elif stop not in {"battle_won", "party_defeated"}:
            raise TrainerPracticeAdmissionError("choice has an unqualified terminal")
        if (stop == "battle_won") != episode["battle_won"]:
            raise TrainerPracticeAdmissionError("choice win terminal differs")
        metrics = episode.get("metrics")
        if not isinstance(metrics, dict) or any(
            type(metrics.get(key)) is not int or metrics[key] < 0  # noqa: E721
            for key in (
                "opponent_faints", "party_faints", "party_hp_lost", "party_pp_spent",
                "teacher_interventions", "invalid_action_failures",
            )
        ) or metrics["teacher_interventions"] or metrics["invalid_action_failures"]:
            raise TrainerPracticeAdmissionError("choice metrics differ or include intervention")
        frames = episode.get("frames_executed")
        if type(frames) is not int or frames < 0:  # noqa: E721
            raise TrainerPracticeAdmissionError("choice frame cost differs")
        rows.append({
            "first_choice_ref": choice,
            "stop_reason": stop,
            "battle_won": episode.get("battle_won") is True,
            "player_turn_count": turns,
            "opponent_faints": metrics["opponent_faints"],
            "party_faints": metrics["party_faints"],
            "party_hp_lost": metrics["party_hp_lost"],
            "party_pp_spent": metrics["party_pp_spent"],
            "frames_executed": frames,
        })
    return {
        "schema": "pokemon.red.trainer-practice-admission.v1",
        "capture_id": capture.manifest.capture_id,
        "manifest_sha256": capture.manifest_sha256,
        "source_commit": capture.manifest.source_commit,
        "state_sha256": capture.manifest.state_sha256,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "partition": "train",
        "player_turn_horizon": horizon,
        "executed_choice_count": len(rows),
        "measured_choices": rows,
        "fit_targets": 0,
        "model_updates": 0,
        "new_independent_upstream_roots": 0,
    }


def _matches_first_choice(first: Mapping[str, object], choice: str) -> bool:
    if choice == "pokemon.core:battle:decline-switch":
        return first.get("kind") == "switch_prompt" and first.get("party_slot") is None
    prefix, separator, number = choice.rpartition(":")
    if not separator or not number.isdecimal():
        return False
    slot = int(number)
    if prefix == "pokemon.core:battle:move":
        return first.get("kind") == "attack" and first.get("move_slot") == slot
    if prefix == "pokemon.core:battle:switch":
        return first.get("kind") in {"voluntary_switch", "switch_prompt"} and (
            first.get("party_slot") == slot
        )
    return False


def _plausible_resources(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    hp, maximum = value.get("party_hp"), value.get("party_max_hp")
    if (
        not isinstance(hp, list)
        or not isinstance(maximum, list)
        or not hp
        or len(hp) != len(maximum)
    ):
        return False
    return all(
        type(current) is int and type(cap) is int and 0 <= current <= cap and cap > 0
        for current, cap in zip(hp, maximum, strict=True)
    ) and (
        value.get("active_hp") is None
        or (
            type(value.get("active_hp")) is int
            and type(value.get("active_max_hp")) is int
            and 0 <= value["active_hp"] <= value["active_max_hp"]
        )
    )
