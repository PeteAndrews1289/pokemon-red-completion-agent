"""Mechanics-derived target bindings for the first Red living-dex curriculum.

The prospective schedule repeats logical family scopes on purpose.  This
module assigns one real transformation to each such scope without allowing a
slot, root, profile, route, or candidate position to become the family.  The
providers remain generic: species appear only as authenticated parameters to
the reusable boxed-evolution and targeted-development engines.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pokemon_red_completion.generation_one import GENERATION_ONE_LEVEL_EVOLUTIONS
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_collection import red_species_number, red_species_ref
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)


class RedLivingDexProviderCurriculumError(ValueError):
    """The target schedule no longer describes genuine distinct mechanics."""


@dataclass(frozen=True, slots=True)
class RedLevelEvolutionTarget:
    """One title-neutral species transition implemented by Red's level mechanic."""

    source_species_ref: str
    target_species_ref: str
    evolution_level: int

    def __post_init__(self) -> None:
        row = (
            red_species_number(self.source_species_ref),
            red_species_number(self.target_species_ref),
            self.evolution_level,
        )
        if row not in GENERATION_ONE_LEVEL_EVOLUTIONS:
            raise RedLivingDexProviderCurriculumError(
                "curriculum evolution is not in the complete Generation I graph"
            )

    def parameters(self) -> dict[str, object]:
        return {
            "source_species_ref": self.source_species_ref,
            "target_species_ref": self.target_species_ref,
            "evolution_level": self.evolution_level,
        }


@dataclass(frozen=True, slots=True)
class RedPartyDevelopmentTarget:
    """One explicitly chosen party species and one bounded level of progress."""

    trainee_species_ref: str
    level_increment: int = 1

    def __post_init__(self) -> None:
        red_species_number(self.trainee_species_ref)
        if self.level_increment != 1:
            raise RedLivingDexProviderCurriculumError(
                "party-development curriculum must use one-level quanta"
            )

    def parameters(self) -> dict[str, object]:
        return {
            "trainee_species_ref": self.trainee_species_ref,
            "level_increment": self.level_increment,
        }


@dataclass(frozen=True, slots=True)
class RedEncounterSourceTarget:
    """One real Red wild source; its cartridge-derived corridor is bound later."""

    source_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id.startswith("wild:")
            or not self.source_id.endswith(":grass")
        ):
            raise RedLivingDexProviderCurriculumError(
                "encounter curriculum source is not a Red grass source"
            )

    def family_parameters(self) -> dict[str, object]:
        return {"source_id": self.source_id}


@dataclass(frozen=True, slots=True)
class RedStorageTarget:
    """One genuine switch to a different Red storage box."""

    target_box_index: int

    def __post_init__(self) -> None:
        if (
            type(self.target_box_index) is not int  # noqa: E721
            or not 1 <= self.target_box_index < 12
        ):
            raise RedLivingDexProviderCurriculumError(
                "storage curriculum target must leave the authenticated current box"
            )

    def parameters(self) -> dict[str, object]:
        return {
            "target_box_index": self.target_box_index,
            "map_id": int(MapId.CINNABAR_POKECENTER),
            "player_x": 13,
            "player_y": 4,
        }

    def family_parameters(self) -> dict[str, object]:
        return {"target_box_index": self.target_box_index}


@dataclass(frozen=True, slots=True)
class RedResupplyTarget:
    """One bounded purchase from Red's already qualified Cinnabar clerk."""

    quantity: int

    def __post_init__(self) -> None:
        if type(self.quantity) is not int or not 1 <= self.quantity <= 99:  # noqa: E721
            raise RedLivingDexProviderCurriculumError(
                "resupply curriculum quantity is invalid"
            )

    def parameters(self) -> dict[str, object]:
        return {
            "map_id": int(MapId.CINNABAR_MART),
            "player_x": 2,
            "player_y": 5,
            "interaction_direction": "left",
            "purchases": [
                {
                    "absolute_index": 1,
                    "item_id": int(ItemId.GREAT_BALL),
                    "quantity": self.quantity,
                    "unit_price": 600,
                }
            ],
        }

    def family_parameters(self) -> dict[str, object]:
        return {
            "purchases": (
                {
                    "item_id": int(ItemId.GREAT_BALL),
                    "quantity": self.quantity,
                },
            )
        }


@dataclass(frozen=True, slots=True)
class RedStoryTarget:
    """One dependency-legal objective frontier supplied by the real quest graph."""

    objective_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.objective_id, str)
            or not self.objective_id
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for character in self.objective_id
            )
        ):
            raise RedLivingDexProviderCurriculumError(
                "story curriculum objective identity is invalid"
            )

    def parameters(self) -> dict[str, object]:
        return {}

    def family_parameters(self) -> dict[str, object]:
        return {"objective_id": self.objective_id}


