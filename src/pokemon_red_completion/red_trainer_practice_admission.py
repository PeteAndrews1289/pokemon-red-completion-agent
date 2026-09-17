"""Read-only admission of executed TRAIN choice contrasts before model fitting.

This emits measured branch outcomes, not a teacher preference or an inferred
label for an unplayed action. Every sibling remains one upstream root.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_episode import _episode_metrics
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.red_trainer_practice_returns import (
    TrainerPracticeReturnError,
    score_trainer_practice_episode,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


class TrainerPracticeAdmissionError(ValueError):
    """The proposed choice contrast is unsafe to use as training evidence."""


def inspect_trainer_practice_choices(
    capture: BattleScenarioCapture,
    document: Mapping[str, object],
    *,
    expected_choice_refs: tuple[str, ...],
    continuation_policy_id: str,
    branch_event_logs: Mapping[str, Path] | None = None,
    plan_sha256: str | None = None,
    model_sha256: str | None = None,
    max_decisions: int | None = None,
    expected_opening_idle_frames: int = 0,
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
        or not isinstance(expected_choice_refs, tuple)
        or not 2 <= len(expected_choice_refs) <= 10
        or len(set(expected_choice_refs)) != len(expected_choice_refs)
        or not isinstance(continuation_policy_id, str)
        or not continuation_policy_id
        or type(expected_opening_idle_frames) is not int  # noqa: E721
        or not 0 <= expected_opening_idle_frames <= 12
    ):
        raise TrainerPracticeAdmissionError("choice inventory or horizon differs")
    rows: list[dict[str, object]] = []
    return_proof_complete = True
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
        if branch_event_logs is not None:
            if (
                plan_sha256 is None
                or model_sha256 is None
                or max_decisions is None
                or choice not in branch_event_logs
            ):
                raise TrainerPracticeAdmissionError("choice lacks prospective execution evidence")
            _verify_branch_log(
                branch_event_logs[choice],
                capture,
                choice,
                episode,
                continuation_policy_id,
                horizon,
                plan_sha256,
                model_sha256,
                max_decisions,
                expected_opening_idle_frames,
            )
        decisions = episode.get("decisions")
        policy_id = episode.get("policy_id")
        if (
            episode.get("schema") != "pokemon.red.trainer-practice-model-episode.v4"
            or episode.get("capture_id") != capture.manifest.capture_id
            or episode.get("manifest_sha256") != capture.manifest_sha256
            or not isinstance(policy_id, str)
            or policy_id != f"{continuation_policy_id}:first={choice}"
            or not isinstance(decisions, list)
            or not decisions
            or episode.get("decision_count") != len(decisions)
            or episode.get("teacher_queries") != 0
            or episode.get("memory_write_actions") != 0
            or episode.get("authority_promotions") != 0
            or episode.get("opening_idle_frames", 0) != expected_opening_idle_frames
            or type(episode.get("battle_won")) is not bool
        ):
            raise TrainerPracticeAdmissionError("choice episode binding differs")
        first = decisions[0]
        if (
            not isinstance(first, dict)
            or first.get("observation_sha256") != capture.manifest.initial_observation_sha256
            or not _matches_first_choice(first, choice)
        ):
            raise TrainerPracticeAdmissionError("first executed action differs")
        if first_resources is None:
            first_resources = first.get("state_before")
        elif first.get("state_before") != first_resources:
            raise TrainerPracticeAdmissionError("choice branches differ at their starting state")
        prior: dict[str, object] | None = None
        counted_turns = 0
        counted_frames = 0
        for index, decision in enumerate(decisions, 1):
            if not isinstance(decision, dict):
                raise TrainerPracticeAdmissionError("choice decision differs")
            if decision.get("decision_index") != index:
                raise TrainerPracticeAdmissionError("choice decision sequence differs")
            observation = decision.get("observation")
            if not isinstance(observation, dict) or (
                canonical_sha256(observation) != decision.get("observation_sha256")
            ):
                raise TrainerPracticeAdmissionError("choice observation digest differs")
            if prior is not None and (
                prior.get("state_after") != decision.get("state_before")
                or (
                    prior.get("after_observation_sha256") is not None
                    and prior.get("after_observation_sha256") != decision.get("observation_sha256")
                )
            ):
                raise TrainerPracticeAdmissionError("choice decision chain differs")
            for name in ("state_before", "state_after"):
                if not _plausible_resources(decision.get(name)):
                    raise TrainerPracticeAdmissionError("choice has impossible HP resources")
            if not _valid_action(decision):
                raise TrainerPracticeAdmissionError("choice contains an illegal action")
            if branch_event_logs is not None and not _actor_observation_matches(decision):
                raise TrainerPracticeAdmissionError(
                    "choice action or resources differ from actor observation"
                )
            step_frames = decision.get("frames_executed")
            if type(step_frames) is not int or step_frames < 0:  # noqa: E721
                raise TrainerPracticeAdmissionError("choice step frames differ")
            counted_frames += step_frames
            counted_turns += decision.get("kind") in {"attack", "voluntary_switch"}
            prior = decision
        if set(seen) - set(expected_choice_refs):
            raise TrainerPracticeAdmissionError("choice inventory differs from declared plan")
        stop = episode.get("stop_reason")
        turns = episode.get("player_turn_count")
        if type(turns) is not int or turns != counted_turns or not 0 <= turns <= horizon:  # noqa: E721
            raise TrainerPracticeAdmissionError("choice player-turn count differs")
        if stop == "player_turn_budget":
            if turns != horizon:
                raise TrainerPracticeAdmissionError("choice missed its equal-turn horizon")
        elif stop not in {"battle_won", "party_defeated"}:
            raise TrainerPracticeAdmissionError("choice has an unqualified terminal")
        if (stop == "battle_won") != episode["battle_won"]:
            raise TrainerPracticeAdmissionError("choice win terminal differs")
        if stop == "battle_won":
            roster = episode.get("final_enemy_roster_hp")
            if (
                episode.get("final_battle_state") != 0
                or not isinstance(roster, list)
                or not roster
                or any(type(value) is not int or value != 0 for value in roster)  # noqa: E721
                or not any(value > 0 for value in decisions[-1]["state_after"]["party_hp"])
            ):
                raise TrainerPracticeAdmissionError("choice win lacks terminal proof")
        elif stop == "party_defeated":
            if any(value > 0 for value in decisions[-1]["state_after"]["party_hp"]):
                raise TrainerPracticeAdmissionError("choice defeat lacks terminal proof")
        elif episode.get("final_battle_state") != 2:
            raise TrainerPracticeAdmissionError("choice horizon left its trainer battle")
        final_observation = episode.get("final_observation")
        if not isinstance(final_observation, dict) or (
            canonical_sha256(final_observation) != episode.get("final_observation_sha256")
            or not _plausible_observation(final_observation)
        ):
            raise TrainerPracticeAdmissionError("choice final observation differs")
        if decisions[-1].get("after_observation_sha256") is not None and (
            decisions[-1]["after_observation_sha256"] != episode["final_observation_sha256"]
        ):
            raise TrainerPracticeAdmissionError("choice final observation chain differs")
        metrics = episode.get("metrics")
        if (
            not isinstance(metrics, dict)
            or any(
                type(metrics.get(key)) is not int or metrics[key] < 0  # noqa: E721
                for key in (
                    "opponent_faints",
                    "party_faints",
                    "party_hp_lost",
                    "party_pp_spent",
                    "teacher_interventions",
                    "invalid_action_failures",
                )
            )
            or metrics["teacher_interventions"]
            or metrics["invalid_action_failures"]
        ):
            raise TrainerPracticeAdmissionError("choice metrics differ or include intervention")
        measured = _episode_metrics(tuple(decisions))
        if any(
            metrics[key] != measured[key]
            for key in ("opponent_faints", "party_faints", "party_hp_lost", "party_pp_spent")
        ):
            raise TrainerPracticeAdmissionError("choice metrics differ from decisions")
        frames = episode.get("frames_executed")
        if type(frames) is not int or frames != counted_frames:  # noqa: E721
            raise TrainerPracticeAdmissionError("choice frame cost differs")
        try:
            whole_party_return = score_trainer_practice_episode(episode)
        except TrainerPracticeReturnError as error:
            if branch_event_logs is not None:
                raise TrainerPracticeAdmissionError("choice whole-party return differs") from error
            # Pre-contract retained reports may omit per-attack HP. Preserve
            # their diagnostic measurements, never turn them into fit targets.
            whole_party_return = None
            return_proof_complete = False
        rows.append(
            {
                "first_choice_ref": choice,
                "stop_reason": stop,
                "battle_won": episode.get("battle_won") is True,
                "player_turn_count": turns,
                "opponent_faints": metrics["opponent_faints"],
                "party_faints": metrics["party_faints"],
                "party_hp_lost": metrics["party_hp_lost"],
                "party_pp_spent": metrics["party_pp_spent"],
                "frames_executed": frames,
                "whole_party_return": (
                    whole_party_return.public_dict() if whole_party_return is not None else None
                ),
            }
        )
    if seen != set(expected_choice_refs):
        raise TrainerPracticeAdmissionError("choice inventory differs from declared plan")
    if branch_event_logs is not None and set(branch_event_logs) != seen:
        raise TrainerPracticeAdmissionError("branch log inventory differs from declared plan")
    return {
        "schema": "pokemon.red.trainer-practice-admission.v1",
        "capture_id": capture.manifest.capture_id,
        "manifest_sha256": capture.manifest_sha256,
        "source_commit": capture.manifest.source_commit,
        "state_sha256": capture.manifest.state_sha256,
        "root_lineage_id": capture.manifest.root_lineage_id,
        "partition": "train",
        "observation_schema": capture.manifest.observation_schema,
        "player_turn_horizon": horizon,
        "opening_idle_frames": expected_opening_idle_frames,
        "executed_choice_count": len(rows),
        "measured_choices": rows,
        "fit_targets": 0,
        "model_updates": 0,
        "new_independent_upstream_roots": 0,
        "execution_proof_complete": branch_event_logs is not None,
        "return_proof_complete": return_proof_complete,
    }


def _verify_branch_log(
    directory: Path,
    capture: BattleScenarioCapture,
    choice: str,
    episode: Mapping[str, object],
    continuation_policy_id: str,
    horizon: int,
    plan_sha256: str,
    model_sha256: str,
    max_decisions: int,
    opening_idle_frames: int,
) -> None:
    try:
        result = verify_trainer_practice_event_log(directory)
        if result["terminal_event"] != "run_finished" or result["incomplete_decisions"]:
            raise TrainerPracticeAdmissionError("branch log is failed or incomplete")
        payloads = [
            json.loads(path.read_bytes())["payload"]
            for path in sorted(directory.glob("event-*.json"))
        ]
        identity = payloads[0]
        if identity.get("event") != "run_identity" or not isinstance(
            identity.get("identity"), dict
        ):
            raise TrainerPracticeAdmissionError("branch log identity is missing")
        bound = identity["identity"]
        expected = {
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "capture_manifest_sha256": capture.manifest_sha256,
            "source_commit": capture.manifest.source_commit,
            "partition": "train",
            "policy_id": continuation_policy_id,
            "first_choice_ref": choice,
            "player_turn_horizon": horizon,
            "plan_sha256": plan_sha256,
            "model_sha256": model_sha256,
            "max_decisions": max_decisions,
            "opening_idle_frames": opening_idle_frames,
        }
        if any(bound.get(key) != value for key, value in expected.items()):
            raise TrainerPracticeAdmissionError("branch log identity differs from plan")
        starts = [event for event in payloads if event.get("event") == "episode_started"]
        completed = [event for event in payloads if event.get("event") == "decision_completed"]
        choices = [event for event in payloads if event.get("event") == "choice_recorded"]
        decisions = episode.get("decisions")
        if (
            len(starts) != 1
            or starts[0].get("manifest_sha256") != capture.manifest_sha256
            or starts[0].get("policy_id") != f"{continuation_policy_id}:first={choice}"
            or starts[0].get("max_player_turns") != horizon
            or starts[0].get("max_decisions") != max_decisions
            or starts[0].get("opening_idle_frames") != opening_idle_frames
            or not isinstance(decisions, list)
            or len(completed) != len(decisions)
            or len(choices) != len(decisions)
            or any(
                event.get("decision") != decision
                for event, decision in zip(completed, decisions, strict=True)
            )
            or any(event.get("decision_index") != index for index, event in enumerate(choices, 1))
            or any(
                not _choice_log_matches_decision(event, decision)
                for event, decision in zip(choices, decisions, strict=True)
            )
        ):
            raise TrainerPracticeAdmissionError("branch decisions differ from execution log")
        terminal = payloads[-1]
        outcome = terminal.get("outcome")
        if (
            terminal.get("event") != "run_finished"
            or not isinstance(outcome, dict)
            or outcome.get("first_choice_ref") != choice
            or outcome.get("episode_sha256") != canonical_sha256(episode)
            or outcome.get("stop_reason") != episode.get("stop_reason")
        ):
            raise TrainerPracticeAdmissionError("branch terminal differs from execution log")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        if isinstance(error, TrainerPracticeAdmissionError):
            raise
        raise TrainerPracticeAdmissionError("branch execution log cannot be verified") from error


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


def _choice_log_matches_decision(
    event: Mapping[str, object], decision: Mapping[str, object]
) -> bool:
    kind = decision.get("kind")
    action = event.get("selected_action")
    if kind == "attack":
        return (
            isinstance(action, dict)
            and action.get("kind") == "select_move"
            and action.get("move_slot") == decision.get("move_slot")
        )
    if kind == "voluntary_switch":
        return (
            isinstance(action, dict)
            and action.get("kind") == "switch"
            and action.get("party_slot") == decision.get("party_slot")
        )
    if kind in {"forced_switch", "switch_prompt"}:
        return action == (
            "decline_switch" if decision.get("party_slot") is None else "switch"
        ) and event.get("party_slot") == decision.get("party_slot")
    return False


def _actor_observation_matches(decision: Mapping[str, object]) -> bool:
    observation = decision.get("observation")
    state = decision.get("state_before")
    if not isinstance(observation, Mapping) or not isinstance(state, Mapping):
        return False
    features = observation.get("features")
    party = features.get("party") if isinstance(features, Mapping) else None
    if not isinstance(party, Mapping):
        return False
    members, active = party.get("members"), party.get("active_index")
    if not isinstance(members, list) or type(active) is not int or not 0 <= active < len(members):  # noqa: E721
        return False
    if not all(isinstance(member, Mapping) for member in members):
        return False
    hp = [member.get("hp") for member in members]
    caps = [member.get("max_hp") for member in members]
    if hp != state.get("party_hp") or caps != state.get("party_max_hp"):
        return False
    options = [
        index + 1
        for index, value in enumerate(hp)
        if type(value) is int and value > 0 and index != active
    ]  # noqa: E721
    if decision.get("legal_party_slots") != options:
        return False
    if decision.get("kind") not in {"attack", "voluntary_switch"}:
        return True
    model_input = decision.get("model_input")
    if not isinstance(model_input, Mapping):
        return False
    slots = model_input.get("candidate_move_slots")
    mask = model_input.get("supported_candidate_mask")
    if not isinstance(slots, list) or not isinstance(mask, list) or len(slots) != len(mask):
        return False
    legal = [slot for slot, enabled in zip(slots, mask, strict=True) if enabled is True]
    if decision.get("kind") == "attack":
        move_slot = decision.get("move_slot")
        if (
            type(move_slot) is not int  # noqa: E721
            or decision.get("legal_move_slots") != legal
            or move_slot not in legal
        ):
            return False
        lead = party.get("lead")
        moves = lead.get("moves") if isinstance(lead, Mapping) else None
        if not isinstance(moves, list):
            return False
        selected = [
            move
            for move in moves
            if isinstance(move, Mapping) and move.get("slot_index") == move_slot - 1
        ]
        return len(selected) == 1 and type(selected[0].get("pp")) is int and selected[0]["pp"] > 0  # noqa: E721
    return True


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


def _valid_action(decision: Mapping[str, object]) -> bool:
    kind = decision.get("kind")
    legal_party = decision.get("legal_party_slots")
    if not isinstance(legal_party, list) or any(
        type(slot) is not int or not 1 <= slot <= 6
        for slot in legal_party  # noqa: E721
    ):
        return False
    if kind == "attack":
        legal_moves = decision.get("legal_move_slots")
        return (
            isinstance(legal_moves, list)
            and all(type(slot) is int and 1 <= slot <= 4 for slot in legal_moves)
            and decision.get("move_slot") in legal_moves
        )
    if kind in {"voluntary_switch", "forced_switch"}:
        return decision.get("party_slot") in legal_party
    if kind == "switch_prompt":
        return decision.get("party_slot") is None or decision.get("party_slot") in legal_party
    return False


def _plausible_observation(observation: Mapping[str, object]) -> bool:
    features = observation.get("features")
    if not isinstance(features, dict):
        return False
    battle = features.get("battle")
    if isinstance(battle, dict) and battle.get("active") is True:
        hp, cap = battle.get("opponent_hp"), battle.get("opponent_max_hp")
        if type(hp) is not int or type(cap) is not int or not 0 <= hp <= cap or cap <= 0:  # noqa: E721
            return False
    party = features.get("party")
    if isinstance(party, dict):
        members = party.get("members")
        if isinstance(members, list):
            for member in members:
                if not isinstance(member, dict):
                    return False
                hp, cap = member.get("hp"), member.get("max_hp")
                if type(hp) is not int or type(cap) is not int or not 0 <= hp <= cap or cap <= 0:  # noqa: E721
                    return False
    return True
