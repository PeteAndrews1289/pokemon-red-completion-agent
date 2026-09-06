"""Game-neutral long-horizon goal arbitration for transferable Pokemon play.

The existing specialists answer bounded questions such as how to navigate, how
to fight, or how to rotate a trainee.  This module defines the layer above
them: should the player advance the story, acquire a species, train, evolve,
heal, restock, manage storage, recover control, or explore?

The learned boundary is deliberately narrow.  A title adapter may bind a
semantic option to a Red objective or a Crystal task, but the model-facing
projection contains no title, map, objective, species, item, move, coordinate,
party-slot, or candidate-position identity.  Unavailable options are retained
for evidence and hard-masked before selection.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
from pokemon_red_completion.provenance import canonical_sha256

_PARTITIONS = frozenset(
    {"train", "adaptation", "development", "validation", "test", "unassigned"}
)


class GoalManagerError(ValueError):
    """Raised when a goal decision would violate the portable policy contract."""


class GoalNeed(StrEnum):
    """Normalized pressures that recur across mainline Pokemon titles."""

    STORY_PROGRESS = "story_progress"
    COLLECTION_PROGRESS = "collection_progress"
    TEAM_READINESS = "team_readiness"
    EVOLUTION_PROGRESS = "evolution_progress"
    SAFETY = "safety"
    RESOURCES = "resources"
    STORAGE_CAPACITY = "storage_capacity"
    CONTROL_RECOVERY = "control_recovery"
    WORLD_KNOWLEDGE = "world_knowledge"


class GoalKind(StrEnum):
    """Portable high-level intents dispatched to game-specific bindings."""

    ADVANCE_STORY = "advance_story"
    ACQUIRE_SPECIES = "acquire_species"
    DEVELOP_TEAM = "develop_team"
    EVOLVE_SPECIES = "evolve_species"
    RESTORE_TEAM = "restore_team"
    RESUPPLY = "resupply"
    MANAGE_STORAGE = "manage_storage"
    RECOVER_CONTROL = "recover_control"
    EXPLORE = "explore"


class GoalSelectionMode(StrEnum):
    """Whether a choice came from an authority or a forced one-option bridge."""

    AUTHORITY = "authority"
    FORCED_SINGLETON = "forced_singleton"


GOAL_KIND_NEEDS: Mapping[GoalKind, tuple[GoalNeed, ...]] = MappingProxyType(
    {
        GoalKind.ADVANCE_STORY: (GoalNeed.STORY_PROGRESS,),
        GoalKind.ACQUIRE_SPECIES: (GoalNeed.COLLECTION_PROGRESS,),
        GoalKind.DEVELOP_TEAM: (GoalNeed.TEAM_READINESS,),
        GoalKind.EVOLVE_SPECIES: (
            GoalNeed.COLLECTION_PROGRESS,
            GoalNeed.EVOLUTION_PROGRESS,
            GoalNeed.TEAM_READINESS,
        ),
        GoalKind.RESTORE_TEAM: (GoalNeed.SAFETY,),
        GoalKind.RESUPPLY: (GoalNeed.RESOURCES,),
        GoalKind.MANAGE_STORAGE: (
            GoalNeed.COLLECTION_PROGRESS,
            GoalNeed.STORAGE_CAPACITY,
        ),
        GoalKind.RECOVER_CONTROL: (GoalNeed.CONTROL_RECOVERY,),
        GoalKind.EXPLORE: (
            GoalNeed.COLLECTION_PROGRESS,
            GoalNeed.STORY_PROGRESS,
            GoalNeed.WORLD_KNOWLEDGE,
        ),
    }
)


class GoalAvailability(StrEnum):
    """Whether a game adapter can safely bind an option at this decision."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class GoalUnavailableReason(StrEnum):
    """Portable reasons an option is excluded from causal authority."""

    MISSING_CAPABILITY = "missing_capability"
    MISSING_RESOURCE = "missing_resource"
    NO_LEGAL_TARGET = "no_legal_target"
    STORY_GATE_CLOSED = "story_gate_closed"
    STORAGE_BLOCKED = "storage_blocked"
    TEMPORARILY_BLOCKED = "temporarily_blocked"
    WORLD_STATE_UNKNOWN = "world_state_unknown"


