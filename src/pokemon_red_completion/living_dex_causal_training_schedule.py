"""Outcome-blind blocked randomization for the powered Red causal fit.

Each of the ten genuine train menu templates is assigned nine independent
physical roots.  Within every three-root block, a committed random permutation
selects each candidate position exactly once.  A uniformly random permutation
makes every row's marginal propensity exactly one third while guaranteeing the
coverage that independent draws could miss by chance.

The schedule is created before controller input and contains no outcome,
teacher choice, model prediction, private path, species, map, or root identity.
The execution journal must bind each assignment to a distinct claimed root and
persist the selected position before releasing its controller.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from pokemon_red_completion.living_dex_causal_curriculum import (
    LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR,
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_BLOCKED_BEHAVIOR_SCHEDULE_SCHEMA = (
    "pokemon.core.private-living-dex-blocked-behavior-schedule.v1"
)
LIVING_DEX_BLOCKED_BEHAVIOR_PUBLIC_SCHEMA = (
    "pokemon.core.living-dex-blocked-behavior-schedule.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PERMUTATIONS = tuple(itertools.permutations(range(3)))


class LivingDexBlockedBehaviorError(ValueError):
    """The prospective behavior schedule is incomplete or outcome-adaptive."""


@dataclass(frozen=True, slots=True)
class LivingDexBlockedBehaviorAssignment:
    """One root slot's pre-input selected arm and exact marginal propensity."""

    template_ordinal: int
    block_ordinal: int
    within_block_ordinal: int
    candidate_index: int
    selected_kind: LivingDexOptionKind
    behavior_probabilities: tuple[Fraction, Fraction, Fraction] = (
        Fraction(1, 3),
        Fraction(1, 3),
        Fraction(1, 3),
    )

    def __post_init__(self) -> None:
        for value, subject in (
            (self.template_ordinal, "template ordinal"),
            (self.block_ordinal, "block ordinal"),
            (self.within_block_ordinal, "within-block ordinal"),
            (self.candidate_index, "candidate index"),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexBlockedBehaviorError(f"{subject} differs")
        if self.within_block_ordinal >= 3 or self.candidate_index >= 3:
            raise LivingDexBlockedBehaviorError("blocked assignment position differs")
        if self.selected_kind not in RED_DIRECT_CAUSAL_OPTION_KINDS:
            raise LivingDexBlockedBehaviorError(
                "blocked assignment selects an unsupported Red kind"
            )
        if self.behavior_probabilities != (Fraction(1, 3),) * 3:
            raise LivingDexBlockedBehaviorError(
                "blocked assignment marginal propensity differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "behavior_probabilities": [
                {
                    "denominator": value.denominator,
                    "numerator": value.numerator,
                }
                for value in self.behavior_probabilities
            ],
            "block_ordinal": self.block_ordinal,
            "candidate_index": self.candidate_index,
            "schema": "pokemon.core.private-living-dex-blocked-assignment.v1",
            "selected_kind": self.selected_kind.value,
            "template_ordinal": self.template_ordinal,
            "within_block_ordinal": self.within_block_ordinal,
        }


@dataclass(frozen=True, slots=True)
class LivingDexBlockedBehaviorSchedule:
    """Complete 90-context assignment, committed without revealing entropy."""

    menu_templates: tuple[tuple[LivingDexOptionKind, ...], ...]
    entropy_commitment_sha256: str
    assignments: tuple[LivingDexBlockedBehaviorAssignment, ...]

    def __post_init__(self) -> None:
        _validate_templates(self.menu_templates)
        if not isinstance(self.entropy_commitment_sha256, str) or (
            _SHA256.fullmatch(self.entropy_commitment_sha256) is None
        ):
            raise LivingDexBlockedBehaviorError(
                "blocked behavior entropy commitment differs"
            )
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != 90
            or any(
                not isinstance(item, LivingDexBlockedBehaviorAssignment)
                for item in self.assignments
            )
        ):
            raise LivingDexBlockedBehaviorError(
                "blocked behavior schedule must contain 90 assignments"
            )
        for item in self.assignments:
            item.__post_init__()
            if item.template_ordinal >= len(self.menu_templates) or (
                self.menu_templates[item.template_ordinal][item.candidate_index]
                is not item.selected_kind
            ):
                raise LivingDexBlockedBehaviorError(
                    "blocked assignment differs from its complete menu"
                )
        expected_keys = {
            (template, block, within)
            for template in range(10)
            for block in range(3)
            for within in range(3)
        }
        actual_keys = {
            (
                item.template_ordinal,
                item.block_ordinal,
                item.within_block_ordinal,
            )
            for item in self.assignments
        }
        if actual_keys != expected_keys:
            raise LivingDexBlockedBehaviorError(
                "blocked behavior schedule repeats or omits a root slot"
            )
        for template in range(10):
            for block in range(3):
                indices = tuple(
                    item.candidate_index
                    for item in self.assignments
                    if item.template_ordinal == template
                    and item.block_ordinal == block
                )
                if set(indices) != {0, 1, 2} or len(indices) != 3:
                    raise LivingDexBlockedBehaviorError(
                        "blocked behavior block is not a candidate permutation"
                    )
        if Counter(item.candidate_index for item in self.assignments) != Counter(
            {0: 30, 1: 30, 2: 30}
        ):
            raise LivingDexBlockedBehaviorError(
                "blocked behavior candidate positions are unbalanced"
            )

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "behavior_policy": LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR,
            "entropy_commitment_sha256": self.entropy_commitment_sha256,
            "menu_templates": [
                [kind.value for kind in menu] for menu in self.menu_templates
            ],
            "outcomes_observed": 0,
            "schema": LIVING_DEX_BLOCKED_BEHAVIOR_SCHEDULE_SCHEMA,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        kind_counts = Counter(item.selected_kind.value for item in self.assignments)
        candidate_counts = Counter(item.candidate_index for item in self.assignments)
        return {
            "assignment_count": len(self.assignments),
            "behavior_policy": LIVING_DEX_CAUSAL_TRAINING_BEHAVIOR,
            "candidate_index_counts": {
                str(index): candidate_counts[index] for index in range(3)
            },
            "entropy_committed": True,
            "full_support_marginal": {
                "denominator": 3,
                "numerator": 1,
            },
            "menu_template_count": len(self.menu_templates),
            "model_predictions": 0,
            "outcomes_observed": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schedule_sha256": self.schedule_sha256,
            "schema": LIVING_DEX_BLOCKED_BEHAVIOR_PUBLIC_SCHEMA,
            "selected_kind_counts": dict(sorted(kind_counts.items())),
            "teacher_queries": 0,
            "unselected_action_targets": 0,
        }


