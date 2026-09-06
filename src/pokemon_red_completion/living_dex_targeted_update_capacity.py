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
LIVING_DEX_TARGETED_SCHEDULE_SCHEMA = "pokemon.core.living-dex-targeted-update-schedule.v1"
LIVING_DEX_TARGETED_ROOT_DIVERSITY_POLICY_SCHEMA = (
    "pokemon.core.living-dex-targeted-root-diversity-policy.v1"
)
LIVING_DEX_TARGETED_ROOT_DIVERSITY_RESULT_SCHEMA = (
    "pokemon.core.living-dex-targeted-root-diversity-result.v1"
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
                not isinstance(kind, LivingDexOptionKind) for kind in self.available_option_kinds
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
            or self.minimum_settled_train > sum(train.values()) - self.maximum_train_setup_censors
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
                kind.value: count for kind, count in self.minimum_settled_train_by_kind
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
    development_compatible_context_counts: tuple[tuple[LivingDexOptionKind, int], ...]
    maximum_train_replays_per_context: int
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
                kind.value: count for kind, count in self.development_compatible_context_counts
            },
            "development_context_deficit": (
                self.policy.development_roots - self.development_maximum_matching
            ),
            "development_contexts": self.development_contexts,
            "development_maximum_matching": self.development_maximum_matching,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "maximum_train_replays_per_context": (self.maximum_train_replays_per_context),
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
                kind.value: count for kind, count in self.train_compatible_context_counts
            },
            "train_context_deficit": (self.policy.train_roots - self.train_maximum_matching),
            "train_contexts": self.train_contexts,
            "train_maximum_matching": self.train_maximum_matching,
            "training_targets_emitted": 0,
        }


@dataclass(frozen=True, slots=True)
class LivingDexTargetedRootDiversityPolicy:
    """Minimum independent-root coverage for a successor train schedule."""

    minimum_train_physical_roots: int
    maximum_train_slots_per_physical_root: int
    minimum_physical_roots_by_focus_kind: tuple[
        tuple[LivingDexOptionKind, int], ...
    ]

    def __post_init__(self) -> None:
        minimums = _kind_counter(
            self.minimum_physical_roots_by_focus_kind,
            subject="targeted root diversity",
        )
        if (
            type(self.minimum_train_physical_roots) is not int  # noqa: E721
            or self.minimum_train_physical_roots < 2
            or type(self.maximum_train_slots_per_physical_root) is not int  # noqa: E721
            or self.maximum_train_slots_per_physical_root < 1
            or any(value < 2 for value in minimums.values())
        ):
            raise LivingDexTargetedCapacityError(
                "targeted root diversity policy differs"
            )

    @classmethod
    def v1(cls) -> LivingDexTargetedRootDiversityPolicy:
        """Prevent the root/focus confounding observed in the first campaign."""

        return cls(
            minimum_train_physical_roots=4,
            maximum_train_slots_per_physical_root=3,
            minimum_physical_roots_by_focus_kind=(
                (LivingDexOptionKind.ACQUIRE, 2),
                (LivingDexOptionKind.DEVELOP, 2),
            ),
        )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "maximum_train_slots_per_physical_root": (
                self.maximum_train_slots_per_physical_root
            ),
            "minimum_physical_roots_by_focus_kind": {
                kind.value: count
                for kind, count in self.minimum_physical_roots_by_focus_kind
            },
            "minimum_train_physical_roots": self.minimum_train_physical_roots,
            "schema": LIVING_DEX_TARGETED_ROOT_DIVERSITY_POLICY_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class LivingDexTargetedRootDiversityResult:
    """Identity-free audit of root concentration in one frozen schedule."""

    policy: LivingDexTargetedRootDiversityPolicy
    train_slots: int
    train_physical_roots: int
    maximum_slots_on_one_physical_root: int
    physical_roots_by_focus_kind: tuple[tuple[LivingDexOptionKind, int], ...]
    reasons: tuple[str, ...]

    @property
    def diversity_sufficient(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "controller_actions": 0,
            "diversity_sufficient": self.diversity_sufficient,
            "emulator_frames": 0,
            "maximum_slots_on_one_physical_root": (
                self.maximum_slots_on_one_physical_root
            ),
            "model_fits": 0,
            "model_predictions": 0,
            "physical_roots_by_focus_kind": {
                kind.value: count for kind, count in self.physical_roots_by_focus_kind
            },
            "policy": self.policy.public_dict(),
            "policy_sha256": self.policy.policy_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reasons": list(self.reasons),
            "schema": LIVING_DEX_TARGETED_ROOT_DIVERSITY_RESULT_SCHEMA,
            "teacher_queries": 0,
            "train_physical_roots": self.train_physical_roots,
            "train_slots": self.train_slots,
        }