class GoalDecisionOutcome(StrEnum):
    """Observed result of one high-level choice."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class GoalFailureReason(StrEnum):
    """Portable failure and censor reasons retained beside a chosen goal."""

    BINDING_FAILED = "binding_failed"
    SEARCH_EXHAUSTED = "search_exhausted"
    EXECUTION_BUDGET_EXHAUSTED = "execution_budget_exhausted"
    EXTERNAL_INTERRUPTION = "external_interruption"
    OUTCOME_NOT_VERIFIED = "outcome_not_verified"
    RESOURCE_LOST = "resource_lost"
    WORLD_STATE_DIVERGED = "world_state_diverged"


_NEED_FIELD = {
    GoalNeed.STORY_PROGRESS: "story_pressure",
    GoalNeed.COLLECTION_PROGRESS: "collection_pressure",
    GoalNeed.TEAM_READINESS: "team_pressure",
    GoalNeed.EVOLUTION_PROGRESS: "evolution_pressure",
    GoalNeed.SAFETY: "safety_pressure",
    GoalNeed.RESOURCES: "resource_pressure",
    GoalNeed.STORAGE_CAPACITY: "storage_pressure",
    GoalNeed.CONTROL_RECOVERY: "recovery_pressure",
    GoalNeed.WORLD_KNOWLEDGE: "exploration_pressure",
}


def _unit_interval(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalManagerError(f"{subject} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise GoalManagerError(f"{subject} must be between zero and one")
    return result


@dataclass(frozen=True, slots=True)
class GoalSituation:
    """Adapter-produced pressures, normalized to the same scale across titles.

    Zero means the need is currently satisfied; one means it is maximally
    urgent under the declared completion contract.  For example, collection
    pressure can come from the remaining living-Pokedex fraction, while team
    pressure can be measured relative to the next declared challenge.  The
    adapter owns those measurements; it may not add title identity.
    """

    story_pressure: float
    collection_pressure: float
    team_pressure: float
    evolution_pressure: float
    safety_pressure: float
    resource_pressure: float
    storage_pressure: float
    recovery_pressure: float
    exploration_pressure: float

    def __post_init__(self) -> None:
        for field_name in _NEED_FIELD.values():
            object.__setattr__(
                self,
                field_name,
                _unit_interval(getattr(self, field_name), subject=field_name),
            )

    @classmethod
    def from_satisfaction(
        cls,
        *,
        story: float,
        collection: float,
        team: float,
        evolution: float,
        safety: float,
        resources: float,
        storage: float,
        control: float,
        world_knowledge: float,
    ) -> GoalSituation:
        """Convert portable completion/safety fractions into need pressure."""

        values = {
            name: _unit_interval(value, subject=f"{name} satisfaction")
            for name, value in {
                "story": story,
                "collection": collection,
                "team": team,
                "evolution": evolution,
                "safety": safety,
                "resources": resources,
                "storage": storage,
                "control": control,
                "world_knowledge": world_knowledge,
            }.items()
        }
        return cls(
            story_pressure=1.0 - values["story"],
            collection_pressure=1.0 - values["collection"],
            team_pressure=1.0 - values["team"],
            evolution_pressure=1.0 - values["evolution"],
            safety_pressure=1.0 - values["safety"],
            resource_pressure=1.0 - values["resources"],
            storage_pressure=1.0 - values["storage"],
            recovery_pressure=1.0 - values["control"],
            exploration_pressure=1.0 - values["world_knowledge"],
        )

    def pressure(self, need: GoalNeed) -> float:
        if not isinstance(need, GoalNeed):
            raise TypeError("need must be a GoalNeed")
        return float(getattr(self, _NEED_FIELD[need]))

    def policy_dict(self) -> dict[str, object]:
        return {
            "need_pressures": {need.value: self.pressure(need) for need in GoalNeed},
            "schema": "pokemon.core.goal-situation.v1",
        }


@dataclass(frozen=True, slots=True)
class GoalOpportunity:
    """One semantic option plus a private execution binding.

    ``binding_ref`` is used only after an index is selected.  The policy sees
    the canonical goal kind, its fixed need mapping, and normalized effort and
    risk estimates.  Fixed kind-to-need semantics prevent an adapter from
    smuggling a teacher label in through hand-authored "expected utility."
    """

    binding_ref: str
    kind: GoalKind
    availability: GoalAvailability
    estimated_effort: float | None = None
    estimated_risk: float | None = None
    unavailable_reason: GoalUnavailableReason | None = None
    resource_quote: GoalResourceQuote | None = None
    search_history: GoalSearchHistory | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise GoalManagerError("a goal opportunity needs a binding reference")
        if not isinstance(self.kind, GoalKind):
            raise GoalManagerError("goal opportunity kind is unsupported")
        if self.search_history is not None and (
            not isinstance(self.search_history, GoalSearchHistory)
            or self.kind is not GoalKind.ACQUIRE_SPECIES
        ):
            raise GoalManagerError("search history requires an acquisition goal")
        if not isinstance(self.availability, GoalAvailability):
            raise GoalManagerError("goal opportunity availability is unsupported")
        if self.resource_quote is not None and (
            not isinstance(self.resource_quote, GoalResourceQuote)
            or self.availability is not GoalAvailability.AVAILABLE
            or self.kind is not GoalKind.RESUPPLY
        ):
            raise GoalManagerError("resource quote requires an available resupply goal")
        if self.availability is GoalAvailability.AVAILABLE:
            if self.estimated_effort is None or self.estimated_risk is None:
                raise GoalManagerError(
                    "an available goal opportunity needs effort and risk estimates"
                )
            object.__setattr__(
                self,
                "estimated_effort",
                _unit_interval(self.estimated_effort, subject="estimated effort"),
            )
            object.__setattr__(
                self,
                "estimated_risk",
                _unit_interval(self.estimated_risk, subject="estimated risk"),
            )
            if self.unavailable_reason is not None:
                raise GoalManagerError(
                    "an available goal opportunity cannot have an unavailable reason"
                )
        else:
            if self.estimated_effort is not None or self.estimated_risk is not None:
                raise GoalManagerError(
                    "an unavailable goal opportunity cannot advertise effort or risk"
                )
            if not isinstance(self.unavailable_reason, GoalUnavailableReason):
                raise GoalManagerError("an unavailable goal opportunity needs a semantic reason")

    @property
    def addressed_needs(self) -> tuple[GoalNeed, ...]:
        return GOAL_KIND_NEEDS[self.kind]

    def policy_dict(self) -> dict[str, object]:
        """Return the model-facing view, intentionally omitting the binding."""

        result: dict[str, object] = {
            "addressed_needs": [need.value for need in self.addressed_needs],
            "availability": self.availability.value,
            "estimated_effort": self.estimated_effort,
            "estimated_risk": self.estimated_risk,
            "kind": self.kind.value,
            "unavailable_reason": (
                None if self.unavailable_reason is None else self.unavailable_reason.value
            ),
        }
        if self.resource_quote is not None:
            result["resource_quote"] = self.resource_quote.public_dict()
        if self.search_history is not None:
            result["search_history"] = self.search_history.public_dict()
        return result


@dataclass(frozen=True, slots=True)
class GoalManagerQuestion:
    """One unlabeled, variable-sized high-level decision."""

    situation: GoalSituation
    opportunities: tuple[GoalOpportunity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.situation, GoalSituation):
            raise GoalManagerError("goal-manager situation is invalid")
        if not isinstance(self.opportunities, tuple) or len(self.opportunities) < 2:
            raise GoalManagerError("goal manager needs at least two immutable options")
        if any(not isinstance(item, GoalOpportunity) for item in self.opportunities):
            raise GoalManagerError("goal-manager opportunity is invalid")
        bindings = tuple(item.binding_ref for item in self.opportunities)
        if len(set(bindings)) != len(bindings):
            raise GoalManagerError("goal-manager bindings must be unique")
        kinds = tuple(item.kind for item in self.opportunities)
        if len(set(kinds)) != len(kinds):
            raise GoalManagerError(
                "goal manager accepts one option per kind; destination choice belongs below it"
            )
        if not self.available_indices:
            raise GoalManagerError("goal manager needs at least one available option")

    @classmethod
    def from_policy_input(cls, value: Mapping[str, object]) -> GoalManagerQuestion:
        """Reconstruct an identity-free recorded question with inert bindings."""

        if (
            set(value) != {"candidates", "schema", "situation"}
            or value.get("schema") not in {
                "pokemon.core.goal-manager-input.v1", "pokemon.core.goal-manager-input.v2",
                "pokemon.core.goal-manager-input.v3",
            }
        ):
            raise GoalManagerError("goal-manager policy input schema is invalid")
        situation_raw = value.get("situation")
        if (
            not isinstance(situation_raw, Mapping)
            or set(situation_raw)
            != {
                "need_pressures",
                "schema",
            }
            or situation_raw.get("schema") != "pokemon.core.goal-situation.v1"
        ):
            raise GoalManagerError("goal-manager situation schema is invalid")
        pressures_raw = situation_raw.get("need_pressures")
        if not isinstance(pressures_raw, Mapping) or set(pressures_raw) != {
            need.value for need in GoalNeed
        }:
            raise GoalManagerError("goal-manager need-pressure schema is invalid")
        pressures = {
            _NEED_FIELD[need]: _unit_interval(
                pressures_raw.get(need.value),
                subject=f"{need.value} pressure",
            )
            for need in GoalNeed
        }
        candidates_raw = value.get("candidates")
        if not isinstance(candidates_raw, (list, tuple)):
            raise GoalManagerError("goal-manager candidate collection is invalid")
        opportunities: list[GoalOpportunity] = []
        for index, raw in enumerate(candidates_raw):
            expected_keys = {
                "addressed_needs",
                "availability",
                "estimated_effort",
                "estimated_risk",
                "kind",
                "unavailable_reason",
            }
            if (
                isinstance(raw, Mapping)
                and value["schema"] in {
                    "pokemon.core.goal-manager-input.v2", "pokemon.core.goal-manager-input.v3"
                }
                and "resource_quote" in raw
            ):
                expected_keys.add("resource_quote")
            if (
                isinstance(raw, Mapping)
                and value["schema"] == "pokemon.core.goal-manager-input.v3"
                and "search_history" in raw
            ):
                expected_keys.add("search_history")
            if not isinstance(raw, Mapping) or set(raw) != expected_keys:
                raise GoalManagerError("goal-manager candidate schema is invalid")
            kind_raw = raw.get("kind")
            availability_raw = raw.get("availability")
            if not isinstance(kind_raw, str) or not isinstance(availability_raw, str):
                raise GoalManagerError("goal-manager candidate vocabulary is invalid")
            try:
                kind = GoalKind(kind_raw)
                availability = GoalAvailability(availability_raw)
            except (TypeError, ValueError) as error:
                raise GoalManagerError("goal-manager candidate vocabulary is invalid") from error
            addressed = raw.get("addressed_needs")
            if not isinstance(addressed, (list, tuple)) or tuple(addressed) != tuple(
                need.value for need in GOAL_KIND_NEEDS[kind]
            ):
                raise GoalManagerError("goal-manager candidate need mapping is invalid")
            reason_raw = raw.get("unavailable_reason")
            try:
                reason = None if reason_raw is None else GoalUnavailableReason(reason_raw)
            except (TypeError, ValueError) as error:
                raise GoalManagerError("goal-manager unavailable reason is invalid") from error
            opportunities.append(
                GoalOpportunity(
                    binding_ref=f"recorded-policy-candidate:{index}",
                    kind=kind,
                    availability=availability,
                    estimated_effort=raw.get("estimated_effort"),
                    estimated_risk=raw.get("estimated_risk"),
                    unavailable_reason=reason,
                    resource_quote=(
                        GoalResourceQuote.from_public_dict(raw["resource_quote"])
                        if "resource_quote" in raw else None
                    ),
                    search_history=(GoalSearchHistory.from_public_dict(raw["search_history"])
                                    if "search_history" in raw else None),
                )
            )
        result = cls(
            situation=GoalSituation(**pressures),
            opportunities=tuple(opportunities),
        )
        if result.policy_input["schema"] != value["schema"]:
            raise GoalManagerError("resource quote input version differs")
        return result

    @property
    def available_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, item in enumerate(self.opportunities)
            if item.availability is GoalAvailability.AVAILABLE
        )

    @property
    def policy_input(self) -> Mapping[str, object]:
        """Identity-free model input; bindings remain on ``opportunities``."""

        return MappingProxyType(
            {
                "candidates": tuple(
                    MappingProxyType(item.policy_dict()) for item in self.opportunities
                ),
                "schema": (
                    "pokemon.core.goal-manager-input.v3"
                    if any(item.search_history is not None for item in self.opportunities)
                    else
                    "pokemon.core.goal-manager-input.v2"
                    if any(item.resource_quote is not None for item in self.opportunities)
                    else "pokemon.core.goal-manager-input.v1"
                ),
                "situation": MappingProxyType(self.situation.policy_dict()),
            }
        )

    @property
    def ordered_policy_input_sha256(self) -> str:
        return canonical_sha256(_thaw(self.policy_input))

    @property
    def policy_context_sha256(self) -> str:
        """Hash an input independently of candidate order and private bindings."""

        thawed = _thaw(self.policy_input)
        if not isinstance(thawed, dict):  # pragma: no cover - constructed above
            raise AssertionError("goal-manager policy input did not thaw to an object")
        value: dict[str, object] = thawed
        candidates = value.get("candidates")
        if not isinstance(candidates, list):  # pragma: no cover - constructed above
            raise AssertionError("goal-manager candidates did not thaw to a list")
        value["candidates"] = sorted(candidates, key=canonical_sha256)
        return canonical_sha256(value)

    @property
    def candidate_menu_sha256(self) -> str:
        """Hash only the multiset of goal kinds, ignoring state and metrics."""

        return canonical_sha256(
            {
                "goal_kinds": sorted(item.kind.value for item in self.opportunities),
                "schema": "pokemon.core.goal-menu.v1",
            }
        )

    @property
    def available_menu_sha256(self) -> str:
        """Hash the executable semantic menu while ignoring order and bindings."""

        return canonical_sha256(
            {
                "available_goal_kinds": sorted(
                    item.kind.value
                    for item in self.opportunities
                    if item.availability is GoalAvailability.AVAILABLE
                ),
                "schema": "pokemon.core.available-goal-menu.v1",
            }
        )


@dataclass(frozen=True, slots=True)
class BoundGoalSelection:
    """A model index rebound to the adapter-private execution identity."""

    selected_index: int
    binding_ref: str
    kind: GoalKind


def bind_goal_selection(
    question: GoalManagerQuestion,
    selected_index: int,
) -> BoundGoalSelection:
    """Fail closed if a scorer selects an invalid or masked candidate."""

    if not isinstance(question, GoalManagerQuestion):
        raise TypeError("question must be a GoalManagerQuestion")
    if type(selected_index) is not int or selected_index not in range(  # noqa: E721
        len(question.opportunities)
    ):
        raise GoalManagerError("goal-manager selection index is invalid")
    opportunity = question.opportunities[selected_index]
    if opportunity.availability is not GoalAvailability.AVAILABLE:
        raise GoalManagerError("goal-manager selection is unavailable")
    return BoundGoalSelection(
        selected_index=selected_index,
        binding_ref=opportunity.binding_ref,
        kind=opportunity.kind,
    )


@dataclass(frozen=True, slots=True)
class GoalManagerExample:
    """One provenance-bearing choice and observed outcome.

    ``environment_id`` is retained for grouped and held-out-title audits but is
    structurally absent from :attr:`GoalManagerQuestion.policy_input`.
    """

    decision_id: str
    episode_id: str
    decision_index: int
    root_lineage_id: str
    partition: str
    environment_id: str
    actor: str
    policy_id: str
    question: GoalManagerQuestion
    selected_candidate_index: int
    outcome_status: GoalDecisionOutcome
    failure_reason: GoalFailureReason | None = None
    behavior_policy_id: str | None = None
    behavior_probability: float | None = None
    behavior_candidate_probabilities: tuple[float, ...] | None = None
    behavior_base_probability: float | None = None
    behavior_exploration_mix: float | None = None
    behavior_temperature: float | None = None
    selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY

    def __post_init__(self) -> None:
        for field_name in (
            "decision_id",
            "episode_id",
            "root_lineage_id",
            "partition",
            "environment_id",
            "actor",
            "policy_id",
        ):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name):
                raise GoalManagerError(f"{field_name} must be non-empty")
        if self.partition not in _PARTITIONS:
            raise GoalManagerError("goal-manager partition is unsupported")
        if not isinstance(self.selection_mode, GoalSelectionMode):
            raise GoalManagerError("goal-manager selection mode is invalid")
        if type(self.decision_index) is not int or self.decision_index < 0:  # noqa: E721
            raise GoalManagerError("goal-manager decision index is invalid")
        if not isinstance(self.question, GoalManagerQuestion):
            raise GoalManagerError("goal-manager example question is invalid")
        bind_goal_selection(self.question, self.selected_candidate_index)
        if not isinstance(self.outcome_status, GoalDecisionOutcome):
            raise GoalManagerError("goal-manager outcome is invalid")
        if self.outcome_status is GoalDecisionOutcome.SUCCEEDED:
            if self.failure_reason is not None:
                raise GoalManagerError(
                    "a successful goal-manager example cannot have a failure reason"
                )
        elif not isinstance(self.failure_reason, GoalFailureReason):
            raise GoalManagerError("a failed or interrupted goal-manager example needs a reason")
        behavior_values = (
            self.behavior_probability,
            self.behavior_candidate_probabilities,
            self.behavior_base_probability,
            self.behavior_exploration_mix,
            self.behavior_temperature,
        )
        if (self.behavior_policy_id is None) != all(
            value is None for value in behavior_values
        ):
            raise GoalManagerError(
                "goal-manager behavior identity and metadata must be recorded together"
            )
        if self.behavior_policy_id is not None and (
            not isinstance(self.behavior_policy_id, str)
            or not self.behavior_policy_id
            or isinstance(self.behavior_probability, bool)
            or not isinstance(self.behavior_probability, (int, float))
            or not math.isfinite(float(self.behavior_probability))
            or not 0.0 < float(self.behavior_probability) <= 1.0
        ):
            raise GoalManagerError("goal-manager behavior policy metadata is invalid")
        if self.behavior_probability is not None:
            object.__setattr__(self, "behavior_probability", float(self.behavior_probability))
            probabilities = self.behavior_candidate_probabilities
            if (
                not isinstance(probabilities, tuple)
                or len(probabilities) != len(self.question.opportunities)
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                    for value in probabilities
                )
                or abs(sum(float(value) for value in probabilities) - 1.0) > 1e-9
                or float(probabilities[self.selected_candidate_index])
                != self.behavior_probability
                or any(
                    float(probabilities[index]) != 0.0
                    for index in range(len(probabilities))
                    if index not in self.question.available_indices
                )
            ):
                raise GoalManagerError(
                    "goal-manager behavior candidate probabilities are invalid"
                )
            normalized_behavior_values: list[float] = []
            for value, subject, lower_inclusive in (
                (self.behavior_base_probability, "base probability", True),
                (self.behavior_exploration_mix, "exploration mix", True),
                (self.behavior_temperature, "temperature", False),
            ):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or (lower_inclusive and not 0.0 <= float(value) <= 1.0)
                    or (not lower_inclusive and float(value) <= 0.0)
                ):
                    raise GoalManagerError(
                        f"goal-manager behavior {subject} is invalid"
                    )
                normalized_behavior_values.append(float(value))
            object.__setattr__(
                self,
                "behavior_candidate_probabilities",
                tuple(float(value) for value in probabilities),
            )
            object.__setattr__(
                self,
                "behavior_base_probability",
                normalized_behavior_values[0],
            )
            object.__setattr__(
                self,
                "behavior_exploration_mix",
                normalized_behavior_values[1],
            )
            object.__setattr__(
                self,
                "behavior_temperature",
                normalized_behavior_values[2],
            )

    @property
    def teacher_choice_target(self) -> int | None:
        if (
            self.selection_mode is GoalSelectionMode.AUTHORITY
            and self.actor == "deterministic_teacher"
            and self.outcome_status is GoalDecisionOutcome.SUCCEEDED
        ):
            return self.selected_candidate_index
        return None

    @property
    def selected_kind(self) -> GoalKind:
        return self.question.opportunities[self.selected_candidate_index].kind

    @property
    def selected_candidate_sha256(self) -> str:
        return canonical_sha256(
            self.question.opportunities[self.selected_candidate_index].policy_dict()
        )


@dataclass(frozen=True, slots=True)
class GoalCurriculumRequirements:
    """Prospective admission thresholds for a genuinely multi-need curriculum."""

    required_needs: tuple[GoalNeed, ...] = tuple(GoalNeed)
    required_selected_goal_kinds: tuple[GoalKind, ...] = tuple(GoalKind)
    minimum_train_examples: int = 54
    minimum_validation_examples: int = 27
    minimum_train_examples_per_need: int = 6
    minimum_validation_examples_per_need: int = 3
    minimum_train_selections_per_kind: int = 4
    minimum_validation_selections_per_kind: int = 2
    minimum_multiway_train_examples: int = 24
    minimum_context_dependent_menus: int = 3
    active_pressure_threshold: float = 0.5
    held_out_environment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.required_needs
            or len(set(self.required_needs)) != len(self.required_needs)
            or any(not isinstance(item, GoalNeed) for item in self.required_needs)
        ):
            raise GoalManagerError("required goal needs must be unique and typed")
        if (
            not self.required_selected_goal_kinds
            or len(set(self.required_selected_goal_kinds)) != len(self.required_selected_goal_kinds)
            or any(not isinstance(item, GoalKind) for item in self.required_selected_goal_kinds)
        ):
            raise GoalManagerError("required goal kinds must be unique and typed")
        for field_name in (
            "minimum_train_examples",
            "minimum_validation_examples",
            "minimum_train_examples_per_need",
            "minimum_validation_examples_per_need",
            "minimum_train_selections_per_kind",
            "minimum_validation_selections_per_kind",
            "minimum_multiway_train_examples",
            "minimum_context_dependent_menus",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise GoalManagerError(f"{field_name} must be a non-negative integer")
        object.__setattr__(
            self,
            "active_pressure_threshold",
            _unit_interval(
                self.active_pressure_threshold,
                subject="active pressure threshold",
            ),
        )
        if len(set(self.held_out_environment_ids)) != len(self.held_out_environment_ids) or any(
            not isinstance(item, str) or not item for item in self.held_out_environment_ids
        ):
            raise GoalManagerError("held-out environment identities are invalid")


@dataclass(frozen=True, slots=True)
class GoalCurriculumAudit:
    """Leakage, coverage, and shortcut audit before manager fitting."""

    examples: int
    teacher_choice_examples: int
    replicated_teacher_choice_example_count: int
    partition_teacher_choice_counts: tuple[tuple[str, int], ...]
    environment_partition_counts: tuple[tuple[str, str, int], ...]
    train_need_counts: tuple[tuple[str, int], ...]
    validation_need_counts: tuple[tuple[str, int], ...]
    train_selected_kind_counts: tuple[tuple[str, int], ...]
    validation_selected_kind_counts: tuple[tuple[str, int], ...]
    multiway_train_examples: int
    context_dependent_menu_count: int
    selected_train_position_counts: tuple[tuple[int, int], ...]
    train_validation_context_overlap_count: int
    context_target_conflict_count: int
    ready_for_training: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-curriculum-audit.v1",
            "examples": self.examples,
            "teacher_choice_examples": self.teacher_choice_examples,
            "replicated_teacher_choice_example_count": (
                self.replicated_teacher_choice_example_count
            ),
            "partition_teacher_choice_counts": dict(self.partition_teacher_choice_counts),
            "environment_partition_counts": [
                {"environment": environment, "partition": partition, "count": count}
                for environment, partition, count in self.environment_partition_counts
            ],
            "train_need_counts": dict(self.train_need_counts),
            "validation_need_counts": dict(self.validation_need_counts),
            "train_selected_kind_counts": dict(self.train_selected_kind_counts),
            "validation_selected_kind_counts": dict(self.validation_selected_kind_counts),
            "multiway_train_examples": self.multiway_train_examples,
            "context_dependent_menu_count": self.context_dependent_menu_count,
            "selected_train_position_counts": {
                str(index): count for index, count in self.selected_train_position_counts
            },
            "train_validation_context_overlap_count": (self.train_validation_context_overlap_count),
            "context_target_conflict_count": self.context_target_conflict_count,
            "model_input_excludes_environment_identity": True,
            "model_input_excludes_binding_identity": True,
            "ready_for_training": self.ready_for_training,
            "reasons": list(self.reasons),
        }


def audit_goal_curriculum(
    examples: Iterable[GoalManagerExample],
    *,
    requirements: GoalCurriculumRequirements | None = None,
) -> GoalCurriculumAudit:
    """Audit whole-lineage splits and require evidence of context dependence."""

    rows = tuple(examples)
    rules = requirements or GoalCurriculumRequirements()
    if any(not isinstance(item, GoalManagerExample) for item in rows):
        raise TypeError("goal curriculum contains an invalid example")
    reasons: list[str] = []

    decisions = [item.decision_id for item in rows]
    if len(decisions) != len(set(decisions)):
        reasons.append("duplicate_decision_id")

    root_partitions: defaultdict[str, set[str]] = defaultdict(set)
    root_environments: defaultdict[str, set[str]] = defaultdict(set)
    for item in rows:
        root_partitions[item.root_lineage_id].add(item.partition)
        root_environments[item.root_lineage_id].add(item.environment_id)
    if any(len(values) != 1 for values in root_partitions.values()):
        reasons.append("root_lineage_crosses_partitions")
    if any(len(values) != 1 for values in root_environments.values()):
        reasons.append("root_lineage_crosses_environments")
    if any(item.partition == "unassigned" for item in rows):
        reasons.append("unassigned_example")

    teacher = tuple(item for item in rows if item.teacher_choice_target is not None)
    by_partition = Counter(item.partition for item in teacher)
    if by_partition["train"] < rules.minimum_train_examples:
        reasons.append("insufficient_train_teacher_choices")
    if by_partition["validation"] < rules.minimum_validation_examples:
        reasons.append("insufficient_validation_teacher_choices")

    partition_contexts: defaultdict[str, set[str]] = defaultdict(set)
    targets_by_context: defaultdict[str, set[str]] = defaultdict(set)
    for item in teacher:
        context = item.question.policy_context_sha256
        partition_contexts[item.partition].add(context)
        targets_by_context[context].add(item.selected_candidate_sha256)
    unique_partition_context_count = sum(len(values) for values in partition_contexts.values())
    replicated = len(teacher) - unique_partition_context_count
    if replicated:
        reasons.append("replicated_policy_context")
    overlap = len(partition_contexts["train"] & partition_contexts["validation"])
    if overlap:
        reasons.append("train_validation_policy_context_overlap")
    conflicts = sum(len(targets) > 1 for targets in targets_by_context.values())
    if conflicts:
        reasons.append("policy_context_has_conflicting_teacher_target")

    need_counts: dict[str, Counter[GoalNeed]] = {
        "train": Counter(),
        "validation": Counter(),
    }
    selected_counts: dict[str, Counter[GoalKind]] = {
        "train": Counter(),
        "validation": Counter(),
    }
    for item in teacher:
        if item.partition not in need_counts:
            continue
        for need in GoalNeed:
            if item.question.situation.pressure(need) >= rules.active_pressure_threshold:
                need_counts[item.partition][need] += 1
        selected_counts[item.partition][item.selected_kind] += 1

    for need in rules.required_needs:
        if need_counts["train"][need] < rules.minimum_train_examples_per_need:
            reasons.append(f"insufficient_train_need:{need.value}")
        if need_counts["validation"][need] < rules.minimum_validation_examples_per_need:
            reasons.append(f"insufficient_validation_need:{need.value}")
    for kind in rules.required_selected_goal_kinds:
        if selected_counts["train"][kind] < rules.minimum_train_selections_per_kind:
            reasons.append(f"insufficient_train_selected_kind:{kind.value}")
        if selected_counts["validation"][kind] < rules.minimum_validation_selections_per_kind:
            reasons.append(f"insufficient_validation_selected_kind:{kind.value}")

    multiway_train = sum(
        item.partition == "train" and len(item.question.available_indices) >= 3 for item in teacher
    )
    if multiway_train < rules.minimum_multiway_train_examples:
        reasons.append("insufficient_multiway_train_choices")

    menu_targets: defaultdict[str, set[GoalKind]] = defaultdict(set)
    for item in teacher:
        if item.partition == "train":
            menu_targets[item.question.available_menu_sha256].add(item.selected_kind)
    context_dependent_menus = sum(len(targets) >= 2 for targets in menu_targets.values())
    if context_dependent_menus < rules.minimum_context_dependent_menus:
        reasons.append("candidate_menus_do_not_require_context")

    selected_positions = Counter(
        item.selected_candidate_index for item in teacher if item.partition == "train"
    )
    if len(selected_positions) < 2:
        reasons.append("selected_candidate_position_not_diverse")

    environment_partitions = Counter((item.environment_id, item.partition) for item in teacher)
    for environment_id in rules.held_out_environment_ids:
        if environment_partitions[(environment_id, "train")]:
            reasons.append(f"held_out_environment_used_for_training:{environment_id}")
        if not (
            environment_partitions[(environment_id, "validation")]
            or environment_partitions[(environment_id, "test")]
        ):
            reasons.append(f"held_out_environment_has_no_evaluation:{environment_id}")

    return GoalCurriculumAudit(
        examples=len(rows),
        teacher_choice_examples=len(teacher),
        replicated_teacher_choice_example_count=replicated,
        partition_teacher_choice_counts=tuple(sorted(by_partition.items())),
        environment_partition_counts=tuple(
            (environment, partition, count)
            for (environment, partition), count in sorted(environment_partitions.items())
        ),
        train_need_counts=tuple((need.value, need_counts["train"][need]) for need in GoalNeed),
        validation_need_counts=tuple(
            (need.value, need_counts["validation"][need]) for need in GoalNeed
        ),
        train_selected_kind_counts=tuple(
            (kind.value, selected_counts["train"][kind]) for kind in GoalKind
        ),
        validation_selected_kind_counts=tuple(
            (kind.value, selected_counts["validation"][kind]) for kind in GoalKind
        ),
        multiway_train_examples=multiway_train,
        context_dependent_menu_count=context_dependent_menus,
        selected_train_position_counts=tuple(sorted(selected_positions.items())),
        train_validation_context_overlap_count=overlap,
        context_target_conflict_count=conflicts,
        ready_for_training=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