def _evolution(source: int, target: int, level: int) -> RedLevelEvolutionTarget:
    return RedLevelEvolutionTarget(
        red_species_ref(source),
        red_species_ref(target),
        level,
    )


def _development(species: int) -> RedPartyDevelopmentTarget:
    return RedPartyDevelopmentTarget(red_species_ref(species))


# These five precursors are all retained in the authenticated Red capture bank,
# live in the current box, have absent evolved forms, and use automatic level
# evolution.  Two families with duplicate precursors and three with single
# precursors also exercise both multiplicity boundaries of the existing boxed
# engine.
_EVOLUTION_BY_FAMILY_SCOPE: Mapping[str, RedLevelEvolutionTarget] = MappingProxyType(
    {
        "train-family-scope-a": _evolution(11, 12, 10),
        "train-family-scope-b": _evolution(14, 15, 10),
        "train-family-scope-c": _evolution(16, 17, 18),
        "development-family-scope-1": _evolution(19, 20, 20),
        "development-family-scope-3": _evolution(41, 42, 22),
    }
)

# These are four distinct, uniquely retained members of the authenticated
# six-member party.  The target-specific trainer, rather than global weakest-
# member ordering, binds the selected specimen.
_DEVELOPMENT_BY_FAMILY_SCOPE: Mapping[str, RedPartyDevelopmentTarget] = MappingProxyType(
    {
        "train-family-scope-a": _development(83),
        "train-family-scope-c": _development(143),
        "development-family-scope-3": _development(135),
        "development-family-scope-4": _development(106),
    }
)


_ENCOUNTER_SOURCE_BY_KIND_AND_SCOPE: Mapping[
    tuple[LivingDexOptionKind, str],
    RedEncounterSourceTarget,
] = MappingProxyType(
    {
        (LivingDexOptionKind.ACQUIRE, "train-family-scope-a"): RedEncounterSourceTarget(
            "wild:Route24:grass"
        ),
        (LivingDexOptionKind.ACQUIRE, "train-family-scope-b"): RedEncounterSourceTarget(
            "wild:Route11:grass"
        ),
        (LivingDexOptionKind.ACQUIRE, "train-family-scope-c"): RedEncounterSourceTarget(
            "wild:Route22:grass"
        ),
        (LivingDexOptionKind.ACQUIRE, "development-family-scope-0"): (
            RedEncounterSourceTarget("wild:Route2:grass")
        ),
        (LivingDexOptionKind.ACQUIRE, "development-family-scope-2"): (
            RedEncounterSourceTarget("wild:Route16:grass")
        ),
        (LivingDexOptionKind.EXPLORE, "train-family-scope-a"): RedEncounterSourceTarget(
            "wild:Route24:grass"
        ),
        (LivingDexOptionKind.EXPLORE, "train-family-scope-b"): RedEncounterSourceTarget(
            "wild:Route11:grass"
        ),
        (LivingDexOptionKind.EXPLORE, "train-family-scope-c"): RedEncounterSourceTarget(
            "wild:Route22:grass"
        ),
        (LivingDexOptionKind.EXPLORE, "development-family-scope-2"): (
            RedEncounterSourceTarget("wild:Route8:grass")
        ),
        (LivingDexOptionKind.EXPLORE, "development-family-scope-4"): (
            RedEncounterSourceTarget("wild:Route21:grass")
        ),
    }
)

_STORAGE_BY_FAMILY_SCOPE: Mapping[str, RedStorageTarget] = MappingProxyType(
    {
        "train-family-scope-a": RedStorageTarget(1),
        "train-family-scope-c": RedStorageTarget(2),
        "development-family-scope-0": RedStorageTarget(3),
        "development-family-scope-1": RedStorageTarget(4),
        "development-family-scope-4": RedStorageTarget(5),
    }
)

_RESUPPLY_BY_FAMILY_SCOPE: Mapping[str, RedResupplyTarget] = MappingProxyType(
    {
        "train-family-scope-b": RedResupplyTarget(1),
        "train-family-scope-c": RedResupplyTarget(2),
        "development-family-scope-0": RedResupplyTarget(3),
        "development-family-scope-3": RedResupplyTarget(4),
    }
)

