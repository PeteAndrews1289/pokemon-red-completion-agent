"""Explicit opt-in continuation policy; not native admission or adoption.

History is bound to a menu and a recorded prefix, not a private objective name.
The native auditor must still reconstruct that prefix before admitting data.
The combined identity cannot be confused with the unchanged immediate model.
"""

import math
from dataclasses import asdict, astuple, dataclass, replace
from typing import Any

from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from .living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
)
from .player_sequence_value import SequenceValueHead, sequence_feature_width
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory, STORY_HISTORY, validate_history_contract


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
    feature_version: int = 6
    costly_search_witnesses: tuple[bool | None, ...] | None = None
    history_contract: str = STORY_HISTORY

    def __post_init__(self) -> None:
        if self.costly_search_witnesses is not None and (
                type(self.costly_search_witnesses) is not tuple
                or len(self.costly_search_witnesses) != len(self.histories)
                or any(v is not None and type(v) is not bool for v in self.costly_search_witnesses)):
            raise ValueError("costly search witnesses differ")
        sequence_feature_width(self.feature_version)
        validate_history_contract(self.history_contract)
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
            schema=(
                "pokemon.player.sequence-choice-context.v3" if self.costly_search_witnesses is not None else
                "pokemon.player.sequence-choice-context.v1"
                if self.feature_version == 6
                else "pokemon.player.sequence-choice-context.v2"
            ),
            **({"feature_version": self.feature_version} if self.feature_version != 6 else {}),
            menu_sha256=self.menu_sha256,
            prefix_sha256=self.prefix_sha256,
            histories=[asdict(h) for h in self.histories],
            **({"history_contract": self.history_contract} if self.history_contract != STORY_HISTORY else {}),
            **({"costly_search_witnesses": list(self.costly_search_witnesses)}
               if self.costly_search_witnesses is not None else {}),
        )

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "SequenceChoiceContext":
        context = cls(
            document["menu_sha256"],
            document["prefix_sha256"],
            tuple(RecordedBranchHistory(**h) for h in document["histories"]),
            document.get("feature_version", 6),
            tuple(document["costly_search_witnesses"]) if "costly_search_witnesses" in document else None,
            document.get("history_contract", STORY_HISTORY),
        )
        if canonical_sha256(context.document()) != canonical_sha256(document):
            raise ValueError("sequence choice context contract differs")
        return context

    def for_history_contract(self, menu, history_contract):
        """Retained legacy heads receive their exact old nonstory-zero inputs."""
        validate_history_contract(history_contract)
        if history_contract == self.history_contract:
            return self
        if history_contract != STORY_HISTORY:
            raise ValueError("a story-only context cannot supply preparation history")
        self.vectors(menu)
        return replace(self, history_contract=STORY_HISTORY, histories=tuple(
            h if c.features.kind is LivingDexOptionKind.UNLOCK_ACCESS else
            RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
            for c,h in zip(menu.candidates,self.histories,strict=True)))

    def vectors(self, menu: LivingDexOptionMenu) -> tuple[tuple[float, ...], ...]:
        if (
            menu.feature_version > self.feature_version
            or menu.policy_sha256 != self.menu_sha256
            or len(menu.candidates) != len(self.histories)
        ):
            raise ValueError("sequence choice context is not bound to this feature-compatible menu")
        return tuple(
            c.vector(menu.context, feature_version=self.feature_version) + h.vector()
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
    kind_balanced_exploration: bool = False
    # Explicit V2: predictions remain conditional on this separately recorded
    # behavior. This is an experimental new policy, not counterfactual truth or
    # an assertion that the immediate scorer generated the training records.
    continuation_behavior_sha256: str | None = None
    selection_mode: str = "sample"
    retained_policy: "SequencePolicy | None" = None
    supported_kinds: tuple[str, ...] = ()
    support_evidence_sha256: str | None = None
    task_return_scope: str | None = None

    def __post_init__(self) -> None:
        _digest(self.baseline_sha256)
        from .player_sequence_targets import RESOURCE_TASK_TARGET_CONTRACT
        if self.task_return_scope is not None:
            u = self.immediate_utility
            funded = self.task_return_scope in {"resource-pressure-positive-with-earning-peer-v2",
                "cash-short-resource-pressure-with-earning-peer-v3"}
            expected = (u.completion_gain_weight, 0.0 if funded else u.success_weight, -u.action_cost_weight,
                        -u.frame_cost_weight, -u.resource_cost_weight, u.resource_cost_weight, 0.0)
            from .recorded_branch_history import PREPARATION_HISTORY
            if (self.task_return_scope not in {"resource-pressure-one-with-earning-peer-v1",
                    "resource-pressure-positive-with-earning-peer-v2",
                    "cash-short-resource-pressure-with-earning-peer-v3"}
                or funded and self.head.history_contract != PREPARATION_HISTORY
                or self.head.target_contract != RESOURCE_TASK_TARGET_CONTRACT
                or self.head.feature_version != 16 or self.retained_policy is None
                or self.supported_kinds != (("acquire", "develop", "resupply") if funded else ("develop", "resupply"))
                or self.sequence_utility != expected or self.sequence_weight != 1.0):
                raise ValueError("task-return composition requires exact public support and unchanged utility units")
        elif self.head.target_contract == RESOURCE_TASK_TARGET_CONTRACT:
            raise ValueError("stock-cost task head requires explicit task-return composition")

        if self.continuation_behavior_sha256 is not None:
            _digest(self.continuation_behavior_sha256)
        expected_behavior = (self.baseline_sha256 if self.continuation_behavior_sha256 is None
                             else self.continuation_behavior_sha256)
        if (
            type(self.selection_mode) is not str
            or self.selection_mode not in {"sample", "stable", "stable_recurrence", "stable_costly_recurrence"}
            or type(self.kind_balanced_exploration) is not bool
            or type(self.head) is not SequenceValueHead
            or self.selection_mode in {"stable_recurrence", "stable_costly_recurrence"} and self.head.feature_version != 16
            or self.head.behavior_model_sha256 != expected_behavior
            or type(self.immediate_utility) is not LivingDexOptionUtility
            or type(self.sequence_weight) not in (int, float)
            or not math.isfinite(self.sequence_weight)
            or self.sequence_weight <= 0
            or type(self.exploration_mix) not in (int, float)
            or not 0 <= self.exploration_mix <= 1
        ):
            raise ValueError("sequence policy composition differs")
        if self.retained_policy is None:
            if self.supported_kinds != () or self.support_evidence_sha256 is not None:
                raise ValueError("sequence retention requires an explicit prior policy")
        else:
            prior = self.retained_policy
            _digest(self.support_evidence_sha256)
            if (
                type(prior) is not SequencePolicy
                or prior.retained_policy is not None and (self.task_return_scope is None or prior.retained_policy.retained_policy is not None)
                or type(self.supported_kinds) is not tuple
                or not self.supported_kinds
                or self.supported_kinds != tuple(sorted(set(self.supported_kinds)))
                or any(type(k) is not str or k not in {x.value for x in LivingDexOptionKind}
                       for k in self.supported_kinds)
                or prior.baseline_sha256 != self.baseline_sha256
                or prior.head.feature_version != self.head.feature_version
                or any(getattr(prior, k) != getattr(self, k) for k in (("sequence_utility",) if self.task_return_scope is None else ()) + (
                    "sequence_weight", "immediate_utility",
                    "exploration_mix", "kind_balanced_exploration", "selection_mode"))
            ):
                raise ValueError("sequence retained policy or observed-kind scope differs")
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
            schema=("pokemon.player.sequence-policy.v5" if self.task_return_scope is not None else "pokemon.player.sequence-policy.v4" if self.selection_mode == "stable_costly_recurrence" else "pokemon.player.sequence-policy.v3" if self.selection_mode != "sample" else
                    "pokemon.player.sequence-policy.v1" if self.continuation_behavior_sha256 is None
                    else "pokemon.player.sequence-policy.v2"),
            composition=("supported-whole-task-return-replaces-primitive-utility-v5" if self.task_return_scope is not None else "immediate-plus-certified-costly-recurrence-v4" if self.selection_mode == "stable_costly_recurrence" else "immediate-plus-declared-selection-continuation-v3" if self.selection_mode != "sample" else
                         "immediate-plus-weighted-continuation-v1" if self.continuation_behavior_sha256 is None
                         else "immediate-plus-behavior-conditional-continuation-v2"),
            **({"continuation_behavior_sha256": self.continuation_behavior_sha256,
                "continuation_semantics": "observed-under-separately-pinned-behavior-not-counterfactual",
                "off_policy_improvement_verified": False}
               if self.continuation_behavior_sha256 is not None else {}),
            **({"selection_mode": self.selection_mode,
                "selection_semantics": "frozen-scores-new-selection-not-counterfactual-proof"}
               if self.selection_mode != "sample" else {}),
            **({"off_policy_improvement_verified": False}
               if self.selection_mode != "sample" and self.continuation_behavior_sha256 is None else {}),
            **({"recurrence_rule": "all-maxima-observed-unchanged-movement-v1"}
               if self.selection_mode == "stable_recurrence" else {}),
            **({"recurrence_rule": "all-maxima-exact-movement-or-two-certified-paid-failures-v1"}
               if self.selection_mode == "stable_costly_recurrence" else {}),
            **({"task_return_scope": self.task_return_scope} if self.task_return_scope is not None else {}),
            baseline_sha256=self.baseline_sha256,
            head=self.head.document(),
            head_sha256=self.head.model_sha256,
            sequence_utility=self.sequence_utility,
            sequence_weight=self.sequence_weight,
            immediate_utility=asdict(self.immediate_utility),
            exploration_mix=self.exploration_mix,
            **({"kind_balanced_exploration": True} if self.kind_balanced_exploration else {}),
            **({"retained_sequence_scope": dict(
                schema="pokemon.sequence.task-return-retention.v2" if self.task_return_scope is not None else "pokemon.sequence.TRAIN-kind-retention.v1",
                supported_kinds=list(self.supported_kinds),
                support_evidence_sha256=self.support_evidence_sha256,
                prior_policy=self.retained_policy.document(),
                prior_policy_sha256=self.retained_policy.model_sha256,
                semantics=("whole-task-return-on-observed-resource-scarcity;exact-prior-scores-elsewhere" if self.task_return_scope is not None else "new-head-on-observed-TRAIN-kinds;exact-prior-scores-elsewhere"),
                primary_horizon=self.head.horizon,
                prior_horizon=self.retained_policy.head.horizon,
                action_availability_unchanged=True,
            )} if self.retained_policy is not None else {}),
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
            document.get("kind_balanced_exploration", False),
            document.get("continuation_behavior_sha256"),
            document.get("selection_mode", "sample"),
            (cls.from_document(document["retained_sequence_scope"]["prior_policy"],
                expected_sha256=document["retained_sequence_scope"]["prior_policy_sha256"])
             if "retained_sequence_scope" in document else None),
            (tuple(document["retained_sequence_scope"]["supported_kinds"])
             if "retained_sequence_scope" in document else ()),
            (document["retained_sequence_scope"]["support_evidence_sha256"]
             if "retained_sequence_scope" in document else None),
            document.get("task_return_scope"),
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
            model.feature_version != self.head.feature_version
            or model.model_sha256 != self.baseline_sha256
            or type(context) is not SequenceChoiceContext
            or context.feature_version != self.head.feature_version
            or context.history_contract != self.head.history_contract
            or (context.costly_search_witnesses is not None) != (self.selection_mode == "stable_costly_recurrence")
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
        if self.task_return_scope is not None and not _task_return_context_supported(menu, self.task_return_scope):
            return self.retained_policy.scores(model, menu, context.for_history_contract(
                menu, self.retained_policy.head.history_contract))
        immediate = model.scores(menu, self.immediate_utility)
        continuation = self.head.score_menu(
            menu, histories=context.histories, utility=self.sequence_utility
        )
        scores = tuple(
            None if a is None or b is None else (0.0 if self.task_return_scope is not None else a) + self.sequence_weight * b
            for a, b in zip(immediate, continuation, strict=True)
        )
        if self.retained_policy is None:
            return scores
        prior = self.retained_policy.scores(model, menu, context.for_history_contract(
                menu, self.retained_policy.head.history_contract))
        if self.task_return_scope is not None:
            return tuple(new if _task_return_candidate_supported(c, self.task_return_scope) else old
                         for c, new, old in zip(menu.candidates, scores, prior, strict=True))
        return tuple(new if c.features.kind.value in self.supported_kinds else old
                     for c, new, old in zip(menu.candidates, scores, prior, strict=True))


def _task_return_income(candidate):
    offer = candidate.economy_offer
    return (candidate.features.kind.value == "resupply" and candidate.preparation is None
            and offer is not None and offer.mode.value == "earn"
            and offer.conditional_income > 0 and offer.planned_spend == 0
            and offer.replenishment is None)


def _task_return_context_supported(menu, scope="resource-pressure-one-with-earning-peer-v1"):
    # Public normalized need and prospective earning facts only. No inventory
    # identifiers, private binding identities, map, species or supplied target.
    pressure = menu.context.resource_pressure
    supported_pressure = (0.0 < pressure <= 1.0 if scope in {"resource-pressure-positive-with-earning-peer-v2",
                              "cash-short-resource-pressure-with-earning-peer-v3"}
                          else pressure == 1.0)
    return (supported_pressure
            and menu.context.economy_snapshot is not None
            and menu.context.target_cash is not None and menu.context.target_cash > 0
            and (scope != "cash-short-resource-pressure-with-earning-peer-v3"
                 or menu.context.economy_snapshot.cash < menu.context.target_cash)
            and any(_task_return_income(menu.candidates[i]) for i in menu.available_indices))


def _task_return_candidate_supported(candidate, scope="resource-pressure-one-with-earning-peer-v1"):
    if scope in {"resource-pressure-positive-with-earning-peer-v2",
                 "cash-short-resource-pressure-with-earning-peer-v3"}:
        return candidate.features.kind.value in {"acquire", "develop", "resupply"}
    return (_task_return_income(candidate)
            or candidate.features.kind.value == "develop" and candidate.preparation is not None)
