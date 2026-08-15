"""Build one identity-free same-destination Red navigation question.

This is deliberately a local-routing outcome probe, not a strategic objective
teacher.  Two executable plans begin at the same authenticated state and end
on the same terminal tile.  Candidate order is frozen from the state digest,
and each candidate receives an independently reloaded execution outcome.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.strategic_navigation import (
    StrategicNavigationDecision,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationInferenceInput,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    SameDestinationRoutePair,
)

RED_LOCAL_NAVIGATION_SCENARIO_ID = "red-local-navigation-same-terminal-v1"
RED_LOCAL_NAVIGATION_ACTOR = "outcome_probe"
RED_LOCAL_NAVIGATION_POLICY_ID = "same-destination-route-outcome-probe-v1"
RED_LOCAL_NAVIGATION_ORDER_RULE = "state-sha256-high-bit-detour-first-v1"
RED_LOCAL_NAVIGATION_NEED_TAGS = (StrategicNavigationTag.TRANSIT,)
RED_LOCAL_NAVIGATION_ORIGIN_TAGS = (StrategicNavigationTag.OVERWORLD,)
RED_LOCAL_NAVIGATION_CANDIDATE_TAGS = (
    StrategicNavigationTag.CHALLENGE,
    StrategicNavigationTag.OVERWORLD,
    StrategicNavigationTag.TRANSIT,
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedNavigationOutcomeProbeError(ValueError):
    """Raised when a local-navigation outcome question is not comparable."""


@dataclass(frozen=True, slots=True)
class SameDestinationNavigationQuestion:
    """Two route candidates plus the exact identity-free model question."""

    route_pair: SameDestinationRoutePair
    initial_state_sha256: str
    bindings: tuple[DestinationRouteBinding, DestinationRouteBinding]
    inference: StrategicNavigationInferenceInput
    shortest_candidate_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.route_pair, SameDestinationRoutePair):
            raise RedNavigationOutcomeProbeError("navigation route pair is invalid")
        if _SHA256.fullmatch(self.initial_state_sha256) is None:
            raise RedNavigationOutcomeProbeError("navigation state digest is invalid")
        if len(self.bindings) != 2 or any(
            not isinstance(item, DestinationRouteBinding) for item in self.bindings
        ):
            raise RedNavigationOutcomeProbeError(
                "navigation question needs exactly two route bindings"
            )
        if self.shortest_candidate_index not in (0, 1):
            raise RedNavigationOutcomeProbeError(
                "navigation shortest-candidate index is invalid"
            )
        plans = self.plans
        if plans[self.shortest_candidate_index] != self.route_pair.shortest:
            raise RedNavigationOutcomeProbeError(
                "navigation candidate order lost the shortest route"
            )
        if plans[1 - self.shortest_candidate_index] != self.route_pair.detour:
            raise RedNavigationOutcomeProbeError(
                "navigation candidate order lost the detour route"
            )
        candidates = tuple(item.candidate for item in self.bindings)
        expected = StrategicNavigationInferenceInput.from_candidates(
            semantic_need_tags=RED_LOCAL_NAVIGATION_NEED_TAGS,
            origin_semantic_tags=RED_LOCAL_NAVIGATION_ORIGIN_TAGS,
            candidates=candidates,
        )
        if (
            self.inference.ordered_policy_input_sha256
            != expected.ordered_policy_input_sha256
        ):
            raise RedNavigationOutcomeProbeError(
                "navigation inference differs from its ordered route bindings"
            )

    @property
    def plans(self) -> tuple[RoutePlan, RoutePlan]:
        first, second = self.bindings
        if first.plan is None or second.plan is None:  # pragma: no cover - constructor guards
            raise AssertionError("same-destination route binding became unavailable")
        return first.plan, second.plan

    def decision(
        self,
        candidate_index: int,
        *,
        episode_id: str,
        root_lineage_id: str,
        partition: str = "train",
    ) -> StrategicNavigationDecision:
        """Bind one cloned execution without creating a teacher target."""

        if candidate_index not in (0, 1):
            raise RedNavigationOutcomeProbeError(
                "navigation selected candidate index is invalid"
            )
        candidates = tuple(item.candidate for item in self.bindings)
        selected = candidates[candidate_index]
        return StrategicNavigationDecision(
            episode_id=episode_id,
            decision_index=0,
            root_lineage_id=root_lineage_id,
            partition=partition,
            actor=RED_LOCAL_NAVIGATION_ACTOR,
            policy_id=RED_LOCAL_NAVIGATION_POLICY_ID,
            semantic_need_tags=RED_LOCAL_NAVIGATION_NEED_TAGS,
            origin_semantic_tags=RED_LOCAL_NAVIGATION_ORIGIN_TAGS,
            origin_region_ref="pokemon.red:region:cerulean",
            candidates=candidates,
            selected_destination_ref=selected.destination_ref,
        )

    def public_catalog(self) -> dict[str, object]:
        """Return the path- and movement-free prospective candidate catalog."""

        return {
            "schema": "pokemon-red-local-navigation-catalog-v1",
            "scenario_id": RED_LOCAL_NAVIGATION_SCENARIO_ID,
            "initial_state_sha256": self.initial_state_sha256,
            "candidate_count": 2,
            "candidate_order_rule": RED_LOCAL_NAVIGATION_ORDER_RULE,
            "shortest_candidate_index": self.shortest_candidate_index,
            "same_start": True,
            "same_terminal": True,
            "strictly_costlier_detour": True,
            "ordered_policy_input_sha256": (
                self.inference.ordered_policy_input_sha256
            ),
            "candidates": [
                candidate.policy_features(binding_index=index)
                for index, candidate in enumerate(
                    item.candidate for item in self.bindings
                )
            ],
            "movement_action_labels": 0,
            "teacher_choice_targets": 0,
        }


def build_same_destination_navigation_question(
    route_pair: SameDestinationRoutePair,
    *,
    initial_state_sha256: str,
) -> SameDestinationNavigationQuestion:
    """Freeze candidate order before either cloned execution is observed."""

    if not isinstance(route_pair, SameDestinationRoutePair):
        raise RedNavigationOutcomeProbeError("navigation route pair is invalid")
    if _SHA256.fullmatch(initial_state_sha256) is None:
        raise RedNavigationOutcomeProbeError("navigation state digest is invalid")
    detour_first = int(initial_state_sha256[:2], 16) >= 128
    ordered_plans = (
        (route_pair.detour, route_pair.shortest)
        if detour_first
        else (route_pair.shortest, route_pair.detour)
    )
    shortest_candidate_index = 1 if detour_first else 0
    bindings = tuple(
        DestinationRouteBinding.available(
            f"route-option-{index}",
            RED_LOCAL_NAVIGATION_CANDIDATE_TAGS,
            plan,
        )
        for index, plan in enumerate(ordered_plans)
    )
    if len(bindings) != 2:  # pragma: no cover - fixed construction
        raise AssertionError("same-destination route count drifted")
    typed_bindings = (bindings[0], bindings[1])
    inference = StrategicNavigationInferenceInput.from_candidates(
        semantic_need_tags=RED_LOCAL_NAVIGATION_NEED_TAGS,
        origin_semantic_tags=RED_LOCAL_NAVIGATION_ORIGIN_TAGS,
        candidates=tuple(item.candidate for item in typed_bindings),
    )
    return SameDestinationNavigationQuestion(
        route_pair=route_pair,
        initial_state_sha256=initial_state_sha256,
        bindings=typed_bindings,
        inference=inference,
        shortest_candidate_index=shortest_candidate_index,
    )


__all__ = [
    "RED_LOCAL_NAVIGATION_ACTOR",
    "RED_LOCAL_NAVIGATION_CANDIDATE_TAGS",
    "RED_LOCAL_NAVIGATION_NEED_TAGS",
    "RED_LOCAL_NAVIGATION_ORDER_RULE",
    "RED_LOCAL_NAVIGATION_ORIGIN_TAGS",
    "RED_LOCAL_NAVIGATION_POLICY_ID",
    "RED_LOCAL_NAVIGATION_SCENARIO_ID",
    "RedNavigationOutcomeProbeError",
    "SameDestinationNavigationQuestion",
    "build_same_destination_navigation_question",
]
