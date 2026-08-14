"""Fixed paired candidate construction for the Crystal transfer experiment."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_crystal_completion.source_contract import CRYSTAL_GAME_ID
from pokemon_crystal_completion.transfer_artifacts import (
    CrystalTransferCatalog,
    validate_crystal_transfer_catalog,
)
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS,
    CrystalTransferPlan,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    GoalManagerModelError,
    canonical_goal_manager_model_sha256,
)

CRYSTAL_ADAPTATION_BUDGETS = (9, 18, 27)


@dataclass(frozen=True, slots=True)
class CrystalAdaptationPair:
    """Same Crystal prefix and optimizer, differing only in initial weights."""

    budget: int
    red_initialized: GoalManagerLinearModel
    scratch: GoalManagerLinearModel

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.goal-manager-adaptation-pair.v1",
            "budget": self.budget,
            "red_initialized_model_sha256": canonical_goal_manager_model_sha256(
                self.red_initialized
            ),
            "scratch_model_sha256": canonical_goal_manager_model_sha256(self.scratch),
            "same_examples": True,
            "same_order": True,
            "same_optimizer": True,
            "same_feature_normalizer": True,
            "differing_field": "initial_weights",
            "private_path_fields": 0,
        }


def fit_crystal_adaptation_pairs(
    source_model: GoalManagerLinearModel,
    examples: Iterable[GoalManagerExample],
    *,
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
) -> tuple[CrystalAdaptationPair, ...]:
    """Fit all preregistered prefixes without budget or hyperparameter search."""

    if not isinstance(source_model, GoalManagerLinearModel):
        raise TypeError("source_model must be GoalManagerLinearModel")
    if not isinstance(plan, CrystalTransferPlan):
        raise TypeError("plan must be CrystalTransferPlan")
    if not isinstance(catalog, CrystalTransferCatalog):
        raise TypeError("catalog must be CrystalTransferCatalog")
    validate_crystal_transfer_catalog(plan, catalog)
    if catalog.partition != "adaptation":
        raise GoalManagerModelError("Crystal adaptation requires the adaptation catalog")
    rows = tuple(examples)
    if len(rows) != CRYSTAL_ADAPTATION_BUDGETS[-1]:
        raise GoalManagerModelError("Crystal adaptation requires exactly 27 examples")
    if any(item.partition != "adaptation" for item in rows):
        raise GoalManagerModelError("Crystal adaptation examples must stay in adaptation")
    if any(item.environment_id != CRYSTAL_GAME_ID for item in rows):
        raise GoalManagerModelError("Crystal adaptation environment identity differs")
    if len({item.decision_id for item in rows}) != len(rows):
        raise GoalManagerModelError("Crystal adaptation decision identities must be unique")
    if len({item.question.policy_context_sha256 for item in rows}) != len(rows):
        raise GoalManagerModelError("Crystal adaptation policy contexts must be unique")
    if len({item.episode_id for item in rows}) != len(rows) or len(
        {item.root_lineage_id for item in rows}
    ) != len(rows):
        raise GoalManagerModelError(
            "Crystal adaptation examples must use independent episode lineages"
        )
    if tuple(item.decision_id for item in rows) != tuple(
        context.slot_id for context in catalog.entries
    ):
        raise GoalManagerModelError(
            "Crystal adaptation decisions must follow the frozen catalog"
        )
    for item, context in zip(rows, catalog.entries, strict=True):
        candidate_kinds = tuple(option.kind for option in item.question.opportunities)
        available_kinds = tuple(
            option.kind
            for option in item.question.opportunities
            if option.availability is GoalAvailability.AVAILABLE
        )
        if (
            item.actor != "deterministic_teacher"
            or item.outcome_status is not GoalDecisionOutcome.SUCCEEDED
            or item.question.ordered_policy_input_sha256
            != context.ordered_policy_input_sha256
            or item.question.policy_context_sha256 != context.policy_context_sha256
            or item.question.available_menu_sha256 != context.available_menu_sha256
            or candidate_kinds != context.candidate_goal_kinds
            or available_kinds != context.available_goal_kinds
            or item.selected_candidate_index != context.focus_candidate_index
            or item.selected_kind is not context.goal_kind
        ):
            raise GoalManagerModelError(
                "Crystal adaptation example differs from its frozen catalog context"
            )

    scratch_initialization = source_model.zero_weight_comparator()
    pairs: list[CrystalAdaptationPair] = []
    for budget in CRYSTAL_ADAPTATION_BUDGETS:
        prefix = rows[:budget]
        expected_per_kind = budget // len(GoalKind)
        selected = Counter(item.selected_kind for item in prefix)
        if any(selected[kind] != expected_per_kind for kind in GoalKind):
            raise GoalManagerModelError("Crystal adaptation prefix is not goal-kind balanced")
        pairs.append(
            CrystalAdaptationPair(
                budget=budget,
                red_initialized=source_model.fine_tune(prefix),
                scratch=scratch_initialization.fine_tune(prefix),
            )
        )
    return tuple(pairs)


def crystal_adaptation_predictor_sha256(
    pairs: Iterable[CrystalAdaptationPair],
) -> tuple[tuple[str, str], ...]:
    """Bind the six sealed predictor ids to their canonical fitted weights."""

    rows = tuple(pairs)
    if tuple(pair.budget for pair in rows) != CRYSTAL_ADAPTATION_BUDGETS:
        raise GoalManagerModelError("Crystal adaptation pairs must cover fixed budgets")
    result: list[tuple[str, str]] = []
    for pair in rows:
        result.extend(
            (
                (
                    f"red_initialized_budget_{pair.budget}",
                    canonical_goal_manager_model_sha256(pair.red_initialized),
                ),
                (
                    f"scratch_budget_{pair.budget}",
                    canonical_goal_manager_model_sha256(pair.scratch),
                ),
            )
        )
    if tuple(predictor_id for predictor_id, _digest in result) != (
        CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
    ):
        raise GoalManagerModelError("Crystal adaptation predictor order drifted")
    return tuple(result)


__all__ = [
    "CRYSTAL_ADAPTATION_BUDGETS",
    "CrystalAdaptationPair",
    "crystal_adaptation_predictor_sha256",
    "fit_crystal_adaptation_pairs",
]