_STORY_BY_FAMILY_SCOPE: Mapping[str, RedStoryTarget] = MappingProxyType(
    {
        # The objective families are assigned to scopes, not to fixed roots.
        # This order lets the authentic root freezer pair every story offer
        # with the other two real options in its same-state menu.  The five
        # objectives are all available at roots whose other two
        # same-state options remain physically reachable.  Early Erika is
        # paired with nearby Route 16/8 corridors; late Strength is paired with
        # the Route 11/Cinnabar menu.  No objective is borrowed from another
        # captured endpoint.
        "train-family-scope-a": RedStoryTarget("defeat_giovanni"),
        "train-family-scope-b": RedStoryTarget("obtain_strength"),
        "train-family-scope-c": RedStoryTarget("defeat_blaine"),
        "development-family-scope-1": RedStoryTarget("cross_victory_road"),
        "development-family-scope-2": RedStoryTarget("defeat_erika"),
    }
)

RedProviderFamilyTarget = (
    RedLevelEvolutionTarget
    | RedPartyDevelopmentTarget
    | RedEncounterSourceTarget
    | RedStorageTarget
    | RedResupplyTarget
    | RedStoryTarget
)


@dataclass(frozen=True, slots=True)
class RedLivingDexProviderCurriculumAudit:
    """Aggregate, path-free proof that every repeated target scope is covered."""

    evolution_offer_count: int
    evolution_family_count: int
    development_offer_count: int
    development_family_count: int
    offer_count: int
    semantic_family_count: int
    identity_derived_family_count: int = 0

    def __post_init__(self) -> None:
        if (
            self.evolution_offer_count != 6
            or self.evolution_family_count != 5
            or self.development_offer_count != 6
            or self.development_family_count != 4
            or self.offer_count != 45
            or self.semantic_family_count != 33
            or self.identity_derived_family_count != 0
        ):
            raise RedLivingDexProviderCurriculumError(
                "targeted provider curriculum no longer covers the frozen schedule"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "development_family_count": self.development_family_count,
            "development_offer_count": self.development_offer_count,
            "evolution_family_count": self.evolution_family_count,
            "evolution_offer_count": self.evolution_offer_count,
            "identity_derived_family_count": self.identity_derived_family_count,
            "offer_count": self.offer_count,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "raw_controller_sequence_steps": 0,
            "semantic_family_count": self.semantic_family_count,
            "teacher_routes": 0,
        }


def red_living_dex_provider_family_target(
    slot: LivingDexProspectiveCaptureSlot,
    option_kind: LivingDexOptionKind,
) -> RedProviderFamilyTarget:
    """Resolve one mechanics-derived family target for every scheduled option."""

    if not isinstance(slot, LivingDexProspectiveCaptureSlot):
        raise TypeError("provider family target needs a prospective slot")
    slot.__post_init__()
    if not isinstance(option_kind, LivingDexOptionKind):
        raise TypeError("provider family target needs an option kind")
    if option_kind not in slot.available_option_kinds:
        raise RedLivingDexProviderCurriculumError(
            "provider family kind is absent from the prospective menu"
        )
    target: RedProviderFamilyTarget | None
    if option_kind is LivingDexOptionKind.EVOLVE:
        target = _EVOLUTION_BY_FAMILY_SCOPE.get(slot.family_scope_id)
    elif option_kind is LivingDexOptionKind.DEVELOP:
        target = _DEVELOPMENT_BY_FAMILY_SCOPE.get(slot.family_scope_id)
    elif option_kind in {LivingDexOptionKind.ACQUIRE, LivingDexOptionKind.EXPLORE}:
        target = _ENCOUNTER_SOURCE_BY_KIND_AND_SCOPE.get(
            (option_kind, slot.family_scope_id)
        )
    elif option_kind is LivingDexOptionKind.MANAGE_STORAGE:
        target = _STORAGE_BY_FAMILY_SCOPE.get(slot.family_scope_id)
    elif option_kind is LivingDexOptionKind.RESUPPLY:
        target = _RESUPPLY_BY_FAMILY_SCOPE.get(slot.family_scope_id)
    elif option_kind is LivingDexOptionKind.UNLOCK_ACCESS:
        target = _STORY_BY_FAMILY_SCOPE.get(slot.family_scope_id)
    else:
        target = None
    if target is None:
        raise RedLivingDexProviderCurriculumError(
            "prospective family scope lacks a genuine provider target"
        )
    return target


def red_living_dex_targeted_provider_parameters(
    slot: LivingDexProspectiveCaptureSlot,
    option_kind: LivingDexOptionKind,
) -> dict[str, object]:
    """Return mechanics parameters for one scheduled target-specific option."""

    if not isinstance(slot, LivingDexProspectiveCaptureSlot):
        raise TypeError("targeted provider parameters need a prospective slot")
    slot.__post_init__()
    if not isinstance(option_kind, LivingDexOptionKind):
        raise TypeError("targeted provider parameters need an option kind")
    if option_kind not in slot.available_option_kinds:
        raise RedLivingDexProviderCurriculumError(
            "targeted provider kind is absent from the prospective menu"
        )
    if option_kind not in {
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
    }:
        raise RedLivingDexProviderCurriculumError(
            "only evolution and development use target-specific parameters"
        )
    target = red_living_dex_provider_family_target(slot, option_kind)
    if not isinstance(target, (RedLevelEvolutionTarget, RedPartyDevelopmentTarget)):
        raise RedLivingDexProviderCurriculumError(
            "prospective family scope lacks a genuine target transformation"
        )
    return target.parameters()