def freeze_living_dex_blocked_behavior_schedule(
    menu_templates: tuple[tuple[LivingDexOptionKind, ...], ...],
    *,
    entropy: bytes,
) -> LivingDexBlockedBehaviorSchedule:
    """Freeze three unbiased candidate permutations per menu template."""

    _validate_templates(menu_templates)
    if not isinstance(entropy, bytes) or len(entropy) < 32:
        raise LivingDexBlockedBehaviorError(
            "blocked behavior entropy must contain at least 256 bits"
        )
    commitment = canonical_sha256(
        {
            "entropy_sha256": hashlib.sha256(entropy).hexdigest(),
            "schema": "pokemon.core.private-living-dex-behavior-entropy.v1",
        }
    )
    assignments: list[LivingDexBlockedBehaviorAssignment] = []
    for template_ordinal, menu in enumerate(menu_templates):
        for block_ordinal in range(3):
            permutation = _PERMUTATIONS[
                _uniform_permutation_index(
                    entropy,
                    template_ordinal=template_ordinal,
                    block_ordinal=block_ordinal,
                )
            ]
            assignments.extend(
                LivingDexBlockedBehaviorAssignment(
                    template_ordinal=template_ordinal,
                    block_ordinal=block_ordinal,
                    within_block_ordinal=within,
                    candidate_index=candidate,
                    selected_kind=menu[candidate],
                )
                for within, candidate in enumerate(permutation)
            )
    return LivingDexBlockedBehaviorSchedule(
        menu_templates=menu_templates,
        entropy_commitment_sha256=commitment,
        assignments=tuple(assignments),
    )


def _validate_templates(
    menu_templates: tuple[tuple[LivingDexOptionKind, ...], ...],
) -> None:
    if (
        not isinstance(menu_templates, tuple)
        or len(menu_templates) != 10
        or any(
            not isinstance(menu, tuple)
            or len(menu) != 3
            or len(set(menu)) != 3
            or any(kind not in RED_DIRECT_CAUSAL_OPTION_KINDS for kind in menu)
            for menu in menu_templates
        )
    ):
        raise LivingDexBlockedBehaviorError(
            "blocked behavior needs ten complete three-kind Red train menus"
        )
    offered = Counter(kind for menu in menu_templates for kind in menu)
    if set(offered) != set(RED_DIRECT_CAUSAL_OPTION_KINDS) or sorted(
        offered.values()
    ) != [4, 4, 4, 4, 4, 5, 5]:
        raise LivingDexBlockedBehaviorError(
            "blocked behavior templates no longer cover the frozen option schedule"
        )


def _uniform_permutation_index(
    entropy: bytes,
    *,
    template_ordinal: int,
    block_ordinal: int,
) -> int:
    """Map committed entropy to one of six permutations without modulo bias."""

    counter = 0
    while True:
        payload = (
            b"pokemon.core.living-dex-block-permutation.v1\0"
            + entropy
            + template_ordinal.to_bytes(2, "big")
            + block_ordinal.to_bytes(2, "big")
            + counter.to_bytes(4, "big")
        )
        for value in hashlib.sha256(payload).digest():
            if value < 252:
                return value % len(_PERMUTATIONS)
        counter += 1


__all__ = [
    "LIVING_DEX_BLOCKED_BEHAVIOR_PUBLIC_SCHEMA",
    "LIVING_DEX_BLOCKED_BEHAVIOR_SCHEDULE_SCHEMA",
    "LivingDexBlockedBehaviorAssignment",
    "LivingDexBlockedBehaviorError",
    "LivingDexBlockedBehaviorSchedule",
    "freeze_living_dex_blocked_behavior_schedule",
]
