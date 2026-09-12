"""Training-only admission of a measured choice without an action journal.

This is deliberately a lower trust tier than a native causal episode. It can
retain an honestly measured development outcome when a model choice, exact
saved-state chain, and before/after observations exist, but the low-level
controller journal does not. Such evidence may affect a development fit; it can
never be called replay verified, used as independent evaluation, or promote
authority on its own.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionMenu,
    LivingDexOptionValueModel,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_player_model import RedPlayerModelRecord
from pokemon_red_completion.red_registered_observation import REGISTERED_OBSERVATION_SCHEMA
from pokemon_red_completion.red_registered_outcome import red_registered_outcome_from_observations
from pokemon_red_completion.red_safari_acquisition import SAFARI_AREA_CHOICE_POLICY
from pokemon_red_completion.registered_checkpoint import (
    RegisteredCollectionCheckpoint,
    require_registered_transition,
)
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

DEVELOPMENT_MEASURED_CHOICE_SCHEMA = "pokemon.red.development-measured-choice.v1"
DEVELOPMENT_MEASURED_SEGMENT_SCHEMA = "pokemon.red.development-measured-segment.v1"
DEVELOPMENT_MEASURED_CHOICE_KIND = "red_development_measured_choice"
DEVELOPMENT_MEASURED_RESULT_SCHEMA = "pokemon.red.development-measured-choice-result.v1"
DEVELOPMENT_MEASURED_TRUST_TIER = "development_measured_without_action_trace"
DEVELOPMENT_MEASURED_NORMALIZATION = "registered-player-v2-30000-actions-3000000-frames"
DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS = 30_000
DEVELOPMENT_MEASURED_MAXIMUM_FRAMES = 3_000_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SEGMENT_STATUSES = frozenset({"retained_exception", "retained_failure", "retained_success"})
_CHOICE_KEYS = {
    "action_trace_available",
    "after_observation",
    "after_observation_sha256",
    "authority_promotion_eligible",
    "before_observation",
    "before_observation_sha256",
    "behavior_probabilities",
    "choice_id",
    "controller_actions",
    "emulator_frames",
    "independent_evaluation",
    "maximum_actions",
    "maximum_frames",
    "menu",
    "menu_sha256",
    "model_sha256",
    "normalization_contract",
    "observed_outcome",
    "observer_source_bundle_sha256",
    "observer_source_commit",
    "parent_checkpoint_sha256",
    "parent_episode_id",
    "parent_state_sha256",
    "policy_id",
    "resource_costs",
    "schema",
    "scores",
    "selection_declaration",
    "selection_declaration_sha256",
    "segments",
    "segments_sha256",
    "selected_candidate_index",
    "selection_seed",
    "teacher_labels",
    "terminal_state_sha256",
    "training_only",
    "trust_tier",
}


def development_measured_choice_record_id(choice_id: str) -> str:
    return "dmc-" + canonical_sha256(
        {"choice_id": choice_id, "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA}
    )


def _mapping(value: object, *, subject: str = "measured choice") -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{subject} must be a mapping")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"measured choice {key} differs")
    return value


def _sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"measured choice {subject} differs")
    return value


def _git_commit(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise ValueError(f"measured choice {subject} differs")
    return value


def _integer(value: object, *, subject: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"measured choice {subject} differs")
    return value


def _float_tuple(value: object, *, subject: str) -> tuple[float, ...]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in value
    ):
        raise ValueError(f"measured choice {subject} differs")
    result = tuple(float(item) for item in value)
    if any(not math.isfinite(item) for item in result):
        raise ValueError(f"measured choice {subject} differs")
    return result


@dataclass(frozen=True, slots=True)
class RedDevelopmentMeasuredSegment:
    """One immutable receipt link in a no-retry continuation chain."""

    pair_id: str
    declaration_sha256: str
    claim_sha256: str
    result_sha256: str
    parent_state_sha256: str
    terminal_state_sha256: str
    controller_actions: int
    emulator_frames: int
    status: str
    retry_allowed: bool = False
    choice_resampled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("measured segment pair identity differs")
        for value, subject in (
            (self.declaration_sha256, "declaration hash"),
            (self.claim_sha256, "claim hash"),
            (self.result_sha256, "result hash"),
            (self.parent_state_sha256, "parent state hash"),
            (self.terminal_state_sha256, "terminal state hash"),
        ):
            _sha256(value, subject=subject)
        _integer(self.controller_actions, subject="segment action count", minimum=1)
        _integer(self.emulator_frames, subject="segment frame count")
        if self.status not in _SEGMENT_STATUSES:
            raise ValueError("measured segment status differs")
        if self.retry_allowed is not False or self.choice_resampled is not False:
            raise ValueError("measured segment must retain one no-retry model choice")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DEVELOPMENT_MEASURED_SEGMENT_SCHEMA,
            "pair_id": self.pair_id,
            "declaration_sha256": self.declaration_sha256,
            "claim_sha256": self.claim_sha256,
            "result_sha256": self.result_sha256,
            "parent_state_sha256": self.parent_state_sha256,
            "terminal_state_sha256": self.terminal_state_sha256,
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "status": self.status,
            "retry_allowed": False,
            "choice_resampled": False,
        }

    @classmethod
    def from_public(cls, document: Mapping[str, object]) -> RedDevelopmentMeasuredSegment:
        expected = {
            "schema",
            "pair_id",
            "declaration_sha256",
            "claim_sha256",
            "result_sha256",
            "parent_state_sha256",
            "terminal_state_sha256",
            "controller_actions",
            "emulator_frames",
            "status",
            "retry_allowed",
            "choice_resampled",
        }
        if (
            set(document) != expected
            or document.get("schema") != DEVELOPMENT_MEASURED_SEGMENT_SCHEMA
        ):
            raise ValueError("measured segment declaration differs")
        return cls(
            pair_id=_text(document, "pair_id"),
            declaration_sha256=_sha256(
                document.get("declaration_sha256"), subject="declaration hash"
            ),
            claim_sha256=_sha256(document.get("claim_sha256"), subject="claim hash"),
            result_sha256=_sha256(document.get("result_sha256"), subject="result hash"),
            parent_state_sha256=_sha256(
                document.get("parent_state_sha256"), subject="parent state hash"
            ),
            terminal_state_sha256=_sha256(
                document.get("terminal_state_sha256"), subject="terminal state hash"
            ),
            controller_actions=_integer(
                document.get("controller_actions"), subject="segment action count", minimum=1
            ),
            emulator_frames=_integer(
                document.get("emulator_frames"), subject="segment frame count"
            ),
            status=_text(document, "status"),
            retry_allowed=cast(bool, document.get("retry_allowed")),
            choice_resampled=cast(bool, document.get("choice_resampled")),
        )


def _replay_behavior(
    model: LivingDexOptionValueModel,
    menu: LivingDexOptionMenu,
    *,
    seed: int,
) -> tuple[tuple[float | None, ...], tuple[float, ...], int]:
    if model.feature_version < menu.feature_version:
        raise ValueError("measured choice behavior feature version differs")
    scores = tuple(model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY))
    available_scores = [scores[index] for index in menu.available_indices]
    if any(value is None or not math.isfinite(value) for value in available_scores):
        raise ValueError("measured choice behavior score differs")
    concrete = [float(value) for value in available_scores if value is not None]
    peak = max(concrete)
    exponentials = [math.exp(value - peak) for value in concrete]
    total = sum(exponentials)
    probabilities = [0.0] * len(menu.candidates)
    for index, value in zip(menu.available_indices, exponentials, strict=True):
        probabilities[index] = 0.75 * value / total + 0.25 / len(exponentials)
    selected = random.Random(seed).choices(
        range(len(probabilities)), weights=probabilities, k=1
    )[0]
    return scores, tuple(probabilities), selected


@dataclass(frozen=True, slots=True)
class RedDevelopmentMeasuredChoice:
    """One lower-trust, training-only selected-arm outcome."""

    choice_id: str
    parent_episode_id: str
    parent_checkpoint_sha256: str
    menu: LivingDexOptionMenu
    selected_candidate_index: int
    behavior_probabilities: tuple[float, ...]
    scores: tuple[float | None, ...]
    selection_seed: int
    selection_declaration: Mapping[str, object]
    selection_declaration_sha256: str
    model_sha256: str
    before_observation: Mapping[str, object]
    after_observation: Mapping[str, object]
    before_observation_sha256: str
    after_observation_sha256: str
    parent_state_sha256: str
    terminal_state_sha256: str
    segments: tuple[RedDevelopmentMeasuredSegment, ...]
    segments_sha256: str
    controller_actions: int
    emulator_frames: int
    resource_costs: Mapping[str, object]
    observer_source_commit: str
    observer_source_bundle_sha256: str
    policy_id: str = SAFARI_AREA_CHOICE_POLICY
    normalization_contract: str = DEVELOPMENT_MEASURED_NORMALIZATION
    maximum_actions: int = DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS
    maximum_frames: int = DEVELOPMENT_MEASURED_MAXIMUM_FRAMES
    action_trace_available: bool = False
    independent_evaluation: bool = False
    authority_promotion_eligible: bool = False
    teacher_labels: int = 0
    training_only: bool = True
    trust_tier: str = DEVELOPMENT_MEASURED_TRUST_TIER

    def __post_init__(self) -> None:
        if not isinstance(self.choice_id, str) or not self.choice_id:
            raise ValueError("measured choice identity differs")
        if not isinstance(self.parent_episode_id, str) or not self.parent_episode_id:
            raise ValueError("measured choice parent episode differs")
        _sha256(self.parent_checkpoint_sha256, subject="parent checkpoint hash")
        if not isinstance(self.menu, LivingDexOptionMenu) or len(self.menu.candidates) < 2:
            raise ValueError("measured choice menu differs")
        if (
            type(self.selected_candidate_index) is not int
            or self.selected_candidate_index not in self.menu.available_indices
        ):
            raise ValueError("measured choice selected candidate differs")
        if (
            not isinstance(self.behavior_probabilities, tuple)
            or len(self.behavior_probabilities) != len(self.menu.candidates)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0.0
                for value in self.behavior_probabilities
            )
            or not math.isclose(
                sum(self.behavior_probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12
            )
        ):
            raise ValueError("measured choice behavior probabilities differ")
        if any(
            (index in self.menu.available_indices) != (probability > 0.0)
            for index, probability in enumerate(self.behavior_probabilities)
        ):
            raise ValueError("measured choice behavior support differs")
        if (
            not isinstance(self.scores, tuple)
            or len(self.scores) != len(self.menu.candidates)
            or any(
                value is not None
                and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                )
                for value in self.scores
            )
        ):
            raise ValueError("measured choice scores differ")
        _integer(self.selection_seed, subject="selection seed")
        _sha256(self.model_sha256, subject="model hash")
        if (
            not self.segments
            or len(self.segments) > 16
            or not all(
                isinstance(segment, RedDevelopmentMeasuredSegment) for segment in self.segments
            )
        ):
            raise ValueError("measured choice segment inventory differs")
        expected_declaration_keys = {
            "capture_quota",
            "maximum_encounters",
            "maximum_semantic_actions",
            "menu_sha256",
            "model_sha256",
            "pair_id",
            "parent_checkpoint_sha256",
            "retry_allowed",
            "schema",
            "seed",
            "selected_candidate_index",
            "source_bundle_sha256",
            "source_commit",
        }
        if (
            not isinstance(self.selection_declaration, Mapping)
            or set(self.selection_declaration) != expected_declaration_keys
            or self.selection_declaration.get("schema")
            != "pokemon.red.private-safari-outcome-declaration.v1"
            or self.selection_declaration.get("pair_id") != self.segments[0].pair_id
            or self.selection_declaration.get("parent_checkpoint_sha256")
            != self.parent_checkpoint_sha256
            or self.selection_declaration.get("model_sha256") != self.model_sha256
            or self.selection_declaration.get("menu_sha256") != self.menu.policy_sha256
            or self.selection_declaration.get("seed") != self.selection_seed
            or self.selection_declaration.get("selected_candidate_index")
            != self.selected_candidate_index
            or self.selection_declaration.get("retry_allowed") is not False
            or self.selection_declaration.get("maximum_semantic_actions") != 300
            or self.selection_declaration.get("maximum_encounters") != 40
            or self.selection_declaration.get("capture_quota") != 1
        ):
            raise ValueError("measured choice pre-input declaration differs")
        _git_commit(
            self.selection_declaration.get("source_commit"),
            subject="selection source commit",
        )
        _sha256(
            self.selection_declaration.get("source_bundle_sha256"),
            subject="selection source bundle",
        )
        _sha256(self.selection_declaration_sha256, subject="selection declaration hash")
        if (
            canonical_sha256(self.selection_declaration)
            != self.selection_declaration_sha256
            or self.selection_declaration_sha256 != self.segments[0].declaration_sha256
        ):
            raise ValueError("measured choice pre-input declaration hash differs")
        for observation, digest, label in (
            (self.before_observation, self.before_observation_sha256, "before observation"),
            (self.after_observation, self.after_observation_sha256, "after observation"),
        ):
            if (
                not isinstance(observation, Mapping)
                or observation.get("schema") != REGISTERED_OBSERVATION_SCHEMA
            ):
                raise ValueError(f"measured choice {label} schema differs")
            _sha256(digest, subject=f"{label} hash")
            if canonical_sha256(observation) != digest:
                raise ValueError(f"measured choice {label} hash differs")
        _sha256(self.parent_state_sha256, subject="parent state hash")
        _sha256(self.terminal_state_sha256, subject="terminal state hash")
        if len({segment.pair_id for segment in self.segments}) != len(self.segments):
            raise ValueError("measured choice segment identity repeats")
        if self.segments[-1].status != "retained_success" or any(
            segment.status == "retained_success" for segment in self.segments[:-1]
        ):
            raise ValueError("measured choice settled segment ordering differs")
        if (
            self.segments[0].parent_state_sha256 != self.parent_state_sha256
            or self.segments[-1].terminal_state_sha256 != self.terminal_state_sha256
        ):
            raise ValueError("measured choice segment endpoints differ")
        if any(
            before.terminal_state_sha256 != after.parent_state_sha256
            for before, after in zip(self.segments, self.segments[1:], strict=False)
        ):
            raise ValueError("measured choice segment chain is discontinuous")
        _sha256(self.segments_sha256, subject="segment inventory hash")
        if (
            canonical_sha256([segment.public_dict() for segment in self.segments])
            != self.segments_sha256
        ):
            raise ValueError("measured choice segment inventory hash differs")
        _integer(self.controller_actions, subject="aggregate action count", minimum=1)
        _integer(self.emulator_frames, subject="aggregate frame count")
        if (
            self.controller_actions != sum(segment.controller_actions for segment in self.segments)
            or self.emulator_frames != sum(segment.emulator_frames for segment in self.segments)
        ):
            raise ValueError("measured choice aggregate costs differ from segments")
        if (
            self.normalization_contract != DEVELOPMENT_MEASURED_NORMALIZATION
            or self.maximum_actions != DEVELOPMENT_MEASURED_MAXIMUM_ACTIONS
            or self.maximum_frames != DEVELOPMENT_MEASURED_MAXIMUM_FRAMES
            or self.controller_actions > self.maximum_actions
            or self.emulator_frames > self.maximum_frames
        ):
            raise ValueError("measured choice fixed normalization differs")
        if not isinstance(self.resource_costs, Mapping):
            raise ValueError("measured choice resource costs differ")
        _git_commit(self.observer_source_commit, subject="observer source commit")
        _sha256(self.observer_source_bundle_sha256, subject="observer source bundle")
        if self.policy_id != SAFARI_AREA_CHOICE_POLICY:
            raise ValueError("measured choice policy differs")
        if (
            self.action_trace_available is not False
            or self.independent_evaluation is not False
            or self.authority_promotion_eligible is not False
            or type(self.teacher_labels) is not int
            or self.teacher_labels != 0
            or self.training_only is not True
            or self.trust_tier != DEVELOPMENT_MEASURED_TRUST_TIER
        ):
            raise ValueError("measured choice trust boundary differs")
        old = RegisteredCollectionCheckpoint.from_public(
            self.before_observation.get("registration")
        )
        new = RegisteredCollectionCheckpoint.from_public(self.after_observation.get("registration"))
        require_registered_transition(
            old,
            new,
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            require_selected_goal_progress=True,
        )
        outcome = self._observed_outcome()
        expected_resources = {
            "irreversible_loss": outcome.irreversible_loss,
            "party_cost": outcome.party_cost,
            "resource_cost": outcome.resource_cost,
            "storage_cost": outcome.storage_cost,
        }
        if dict(self.resource_costs) != expected_resources:
            raise ValueError("measured choice resource costs differ from observations")

    def _observed_outcome(self) -> LivingDexObservedOutcome:
        return red_registered_outcome_from_observations(
            self.before_observation,
            self.after_observation,
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            succeeded=True,
            actions=self.controller_actions,
            frames=self.emulator_frames,
            maximum_actions=self.maximum_actions,
            maximum_frames=self.maximum_frames,
        )

    @property
    def decision_sha256(self) -> str:
        return canonical_sha256(
            {
                "choice_id": self.choice_id,
                "menu_sha256": self.menu.policy_sha256,
                "model_sha256": self.model_sha256,
                "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA,
                "segments_sha256": self.segments_sha256,
            }
        )

    @property
    def record_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DEVELOPMENT_MEASURED_CHOICE_SCHEMA,
            "choice_id": self.choice_id,
            "parent_episode_id": self.parent_episode_id,
            "parent_checkpoint_sha256": self.parent_checkpoint_sha256,
            "policy_id": self.policy_id,
            "menu": self.menu.policy_dict(),
            "menu_sha256": self.menu.policy_sha256,
            "selected_candidate_index": self.selected_candidate_index,
            "behavior_probabilities": list(self.behavior_probabilities),
            "scores": list(self.scores),
            "selection_seed": self.selection_seed,
            "selection_declaration": dict(self.selection_declaration),
            "selection_declaration_sha256": self.selection_declaration_sha256,
            "model_sha256": self.model_sha256,
            "before_observation": dict(self.before_observation),
            "after_observation": dict(self.after_observation),
            "before_observation_sha256": self.before_observation_sha256,
            "after_observation_sha256": self.after_observation_sha256,
            "parent_state_sha256": self.parent_state_sha256,
            "terminal_state_sha256": self.terminal_state_sha256,
            "segments": [segment.public_dict() for segment in self.segments],
            "segments_sha256": self.segments_sha256,
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "resource_costs": dict(self.resource_costs),
            "observed_outcome": self._observed_outcome().public_dict(),
            "observer_source_commit": self.observer_source_commit,
            "observer_source_bundle_sha256": self.observer_source_bundle_sha256,
            "normalization_contract": self.normalization_contract,
            "maximum_actions": self.maximum_actions,
            "maximum_frames": self.maximum_frames,
            "action_trace_available": False,
            "independent_evaluation": False,
            "authority_promotion_eligible": False,
            "teacher_labels": 0,
            "training_only": True,
            "trust_tier": DEVELOPMENT_MEASURED_TRUST_TIER,
        }

    @classmethod
    def from_public(cls, document: Mapping[str, object]) -> RedDevelopmentMeasuredChoice:
        if (
            set(document) != _CHOICE_KEYS
            or document.get("schema") != DEVELOPMENT_MEASURED_CHOICE_SCHEMA
        ):
            raise ValueError("measured choice declaration differs")
        raw_segments = document.get("segments")
        if not isinstance(raw_segments, list):
            raise ValueError("measured choice segment inventory differs")
        menu = restore_living_dex_policy_menu(
            _mapping(document.get("menu"), subject="menu")
        )
        if document.get("menu_sha256") != menu.policy_sha256:
            raise ValueError("measured choice menu hash differs")
        probabilities = _float_tuple(
            document.get("behavior_probabilities"), subject="probabilities"
        )
        raw_scores = document.get("scores")
        if not isinstance(raw_scores, list) or any(
            item is not None
            and (isinstance(item, bool) or not isinstance(item, (int, float)))
            for item in raw_scores
        ):
            raise ValueError("measured choice scores differ")
        choice = cls(
            choice_id=_text(document, "choice_id"),
            parent_episode_id=_text(document, "parent_episode_id"),
            parent_checkpoint_sha256=_sha256(
                document.get("parent_checkpoint_sha256"), subject="parent checkpoint hash"
            ),
            menu=menu,
            selected_candidate_index=_integer(
                document.get("selected_candidate_index"), subject="selected candidate"
            ),
            behavior_probabilities=probabilities,
            scores=tuple(cast(float | None, item) for item in raw_scores),
            selection_seed=_integer(document.get("selection_seed"), subject="selection seed"),
            selection_declaration=_mapping(
                document.get("selection_declaration"), subject="selection declaration"
            ),
            selection_declaration_sha256=_sha256(
                document.get("selection_declaration_sha256"),
                subject="selection declaration hash",
            ),
            model_sha256=_sha256(document.get("model_sha256"), subject="model hash"),
            before_observation=_mapping(
                document.get("before_observation"), subject="before observation"
            ),
            after_observation=_mapping(
                document.get("after_observation"), subject="after observation"
            ),
            before_observation_sha256=_sha256(
                document.get("before_observation_sha256"), subject="before observation hash"
            ),
            after_observation_sha256=_sha256(
                document.get("after_observation_sha256"), subject="after observation hash"
            ),
            parent_state_sha256=_sha256(
                document.get("parent_state_sha256"), subject="parent state hash"
            ),
            terminal_state_sha256=_sha256(
                document.get("terminal_state_sha256"), subject="terminal state hash"
            ),
            segments=tuple(
                RedDevelopmentMeasuredSegment.from_public(_mapping(item, subject="segment"))
                for item in raw_segments
            ),
            segments_sha256=_sha256(
                document.get("segments_sha256"), subject="segment inventory hash"
            ),
            controller_actions=_integer(
                document.get("controller_actions"), subject="aggregate action count", minimum=1
            ),
            emulator_frames=_integer(
                document.get("emulator_frames"), subject="aggregate frame count"
            ),
            resource_costs=_mapping(document.get("resource_costs"), subject="resource costs"),
            observer_source_commit=_git_commit(
                document.get("observer_source_commit"), subject="observer source commit"
            ),
            observer_source_bundle_sha256=_sha256(
                document.get("observer_source_bundle_sha256"),
                subject="observer source bundle",
            ),
            policy_id=_text(document, "policy_id"),
            normalization_contract=_text(document, "normalization_contract"),
            maximum_actions=_integer(
                document.get("maximum_actions"), subject="maximum actions", minimum=1
            ),
            maximum_frames=_integer(
                document.get("maximum_frames"), subject="maximum frames", minimum=1
            ),
            action_trace_available=cast(bool, document.get("action_trace_available")),
            independent_evaluation=cast(bool, document.get("independent_evaluation")),
            authority_promotion_eligible=cast(
                bool, document.get("authority_promotion_eligible")
            ),
            teacher_labels=_integer(
                document.get("teacher_labels"), subject="teacher label count"
            ),
            training_only=cast(bool, document.get("training_only")),
            trust_tier=_text(document, "trust_tier"),
        )
        if document.get("observed_outcome") != choice._observed_outcome().public_dict():
            raise ValueError("measured choice observed outcome differs")
        return choice

    def to_observed_arm_example(self) -> LivingDexObservedArmExample:
        return LivingDexObservedArmExample(
            decision_sha256=self.decision_sha256,
            partition="train",
            menu=self.menu,
            selected_candidate_index=self.selected_candidate_index,
            behavior_probabilities=self.behavior_probabilities,
            outcome=self._observed_outcome(),
        )


RedDevelopmentMeasuredObservedChoice = RedDevelopmentMeasuredChoice


@dataclass(frozen=True, slots=True)
class RedDevelopmentMeasuredChoiceInput:
    choice_id: str
    record_sha256: str
    behavior_record: RedPlayerModelRecord

    def __post_init__(self) -> None:
        if not isinstance(self.choice_id, str) or not self.choice_id:
            raise ValueError("measured choice input identity differs")
        _sha256(self.record_sha256, subject="input record hash")
        if (
            not isinstance(self.behavior_record, RedPlayerModelRecord)
            or self.behavior_record.objective != REGISTERED_OBJECTIVE
        ):
            raise ValueError("measured choice input behavior model differs")


def _validate_behavior(
    choice: RedDevelopmentMeasuredChoice, behavior: RedPlayerModelRecord
) -> None:
    if (
        not isinstance(behavior, RedPlayerModelRecord)
        or behavior.objective != REGISTERED_OBJECTIVE
        or choice.model_sha256 != behavior.model.model_sha256
    ):
        raise ValueError("measured choice behavior model differs")
    scores, probabilities, selected = _replay_behavior(
        behavior.model, choice.menu, seed=choice.selection_seed
    )
    if (
        selected != choice.selected_candidate_index
        or scores != choice.scores
        or any(
            not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
            for actual, expected in zip(
                choice.behavior_probabilities, probabilities, strict=True
            )
        )
    ):
        raise ValueError("measured choice behavior selection does not replay")


def publish_development_measured_choice(
    store: PrivateArtifactRoot,
    choice: RedDevelopmentMeasuredChoice,
    behavior_record: RedPlayerModelRecord,
) -> RedDevelopmentMeasuredChoiceInput:
    _validate_behavior(choice, behavior_record)
    record = store.publish_sealed_record(
        development_measured_choice_record_id(choice.choice_id),
        kind=DEVELOPMENT_MEASURED_CHOICE_KIND,
        record=choice.public_dict(),
    )
    return RedDevelopmentMeasuredChoiceInput(
        choice.choice_id, record.summary.record_sha256, behavior_record
    )


def load_red_development_measured_choice_example(
    store: PrivateArtifactRoot,
    item: RedDevelopmentMeasuredChoiceInput,
    *,
    objective: str | None = None,
) -> LivingDexObservedArmExample:
    if objective != REGISTERED_OBJECTIVE:
        raise ValueError("measured choice requires the registered training objective")
    record = store.find_sealed_record(
        development_measured_choice_record_id(item.choice_id),
        expected_kind=DEVELOPMENT_MEASURED_CHOICE_KIND,
    )
    if record is None or record.summary.record_sha256 != item.record_sha256:
        raise ValueError("measured choice record is absent or changed")
    choice = RedDevelopmentMeasuredChoice.from_public(record.read())
    if choice.choice_id != item.choice_id:
        raise ValueError("measured choice identity differs")
    _validate_behavior(choice, item.behavior_record)
    checkpoint_record = store.find_sealed_record(
        checkpoint_record_id(choice.parent_episode_id), expected_kind=CHECKPOINT_KIND
    )
    if (
        checkpoint_record is None
        or checkpoint_record.summary.record_sha256 != choice.parent_checkpoint_sha256
    ):
        raise ValueError("measured choice parent checkpoint differs")
    checkpoint = checkpoint_record.read()
    if (
        checkpoint.get("state_sha256") != choice.parent_state_sha256
        or checkpoint.get("model_sha256") != choice.model_sha256
        or checkpoint.get("collection") != choice.before_observation.get("registration")
    ):
        raise ValueError("measured choice parent state or observation differs")
    return choice.to_observed_arm_example()
