"""Authenticated development-measured observed choice without action trace.

This type binds a precommitted candidate menu, selected candidate, behavior-model
identity, before/after registered observations, exact parent/terminal/segment
hashes, and aggregate action/frame/resource costs.

Such rows are training-only (partition="train"), explicitly declare that no
action trace is available, cannot serve as independent evaluation, and are not
eligible for authority promotion.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexOptionMenu,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_model import RedPlayerModelRecord
from pokemon_red_completion.red_registered_observation import REGISTERED_OBSERVATION_SCHEMA
from pokemon_red_completion.red_registered_outcome import red_registered_outcome_from_observations
from pokemon_red_completion.registered_checkpoint import (
    RegisteredCollectionCheckpoint,
    require_registered_transition,
)
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

DEVELOPMENT_MEASURED_CHOICE_SCHEMA = "pokemon.red.development-measured-choice.v1"
DEVELOPMENT_MEASURED_CHOICE_KIND = "red_development_measured_choice"
DEVELOPMENT_MEASURED_RESULT_SCHEMA = "pokemon.red.development-measured-choice-result.v1"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def development_measured_choice_record_id(choice_id: str) -> str:
    return "dmc-" + canonical_sha256(
        {"choice_id": choice_id, "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA}
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("mapping required")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"field {key!r} must be non-empty string")
    return value


def _validate_hex_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a 64-character lowercase hexadecimal hash")
    return value


@dataclass(frozen=True, slots=True)
class RedDevelopmentMeasuredChoice:
    """An authenticated development-measured observed choice without an action trace.

    Binds:
    - precommitted candidate menu and selected candidate index
    - behavior-model identity
    - before/after registered observations
    - exact parent, terminal, and segment hashes
    - aggregate action, frame, and resource costs

    Explicitly encodes:
    - action_trace_available = False
    - independent_evaluation = False
    - authority_promotion_eligible = False
    - teacher_labels = 0
    - training_only = True
    """

    choice_id: str
    menu: LivingDexOptionMenu
    selected_candidate_index: int
    behavior_probabilities: tuple[float, ...]
    model_sha256: str
    before_observation: Mapping[str, object]
    after_observation: Mapping[str, object]
    parent_state_sha256: str
    terminal_state_sha256: str
    segments_sha256: str
    controller_actions: int
    emulator_frames: int
    resource_costs: Mapping[str, object]
    action_trace_available: bool = False
    independent_evaluation: bool = False
    authority_promotion_eligible: bool = False
    teacher_labels: int = 0
    training_only: bool = True
    selection_seed: int | None = None
    scores: tuple[float | None, ...] = ()
    maximum_actions: int = 30_000
    maximum_frames: int = 3_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.choice_id, str) or not self.choice_id:
            raise ValueError("development measured choice id must be non-empty string")
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise ValueError("development measured choice menu must be LivingDexOptionMenu")
        if len(self.menu.candidates) < 2:
            raise ValueError("development measured choice menu needs at least two candidates")
        if (
            type(self.selected_candidate_index) is not int
            or self.selected_candidate_index not in self.menu.available_indices
        ):
            raise ValueError("development measured choice selected candidate is unavailable")

        if not isinstance(self.behavior_probabilities, tuple) or len(
            self.behavior_probabilities
        ) != len(self.menu.candidates):
            raise ValueError("development measured choice probability length differs")
        if any(
            type(p) not in (float, int) or p < 0.0 or not math.isfinite(p)
            for p in self.behavior_probabilities
        ):
            raise ValueError("development measured choice probabilities must be non-negative")
        if not math.isclose(sum(self.behavior_probabilities), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("development measured choice probabilities must sum to 1.0")
        if self.behavior_probabilities[self.selected_candidate_index] <= 0.0:
            raise ValueError("development measured choice selected candidate probability is zero")

        _validate_hex_sha256(self.model_sha256, "model_sha256")
        _validate_hex_sha256(self.parent_state_sha256, "parent_state_sha256")
        _validate_hex_sha256(self.terminal_state_sha256, "terminal_state_sha256")
        _validate_hex_sha256(self.segments_sha256, "segments_sha256")
        if self.parent_state_sha256 == self.terminal_state_sha256:
            raise ValueError("parent and terminal state hashes must differ")

        if not isinstance(self.before_observation, Mapping) or not isinstance(
            self.after_observation, Mapping
        ):
            raise ValueError("before and after observations must be mappings")
        if (
            self.before_observation.get("schema") != REGISTERED_OBSERVATION_SCHEMA
            or self.after_observation.get("schema") != REGISTERED_OBSERVATION_SCHEMA
        ):
            raise ValueError("observations must use registered observation schema")

        old_reg = RegisteredCollectionCheckpoint.from_public(
            self.before_observation.get("registration")
        )
        new_reg = RegisteredCollectionCheckpoint.from_public(
            self.after_observation.get("registration")
        )
        require_registered_transition(
            old_reg,
            new_reg,
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            require_selected_goal_progress=True,
        )

        old_local = _mapping(self.before_observation.get("semantic_observation"))
        new_local = _mapping(self.after_observation.get("semantic_observation"))
        for local, checkpoint in ((old_local, old_reg), (new_local, new_reg)):
            collection = local.get("collection")
            if collection != {
                "registered": checkpoint.registered_species,
                "registered_target": len(checkpoint.target_species),
                "living": 0,
                "living_target": 0,
                "level_cap": 0,
                "level_cap_target": 0,
            }:
                raise ValueError("observation projected counts differ from checkpoint")

        if type(self.maximum_actions) is not int or self.maximum_actions <= 0:
            raise ValueError("maximum actions must be positive integer")
        if type(self.maximum_frames) is not int or self.maximum_frames <= 0:
            raise ValueError("maximum frames must be positive integer")

        if (
            type(self.controller_actions) is not int
            or self.controller_actions <= 0
            or self.controller_actions > self.maximum_actions
        ):
            raise ValueError("controller actions must be positive integer within bounds")
        if (
            type(self.emulator_frames) is not int
            or self.emulator_frames < 0
            or self.emulator_frames > self.maximum_frames
        ):
            raise ValueError("emulator frames must be non-negative integer within bounds")

        if not isinstance(self.resource_costs, Mapping):
            raise ValueError("resource costs must be a mapping")
        for key, cost_value in self.resource_costs.items():
            if (
                not isinstance(key, str)
                or not isinstance(cost_value, (int, float))
                or isinstance(cost_value, bool)
                or cost_value < 0
            ):
                raise ValueError("resource costs must be non-negative numbers")

        if self.action_trace_available is not False:
            raise ValueError("action_trace_available must be explicitly false")
        if self.independent_evaluation is not False:
            raise ValueError("independent_evaluation must be explicitly false")
        if self.authority_promotion_eligible is not False:
            raise ValueError("authority_promotion_eligible must be explicitly false")
        if type(self.teacher_labels) is not int or self.teacher_labels != 0:
            raise ValueError("teacher_labels must be 0")
        if self.training_only is not True:
            raise ValueError("training_only must be true")

        if self.scores and len(self.scores) != len(self.menu.candidates):
            raise ValueError("scores length must match candidate count")

        if self.selection_seed is not None:
            if type(self.selection_seed) is not int or self.selection_seed < 0:
                raise ValueError("selection seed must be non-negative integer")
            replayed = random.Random(self.selection_seed).choices(
                range(len(self.behavior_probabilities)),
                weights=self.behavior_probabilities,
                k=1,
            )[0]
            if replayed != self.selected_candidate_index:
                raise ValueError("selection seed does not replay the recorded selection")

    @property
    def behavior_model_sha256(self) -> str:
        return self.model_sha256

    @property
    def record_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    @property
    def decision_sha256(self) -> str:
        return canonical_sha256({
            "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA,
            "choice_id": self.choice_id,
            "record_sha256": self.record_sha256,
        })

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA,
            "choice_id": self.choice_id,
            "model_sha256": self.model_sha256,
            "menu": self.menu.policy_dict(),
            "selected_candidate_index": self.selected_candidate_index,
            "behavior_probabilities": list(self.behavior_probabilities),
            "before_observation": dict(self.before_observation),
            "after_observation": dict(self.after_observation),
            "parent_state_sha256": self.parent_state_sha256,
            "terminal_state_sha256": self.terminal_state_sha256,
            "segments_sha256": self.segments_sha256,
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "resource_costs": dict(self.resource_costs),
            "action_trace_available": False,
            "independent_evaluation": False,
            "authority_promotion_eligible": False,
            "teacher_labels": 0,
            "training_only": True,
            "scores": list(self.scores),
            "selection_seed": self.selection_seed,
            "maximum_actions": self.maximum_actions,
            "maximum_frames": self.maximum_frames,
        }

    @classmethod
    def from_public(cls, document: Mapping[str, object]) -> RedDevelopmentMeasuredChoice:
        if (
            not isinstance(document, Mapping)
            or document.get("schema") != DEVELOPMENT_MEASURED_CHOICE_SCHEMA
        ):
            raise ValueError("development measured choice schema differs")
        if document.get("action_trace_available") is not False:
            raise ValueError("action_trace_available must be false")
        if document.get("independent_evaluation") is not False:
            raise ValueError("independent_evaluation must be false")
        if document.get("authority_promotion_eligible") is not False:
            raise ValueError("authority_promotion_eligible must be false")
        if document.get("teacher_labels") != 0 or type(document.get("teacher_labels")) is not int:
            raise ValueError("teacher_labels must be 0")
        if document.get("training_only") is not True:
            raise ValueError("training_only must be true")

        menu = restore_living_dex_policy_menu(_mapping(document["menu"]))
        probabilities = tuple(cast(list[float], document["behavior_probabilities"]))
        scores_raw = document.get("scores", ())
        scores: tuple[float | None, ...] = (
            tuple(cast(list[float | None], scores_raw))
            if isinstance(scores_raw, list)
            else ()
        )
        return cls(
            choice_id=_text(document, "choice_id"),
            menu=menu,
            selected_candidate_index=cast(int, document["selected_candidate_index"]),
            behavior_probabilities=probabilities,
            model_sha256=_validate_hex_sha256(document.get("model_sha256"), "model_sha256"),
            before_observation=_mapping(document["before_observation"]),
            after_observation=_mapping(document["after_observation"]),
            parent_state_sha256=_validate_hex_sha256(
                document.get("parent_state_sha256"), "parent_state_sha256"
            ),
            terminal_state_sha256=_validate_hex_sha256(
                document.get("terminal_state_sha256"), "terminal_state_sha256"
            ),
            segments_sha256=_validate_hex_sha256(
                document.get("segments_sha256"), "segments_sha256"
            ),
            controller_actions=cast(int, document["controller_actions"]),
            emulator_frames=cast(int, document["emulator_frames"]),
            resource_costs=_mapping(document["resource_costs"]),
            action_trace_available=False,
            independent_evaluation=False,
            authority_promotion_eligible=False,
            teacher_labels=0,
            training_only=True,
            selection_seed=cast(int | None, document.get("selection_seed")),
            scores=scores,
            maximum_actions=cast(int, document.get("maximum_actions", 30_000)),
            maximum_frames=cast(int, document.get("maximum_frames", 3_000_000)),
        )

    def to_observed_arm_example(self) -> LivingDexObservedArmExample:
        """Reconstruct the training-only observed arm example for optimizer consumption."""
        outcome = red_registered_outcome_from_observations(
            self.before_observation,
            self.after_observation,
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            succeeded=True,
            actions=self.controller_actions,
            frames=self.emulator_frames,
            maximum_actions=self.maximum_actions,
            maximum_frames=self.maximum_frames,
        )
        return LivingDexObservedArmExample(
            decision_sha256=self.decision_sha256,
            partition="train",
            menu=self.menu,
            selected_candidate_index=self.selected_candidate_index,
            behavior_probabilities=self.behavior_probabilities,
            outcome=outcome,
        )


RedDevelopmentMeasuredObservedChoice = RedDevelopmentMeasuredChoice


@dataclass(frozen=True, slots=True)
class RedDevelopmentMeasuredChoiceInput:
    """Reference binding one stored development-measured choice to its behavior model."""

    choice_id: str
    record_sha256: str
    behavior_record: LivingDexGoalModelRecord | RedPlayerModelRecord


def publish_development_measured_choice(
    store: PrivateArtifactRoot,
    choice: RedDevelopmentMeasuredChoice,
    behavior_record: LivingDexGoalModelRecord | RedPlayerModelRecord,
) -> RedDevelopmentMeasuredChoiceInput:
    """Publish the choice as an immutable sealed record and return its typed input."""
    if choice.model_sha256 != behavior_record.model.model_sha256:
        raise ValueError("choice model sha256 does not match behavior record")
    record = store.publish_sealed_record(
        development_measured_choice_record_id(choice.choice_id),
        kind=DEVELOPMENT_MEASURED_CHOICE_KIND,
        record=choice.public_dict(),
    )
    return RedDevelopmentMeasuredChoiceInput(
        choice_id=choice.choice_id,
        record_sha256=record.summary.record_sha256,
        behavior_record=behavior_record,
    )


def load_red_development_measured_choice_example(
    store: PrivateArtifactRoot,
    item: RedDevelopmentMeasuredChoiceInput,
    *,
    objective: str | None = None,
) -> LivingDexObservedArmExample:
    """Load and authenticate a development-measured choice as a training-only row."""
    if objective not in (None, REGISTERED_OBJECTIVE):
        raise ValueError("development measured choice objective differs")
    record = store.find_sealed_record(
        development_measured_choice_record_id(item.choice_id),
        expected_kind=DEVELOPMENT_MEASURED_CHOICE_KIND,
    )
    if record is None or record.summary.record_sha256 != item.record_sha256:
        raise ValueError("development measured choice record is absent or changed")
    choice = RedDevelopmentMeasuredChoice.from_public(record.read())
    if choice.model_sha256 != item.behavior_record.model.model_sha256:
        raise ValueError("development measured choice model differs from behavior record")
    example = choice.to_observed_arm_example()
    if example.partition != "train":
        raise ValueError("development measured choice must be training-only")
    return example
