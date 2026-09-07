"""Admission of one source choice above a deterministic bounded acquisition.

The parent episode supplies the controller trace and safe terminal. The child
decision supplies a prospectively recorded, replayable source distribution.
Neither an unplayed candidate nor the deterministic parent becomes a target.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_trajectory import load_goal_manager_episode
from pokemon_red_completion.living_dex_causal_journal import restore_living_dex_observed_arm_example
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexOptionKind,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_player_model import RedPlayerModelRecord
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_acquisition import sample_regional_acquisition

REGIONAL_CHOICE_SCHEMA = "pokemon.red.regional-acquisition-choice.v1"
REGIONAL_OUTCOME_SCHEMA = "pokemon.red.regional-acquisition-outcome.v1"
REGIONAL_CHOICE_KIND = "red_regional_acquisition_choice"
REGIONAL_OUTCOME_KIND = "red_regional_acquisition_outcome"


def regional_choice_record_id(episode_id: str) -> str:
    return "rsc-" + canonical_sha256({"episode_id": episode_id, "schema": REGIONAL_CHOICE_SCHEMA})


def regional_outcome_record_id(episode_id: str) -> str:
    return "rso-" + canonical_sha256({"episode_id": episode_id, "schema": REGIONAL_OUTCOME_SCHEMA})


@dataclass(frozen=True, slots=True)
class RedRegionalChoiceInput:
    episode_id: str
    choice_record_sha256: str
    outcome_record_sha256: str
    behavior_record: LivingDexGoalModelRecord | RedPlayerModelRecord


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("regional choice requires a mapping")
    return value


def load_red_regional_choice_example(
    store: PrivateArtifactRoot,
    item: RedRegionalChoiceInput,
) -> LivingDexObservedArmExample:
    choice_record = store.find_sealed_record(
        regional_choice_record_id(item.episode_id),
        expected_kind=REGIONAL_CHOICE_KIND,
    )
    outcome_record = store.find_sealed_record(
        regional_outcome_record_id(item.episode_id),
        expected_kind=REGIONAL_OUTCOME_KIND,
    )
    if (
        choice_record is None
        or outcome_record is None
        or (
            choice_record.summary.record_sha256 != item.choice_record_sha256
            or outcome_record.summary.record_sha256 != item.outcome_record_sha256
        )
    ):
        raise ValueError("regional choice records are absent or changed")
    choice, outcome = choice_record.read(), outcome_record.read()
    if (
        set(choice)
        != {
            "schema",
            "episode_id",
            "parent_plan",
            "before",
            "menu",
            "selection",
            "candidates",
            "controller_input_before_commit",
            "independent_evaluation",
        }
        or choice.get("schema") != REGIONAL_CHOICE_SCHEMA
        or (
            choice.get("episode_id") != item.episode_id
            or choice.get("controller_input_before_commit") is not False
            or choice.get("independent_evaluation") is not False
        )
    ):
        raise ValueError("regional choice declaration differs")
    if (
        set(outcome)
        != {
            "schema",
            "episode_id",
            "choice_record_sha256",
            "manifest_sha256",
            "terminal_checkpoint_sha256",
            "after",
            "example",
        }
        or outcome.get("schema") != REGIONAL_OUTCOME_SCHEMA
        or (
            outcome.get("episode_id") != item.episode_id
            or outcome.get("choice_record_sha256") != item.choice_record_sha256
        )
    ):
        raise ValueError("regional outcome declaration differs")
    plan = RedPlayerTrainingPlan(_mapping(choice["parent_plan"]))
    if plan.document["decision_limit"] != 1:
        raise ValueError("regional parent must contain one decision")
    menu = restore_living_dex_policy_menu(_mapping(choice["menu"]))
    selection = _mapping(choice["selection"])
    replay = sample_regional_acquisition(
        item.behavior_record.model,
        menu,
        seed=cast(int, selection.get("seed")),
    )
    if replay != selection or selection["seed"] != plan.document["seed"]:
        raise ValueError("regional source sampling does not replay")
    candidates = choice["candidates"]
    if (
        not isinstance(candidates, list)
        or not 2 <= len(candidates) <= 8
        or (
            len(candidates) != len(menu.candidates)
            or any(row.features.kind is not LivingDexOptionKind.ACQUIRE for row in menu.candidates)
        )
    ):
        raise ValueError("regional source candidate census differs")
    sources = set()
    for index, raw in enumerate(candidates):
        candidate = _mapping(raw)
        if set(candidate) != {
            "source_id",
            "profile_sha256",
            "profile",
            "estimated_effort",
            "estimated_risk",
        }:
            raise ValueError("regional candidate declaration differs")
        profile = parse_red_goal_context_profile(
            (
                json.dumps(candidate["profile"], sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )
        captures = [spec for spec in profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES]
        source = candidate["source_id"]
        if (
            not isinstance(source, str)
            or source in sources
            or len(captures) != 1
            or captures[0].parameters.get("source_id") != source
            or profile.profile_sha256 != candidate["profile_sha256"]
        ):
            raise ValueError("regional candidate source or profile differs")
        sources.add(source)
        projected = red_living_dex_setup_candidate_features(
            LivingDexOptionKind.ACQUIRE,
            route_controller_actions=0,
            maximum_controller_actions=1,
            estimated_effort=cast(float, candidate["estimated_effort"]),
            estimated_risk=cast(float, candidate["estimated_risk"]),
            storage_unit=menu.context.storage_pressure,
        )
        if menu.candidates[index].features != projected:
            raise ValueError("regional candidate semantic projection differs")
    selected = _mapping(candidates[cast(int, replay["selected_candidate_index"])])
    if selected.get("profile_sha256") != plan.document["profile_sha256"]:
        raise ValueError("regional selected profile differs from executed profile")
    dataset = load_red_player_training_episode(
        store,
        episode_id=item.episode_id,
        expected_manifest_sha256=cast(str, outcome["manifest_sha256"]),
        plan=plan,
        behavior_model=item.behavior_record.model,
    )
    # This first integration deliberately has one acquisition parent and one
    # learned source choice, not two labels for the same physical execution.
    if dataset.examples or dataset.decisions != 1:
        raise ValueError("regional source outcome overlaps parent learning")
    reader = store.open_episode(item.episode_id)
    metadata = _mapping(reader.read_header().get("metadata"))
    if metadata.get("regional_choice_record_sha256") != item.choice_record_sha256:
        raise ValueError("regional choice was not bound before parent controller input")
    joined = load_goal_manager_episode(reader)
    decision = joined.examples[0]
    if decision.selected_kind is not GoalKind.ACQUIRE_SPECIES or (
        decision.outcome_status is GoalDecisionOutcome.INTERRUPTED
    ):
        raise ValueError("regional acquisition was not a settled played parent")
    terminal = store.find_sealed_record(
        checkpoint_record_id(item.episode_id),
        expected_kind=CHECKPOINT_KIND,
    )
    if terminal is None or terminal.summary.record_sha256 != outcome["terminal_checkpoint_sha256"]:
        raise ValueError("regional acquisition lacks its verified terminal")
    checkpoint = terminal.read()
    if any(
        checkpoint.get(key) != value
        for key, value in {
            "episode_id": item.episode_id,
            "trajectory_manifest_sha256": reader.manifest_sha256,
            "profile_sha256": plan.document["profile_sha256"],
            "original_state_sha256": plan.document["state_sha256"],
            "model_sha256": item.behavior_record.model.model_sha256,
            "context_origin": "training",
        }.items()
    ):
        raise ValueError("regional terminal provenance differs")
    result = _mapping(checkpoint.get("terminal_result"))
    steps = result.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        raise ValueError("regional terminal decision count differs")
    step = _mapping(steps[0])
    actions, frames = step.get("actions_executed"), step.get("frames_executed")
    if type(actions) is not int or actions <= 0 or type(frames) is not int or frames < 0:
        raise ValueError("regional outcome lacks controller execution")
    traces = tuple(reader.iter_stream("executions"))
    recorded_frames = sum(cast(int, trace["frames"]) for trace in traces)
    if (
        len(traces) != actions
        or recorded_frames > frames
        or (all(trace.get("status") == "success" for trace in traces) and recorded_frames != frames)
    ):
        raise ValueError("regional controller cost differs from its trace")
    if (
        result.get("total_actions") != actions
        or result.get("total_frames") != frames
        or (
            step.get("selected_kind") != "acquire_species"
            or step.get("status") != decision.outcome_status.value
            or step.get("collection_after") != checkpoint.get("collection")
        )
    ):
        raise ValueError("regional terminal result differs")
    expected = red_living_dex_outcome_from_observations(
        _mapping(choice["before"]),
        _mapping(outcome["after"]),
        succeeded=decision.outcome_status is GoalDecisionOutcome.SUCCEEDED,
        actions=actions,
        frames=frames,
        maximum_actions=plan.maximum_actions,
        maximum_frames=plan.maximum_frames,
    )
    example = restore_living_dex_observed_arm_example(_mapping(outcome["example"]))
    if (
        example.outcome != expected
        or example.menu.policy_dict() != menu.policy_dict()
        or (
            example.selected_candidate_index != replay["selected_candidate_index"]
            or example.behavior_probabilities != tuple(cast(list[float], replay["probabilities"]))
            or example.partition != "train"
            or example.decision_sha256
            != canonical_sha256(
                {
                    "schema": REGIONAL_CHOICE_SCHEMA,
                    "choice_record_sha256": item.choice_record_sha256,
                }
            )
        )
    ):
        raise ValueError("regional selected outcome differs from observed evidence")
    return example
