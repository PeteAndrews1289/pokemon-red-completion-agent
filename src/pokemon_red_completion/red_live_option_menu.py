"""Opt-in mixed-family Red menu for the learned living-Dex policy.

The established goal manager intentionally permits one candidate per semantic
goal kind; destination selection lives below that boundary.  Late collection
can nevertheless expose several concrete acquisition mechanisms at the same
time as recovery and funding.  This module joins those already-authenticated
private bindings to one variable-size :class:`LivingDexOptionMenu` without
placing map, species, route, or binding identity in the model input.

Construction and selection are action-free.  The selected
``ExecutableGoalBinding`` is returned privately to a caller, which remains
responsible for durable decision recording, bounded execution, independent
verification, and outcome fitting.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from pokemon_red_completion.goal_manager import GoalKind, GoalSituation
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    ExecutableGoalBinding,
    GoalBindingSet,
)
from pokemon_red_completion.living_dex_goal_policy import (
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
    living_dex_option_kind_for_goal,
    project_living_dex_goal_candidate,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionMenu,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.resource_economy_observation import EconomySnapshot

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLiveOptionMenuError(ValueError):
    """A mixed live menu would cross its policy or execution boundary."""


class RedLiveOptionSelectionMode(StrEnum):
    """Whether hard safety or the learned model selected the private binding."""

    DETERMINISTIC_SAFETY = "deterministic_safety"
    MODEL_EXPLORATION = "model_exploration"


@dataclass(frozen=True, slots=True)
class RedLiveSupplementalOption:
    """One extra private executor and its identity-free policy candidate."""

    binding: ExecutableGoalBinding
    candidate: LivingDexOptionCandidate

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ExecutableGoalBinding):
            raise TypeError("supplemental option needs an executable goal binding")
        if not isinstance(self.candidate, LivingDexOptionCandidate):
            raise TypeError("supplemental option needs a living-Dex candidate")
        if (
            self.candidate.binding_ref != self.binding.binding_ref
            or self.candidate.availability is not LivingDexOptionAvailability.AVAILABLE
        ):
            raise RedLiveOptionMenuError(
                "supplemental candidate and executable binding differ"
            )


@dataclass(frozen=True, slots=True)
class RedLiveOptionSet:
    """One policy-safe menu aligned exactly with private executable bindings."""

    situation: GoalSituation
    original_bindings: GoalBindingSet
    menu: LivingDexOptionMenu
    bindings: tuple[ExecutableGoalBinding, ...]
    ordinary_binding_refs: frozenset[str]
    ordering_seed_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.situation, GoalSituation):
            raise TypeError("live option set needs a goal situation")
        if not isinstance(self.original_bindings, GoalBindingSet):
            raise TypeError("live option set needs original goal bindings")
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise TypeError("live option set needs a living-Dex menu")
        if (
            not isinstance(self.bindings, tuple)
            or len(self.bindings) != len(self.menu.candidates)
            or any(not isinstance(item, ExecutableGoalBinding) for item in self.bindings)
            or tuple(item.binding_ref for item in self.bindings)
            != tuple(item.binding_ref for item in self.menu.candidates)
        ):
            raise RedLiveOptionMenuError("live option menu and bindings differ")
        if (
            not isinstance(self.ordinary_binding_refs, frozenset)
            or not self.ordinary_binding_refs <= {
                item.binding_ref for item in self.bindings
            }
        ):
            raise RedLiveOptionMenuError("ordinary binding inventory differs")
        if (
            not isinstance(self.ordering_seed_sha256, str)
            or _SHA256.fullmatch(self.ordering_seed_sha256) is None
        ):
            raise RedLiveOptionMenuError("live option ordering seed differs")

    def binding(self, candidate_index: int) -> ExecutableGoalBinding:
        if (
            type(candidate_index) is not int
            or candidate_index not in self.menu.available_indices
        ):
            raise RedLiveOptionMenuError("live option selection is unavailable")
        return self.bindings[candidate_index]

    def public_dict(self) -> dict[str, object]:
        return {
            "available_candidate_count": len(self.menu.available_indices),
            "distinct_option_kinds": len(
                {
                    self.menu.candidates[index].features.kind
                    for index in self.menu.available_indices
                }
            ),
            "identity_fields_public": 0,
            "menu": self.menu.policy_dict(),
            "menu_sha256": self.menu.policy_sha256,
            "ordinary_candidate_count": len(self.ordinary_binding_refs),
            "private_binding_fields": 0,
            "schema": "pokemon.red.live-mixed-option-set.v1",
            "supplemental_candidate_count": (
                len(self.bindings) - len(self.ordinary_binding_refs)
            ),
        }


@dataclass(frozen=True, slots=True)
class RedLiveOptionChoice:
    """Action-free learned or safety choice over one mixed-family menu."""

    options: RedLiveOptionSet
    selected_candidate_index: int
    mode: RedLiveOptionSelectionMode
    scores: tuple[float | None, ...]
    probabilities: tuple[float, ...]
    seed: int
    model_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.options, RedLiveOptionSet):
            raise TypeError("live mixed-family choice needs a RedLiveOptionSet")
        count = len(self.options.menu.candidates)
        if (
            self.selected_candidate_index not in self.options.menu.available_indices
            or not isinstance(self.mode, RedLiveOptionSelectionMode)
            or len(self.scores) != count
            or len(self.probabilities) != count
            or any(
                value is not None and (not isinstance(value, float) or not math.isfinite(value))
                for value in self.scores
            )
            or any(
                not isinstance(value, float) or not math.isfinite(value) or value < 0.0
                for value in self.probabilities
            )
            or not math.isclose(sum(self.probabilities), 1.0, abs_tol=1e-12)
            or type(self.seed) is not int
            or self.seed < 0
            or not isinstance(self.model_sha256, str)
            or _SHA256.fullmatch(self.model_sha256) is None
        ):
            raise RedLiveOptionMenuError("live mixed-family choice differs")
        if self.probabilities[self.selected_candidate_index] <= 0.0:
            raise RedLiveOptionMenuError("selected live option has zero probability")
        if (
            self.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
            and (
                any(value is not None for value in self.scores)
                or sum(
                value > 0.0 for value in self.probabilities
                )
                != 1
            )
        ):
            raise RedLiveOptionMenuError("safety choice retained model authority")

    @property
    def selected_binding(self) -> ExecutableGoalBinding:
        return self.options.binding(self.selected_candidate_index)

    def public_dict(self) -> dict[str, object]:
        candidate = self.options.menu.candidates[self.selected_candidate_index]
        return {
            "actions_executed": 0,
            "candidate_count": len(self.options.menu.candidates),
            "emulator_frames": 0,
            "menu_sha256": self.options.menu.policy_sha256,
            "mode": self.mode.value,
            "model_sha256": self.model_sha256,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "probabilities": list(self.probabilities),
            "schema": "pokemon.red.live-mixed-option-choice.v1",
            "scores": list(self.scores),
            "selected_candidate_index": self.selected_candidate_index,
            "selected_option_kind": candidate.features.kind.value,
            "teacher_labels": 0,
        }


def build_red_live_option_set(
    *,
    situation: GoalSituation,
    binding_set: GoalBindingSet,
    supplements: tuple[RedLiveSupplementalOption, ...],
    model_feature_version: int,
    ordering_seed_sha256: str,
    economy_snapshot: EconomySnapshot | None = None,
    target_cash: int | None = None,
) -> RedLiveOptionSet:
    """Compose ordinary goals and concrete mechanisms into one model menu."""

    if not isinstance(situation, GoalSituation):
        raise TypeError("mixed live menu needs a GoalSituation")
    if not isinstance(binding_set, GoalBindingSet):
        raise TypeError("mixed live menu needs a GoalBindingSet")
    if (
        not isinstance(supplements, tuple)
        or any(not isinstance(item, RedLiveSupplementalOption) for item in supplements)
    ):
        raise TypeError("mixed live menu supplements must be immutable")
    if type(model_feature_version) is not int or model_feature_version not in {1, 2, 3, 4}:
        raise RedLiveOptionMenuError("mixed live menu feature version differs")
    if not isinstance(ordering_seed_sha256, str) or _SHA256.fullmatch(
        ordering_seed_sha256
    ) is None:
        raise RedLiveOptionMenuError("mixed live menu ordering seed differs")
    if (economy_snapshot is None) != (target_cash is None):
        raise RedLiveOptionMenuError("mixed live menu economy context is incomplete")

    question = binding_set.question(situation)
    if any(
        question.opportunities[index].kind is GoalKind.RECOVER_CONTROL
        for index in question.available_indices
    ):
        raise RedLiveOptionMenuError(
            "control recovery must remain outside learned mixed-family authority"
        )
    rows: list[tuple[ExecutableGoalBinding, LivingDexOptionCandidate, bool]] = []
    for index in question.available_indices:
        opportunity = question.opportunities[index]
        candidate = project_living_dex_goal_candidate(
            question,
            index,
            feature_version=model_feature_version,
            binding_ref=opportunity.binding_ref,
        )
        if candidate is None:
            continue
        rows.append((binding_set.require(opportunity.binding_ref), candidate, True))

    for supplement in supplements:
        expected_kind = living_dex_option_kind_for_goal(
            supplement.binding.kind,
            feature_version=model_feature_version,
        )
        if expected_kind is None or supplement.candidate.features.kind is not expected_kind:
            raise RedLiveOptionMenuError(
                "supplemental executor and portable option kind differ"
            )
        rows.append((supplement.binding, supplement.candidate, False))

    refs = tuple(binding.binding_ref for binding, _candidate, _ordinary in rows)
    if len(rows) < 2 or len(set(refs)) != len(refs):
        raise RedLiveOptionMenuError(
            "mixed live menu needs distinct executable candidates"
        )

    def ordering_key(index: int) -> str:
        return canonical_sha256(
            {
                "candidate_ordinal": index,
                "ordering_seed_sha256": ordering_seed_sha256,
                "schema": "pokemon.core.neutral-live-menu-permutation.v1",
            }
        )

    ordered = tuple(rows[index] for index in sorted(range(len(rows)), key=ordering_key))
    context = living_dex_option_context_from_goal_situation(
        situation,
        economy_snapshot=economy_snapshot,
        target_cash=target_cash,
    )
    if economy_snapshot is None and any(
        candidate.economy_offer is not None
        for _binding, candidate, _ordinary in ordered
    ):
        raise RedLiveOptionMenuError(
            "economy-bearing mixed options need a measured economy context"
        )
    menu = LivingDexOptionMenu(context, tuple(candidate for _binding, candidate, _ in ordered))
    if menu.feature_version > model_feature_version:
        raise RedLiveOptionMenuError("mixed live menu exceeds the model feature version")
    return RedLiveOptionSet(
        situation,
        binding_set,
        menu,
        tuple(binding for binding, _candidate, _ordinary in ordered),
        frozenset(
            binding.binding_ref for binding, _candidate, ordinary in ordered if ordinary
        ),
        ordering_seed_sha256,
    )


def select_red_live_option(
    model: LivingDexOptionValueModel,
    options: RedLiveOptionSet,
    *,
    seed: int,
    exploration_mix: float = 0.25,
    utility: LivingDexOptionUtility = DEFAULT_LIVING_DEX_GOAL_UTILITY,
    safety: CompletionFirstGoalTeacher | None = None,
    allow_earning_exploration: bool = False,
) -> RedLiveOptionChoice:
    """Select one private binding without executing it or creating a teacher label."""

    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("mixed live selection needs a living-Dex model")
    if not isinstance(options, RedLiveOptionSet):
        raise TypeError("mixed live selection needs a RedLiveOptionSet")
    if type(seed) is not int or seed < 0:
        raise RedLiveOptionMenuError("mixed live selection seed differs")
    if (
        isinstance(exploration_mix, bool)
        or not isinstance(exploration_mix, (int, float))
        or not 0.0 <= float(exploration_mix) <= 1.0
    ):
        raise RedLiveOptionMenuError("mixed live exploration mix differs")
    if not isinstance(utility, LivingDexOptionUtility):
        raise TypeError("mixed live selection needs a utility contract")
    if safety is None:
        safety = CompletionFirstGoalTeacher()
    if not isinstance(safety, CompletionFirstGoalTeacher):
        raise TypeError("mixed live selection needs a safety policy")
    if type(allow_earning_exploration) is not bool:
        raise TypeError("earning exploration opt-in must be boolean")
    if model.feature_version < options.menu.feature_version:
        raise RedLiveOptionMenuError("mixed live menu exceeds the fitted model")

    question = options.original_bindings.question(options.situation)
    deterministic = safety.select(question)
    selected_opportunity = question.opportunities[deterministic.selected_index]
    relax_earning = (
        allow_earning_exploration
        and selected_opportunity.kind is GoalKind.RESUPPLY
        and selected_opportunity.resource_quote is not None
        and selected_opportunity.resource_quote.expected_income > 0
        and options.menu.context.economy_snapshot is not None
        and options.menu.context.target_cash is not None
        and options.menu.context.target_cash > options.menu.context.economy_snapshot.cash
    )
    safety_forced = (
        deterministic.kind is GoalKind.RECOVER_CONTROL
        or (
            deterministic.kind is GoalKind.RESTORE_TEAM
            and options.situation.safety_pressure >= safety.safety_gate
        )
        or (
            deterministic.kind is GoalKind.MANAGE_STORAGE
            and options.situation.storage_pressure >= safety.storage_gate
        )
        or (
            deterministic.kind is GoalKind.RESUPPLY
            and options.situation.resource_pressure >= safety.resource_gate
            and not relax_earning
        )
    )
    if safety_forced:
        try:
            selected_index = next(
                index
                for index, binding in enumerate(options.bindings)
                if binding.binding_ref == deterministic.binding_ref
            )
        except StopIteration as error:
            raise RedLiveOptionMenuError(
                "safety-selected goal is absent from the mixed menu"
            ) from error
        probabilities = tuple(
            1.0 if index == selected_index else 0.0
            for index in range(len(options.bindings))
        )
        return RedLiveOptionChoice(
            options,
            selected_index,
            RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY,
            (None,) * len(options.bindings),
            probabilities,
            seed,
            model.model_sha256,
        )

    raw_scores = model.scores(options.menu, utility)
    if len(raw_scores) != len(options.bindings):
        raise RedLiveOptionMenuError("mixed live model score width differs")
    available = options.menu.available_indices
    concrete: list[float] = []
    for index in available:
        value = raw_scores[index]
        if value is None or not math.isfinite(value):
            raise RedLiveOptionMenuError("mixed live model returned invalid scores")
        concrete.append(value)
    peak = max(concrete)
    exponentials = [math.exp(value - peak) for value in concrete]
    total = sum(exponentials)
    mix = float(exploration_mix)
    probabilities_list = [0.0] * len(options.bindings)
    for index, weight in zip(available, exponentials, strict=True):
        probabilities_list[index] = (
            (1.0 - mix) * weight / total + mix / len(available)
        )
    selected_index = random.Random(seed).choices(
        range(len(probabilities_list)),
        weights=probabilities_list,
        k=1,
    )[0]
    scores = tuple(
        None if value is None else float(value) for value in raw_scores
    )
    return RedLiveOptionChoice(
        options,
        selected_index,
        RedLiveOptionSelectionMode.MODEL_EXPLORATION,
        scores,
        tuple(probabilities_list),
        seed,
        model.model_sha256,
    )


def supplemental_live_option(
    binding: ExecutableGoalBinding,
    candidate: LivingDexOptionCandidate,
) -> RedLiveSupplementalOption:
    """Rebind an identity-free provider row to its authenticated executor."""

    if not isinstance(binding, ExecutableGoalBinding):
        raise TypeError("supplemental option needs an executable goal binding")
    if not isinstance(candidate, LivingDexOptionCandidate):
        raise TypeError("supplemental option needs a living-Dex candidate")
    return RedLiveSupplementalOption(
        binding,
        replace(candidate, binding_ref=binding.binding_ref),
    )


__all__ = [
    "RedLiveOptionChoice",
    "RedLiveOptionMenuError",
    "RedLiveOptionSelectionMode",
    "RedLiveOptionSet",
    "RedLiveSupplementalOption",
    "build_red_live_option_set",
    "select_red_live_option",
    "supplemental_live_option",
]