@dataclass(frozen=True, slots=True)
class LivingDexTargetedScheduleSlot:
    """One prospectively assigned semantic question and reset identity."""

    partition: LivingDexTargetedPartition
    focus_kind: LivingDexOptionKind
    lineage_sha256: str
    physical_root_sha256: str
    reset_ordinal: int

    def __post_init__(self) -> None:
        if self.partition not in {"train", "development"}:
            raise LivingDexTargetedCapacityError("targeted schedule partition differs")
        if not isinstance(self.focus_kind, LivingDexOptionKind):
            raise TypeError("targeted schedule focus kind differs")
        for value in (self.lineage_sha256, self.physical_root_sha256):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise LivingDexTargetedCapacityError("targeted schedule identity differs")
        if type(self.reset_ordinal) is not int or self.reset_ordinal < 0:  # noqa: E721
            raise LivingDexTargetedCapacityError("targeted schedule reset ordinal differs")
        if self.partition == "development" and self.reset_ordinal != 0:
            raise LivingDexTargetedCapacityError(
                "development schedule cannot contain a reset replay"
            )

    @property
    def slot_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "focus_kind": self.focus_kind.value,
            "lineage_sha256": self.lineage_sha256,
            "partition": self.partition,
            "physical_root_sha256": self.physical_root_sha256,
            "reset_ordinal": self.reset_ordinal,
            "schema": "pokemon.core.living-dex-targeted-update-schedule-slot.v1",
        }


@dataclass(frozen=True, slots=True)
class LivingDexTargetedSchedule:
    """Complete train/reset and one-shot development allocation."""

    policy: LivingDexTargetedCapacityPolicy
    maximum_train_replays_per_context: int
    slots: tuple[LivingDexTargetedScheduleSlot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, LivingDexTargetedCapacityPolicy):
            raise TypeError("targeted schedule policy differs")
        self.policy.__post_init__()
        if (
            type(self.maximum_train_replays_per_context) is not int  # noqa: E721
            or not 1 <= self.maximum_train_replays_per_context <= 32
        ):
            raise LivingDexTargetedCapacityError("targeted schedule train replay bound differs")
        if not isinstance(self.slots, tuple) or any(
            not isinstance(slot, LivingDexTargetedScheduleSlot) for slot in self.slots
        ):
            raise TypeError("targeted schedule slots differ")
        for slot in self.slots:
            slot.__post_init__()
        train = tuple(slot for slot in self.slots if slot.partition == "train")
        development = tuple(slot for slot in self.slots if slot.partition == "development")
        if (
            len(train) != self.policy.train_roots
            or len(development) != self.policy.development_roots
            or Counter(slot.focus_kind for slot in train)
            != Counter(dict(self.policy.train_focus_kind_counts))
            or Counter(slot.focus_kind for slot in development)
            != Counter(dict(self.policy.development_focus_kind_counts))
        ):
            raise LivingDexTargetedCapacityError("targeted schedule denominator differs")
        train_lineages = Counter(slot.lineage_sha256 for slot in train)
        if any(
            count > self.maximum_train_replays_per_context for count in train_lineages.values()
        ) or any(
            sorted(slot.reset_ordinal for slot in train if slot.lineage_sha256 == lineage)
            != list(range(count))
            for lineage, count in train_lineages.items()
        ):
            raise LivingDexTargetedCapacityError("targeted schedule exceeds its train reset bound")
        development_lineages = [slot.lineage_sha256 for slot in development]
        development_roots = [slot.physical_root_sha256 for slot in development]
        if (
            len(set(development_lineages)) != len(development_lineages)
            or len(set(development_roots)) != len(development_roots)
            or set(train_lineages) & set(development_lineages)
            or {slot.physical_root_sha256 for slot in train} & set(development_roots)
            or len({slot.slot_sha256 for slot in self.slots}) != len(self.slots)
        ):
            raise LivingDexTargetedCapacityError(
                "targeted schedule violates train/development separation"
            )

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "maximum_train_replays_per_context": (self.maximum_train_replays_per_context),
            "policy_sha256": self.policy.policy_sha256,
            "schema": LIVING_DEX_TARGETED_SCHEDULE_SCHEMA,
            "slots": [slot.private_dict() for slot in self.slots],
        }

    def public_dict(self) -> dict[str, object]:
        train = tuple(slot for slot in self.slots if slot.partition == "train")
        development = tuple(slot for slot in self.slots if slot.partition == "development")
        return {
            "behavior_commitments": 0,
            "controller_actions": 0,
            "development_replays": 0,
            "development_roots": len(development),
            "emulator_frames": 0,
            "maximum_train_replays_per_context": (self.maximum_train_replays_per_context),
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "policy_sha256": self.policy.policy_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schedule_sha256": self.schedule_sha256,
            "schema": LIVING_DEX_TARGETED_SCHEDULE_SCHEMA,
            "teacher_queries": 0,
            "train_focus_kind_counts": {
                kind.value: count for kind, count in self.policy.train_focus_kind_counts
            },
            "train_resets": len(train),
            "train_roots": len({slot.lineage_sha256 for slot in train}),
        }


