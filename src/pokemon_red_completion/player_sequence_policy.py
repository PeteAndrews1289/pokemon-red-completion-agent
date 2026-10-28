"""Explicit opt-in continuation policy; not native admission or adoption.

History is bound to a menu and a recorded prefix, not a private objective name.
The native auditor must still reconstruct that prefix before admitting data.
The combined identity cannot be confused with the unchanged immediate model.
"""

import math
from dataclasses import asdict, astuple, dataclass
from typing import Any

from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from .living_dex_option_value import (
    LivingDexOptionMenu,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
)
from .player_sequence_value import SequenceValueHead
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory


def _digest(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("sequence policy identity differs")


@dataclass(frozen=True)
class SequenceChoiceContext:
    menu_sha256: str
    prefix_sha256: str
    histories: tuple[RecordedBranchHistory, ...]

    def __post_init__(self) -> None:
        _digest(self.menu_sha256)
        _digest(self.prefix_sha256)
        if (
            type(self.histories) is not tuple
            or not self.histories
            or any(type(h) is not RecordedBranchHistory for h in self.histories)
            or any(type(n) is not int or n < 0 for h in self.histories for n in astuple(h))
        ):
            raise ValueError("sequence choice histories differ")

    def document(self) -> dict[str, Any]:
        return dict(
            schema="pokemon.player.sequence-choice-context.v1",
            menu_sha256=self.menu_sha256,
            prefix_sha256=self.prefix_sha256,
            histories=[asdict(h) for h in self.histories],
        )

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "SequenceChoiceContext":
        context = cls(
            document["menu_sha256"],
            document["prefix_sha256"],
            tuple(RecordedBranchHistory(**h) for h in document["histories"]),
        )
        if canonical_sha256(context.document()) != canonical_sha256(document):
            raise ValueError("sequence choice context contract differs")
        return context

    def vectors(self, menu: LivingDexOptionMenu) -> tuple[tuple[float, ...], ...]:
        if (
            menu.feature_version > 6
            or menu.policy_sha256 != self.menu_sha256
            or len(menu.candidates) != len(self.histories)
        ):
            raise ValueError("sequence choice context is not bound to this V6-compatible menu")
        return tuple(
            c.vector(menu.context, feature_version=6) + h.vector()
            for c, h in zip(menu.candidates, self.histories, strict=True)
        )


@dataclass(frozen=True)
class SequencePolicy:
    """Immediate utility plus explicitly weighted measured continuation utility."""

    baseline_sha256: str
    head: SequenceValueHead
    sequence_utility: tuple[float, ...]
    sequence_weight: float
    immediate_utility: LivingDexOptionUtility = DEFAULT_LIVING_DEX_GOAL_UTILITY
    exploration_mix: float = 0.25

    def __post_init__(self) -> None:
        _digest(self.baseline_sha256)
        if (
            type(self.head) is not SequenceValueHead
            or self.head.behavior_model_sha256 != self.baseline_sha256
            or type(self.immediate_utility) is not LivingDexOptionUtility
            or type(self.sequence_weight) not in (int, float)
            or not math.isfinite(self.sequence_weight)
            or self.sequence_weight <= 0
            or type(self.exploration_mix) not in (int, float)
            or not 0 <= self.exploration_mix <= 1
        ):
            raise ValueError("sequence policy composition differs")
        # Validates utility and rejects unknown target channels without querying
        # a model or allowing missing losses to become zero-loss predictions.
        if (
            type(self.sequence_utility) is not tuple
            or len(self.sequence_utility) != len(self.head.parameters)
            or not any(self.sequence_utility)
            or any(
                type(w) not in (int, float) or not math.isfinite(w) or (w != 0 and p is None)
                for w, p in zip(self.sequence_utility, self.head.parameters, strict=True)
            )
        ):
            raise ValueError("sequence utility requires measured channels")

    def document(self) -> dict[str, Any]:
        return dict(
            schema="pokemon.player.sequence-policy.v1",
            composition="immediate-plus-weighted-continuation-v1",
            baseline_sha256=self.baseline_sha256,
            head=self.head.document(),
            head_sha256=self.head.model_sha256,
            sequence_utility=self.sequence_utility,
            sequence_weight=self.sequence_weight,
            immediate_utility=asdict(self.immediate_utility),
            exploration_mix=self.exploration_mix,
            native_admission_verified=False,
            live_policy_adopted=False,
        )

    @property
    def model_sha256(self) -> str:
        return canonical_sha256(self.document())

    @classmethod
    def from_document(cls, document: dict[str, Any], *, expected_sha256: str) -> "SequencePolicy":
        if canonical_sha256(document) != expected_sha256:
            raise ValueError("sequence policy document identity differs")
        policy = cls(
            document["baseline_sha256"],
            SequenceValueHead.from_document(
                document["head"], expected_sha256=document["head_sha256"]
            ),
            tuple(document["sequence_utility"]),
            document["sequence_weight"],
            LivingDexOptionUtility(**document["immediate_utility"]),
            document["exploration_mix"],
        )
        if canonical_sha256(policy.document()) != expected_sha256:
            raise ValueError("sequence policy document contract differs")
        return policy

    def validate_selection(
        self,
        model: LivingDexOptionValueModel,
        menu: LivingDexOptionMenu,
        context: SequenceChoiceContext,
        *,
        utility: LivingDexOptionUtility,
        exploration_mix: float,
    ) -> None:
        if (
            model.feature_version != 6
            or model.model_sha256 != self.baseline_sha256
            or type(context) is not SequenceChoiceContext
            or utility != self.immediate_utility
            or exploration_mix != self.exploration_mix
        ):
            raise ValueError("sequence selection differs from the frozen policy")
        context.vectors(menu)

    def scores(
        self,
        model: LivingDexOptionValueModel,
        menu: LivingDexOptionMenu,
        context: SequenceChoiceContext,
    ) -> tuple[float | None, ...]:
        self.validate_selection(
            model,
            menu,
            context,
            utility=self.immediate_utility,
            exploration_mix=self.exploration_mix,
        )
        immediate = model.scores(menu, self.immediate_utility)
        continuation = self.head.score_menu(
            menu, histories=context.histories, utility=self.sequence_utility
        )
        return tuple(
            None if a is None or b is None else a + self.sequence_weight * b
            for a, b in zip(immediate, continuation, strict=True)
        )
