"""Logical root demand for the powered living-Pokedex causal curriculum.

This schedule is a capacity probe, not a behavior commitment.  It expands ten
train menus to nine independent contexts each and five development menus to
twenty-one independent contexts each.  Train candidate positions are balanced
only to prove that the inventory can host the eventual blocked randomization;
the real random permutations are frozen separately immediately before a
campaign.  Development focus strata are balanced without choosing a policy
arm or reading any outcome.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Literal

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    LivingDexCausalCurriculumDesign,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CAUSAL_CAPACITY_SCHEDULE_SCHEMA = (
    "pokemon.core.living-dex-causal-capacity-schedule.v1"
)

LivingDexCapacityPartition = Literal["train", "development"]


class LivingDexCausalCapacityScheduleError(ValueError):
    """The logical demand no longer represents the powered design."""


@dataclass(frozen=True, slots=True)
class LivingDexCausalCapacitySlot:
    """One outcome-blind logical demand for a distinct physical root."""

    partition: LivingDexCapacityPartition
    template_ordinal: int
    repetition_ordinal: int
    focus_kind: LivingDexOptionKind
    assigned_candidate_index: int | None

    def __post_init__(self) -> None:
        if self.partition not in {"train", "development"}:
            raise LivingDexCausalCapacityScheduleError(
                "causal capacity partition differs"
            )
        for value, subject in (
            (self.template_ordinal, "template ordinal"),
            (self.repetition_ordinal, "repetition ordinal"),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexCausalCapacityScheduleError(f"{subject} differs")
        if self.focus_kind not in RED_DIRECT_CAUSAL_OPTION_KINDS:
            raise LivingDexCausalCapacityScheduleError(
                "capacity focus kind is not directly executable in Red"
            )
        if self.partition == "train":
            if (
                type(self.assigned_candidate_index) is not int  # noqa: E721
                or not 0 <= self.assigned_candidate_index < 3
            ):
                raise LivingDexCausalCapacityScheduleError(
                    "train capacity lacks a candidate position"
                )
        elif self.assigned_candidate_index is not None:
            raise LivingDexCausalCapacityScheduleError(
                "development capacity contains a policy choice"
            )

    @property
    def logical_slot_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "assigned_candidate_index": self.assigned_candidate_index,
            "focus_kind": self.focus_kind.value,
            "partition": self.partition,
            "repetition_ordinal": self.repetition_ordinal,
            "schema": "pokemon.core.private-living-dex-causal-capacity-slot.v1",
            "template_ordinal": self.template_ordinal,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCausalCapacitySchedule:
    """Complete 90+105 logical demand frozen without title input."""

    train_menus: tuple[tuple[LivingDexOptionKind, ...], ...]
    development_menus: tuple[tuple[LivingDexOptionKind, ...], ...]
    slots: tuple[LivingDexCausalCapacitySlot, ...]

    def __post_init__(self) -> None:
        _validate_menus(self.train_menus, expected=10)
        _validate_menus(self.development_menus, expected=5)
        if (
            not isinstance(self.slots, tuple)
            or len(self.slots) != 195
            or any(not isinstance(item, LivingDexCausalCapacitySlot) for item in self.slots)
        ):
            raise LivingDexCausalCapacityScheduleError(
                "causal capacity schedule must contain 195 slots"
            )
        for item in self.slots:
            item.__post_init__()
            menus = self.train_menus if item.partition == "train" else self.development_menus
            if item.template_ordinal >= len(menus) or item.focus_kind not in menus[
                item.template_ordinal
            ]:
                raise LivingDexCausalCapacityScheduleError(
                    "capacity focus kind is absent from its menu"
                )
            if item.partition == "train":
                candidate_index = item.assigned_candidate_index
                assert candidate_index is not None
                if menus[item.template_ordinal][candidate_index] is not item.focus_kind:
                    raise LivingDexCausalCapacityScheduleError(
                        "train capacity candidate position differs from its menu"
                    )
        digests = tuple(item.logical_slot_sha256 for item in self.slots)
        if len(set(digests)) != len(digests):
            raise LivingDexCausalCapacityScheduleError(
                "causal capacity schedule repeats a logical slot"
            )

        train = tuple(item for item in self.slots if item.partition == "train")
        development = tuple(item for item in self.slots if item.partition == "development")
        train_templates = Counter(item.template_ordinal for item in train)
        development_templates = Counter(item.template_ordinal for item in development)
        if train_templates != Counter({index: 9 for index in range(10)}):
            raise LivingDexCausalCapacityScheduleError(
                "train capacity template demand differs"
            )
        if development_templates != Counter({index: 21 for index in range(5)}):
            raise LivingDexCausalCapacityScheduleError(
                "development capacity template demand differs"
            )
        for template in range(10):
            positions = Counter(
                item.assigned_candidate_index
                for item in train
                if item.template_ordinal == template
            )
            if positions != Counter({0: 3, 1: 3, 2: 3}):
                raise LivingDexCausalCapacityScheduleError(
                    "train capacity positions are not balanced within template"
                )
        if Counter(item.focus_kind for item in development) != Counter(
            {kind: 15 for kind in RED_DIRECT_CAUSAL_OPTION_KINDS}
        ):
            raise LivingDexCausalCapacityScheduleError(
                "development capacity focus strata differ"
            )

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "behavior_commitments": 0,
            "development_menus": [
                [kind.value for kind in menu] for menu in self.development_menus
            ],
            "model_choices": 0,
            "outcomes_observed": 0,
            "schema": LIVING_DEX_CAUSAL_CAPACITY_SCHEDULE_SCHEMA,
            "slots": [item.private_dict() for item in self.slots],
            "train_menus": [[kind.value for kind in menu] for menu in self.train_menus],
        }

    def public_dict(self) -> dict[str, object]:
        train = tuple(item for item in self.slots if item.partition == "train")
        development = tuple(item for item in self.slots if item.partition == "development")
        return {
            "behavior_commitments": 0,
            "capacity_only_not_behavior_assignment": True,
            "development_contexts": len(development),
            "development_focus_kind_counts": dict(
                sorted(Counter(item.focus_kind.value for item in development).items())
            ),
            "development_menu_templates": len(self.development_menus),
            "model_choices": 0,
            "outcomes_observed": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schedule_sha256": self.schedule_sha256,
            "schema": LIVING_DEX_CAUSAL_CAPACITY_SCHEDULE_SCHEMA,
            "train_candidate_index_counts": dict(
                sorted(
                    Counter(str(item.assigned_candidate_index) for item in train).items()
                )
            ),
            "train_contexts": len(train),
            "train_focus_kind_counts": dict(
                sorted(Counter(item.focus_kind.value for item in train).items())
            ),
            "train_menu_templates": len(self.train_menus),
        }


def build_living_dex_causal_capacity_schedule(
    train_menus: tuple[tuple[LivingDexOptionKind, ...], ...],
    development_menus: tuple[tuple[LivingDexOptionKind, ...], ...],
    *,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalCapacitySchedule:
    """Expand genuine menu templates into the complete logical root demand."""

    active_design = LivingDexCausalCurriculumDesign() if design is None else design
    if not isinstance(active_design, LivingDexCausalCurriculumDesign):
        raise TypeError("causal capacity schedule needs its frozen design")
    active_design.__post_init__()
    _validate_menus(train_menus, expected=active_design.train_menu_templates)
    _validate_menus(
        development_menus,
        expected=active_design.minimum_development_menu_templates,
    )
    train_slots = tuple(
        LivingDexCausalCapacitySlot(
            partition="train",
            template_ordinal=template,
            repetition_ordinal=repetition,
            focus_kind=menu[repetition % 3],
            assigned_candidate_index=repetition % 3,
        )
        for template, menu in enumerate(train_menus)
        for repetition in range(active_design.train_contexts_per_menu_template)
    )
    development_slot_menus = tuple(
        development_menus[template]
        for template in range(len(development_menus))
        for _ in range(
            active_design.prospective_development_contexts // len(development_menus)
        )
    )
    development_focus = _balanced_development_focus(development_slot_menus)
    development_contexts_per_template = (
        active_design.prospective_development_contexts // len(development_menus)
    )
    development_slots = tuple(
        LivingDexCausalCapacitySlot(
            partition="development",
            template_ordinal=index // development_contexts_per_template,
            repetition_ordinal=index % development_contexts_per_template,
            focus_kind=focus,
            assigned_candidate_index=None,
        )
        for index, focus in enumerate(development_focus)
    )
    return LivingDexCausalCapacitySchedule(
        train_menus=train_menus,
        development_menus=development_menus,
        slots=(*train_slots, *development_slots),
    )


def _balanced_development_focus(
    menus: tuple[tuple[LivingDexOptionKind, ...], ...],
) -> tuple[LivingDexOptionKind, ...]:
    """Solve the fixed 105-by-7 stratification as an exact bipartite flow."""

    slot_count = len(menus)
    kinds = RED_DIRECT_CAUSAL_OPTION_KINDS
    source = 0
    first_slot = 1
    first_kind = first_slot + slot_count
    sink = first_kind + len(kinds)
    capacity: dict[tuple[int, int], int] = {}
    neighbors: dict[int, list[int]] = {node: [] for node in range(sink + 1)}

    def edge(left: int, right: int, amount: int) -> None:
        capacity[(left, right)] = amount
        capacity.setdefault((right, left), 0)
        neighbors[left].append(right)
        neighbors[right].append(left)

    for index, menu in enumerate(menus):
        slot_node = first_slot + index
        edge(source, slot_node, 1)
        for kind in menu:
            edge(slot_node, first_kind + kinds.index(kind), 1)
    if slot_count % len(kinds):
        raise LivingDexCausalCapacityScheduleError(
            "development focus demand cannot be balanced across Red kinds"
        )
    contexts_per_kind = slot_count // len(kinds)
    for index in range(len(kinds)):
        edge(first_kind + index, sink, contexts_per_kind)

    flow: dict[tuple[int, int], int] = Counter()
    total = 0
    while True:
        parent: dict[int, int] = {source: -1}
        queue = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for successor in neighbors[node]:
                if successor not in parent and flow[(node, successor)] < capacity[
                    (node, successor)
                ]:
                    parent[successor] = node
                    queue.append(successor)
        if sink not in parent:
            break
        node = sink
        while node != source:
            prior = parent[node]
            flow[(prior, node)] += 1
            flow[(node, prior)] -= 1
            node = prior
        total += 1
    if total != slot_count:
        raise LivingDexCausalCapacityScheduleError(
            "development menus cannot support ten focus contexts per Red kind"
        )
    selected: list[LivingDexOptionKind] = []
    for index in range(slot_count):
        slot_node = first_slot + index
        choices = tuple(
            kinds[kind_index]
            for kind_index in range(len(kinds))
            if flow[(slot_node, first_kind + kind_index)] == 1
        )
        if len(choices) != 1:
            raise LivingDexCausalCapacityScheduleError(
                "development focus flow is incomplete"
            )
        selected.append(choices[0])
    return tuple(selected)


def _validate_menus(
    menus: tuple[tuple[LivingDexOptionKind, ...], ...],
    *,
    expected: int,
) -> None:
    if (
        not isinstance(menus, tuple)
        or len(menus) != expected
        or any(
            not isinstance(menu, tuple)
            or len(menu) != 3
            or len(set(menu)) != 3
            or any(kind not in RED_DIRECT_CAUSAL_OPTION_KINDS for kind in menu)
            for menu in menus
        )
    ):
        raise LivingDexCausalCapacityScheduleError(
            "causal capacity needs genuine three-kind Red menus"
        )


__all__ = [
    "LIVING_DEX_CAUSAL_CAPACITY_SCHEDULE_SCHEMA",
    "LivingDexCausalCapacitySchedule",
    "LivingDexCausalCapacityScheduleError",
    "LivingDexCausalCapacitySlot",
    "build_living_dex_causal_capacity_schedule",
]
