"""Action-free capacity gate for a targeted living-Pokedex model update.

The first authentic shadow batch exposed acquisition overconfidence and party-
development underconfidence.  This title-neutral boundary asks whether a bank
contains enough untouched upstream lineages to collect a small correction and
then evaluate it on a separate paired partition.  It chooses no policy action,
opens no outcome, and publishes no lineage identity.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_TARGETED_CAPACITY_POLICY_SCHEMA = (
    "pokemon.core.living-dex-targeted-update-capacity-policy.v1"
)
LIVING_DEX_TARGETED_CAPACITY_RESULT_SCHEMA = (
    "pokemon.core.living-dex-targeted-update-capacity-result.v1"
)

LivingDexTargetedPartition = Literal["train", "development"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_KIND_ORDER = {kind: index for index, kind in enumerate(LivingDexOptionKind)}


class LivingDexTargetedCapacityError(ValueError):
    """Untouched capacity cannot support the frozen targeted design."""


@dataclass(frozen=True, slots=True)
class LivingDexTargetedCapacityContext:
    """One untouched upstream lineage and the option kinds it can expose."""

    lineage_sha256: str
    physical_root_sha256: str
    partition: LivingDexTargetedPartition
    available_option_kinds: tuple[LivingDexOptionKind, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.lineage_sha256, str)
            or _SHA256.fullmatch(self.lineage_sha256) is None
            or not isinstance(self.physical_root_sha256, str)
            or _SHA256.fullmatch(self.physical_root_sha256) is None
        ):
            raise LivingDexTargetedCapacityError("targeted capacity identity differs")
        if self.partition not in {"train", "development"}:
            raise LivingDexTargetedCapacityError("targeted capacity partition differs")
        if (
            not isinstance(self.available_option_kinds, tuple)
            or len(self.available_option_kinds) < 2
            or len(set(self.available_option_kinds)) != len(self.available_option_kinds)
            or any(
                not isinstance(kind, LivingDexOptionKind)
                for kind in self.available_option_kinds
            )
            or tuple(sorted(self.available_option_kinds, key=_KIND_ORDER.__getitem__))
            != self.available_option_kinds
        ):
            raise LivingDexTargetedCapacityError("targeted capacity option menu differs")


@dataclass(frozen=True, slots=True)
class LivingDexTargetedCapacityPolicy:
    """Prospective train and paired-development demand by semantic kind."""

    train_focus_kind_counts: tuple[tuple[LivingDexOptionKind, int], ...]
    development_focus_kind_counts: tuple[tuple[LivingDexOptionKind, int], ...]
    maximum_train_setup_censors: int
    minimum_settled_train: int
    minimum_settled_train_by_kind: tuple[tuple[LivingDexOptionKind, int], ...]

    def __post_init__(self) -> None:
        train = _kind_counter(self.train_focus_kind_counts, subject="train focus")
        development = _kind_counter(
            self.development_focus_kind_counts,
            subject="development focus",
        )
        minimums = _kind_counter(
            self.minimum_settled_train_by_kind,
            subject="settled train",
        )
        if (
            type(self.maximum_train_setup_censors) is not int  # noqa: E721
            or self.maximum_train_setup_censors < 0
            or type(self.minimum_settled_train) is not int  # noqa: E721
            or self.minimum_settled_train <= 0
            or self.minimum_settled_train
            > sum(train.values()) - self.maximum_train_setup_censors
            or any(minimums[kind] > train[kind] for kind in minimums)
            or sum(development.values()) < 2
        ):
            raise LivingDexTargetedCapacityError(
                "targeted capacity policy is arithmetically impossible"
            )

    @classmethod
    def v1(cls) -> LivingDexTargetedCapacityPolicy:
        """Return the frozen post-five-case capacity demand."""

        return cls(
            train_focus_kind_counts=(
                (LivingDexOptionKind.ACQUIRE, 4),
                (LivingDexOptionKind.DEVELOP, 4),
                (LivingDexOptionKind.MANAGE_STORAGE, 1),
                (LivingDexOptionKind.RESUPPLY, 1),
            ),
            development_focus_kind_counts=(
                (LivingDexOptionKind.ACQUIRE, 2),
                (LivingDexOptionKind.EVOLVE, 1),
                (LivingDexOptionKind.DEVELOP, 2),
                (LivingDexOptionKind.MANAGE_STORAGE, 1),
                (LivingDexOptionKind.RESUPPLY, 1),
                (LivingDexOptionKind.UNLOCK_ACCESS, 1),
            ),
            maximum_train_setup_censors=2,
            minimum_settled_train=8,
            minimum_settled_train_by_kind=(
                (LivingDexOptionKind.ACQUIRE, 3),
                (LivingDexOptionKind.DEVELOP, 3),
            ),
        )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    @property
    def train_roots(self) -> int:
        return sum(count for _, count in self.train_focus_kind_counts)

    @property
    def development_roots(self) -> int:
        return sum(count for _, count in self.development_focus_kind_counts)

    def public_dict(self) -> dict[str, object]:
        return {
            "development_focus_kind_counts": {
                kind.value: count for kind, count in self.development_focus_kind_counts
            },
            "development_roots": self.development_roots,
            "maximum_train_setup_censors": self.maximum_train_setup_censors,
            "minimum_settled_train": self.minimum_settled_train,
            "minimum_settled_train_by_kind": {
                kind.value: count
                for kind, count in self.minimum_settled_train_by_kind
            },
            "schema": LIVING_DEX_TARGETED_CAPACITY_POLICY_SCHEMA,
            "train_focus_kind_counts": {
                kind.value: count for kind, count in self.train_focus_kind_counts
            },
            "train_roots": self.train_roots,
        }


@dataclass(frozen=True, slots=True)
class LivingDexTargetedCapacityResult:
    """Aggregate exact-matching result with all identities suppressed."""

    policy: LivingDexTargetedCapacityPolicy
    contexts_observed: int
    train_contexts: int
    development_contexts: int
    train_maximum_matching: int
    development_maximum_matching: int
    train_compatible_context_counts: tuple[tuple[LivingDexOptionKind, int], ...]
    development_compatible_context_counts: tuple[
        tuple[LivingDexOptionKind, int], ...
    ]
    reasons: tuple[str, ...]

    @property
    def capacity_sufficient(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_commitments": 0,
            "capacity_sufficient": self.capacity_sufficient,
            "contexts_observed": self.contexts_observed,
            "controller_actions": 0,
            "development_compatible_context_counts": {
                kind.value: count
                for kind, count in self.development_compatible_context_counts
            },
            "development_context_deficit": (
                self.policy.development_roots - self.development_maximum_matching
            ),
            "development_contexts": self.development_contexts,
            "development_maximum_matching": self.development_maximum_matching,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "policy": self.policy.public_dict(),
            "policy_sha256": self.policy.policy_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reasons": list(self.reasons),
            "root_claims": 0,
            "schema": LIVING_DEX_TARGETED_CAPACITY_RESULT_SCHEMA,
            "teacher_queries": 0,
            "train_compatible_context_counts": {
                kind.value: count
                for kind, count in self.train_compatible_context_counts
            },
            "train_context_deficit": (
                self.policy.train_roots - self.train_maximum_matching
            ),
            "train_contexts": self.train_contexts,
            "train_maximum_matching": self.train_maximum_matching,
            "training_targets_emitted": 0,
        }


def audit_living_dex_targeted_update_capacity(
    contexts: Iterable[LivingDexTargetedCapacityContext],
    *,
    policy: LivingDexTargetedCapacityPolicy | None = None,
) -> LivingDexTargetedCapacityResult:
    """Match each frozen semantic demand to a distinct untouched lineage."""

    rows = tuple(contexts)
    if any(not isinstance(row, LivingDexTargetedCapacityContext) for row in rows):
        raise TypeError("targeted capacity contexts differ")
    for row in rows:
        row.__post_init__()
    if len({row.lineage_sha256 for row in rows}) != len(rows):
        raise LivingDexTargetedCapacityError("targeted capacity repeats a lineage")
    if len({row.physical_root_sha256 for row in rows}) != len(rows):
        raise LivingDexTargetedCapacityError("targeted capacity repeats a physical root")
    active = LivingDexTargetedCapacityPolicy.v1() if policy is None else policy
    if not isinstance(active, LivingDexTargetedCapacityPolicy):
        raise TypeError("targeted capacity policy differs")
    active.__post_init__()
    train = tuple(row for row in rows if row.partition == "train")
    development = tuple(row for row in rows if row.partition == "development")
    train_demands = _expand_demands(active.train_focus_kind_counts)
    development_demands = _expand_demands(active.development_focus_kind_counts)
    train_matching = _maximum_matching(train_demands, train)
    development_matching = _maximum_matching(development_demands, development)
    reasons: list[str] = []
    if train_matching < len(train_demands):
        reasons.append("insufficient_train_kind_compatible_lineages")
    if development_matching < len(development_demands):
        reasons.append("insufficient_development_kind_compatible_lineages")
    return LivingDexTargetedCapacityResult(
        policy=active,
        contexts_observed=len(rows),
        train_contexts=len(train),
        development_contexts=len(development),
        train_maximum_matching=train_matching,
        development_maximum_matching=development_matching,
        train_compatible_context_counts=_compatible_counts(
            train,
            active.train_focus_kind_counts,
        ),
        development_compatible_context_counts=_compatible_counts(
            development,
            active.development_focus_kind_counts,
        ),
        reasons=tuple(reasons),
    )


def _kind_counter(
    rows: tuple[tuple[LivingDexOptionKind, int], ...],
    *,
    subject: str,
) -> Counter[LivingDexOptionKind]:
    if (
        not isinstance(rows, tuple)
        or not rows
        or any(
            not isinstance(row, tuple)
            or len(row) != 2
            or not isinstance(row[0], LivingDexOptionKind)
            or type(row[1]) is not int  # noqa: E721
            or row[1] <= 0
            for row in rows
        )
        or len({row[0] for row in rows}) != len(rows)
        or tuple(sorted((row[0] for row in rows), key=_KIND_ORDER.__getitem__))
        != tuple(row[0] for row in rows)
    ):
        raise LivingDexTargetedCapacityError(f"{subject} kind counts differ")
    return Counter(dict(rows))


def _expand_demands(
    rows: tuple[tuple[LivingDexOptionKind, int], ...],
) -> tuple[LivingDexOptionKind, ...]:
    return tuple(kind for kind, count in rows for _ in range(count))


def _compatible_counts(
    contexts: tuple[LivingDexTargetedCapacityContext, ...],
    demands: tuple[tuple[LivingDexOptionKind, int], ...],
) -> tuple[tuple[LivingDexOptionKind, int], ...]:
    return tuple(
        (
            kind,
            sum(kind in context.available_option_kinds for context in contexts),
        )
        for kind, _ in demands
    )


def _maximum_matching(
    demands: tuple[LivingDexOptionKind, ...],
    contexts: tuple[LivingDexTargetedCapacityContext, ...],
) -> int:
    """Return exact one-context-per-demand cardinality by augmenting paths."""

    context_to_demand: dict[int, int] = {}
    ordered = tuple(
        sorted(
            range(len(demands)),
            key=lambda index: (
                sum(demands[index] in row.available_option_kinds for row in contexts),
                _KIND_ORDER[demands[index]],
                index,
            ),
        )
    )

    def augment(demand_index: int, seen: set[int]) -> bool:
        kind = demands[demand_index]
        for context_index, context in enumerate(contexts):
            if context_index in seen or kind not in context.available_option_kinds:
                continue
            seen.add(context_index)
            prior = context_to_demand.get(context_index)
            if prior is None or augment(prior, seen):
                context_to_demand[context_index] = demand_index
                return True
        return False

    return sum(augment(index, set()) for index in ordered)


__all__ = [
    "LIVING_DEX_TARGETED_CAPACITY_POLICY_SCHEMA",
    "LIVING_DEX_TARGETED_CAPACITY_RESULT_SCHEMA",
    "LivingDexTargetedCapacityContext",
    "LivingDexTargetedCapacityError",
    "LivingDexTargetedCapacityPolicy",
    "LivingDexTargetedCapacityResult",
    "audit_living_dex_targeted_update_capacity",
]
