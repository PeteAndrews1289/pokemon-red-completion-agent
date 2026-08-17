"""Repeatable, identity-free scenario selection for party outcome learning.

The one-shot Red campaign froze evidence before the project knew whether its
questions were useful.  Development needs the opposite trade-off: choose many
independent, non-sealed roots deterministically, vary candidate order and RNG
timing without changing learner-visible state, and rerun failed development
questions without pretending they are sealed observations.

This module is title-neutral.  A game adapter supplies prospectively bound
candidate menus and retains every species, map, party-slot, path, and emulator
binding.  The selector sees only portable features, partition identities, and
content digests.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import TypeVar, cast, overload

from pokemon_red_completion.party import PartyMemberObservation
from pokemon_red_completion.party_development_adapter import (
    BoundPartyDevelopmentMenu,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    EvolutionRouteKind,
    PartyDevelopmentCandidate,
    PartyDevelopmentCandidateSet,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

REPEATABLE_PARTY_SCENARIO_SCHEMA = "pokemon.core.repeatable-party-development-scenario-plan.v1"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BindingT = TypeVar("_BindingT", PartyMemberObservation, GrindingArea)


class RepeatablePartyScenarioError(ValueError):
    """Raised when a scenario pool cannot support an honest learning split."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentScenarioOption:
    """One independently rooted candidate menu available to the selector.

    ``option_id`` is an execution-private lookup key.  It never appears in the
    public plan; only its canonical digest crosses the evidence boundary.
    """

    option_id: str
    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    candidate_set: PartyDevelopmentCandidateSet
    binding: PartyDevelopmentProspectiveBinding

    def __post_init__(self) -> None:
        for value, subject in (
            (self.option_id, "option"),
            (self.root_lineage_id, "root lineage"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise RepeatablePartyScenarioError(
                    f"repeatable party {subject} identity is invalid"
                )
        if (
            not isinstance(self.initial_state_sha256, str)
            or _SHA256.fullmatch(self.initial_state_sha256) is None
        ):
            raise RepeatablePartyScenarioError("repeatable party initial-state digest is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise RepeatablePartyScenarioError("repeatable party partition is invalid")
        if not isinstance(self.candidate_set, PartyDevelopmentCandidateSet):
            raise RepeatablePartyScenarioError("repeatable party candidate set is invalid")
        if not isinstance(self.binding, PartyDevelopmentProspectiveBinding):
            raise RepeatablePartyScenarioError("repeatable party prospective binding is invalid")
        try:
            self.binding.require_candidate_set(self.candidate_set)
        except (TypeError, ValueError) as error:
            raise RepeatablePartyScenarioError(
                "repeatable party option differs from its prospective binding"
            ) from error
        if (
            self.binding.root_lineage_id != self.root_lineage_id
            or self.binding.initial_state_sha256 != self.initial_state_sha256
            or self.binding.partition is not self.partition
            or self.binding.kind is not self.candidate_set.kind
            or self.binding.goal is not self.candidate_set.goal
            or sum(self.binding.candidate_available) < 2
        ):
            raise RepeatablePartyScenarioError(
                "repeatable party option crosses its bound menu or lacks a choice"
            )

    @property
    def option_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": "pokemon.core.repeatable-party-development-option.v1",
                "root_lineage_id": self.root_lineage_id,
                "initial_state_sha256": self.initial_state_sha256,
                "partition": self.partition.value,
                "kind": self.candidate_set.kind.value,
                "goal": self.candidate_set.goal.value,
                "binding_sha256": self.binding.binding_sha256,
            }
        )

    @property
    def available_candidate_count(self) -> int:
        return sum(self.binding.candidate_available)

    @property
    def diversity_tokens(self) -> frozenset[str]:
        """Return coarse semantic coverage without exposing feature values."""

        tokens = {
            f"kind:{self.candidate_set.kind.value}",
            f"goal:{self.candidate_set.goal.value}",
            f"width:{self.available_candidate_count}",
            f"menu:{self.binding.candidate_menu_sha256}",
        }
        hp_index = _feature_index("candidate.hp_ratio")
        pp_index = _feature_index("candidate.attack_pp")
        survival_index = _feature_index("candidate.projected_survival_margin")
        route_indexes = {
            route: _feature_index(f"candidate.evolution_method.{route.value}")
            for route in EvolutionRouteKind
        }
        for candidate, available in zip(
            self.candidate_set.candidates,
            self.binding.candidate_available,
            strict=True,
        ):
            if not available:
                continue
            features = candidate.features
            tokens.add(f"hp:{_unit_bin(features[hp_index])}")
            tokens.add(f"pp:{_unit_bin(features[pp_index])}")
            tokens.add(f"survival:{_signed_bin(features[survival_index])}")
            routes = tuple(
                route.value for route, index in route_indexes.items() if features[index] == 1.0
            )
            if len(routes) != 1:
                raise RepeatablePartyScenarioError(
                    "repeatable party option has invalid evolution semantics"
                )
            tokens.add(f"route:{routes[0]}")
        return frozenset(tokens)


@dataclass(frozen=True, slots=True)
class PartyDevelopmentScenarioAssignment:
    """One deterministic selection and randomization recipe."""

    scenario_id: str
    option_id: str
    option_sha256: str
    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    candidate_order: tuple[int, ...]
    timing_offset_frames: int

    def __post_init__(self) -> None:
        for value, subject in (
            (self.scenario_id, "scenario"),
            (self.option_id, "option"),
            (self.root_lineage_id, "root lineage"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise RepeatablePartyScenarioError(
                    f"repeatable party assignment {subject} is invalid"
                )
        for value, subject in (
            (self.option_sha256, "option"),
            (self.initial_state_sha256, "initial state"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RepeatablePartyScenarioError(
                    f"repeatable party assignment {subject} digest is invalid"
                )
        if (
            not isinstance(self.partition, ScenarioPartition)
            or not isinstance(self.kind, TrainingChoiceKind)
            or not isinstance(self.goal, PartyDevelopmentGoal)
        ):
            raise RepeatablePartyScenarioError("repeatable party assignment semantics are invalid")
        if (
            not isinstance(self.candidate_order, tuple)
            or len(self.candidate_order) < 2
            or set(self.candidate_order) != set(range(len(self.candidate_order)))
        ):
            raise RepeatablePartyScenarioError(
                "repeatable party candidate order is not a permutation"
            )
        if (
            type(self.timing_offset_frames) is not int  # noqa: E721
            or self.timing_offset_frames < 0
        ):
            raise RepeatablePartyScenarioError("repeatable party timing offset is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.repeatable-party-development-assignment.v1",
            "scenario_id": self.scenario_id,
            "option_sha256": self.option_sha256,
            "root_lineage_id": self.root_lineage_id,
            "initial_state_sha256": self.initial_state_sha256,
            "partition": self.partition.value,
            "kind": self.kind.value,
            "goal": self.goal.value,
            "candidate_count": len(self.candidate_order),
            "candidate_order_sha256": canonical_sha256(list(self.candidate_order)),
            "timing_offset_frames": self.timing_offset_frames,
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class RepeatablePartyScenarioPlan:
    """A deterministic independent-root train/development scenario plan."""

    seed: int
    assignments: tuple[PartyDevelopmentScenarioAssignment, ...]

    def __post_init__(self) -> None:
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:  # noqa: E721
            raise RepeatablePartyScenarioError("repeatable party seed is invalid")
        if (
            not isinstance(self.assignments, tuple)
            or not self.assignments
            or any(
                not isinstance(item, PartyDevelopmentScenarioAssignment)
                for item in self.assignments
            )
        ):
            raise RepeatablePartyScenarioError("repeatable party plan needs typed assignments")
        for attribute, subject in (
            ("scenario_id", "scenario"),
            ("option_sha256", "option"),
            ("root_lineage_id", "root lineage"),
            ("initial_state_sha256", "initial state"),
        ):
            values = tuple(getattr(item, attribute) for item in self.assignments)
            if len(values) != len(set(values)):
                raise RepeatablePartyScenarioError(f"repeatable party plan repeats a {subject}")
        roots: dict[str, ScenarioPartition] = {}
        states: dict[str, ScenarioPartition] = {}
        for assignment in self.assignments:
            prior = roots.setdefault(assignment.root_lineage_id, assignment.partition)
            prior_state = states.setdefault(assignment.initial_state_sha256, assignment.partition)
            if prior is not assignment.partition or prior_state is not assignment.partition:
                raise RepeatablePartyScenarioError(
                    "repeatable party plan crosses train/development roots"
                )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        counts = {
            partition.value: sum(item.partition is partition for item in self.assignments)
            for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)
        }
        return {
            "schema": REPEATABLE_PARTY_SCENARIO_SCHEMA,
            "seed": self.seed,
            "assignments": [item.public_dict() for item in self.assignments],
            "partition_counts": counts,
            "unique_root_count": len({item.root_lineage_id for item in self.assignments}),
            "unique_initial_state_count": len(
                {item.initial_state_sha256 for item in self.assignments}
            ),
            "teacher_choice_targets": 0,
            "sealed_test_cases_opened": 0,
            "private_path_fields": 0,
        }


def select_repeatable_party_scenarios(
    options: tuple[PartyDevelopmentScenarioOption, ...],
    *,
    train_count: int,
    development_count: int,
    seed: int,
    maximum_timing_offset_frames: int = 255,
) -> RepeatablePartyScenarioPlan:
    """Greedily cover portable semantics while keeping roots independent."""

    if (
        not isinstance(options, tuple)
        or not options
        or any(not isinstance(item, PartyDevelopmentScenarioOption) for item in options)
    ):
        raise RepeatablePartyScenarioError("repeatable party scenario pool needs typed options")
    if type(seed) is not int or not 0 <= seed < 2**63:  # noqa: E721
        raise RepeatablePartyScenarioError("repeatable party seed is invalid")
    for value, subject in (
        (train_count, "train count"),
        (development_count, "development count"),
    ):
        if type(value) is not int or value < 1:  # noqa: E721
            raise RepeatablePartyScenarioError(f"repeatable party {subject} must be positive")
    if (
        type(maximum_timing_offset_frames) is not int  # noqa: E721
        or maximum_timing_offset_frames < 0
        or maximum_timing_offset_frames > 10_000
    ):
        raise RepeatablePartyScenarioError("repeatable party timing-offset bound is invalid")
    for attribute, subject in (
        ("option_id", "option"),
        ("option_sha256", "option digest"),
    ):
        values = tuple(getattr(item, attribute) for item in options)
        if len(values) != len(set(values)):
            raise RepeatablePartyScenarioError(
                f"repeatable party scenario pool repeats an {subject}"
            )
    root_partitions: dict[str, ScenarioPartition] = {}
    state_partitions: dict[str, ScenarioPartition] = {}
    for option in options:
        prior = root_partitions.setdefault(option.root_lineage_id, option.partition)
        prior_state = state_partitions.setdefault(option.initial_state_sha256, option.partition)
        if prior is not option.partition or prior_state is not option.partition:
            raise RepeatablePartyScenarioError(
                "repeatable party option pool crosses train/development roots"
            )

    chosen: list[PartyDevelopmentScenarioOption] = []
    for partition, count in (
        (ScenarioPartition.TRAIN, train_count),
        (ScenarioPartition.DEVELOPMENT, development_count),
    ):
        partition_options = tuple(item for item in options if item.partition is partition)
        selected = _select_partition(
            partition_options,
            count=count,
            seed=_derived_seed(seed, partition.value),
        )
        kinds = {item.candidate_set.kind for item in selected}
        goals = {item.candidate_set.goal for item in selected}
        if kinds != set(TrainingChoiceKind):
            raise RepeatablePartyScenarioError(
                f"repeatable party {partition.value} selection lacks a choice kind"
            )
        required_goals = min(len(PartyDevelopmentGoal), max(2, count // 4))
        if len(goals) < required_goals:
            raise RepeatablePartyScenarioError(
                f"repeatable party {partition.value} selection lacks goal diversity"
            )
        chosen.extend(selected)

    assignments = []
    counters = {ScenarioPartition.TRAIN: 0, ScenarioPartition.DEVELOPMENT: 0}
    for option in chosen:
        counters[option.partition] += 1
        scenario_id = f"repeatable-party-{option.partition.value}-{counters[option.partition]:03d}"
        rng = random.Random(_derived_seed(seed, option.option_sha256))
        order = list(range(len(option.candidate_set.candidates)))
        rng.shuffle(order)
        timing_offset = rng.randrange(maximum_timing_offset_frames + 1)
        assignments.append(
            PartyDevelopmentScenarioAssignment(
                scenario_id=scenario_id,
                option_id=option.option_id,
                option_sha256=option.option_sha256,
                root_lineage_id=option.root_lineage_id,
                initial_state_sha256=option.initial_state_sha256,
                partition=option.partition,
                kind=option.candidate_set.kind,
                goal=option.candidate_set.goal,
                candidate_order=tuple(order),
                timing_offset_frames=timing_offset,
            )
        )
    return RepeatablePartyScenarioPlan(seed=seed, assignments=tuple(assignments))


@overload
def permute_bound_party_development_menu(
    menu: BoundPartyDevelopmentMenu[PartyMemberObservation],
    candidate_order: tuple[int, ...],
) -> BoundPartyDevelopmentMenu[PartyMemberObservation]: ...


@overload
def permute_bound_party_development_menu(
    menu: BoundPartyDevelopmentMenu[GrindingArea],
    candidate_order: tuple[int, ...],
) -> BoundPartyDevelopmentMenu[GrindingArea]: ...


@overload
def permute_bound_party_development_menu(
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
    ),
    candidate_order: tuple[int, ...],
) -> (
    BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
): ...


def permute_bound_party_development_menu(
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
    ),
    candidate_order: tuple[int, ...],
) -> BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]:
    """Apply one private permutation while preserving candidate equivariance."""

    if not isinstance(menu, BoundPartyDevelopmentMenu):
        raise TypeError("menu must be a BoundPartyDevelopmentMenu")
    count = len(menu.candidate_set.candidates)
    if (
        not isinstance(candidate_order, tuple)
        or len(candidate_order) != count
        or set(candidate_order) != set(range(count))
    ):
        raise RepeatablePartyScenarioError(
            "repeatable party candidate order does not match the menu"
        )
    if menu.candidate_set.kind is TrainingChoiceKind.TRAINEE:
        return _permute_bound_menu(
            cast(BoundPartyDevelopmentMenu[PartyMemberObservation], menu),
            candidate_order,
        )
    return _permute_bound_menu(
        cast(BoundPartyDevelopmentMenu[GrindingArea], menu),
        candidate_order,
    )


def _permute_bound_menu(
    menu: BoundPartyDevelopmentMenu[_BindingT],
    candidate_order: tuple[int, ...],
) -> BoundPartyDevelopmentMenu[_BindingT]:
    reordered_candidates = tuple(
        PartyDevelopmentCandidate(
            candidate_index=new_index,
            features=menu.candidate_set.candidates[old_index].features,
        )
        for new_index, old_index in enumerate(candidate_order)
    )
    return BoundPartyDevelopmentMenu(
        candidate_set=PartyDevelopmentCandidateSet(
            kind=menu.candidate_set.kind,
            goal=menu.candidate_set.goal,
            candidates=reordered_candidates,
        ),
        semantic_snapshot_sha256=menu.semantic_snapshot_sha256,
        bindings=tuple(menu.bindings[index] for index in candidate_order),
        candidate_available=tuple(menu.candidate_available[index] for index in candidate_order),
        candidate_unavailable_reasons=tuple(
            menu.candidate_unavailable_reasons[index] for index in candidate_order
        ),
        venue_priors=tuple(menu.venue_priors[index] for index in candidate_order),
        shared_venue=menu.shared_venue,
        shared_venue_prior=menu.shared_venue_prior,
    )


def _select_partition(
    options: tuple[PartyDevelopmentScenarioOption, ...],
    *,
    count: int,
    seed: int,
) -> tuple[PartyDevelopmentScenarioOption, ...]:
    roots = {item.root_lineage_id for item in options}
    states = {item.initial_state_sha256 for item in options}
    if len(roots) < count or len(states) < count:
        raise RepeatablePartyScenarioError(
            "repeatable party partition has insufficient independent roots"
        )
    rng = random.Random(seed)
    tie_break = {item.option_id: rng.random() for item in options}
    remaining = list(options)
    selected: list[PartyDevelopmentScenarioOption] = []
    used_roots: set[str] = set()
    used_states: set[str] = set()
    coverage: set[str] = set()
    while len(selected) < count:
        eligible = tuple(
            item
            for item in remaining
            if item.root_lineage_id not in used_roots
            and item.initial_state_sha256 not in used_states
        )
        if not eligible:
            raise RepeatablePartyScenarioError(
                "repeatable party selection exhausted independent roots"
            )

        def score(option: PartyDevelopmentScenarioOption) -> tuple[int, int, int, float]:
            tokens = option.diversity_tokens
            kind_token = f"kind:{option.candidate_set.kind.value}"
            goal_token = f"goal:{option.candidate_set.goal.value}"
            return (
                int(kind_token not in coverage),
                int(goal_token not in coverage),
                len(tokens - coverage),
                tie_break[option.option_id],
            )

        choice = max(eligible, key=score)
        selected.append(choice)
        used_roots.add(choice.root_lineage_id)
        used_states.add(choice.initial_state_sha256)
        coverage.update(choice.diversity_tokens)
        remaining.remove(choice)
    return tuple(selected)


def _derived_seed(seed: int, discriminator: str) -> int:
    payload = f"{seed}:{discriminator}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _feature_index(name: str) -> int:
    try:
        return PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)
    except ValueError as error:  # pragma: no cover - frozen vocabulary owns this
        raise RepeatablePartyScenarioError(
            f"repeatable party feature is unavailable: {name}"
        ) from error


def _unit_bin(value: float) -> str:
    if value <= 0.0:
        return "empty"
    if value < 1.0 / 3.0:
        return "low"
    if value < 2.0 / 3.0:
        return "middle"
    return "high"


def _signed_bin(value: float) -> str:
    if value < -1.0 / 3.0:
        return "unsafe"
    if value > 1.0 / 3.0:
        return "safe"
    return "marginal"


__all__ = [
    "PartyDevelopmentScenarioAssignment",
    "PartyDevelopmentScenarioOption",
    "REPEATABLE_PARTY_SCENARIO_SCHEMA",
    "RepeatablePartyScenarioError",
    "RepeatablePartyScenarioPlan",
    "permute_bound_party_development_menu",
    "select_repeatable_party_scenarios",
]