def audit_living_dex_targeted_update_capacity(
    contexts: Iterable[LivingDexTargetedCapacityContext],
    *,
    policy: LivingDexTargetedCapacityPolicy | None = None,
    maximum_train_replays_per_context: int = 1,
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
    if (
        type(maximum_train_replays_per_context) is not int  # noqa: E721
        or not 1 <= maximum_train_replays_per_context <= 32
    ):
        raise LivingDexTargetedCapacityError("targeted capacity train replay bound differs")
    train = tuple(row for row in rows if row.partition == "train")
    development = tuple(row for row in rows if row.partition == "development")
    train_demands = _expand_demands(active.train_focus_kind_counts)
    development_demands = _expand_demands(active.development_focus_kind_counts)
    train_matching = _maximum_matching(
        train_demands,
        train,
        maximum_uses_per_context=maximum_train_replays_per_context,
    )
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
        maximum_train_replays_per_context=maximum_train_replays_per_context,
        reasons=tuple(reasons),
    )


def freeze_living_dex_targeted_schedule(
    contexts: Iterable[LivingDexTargetedCapacityContext],
    *,
    policy: LivingDexTargetedCapacityPolicy | None = None,
    maximum_train_replays_per_context: int = 1,
) -> LivingDexTargetedSchedule:
    """Deterministically freeze one complete outcome-blind allocation."""

    rows = tuple(contexts)
    result = audit_living_dex_targeted_update_capacity(
        rows,
        policy=policy,
        maximum_train_replays_per_context=maximum_train_replays_per_context,
    )
    if not result.capacity_sufficient:
        raise LivingDexTargetedCapacityError(
            "targeted schedule cannot freeze insufficient capacity"
        )
    active = result.policy
    train_contexts = tuple(row for row in rows if row.partition == "train")
    development_contexts = tuple(row for row in rows if row.partition == "development")
    train_demands = _expand_demands(active.train_focus_kind_counts)
    development_demands = _expand_demands(active.development_focus_kind_counts)
    train_assignment = _matching_assignments(
        train_demands,
        train_contexts,
        maximum_uses_per_context=maximum_train_replays_per_context,
    )
    development_assignment = _matching_assignments(
        development_demands,
        development_contexts,
        maximum_uses_per_context=1,
    )
    reset_counts: Counter[str] = Counter()
    slots: list[LivingDexTargetedScheduleSlot] = []
    for partition, demands, contexts_for_partition, assignment in (
        ("train", train_demands, train_contexts, train_assignment),
        (
            "development",
            development_demands,
            development_contexts,
            development_assignment,
        ),
    ):
        for demand_index, kind in enumerate(demands):
            context = contexts_for_partition[assignment[demand_index]]
            reset_ordinal = reset_counts[context.lineage_sha256] if partition == "train" else 0
            if partition == "train":
                reset_counts[context.lineage_sha256] += 1
            slots.append(
                LivingDexTargetedScheduleSlot(
                    partition=partition,  # type: ignore[arg-type]
                    focus_kind=kind,
                    lineage_sha256=context.lineage_sha256,
                    physical_root_sha256=context.physical_root_sha256,
                    reset_ordinal=reset_ordinal,
                )
            )
    return LivingDexTargetedSchedule(
        policy=active,
        maximum_train_replays_per_context=maximum_train_replays_per_context,
        slots=tuple(slots),
    )


