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


def _valid_status_stages(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 6
        and all(type(v) is int and -6 <= v <= 6 for v in value)
    )


def inspect_trainer_practice_choices(
    capture: BattleScenarioCapture,
    document: Mapping[str, object],
    *,
    expected_choice_refs: tuple[str, ...],
    continuation_policy_id: str,
    branch_event_logs: Mapping[str, Path | str] | None = None,
    plan_sha256: str | None = None,
    model_sha256: str | None = None,
    max_decisions: int | None = None,
    expected_opening_idle_frames: int = 0,
    expected_status_context: Mapping[str, object] | None = None,
    allow_forced_struggle: bool = False,
    train_wild_diagnostic: bool = False,
    train_wild_limits: tuple[int, int] | None = None,
    train_wild_choice_scope: str | None = None,
) -> dict[str, object]:
    """Verify a complete equal-horizon TRAIN set and expose raw outcomes only."""
    if type(train_wild_diagnostic) is not bool or train_wild_diagnostic and allow_forced_struggle:
        raise TrainerPracticeAdmissionError("TRAIN wild diagnostic authority differs")
    if train_wild_limits is not None and (
        not train_wild_diagnostic or type(train_wild_limits) is not tuple
        or len(train_wild_limits) != 2
        or any(type(value) is not int for value in train_wild_limits)
        or train_wild_limits != (8, 32)
    ):
        raise TrainerPracticeAdmissionError("explicit TRAIN wild limits must be (8, 32)")
    if train_wild_choice_scope is not None and (
        type(train_wild_choice_scope) is not str
        or train_wild_choice_scope != "switch_selection"
        or train_wild_diagnostic is not True or train_wild_limits != (8, 32)
    ):
        raise TrainerPracticeAdmissionError("switch-selection scope requires explicit TRAIN wild (8, 32)")
    if document.get("train_wild_choice_scope") != train_wild_choice_scope:
        raise TrainerPracticeAdmissionError("declared TRAIN wild choice scope differs")
    if train_wild_choice_scope == "switch_selection" and (
        not isinstance(expected_choice_refs, tuple) or len(expected_choice_refs) != 2
        or any(type(ref) is not str or ref not in {
            f"pokemon.core:battle:switch:{slot}" for slot in range(1, 7)
        } for ref in expected_choice_refs)
    ):
        raise TrainerPracticeAdmissionError("switch-selection requires two exact switch refs")
    limits_metadata = (None if train_wild_limits is None else
                       {"player_turn_horizon": 8, "max_decisions": 32})
    if document.get("train_wild_limits") != limits_metadata or (
        limits_metadata is not None and (
            type(document["train_wild_limits"].get("player_turn_horizon")) is not int
            or type(document["train_wild_limits"].get("max_decisions")) is not int
        )
    ):
        raise TrainerPracticeAdmissionError("declared TRAIN wild limits metadata differs")
    wild_horizon, wild_decisions = (2, 8) if train_wild_limits is None else train_wild_limits
    expected_battle_state = 1 if train_wild_diagnostic else 2
    if type(allow_forced_struggle) is not bool:
        raise TrainerPracticeAdmissionError("forced Struggle opt-in must be boolean")
    if expected_status_context is not None and (
        not isinstance(expected_status_context, Mapping)
        or expected_status_context.get("schema") != "pokemon.core.battle.status-context.v1"
        or any(
            type(expected_status_context.get(k)) is not bool
            for k in ("player_confused", "opponent_confused")
        )
        or any(
            not _valid_status_stages(expected_status_context.get(k))
            for k in ("player_stages", "opponent_stages")
        )
    ):
        raise TrainerPracticeAdmissionError("prospective native status context differs")
    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.partition is not ScenarioPartition.TRAIN
        or capture.manifest.expected_battle_state != expected_battle_state
        or document.get("schema") != ("pokemon.red.wild-practice-counterfactual-set.v1" if train_wild_diagnostic
                                      else "pokemon.red.trainer-practice-counterfactual-set.v1")
        or document.get("wild_training", False) is not train_wild_diagnostic
        or document.get("train_wild_diagnostic", False) is not train_wild_diagnostic
        or (train_wild_diagnostic and document.get("expected_battle_state") != 1)
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
    if train_wild_diagnostic and (
        horizon != wild_horizon or len(branches) != 2
        or len([r for r in expected_choice_refs if r.startswith("pokemon.core:battle:move:")]) != (
            0 if train_wild_choice_scope == "switch_selection" else 1)
        or len([r for r in expected_choice_refs if r.startswith("pokemon.core:battle:switch:")]) != (
            2 if train_wild_choice_scope == "switch_selection" else 1)
        or (max_decisions is not None and max_decisions > wild_decisions)
        or (train_wild_limits is not None and
            (type(max_decisions) is not int or max_decisions != wild_decisions))
    ):
        raise TrainerPracticeAdmissionError("wild diagnostic contrast or horizon differs")
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
                Path(branch_event_logs[choice]),
                capture,
                choice,
                episode,
                continuation_policy_id,
                horizon,
                plan_sha256,
                model_sha256,
                max_decisions,
                expected_opening_idle_frames,
                expected_status_context,
                allow_forced_struggle,
                train_wild_diagnostic,
                train_wild_choice_scope,
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
            or not _matches_initial_observation(capture, first, expected_status_context)
            or not _matches_first_choice(first, choice)
        ):
            raise TrainerPracticeAdmissionError("first executed action differs")
        if train_wild_choice_scope == "switch_selection" and first.get("kind") != "voluntary_switch":
            raise TrainerPracticeAdmissionError("switch-selection requires native MAIN switches")
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
            if (
                decision.get("kind") == "forced_struggle" and not allow_forced_struggle
            ) or not _valid_action(decision):
                raise TrainerPracticeAdmissionError("choice contains an illegal action")
            if branch_event_logs is not None and not _actor_observation_matches(decision):
                raise TrainerPracticeAdmissionError(
                    "choice action or resources differ from actor observation"
                )
            step_frames = decision.get("frames_executed")
            if type(step_frames) is not int or step_frames < 0:  # noqa: E721
                raise TrainerPracticeAdmissionError("choice step frames differ")
            counted_frames += step_frames
            counted_turns += decision.get("kind") in {
                "attack",
                "voluntary_switch",
                "forced_struggle",
            }
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
        elif episode.get("final_battle_state") != expected_battle_state:
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
        "schema": ("pokemon.red.wild-practice-admission.v1" if train_wild_diagnostic
                   else "pokemon.red.trainer-practice-admission.v1"),
        **({"train_wild_diagnostic": True, "expected_battle_state": 1} if train_wild_diagnostic else {}),
        **({"train_wild_limits": dict(limits_metadata)} if limits_metadata is not None else {}),
        **({"train_wild_choice_scope": train_wild_choice_scope}
           if train_wild_choice_scope is not None else {}),
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
    status_context: Mapping[str, object] | None = None,
    allow_forced_struggle: bool = False,
    train_wild_diagnostic: bool = False,
    train_wild_choice_scope: str | None = None,
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
            **(
                {"allow_status_moves": True, "native_status_context": dict(status_context)}
                if status_context is not None
                else {}
            ),
        }
        if any(bound.get(key) != value for key, value in expected.items()):
            raise TrainerPracticeAdmissionError("branch log identity differs from plan")
        if (bound.get("wild_training", False) is not train_wild_diagnostic
                or bound.get("train_wild_diagnostic", False) is not train_wild_diagnostic):
            raise TrainerPracticeAdmissionError("branch wild authority differs from plan")
        if bound.get("train_wild_choice_scope") != train_wild_choice_scope:
            raise TrainerPracticeAdmissionError("branch choice scope differs from plan")
        if bound.get("allow_forced_struggle", False) is not allow_forced_struggle:
            raise TrainerPracticeAdmissionError("branch Struggle authority differs from plan")
        starts = [event for event in payloads if event.get("event") == "episode_started"]
        completed = [event for event in payloads if event.get("event") == "decision_completed"]
        choices = [event for event in payloads if event.get("event") == "choice_recorded"]
        decisions = episode.get("decisions")
        if (
            len(starts) != 1
            or starts[0].get("wild_training", False) is not train_wild_diagnostic
            or starts[0].get("train_wild_diagnostic", False) is not train_wild_diagnostic
            or starts[0].get("allow_forced_struggle", False) is not allow_forced_struggle
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


def _matches_initial_observation(capture, first, status_context):
    if status_context is None:
        return first.get("observation_sha256") == capture.manifest.initial_observation_sha256
    from copy import deepcopy

    from .battle_scenario_capture import OBSERVATION_SCHEMA_V2

    if capture.manifest.observation_schema != OBSERVATION_SCHEMA_V2:
        return False
    observation = first.get("observation")
    if not isinstance(observation, dict) or canonical_sha256(observation) != first.get(
        "observation_sha256"
    ):
        return False
    legacy = deepcopy(observation)
    features = legacy.get("features")
    battle = features.get("battle") if isinstance(features, dict) else None
    if not isinstance(battle, dict) or battle.pop("status_context", None) != status_context:
        return False
    return canonical_sha256(legacy) == capture.manifest.initial_observation_sha256


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
        return first.get("kind") in {"voluntary_switch", "switch_prompt", "forced_switch"} and (
            first.get("party_slot") == slot
        )
    return False


def _choice_log_matches_decision(
    event: Mapping[str, object], decision: Mapping[str, object]
) -> bool:
    kind = decision.get("kind")
    action = event.get("selected_action")
    if kind == "forced_struggle":
        return (
            action == "forced_struggle"
            and event.get("authority") == "forced_mechanic"
            and event.get("policy_elapsed_ns") == 0
            and event.get("model_diagnostics") == {}
        )
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
    if decision.get("kind") == "forced_struggle":
        moves = party.get("lead", {}).get("moves")
        return (
            not options
            and type(hp[active]) is int
            and hp[active] > 0
            and isinstance(moves, list)
            and bool(moves)
            and all(
                isinstance(m, Mapping) and type(m.get("pp")) is int and m["pp"] == 0 for m in moves
            )
            and _valid_forced_struggle(decision)
        )
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
    if kind == "forced_struggle":
        return _valid_forced_struggle(decision)
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


def _valid_forced_struggle(decision: Mapping[str, object]) -> bool:
    """Verify a singleton mechanic, never authorize an unobserved policy choice."""
    before = decision.get("state_before")
    after = decision.get("state_after")
    outcome = decision.get("outcome")
    if (
        not isinstance(before, Mapping)
        or not isinstance(after, Mapping)
        or not isinstance(outcome, Mapping)
    ):
        return False
    hp, slot, pp = (before.get(k) for k in ("party_hp", "active_party_slot", "active_pp"))
    terminal_roster = outcome.get("terminal_enemy_roster_hp")
    observation = decision.get("observation", {})
    if not isinstance(observation, Mapping):
        return False
    features = observation.get("features", {})
    if not isinstance(features, Mapping):
        return False
    party, battle = features.get("party", {}), features.get("battle", {})
    if not isinstance(party, Mapping) or not isinstance(battle, Mapping):
        return False
    lead = party.get("lead", {})
    if not isinstance(lead, Mapping):
        return False
    status, trapped = lead.get("status"), battle.get("opponent_using_trapping_move")
    suppressed = (
        outcome.get("execution_claim") == "suppressed_before_selection"
        and outcome.get("selected_move_ref") is None
        and outcome.get("cartridge_selection_observed") is False
        and (
            (
                outcome.get("suppression") in ("sleep", "freeze")
                and status == outcome.get("suppression")
            )
            or (outcome.get("suppression") == "trapping" and trapped is True)
        )
    )
    selected = (
        outcome.get("execution_claim") == "attempt_only"
        and outcome.get("selected_move_ref") == "pokemon.red.gb.us.rev0:move:165"
        and outcome.get("cartridge_selection_observed") is True
        and outcome.get("suppression") is None
    )
    terminal = (
        outcome.get("final_battle_state") == 0
        and isinstance(terminal_roster, list)
        and bool(terminal_roster)
        and all(type(v) is int and v == 0 for v in terminal_roster)
        and isinstance(after.get("party_hp"), list)
        and any(type(v) is int and v > 0 for v in after["party_hp"])
        and after.get("opponent_hp") == 0
        and after.get("active_party_slot") is None
    )
    return (
        decision.get("authority") == "forced_mechanic"
        and decision.get("legal_party_slots") == []
        and decision.get("model_diagnostics") == {}
        and decision.get("policy_elapsed_ns") == 0
        and decision.get("move_slot") is None
        and isinstance(hp, list)
        and type(slot) is int
        and 1 <= slot <= len(hp)
        and type(hp[slot - 1]) is int
        and hp[slot - 1] > 0
        and all(v == 0 for i, v in enumerate(hp) if i != slot - 1)
        and isinstance(pp, list)
        and len(pp) == 4
        and all(type(v) is int and 0 <= v <= 255 and v & 63 == 0 for v in pp)
        and (
            terminal
            or (
                outcome.get("final_battle_state") == 2
                and after.get("active_pp") == pp
                and after.get("active_party_slot") == slot
            )
        )
        and outcome.get("schema") == "pokemon.red.forced-struggle-turn.v1"
        and outcome.get("authority") == "forced_mechanic"
        and outcome.get("move_slot") is None
        and (selected or suppressed)
        and outcome.get("departed_main_menu") is True
        and outcome.get("pp_spent") == 0
        and type(outcome.get("actions_executed")) is int
        and outcome["actions_executed"] > 0
        and type(outcome.get("frames_executed")) is int
        and outcome["frames_executed"] > 0
        and outcome["frames_executed"] == decision.get("frames_executed")
    )


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