def audit_red_living_dex_provider_curriculum() -> RedLivingDexProviderCurriculumAudit:
    """Prove exact scope coverage and distinct mechanics without opening a ROM."""

    slots = build_red_living_dex_prospective_capture_plan().slots
    evolution = tuple(
        (
            slot.family_scope_id,
            red_living_dex_targeted_provider_parameters(
                slot,
                LivingDexOptionKind.EVOLVE,
            ),
        )
        for slot in slots
        if LivingDexOptionKind.EVOLVE in slot.available_option_kinds
    )
    development = tuple(
        (
            slot.family_scope_id,
            red_living_dex_targeted_provider_parameters(
                slot,
                LivingDexOptionKind.DEVELOP,
            ),
        )
        for slot in slots
        if LivingDexOptionKind.DEVELOP in slot.available_option_kinds
    )
    _require_scope_function(evolution, "evolution")
    _require_scope_function(development, "development")
    all_targets = tuple(
        (
            slot.family_scope_id,
            option_kind,
            red_living_dex_provider_family_target(slot, option_kind),
        )
        for slot in slots
        for option_kind in slot.available_option_kinds
    )
    for option_kind in {
        row[1] for row in all_targets
    }:
        scoped = tuple(
            (scope, _family_key(kind, target))
            for scope, kind, target in all_targets
            if kind is option_kind
        )
        _require_scope_function(scoped, option_kind.value)
        families_by_scope: dict[str, object] = {}
        for scope, family in scoped:
            previous = families_by_scope.setdefault(scope, family)
            if previous != family:
                raise RedLivingDexProviderCurriculumError(
                    f"{option_kind.value} scope maps to multiple provider families"
                )
        if len(families_by_scope) != len(set(families_by_scope.values())):
            raise RedLivingDexProviderCurriculumError(
                f"{option_kind.value} family crosses disjoint logical scopes"
            )
    return RedLivingDexProviderCurriculumAudit(
        evolution_offer_count=len(evolution),
        evolution_family_count=len({tuple(sorted(row.items())) for _, row in evolution}),
        development_offer_count=len(development),
        development_family_count=len(
            {tuple(sorted(row.items())) for _, row in development}
        ),
        offer_count=len(all_targets),
        semantic_family_count=len(
            {_family_key(kind, target) for _, kind, target in all_targets}
        ),
    )


def _family_key(
    option_kind: LivingDexOptionKind,
    target: RedProviderFamilyTarget,
) -> tuple[object, ...]:
    if isinstance(target, (RedLevelEvolutionTarget, RedPartyDevelopmentTarget)):
        parameters = target.parameters()
    else:
        parameters = target.family_parameters()
    return (
        option_kind.value,
        tuple(
            (key, _freeze_family_value(value))
            for key, value in sorted(parameters.items())
        ),
    )


def _freeze_family_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            (key, _freeze_family_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_family_value(item) for item in value)
    return value


def _require_scope_function(
    rows: tuple[tuple[str, object], ...],
    subject: str,
) -> None:
    by_scope: dict[str, Hashable] = {}
    scope_by_family: dict[Hashable, str] = {}
    for scope, parameters in rows:
        family = _freeze_family_value(parameters)
        if not isinstance(family, Hashable):
            raise RedLivingDexProviderCurriculumError(
                f"{subject} family parameters are not immutable"
            )
        prior_family = by_scope.setdefault(scope, family)
        if prior_family != family:
            raise RedLivingDexProviderCurriculumError(
                f"{subject} scope maps to multiple transformations"
            )
        prior_scope = scope_by_family.setdefault(family, scope)
        if prior_scope != scope:
            raise RedLivingDexProviderCurriculumError(
                f"{subject} transformation overlaps independent family scopes"
            )


__all__ = [
    "RedEncounterSourceTarget",
    "RedLevelEvolutionTarget",
    "RedLivingDexProviderCurriculumAudit",
    "RedLivingDexProviderCurriculumError",
    "RedPartyDevelopmentTarget",
    "RedProviderFamilyTarget",
    "RedResupplyTarget",
    "RedStorageTarget",
    "RedStoryTarget",
    "audit_red_living_dex_provider_curriculum",
    "red_living_dex_provider_family_target",
    "red_living_dex_targeted_provider_parameters",
]