def audit_living_dex_targeted_schedule_root_diversity(
    schedule: LivingDexTargetedSchedule,
    *,
    policy: LivingDexTargetedRootDiversityPolicy | None = None,
) -> LivingDexTargetedRootDiversityResult:
    """Reject arithmetic schedules that confound focus families with one root."""

    if not isinstance(schedule, LivingDexTargetedSchedule):
        raise TypeError("targeted root diversity needs a frozen schedule")
    schedule.__post_init__()
    active = LivingDexTargetedRootDiversityPolicy.v1() if policy is None else policy
    if not isinstance(active, LivingDexTargetedRootDiversityPolicy):
        raise TypeError("targeted root diversity policy differs")
    active.__post_init__()
    train = tuple(slot for slot in schedule.slots if slot.partition == "train")
    concentration = Counter(slot.physical_root_sha256 for slot in train)
    kind_counts = tuple(
        (
            kind,
            len(
                {
                    slot.physical_root_sha256
                    for slot in train
                    if slot.focus_kind is kind
                }
            ),
        )
        for kind, _minimum in active.minimum_physical_roots_by_focus_kind
    )
    reasons: list[str] = []
    if len(concentration) < active.minimum_train_physical_roots:
        reasons.append("insufficient_distinct_train_physical_roots")
    if concentration and max(concentration.values()) > (
        active.maximum_train_slots_per_physical_root
    ):
        reasons.append("excessive_train_slot_root_concentration")
    observed_by_kind = dict(kind_counts)
    if any(
        observed_by_kind[kind] < minimum
        for kind, minimum in active.minimum_physical_roots_by_focus_kind
    ):
        reasons.append("insufficient_focus_kind_root_diversity")
    return LivingDexTargetedRootDiversityResult(
        policy=active,
        train_slots=len(train),
        train_physical_roots=len(concentration),
        maximum_slots_on_one_physical_root=(
            max(concentration.values()) if concentration else 0
        ),
        physical_roots_by_focus_kind=kind_counts,
        reasons=tuple(reasons),
    )


def require_living_dex_targeted_schedule_root_diversity(
    schedule: LivingDexTargetedSchedule,
    *,
    policy: LivingDexTargetedRootDiversityPolicy | None = None,
) -> LivingDexTargetedRootDiversityResult:
    """Return a safe diversity audit or refuse the successor campaign."""

    result = audit_living_dex_targeted_schedule_root_diversity(
        schedule,
        policy=policy,
    )
    if not result.diversity_sufficient:
        raise LivingDexTargetedCapacityError(
            "targeted successor schedule lacks independent root diversity"
        )
    return result


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
    *,
    maximum_uses_per_context: int = 1,
) -> int:
    """Return exact bounded-context demand cardinality by augmenting paths."""

    return len(
        _matching_assignments(
            demands,
            contexts,
            maximum_uses_per_context=maximum_uses_per_context,
        )
    )


def _matching_assignments(
    demands: tuple[LivingDexOptionKind, ...],
    contexts: tuple[LivingDexTargetedCapacityContext, ...],
    *,
    maximum_uses_per_context: int,
) -> dict[int, int]:
    """Map demand index to context index under one deterministic reset cap."""

    context_slots = tuple(
        context_index
        for context_index in range(len(contexts))
        for _ in range(maximum_uses_per_context)
    )
    context_slot_to_demand: dict[int, int] = {}
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
        for slot_index, context_index in enumerate(context_slots):
            context = contexts[context_index]
            if slot_index in seen or kind not in context.available_option_kinds:
                continue
            seen.add(slot_index)
            prior = context_slot_to_demand.get(slot_index)
            if prior is None or augment(prior, seen):
                context_slot_to_demand[slot_index] = demand_index
                return True
        return False

    for index in ordered:
        augment(index, set())
    return {
        demand_index: context_slots[slot_index]
        for slot_index, demand_index in context_slot_to_demand.items()
    }


__all__ = [
    "LIVING_DEX_TARGETED_CAPACITY_POLICY_SCHEMA",
    "LIVING_DEX_TARGETED_CAPACITY_RESULT_SCHEMA",
    "LIVING_DEX_TARGETED_ROOT_DIVERSITY_POLICY_SCHEMA",
    "LIVING_DEX_TARGETED_ROOT_DIVERSITY_RESULT_SCHEMA",
    "LIVING_DEX_TARGETED_SCHEDULE_SCHEMA",
    "LivingDexTargetedCapacityContext",
    "LivingDexTargetedCapacityError",
    "LivingDexTargetedCapacityPolicy",
    "LivingDexTargetedCapacityResult",
    "LivingDexTargetedRootDiversityPolicy",
    "LivingDexTargetedRootDiversityResult",
    "LivingDexTargetedSchedule",
    "LivingDexTargetedScheduleSlot",
    "audit_living_dex_targeted_schedule_root_diversity",
    "audit_living_dex_targeted_update_capacity",
    "freeze_living_dex_targeted_schedule",
    "require_living_dex_targeted_schedule_root_diversity",
]
