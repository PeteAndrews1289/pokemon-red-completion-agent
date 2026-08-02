"""Source-pinned Pokémon Red acquisition graph and collection planner.

The collection policy knows *which* living species is missing, but it cannot
know whether Red should search grass, fish, accept a gift, perform an in-game
trade, or evolve a retained precursor.  This module supplies that game adapter
without exposing RAM addresses or controller inputs.

Canonical encounter locations and levels are derived from pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``.  The catalog deliberately
chooses one reproducible source for each directly obtainable target; later
route optimization may add alternatives without changing the completion
denominator.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .collection import CollectionObservation
from .red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_species_number,
    red_species_ref,
)

PRET_POKERED_ACQUISITION_COMMIT = "1e96034092686d006e863cace09e87273051a3d8"


class RedAcquisitionKind(StrEnum):
    """How one target enters the collection."""

    WILD = "wild"
    SAFARI = "safari"
    FISHING = "fishing"
    GIFT = "gift"
    STATIC = "static"
    PRIZE = "prize"
    FOSSIL = "fossil"
    IN_GAME_TRADE = "in_game_trade"
    EVOLUTION = "evolution"


class RedAcquisitionDirective(StrEnum):
    """Immediate semantic work selected by the Red acquisition planner."""

    SEEK_SOURCE = "seek_source"
    EVOLVE_SPECIES = "evolve_species"
    PERFORM_TRADE = "perform_trade"
    SOURCE_EXHAUSTED = "source_exhausted"
    COMPLETE = "complete"


class RedAreaDirective(StrEnum):
    """Immediate work inside one canonical encounter source."""

    SEEK_ENCOUNTER = "seek_encounter"
    CAPTURE_ENCOUNTER = "capture_encounter"
    FLEE_ENCOUNTER = "flee_encounter"
    SWITCH_BOX = "switch_box"
    MAKE_STORAGE_ROOM = "make_storage_room"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class RedAcquisitionMethod:
    """One canonical, auditable way to obtain a target species."""

    species_ref: str
    kind: RedAcquisitionKind
    source_id: str
    minimum_level: int | None = None
    maximum_level: int | None = None
    consumes_species_ref: str | None = None
    required_item_ref: str | None = None
    repeatable: bool = True

    def __post_init__(self) -> None:
        if self.species_ref not in RED_SOLO_COLLECTION_CONTRACT.target_species:
            raise ValueError("acquisition species must belong to the Red target contract")
        if not isinstance(self.kind, RedAcquisitionKind):
            raise TypeError("kind must be a RedAcquisitionKind")
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if (self.minimum_level is None) != (self.maximum_level is None):
            raise ValueError("minimum_level and maximum_level must be declared together")
        if self.minimum_level is not None and not (
            1 <= self.minimum_level <= self.maximum_level <= 100  # type: ignore[operator]
        ):
            raise ValueError("acquisition levels must be between 1 and 100")
        transforms = {
            RedAcquisitionKind.EVOLUTION,
            RedAcquisitionKind.IN_GAME_TRADE,
        }
        if (self.kind in transforms) != (self.consumes_species_ref is not None):
            raise ValueError("evolution and trade methods must consume one precursor")
        if (
            self.consumes_species_ref is not None
            and self.consumes_species_ref not in RED_SOLO_COLLECTION_CONTRACT.target_species
        ):
            raise ValueError("consumed precursor must belong to the Red target contract")
        if type(self.repeatable) is not bool:
            raise TypeError("repeatable must be a bool")

    @property
    def transforms_precursor(self) -> bool:
        return self.kind in {
            RedAcquisitionKind.EVOLUTION,
            RedAcquisitionKind.IN_GAME_TRADE,
        }


@dataclass(frozen=True, slots=True)
class RedAcquisitionCatalog:
    """Exactly one canonical acquisition method for every Red target."""

    methods: tuple[RedAcquisitionMethod, ...]
    source_commit: str = PRET_POKERED_ACQUISITION_COMMIT

    def __post_init__(self) -> None:
        if self.source_commit != PRET_POKERED_ACQUISITION_COMMIT:
            raise ValueError("acquisition catalog source commit is not the pinned revision")
        species = tuple(method.species_ref for method in self.methods)
        if len(species) != len(set(species)):
            raise ValueError("acquisition catalog must not duplicate target species")
        if set(species) != set(RED_SOLO_COLLECTION_CONTRACT.target_species):
            raise ValueError("acquisition catalog must cover all 124 Red targets exactly")
        by_species = {method.species_ref: method for method in self.methods}
        for method in self.methods:
            seen = {method.species_ref}
            current = method
            while current.transforms_precursor:
                precursor = current.consumes_species_ref
                if precursor is None or precursor not in by_species:
                    raise ValueError("transformation precursor lacks an acquisition method")
                if precursor in seen:
                    raise ValueError("acquisition graph must be acyclic")
                seen.add(precursor)
                current = by_species[precursor]

    def method_for(self, species_ref: str) -> RedAcquisitionMethod:
        try:
            return next(method for method in self.methods if method.species_ref == species_ref)
        except StopIteration as error:
            raise ValueError("species_ref is not present in the Red acquisition catalog") from error

    def methods_at_source(self, source_id: str) -> tuple[RedAcquisitionMethod, ...]:
        return tuple(method for method in self.methods if method.source_id == source_id)

    def required_root_acquisitions(self) -> dict[str, int]:
        """Minimum source specimens needed for the maximal living collection.

        Demand begins with every one of the 120 coexisting living targets.
        Evolution and in-game trade demand is propagated to the consumed
        precursor.  The result therefore includes necessary duplicates instead
        of the misleading one-of-each capture count.
        """

        pending = Counter(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
        roots: Counter[str] = Counter()
        while pending:
            species_ref, quantity = pending.popitem()
            method = self.method_for(species_ref)
            if method.transforms_precursor:
                assert method.consumes_species_ref is not None
                pending[method.consumes_species_ref] += quantity
            else:
                roots[species_ref] += quantity
        return dict(sorted(roots.items(), key=lambda item: red_species_number(item[0])))

    def reachable_registration_species(self) -> frozenset[str]:
        """Species registered while building the maximal living collection."""

        reachable = set(self.required_root_acquisitions())
        changed = True
        while changed:
            changed = False
            for method in self.methods:
                if (
                    method.transforms_precursor
                    and method.consumes_species_ref in reachable
                    and method.species_ref not in reachable
                ):
                    reachable.add(method.species_ref)
                    changed = True
        return frozenset(reachable)

    def required_transformation_counts(self) -> dict[str, int]:
        """Count every evolution/trade execution required by the living plan."""

        pending = Counter(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
        transformations: Counter[str] = Counter()
        while pending:
            species_ref, quantity = pending.popitem()
            method = self.method_for(species_ref)
            if method.transforms_precursor:
                transformations[species_ref] += quantity
                assert method.consumes_species_ref is not None
                pending[method.consumes_species_ref] += quantity
        return dict(sorted(transformations.items(), key=lambda item: red_species_number(item[0])))

    def required_item_quantities(self) -> dict[str, int]:
        """Evolution-item budget implied by the maximal living plan."""

        items: Counter[str] = Counter()
        for species_ref, quantity in self.required_transformation_counts().items():
            item_ref = self.method_for(species_ref).required_item_ref
            if item_ref is not None:
                items[item_ref] += quantity
        return dict(sorted(items.items()))


@dataclass(frozen=True, slots=True)
class RedAcquisitionDecision:
    directive: RedAcquisitionDirective
    goal_species_ref: str
    action_species_ref: str
    source_id: str
    consumes_species_ref: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class RedAreaRequirement:
    species_ref: str
    required_count: int
    retained_count: int

    @property
    def missing_count(self) -> int:
        return max(0, self.required_count - self.retained_count)


@dataclass(frozen=True, slots=True)
class RedAreaSurvey:
    source_id: str
    requirements: tuple[RedAreaRequirement, ...]

    @property
    def missing_species_refs(self) -> tuple[str, ...]:
        return tuple(item.species_ref for item in self.requirements if item.missing_count)

    @property
    def complete(self) -> bool:
        return not self.missing_species_refs


@dataclass(frozen=True, slots=True)
class RedSourcePriority:
    """One incomplete direct source ranked by remaining collection value."""

    source_id: str
    kind: RedAcquisitionKind
    missing_species_refs: tuple[str, ...]
    missing_specimen_count: int

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not isinstance(self.kind, RedAcquisitionKind):
            raise TypeError("kind must be a RedAcquisitionKind")
        if not self.missing_species_refs:
            raise ValueError("source priority must contain a missing species")
        if type(self.missing_specimen_count) is not int or self.missing_specimen_count <= 0:
            raise ValueError("missing_specimen_count must be a positive integer")


@dataclass(frozen=True, slots=True)
class RedAreaDecision:
    directive: RedAreaDirective
    source_id: str
    species_ref: str | None
    box_index: int | None
    reason: str


class RedAreaExecutionError(RuntimeError):
    """The semantic area executor violated a bounded acquisition contract."""


class RedAreaExecutor(Protocol):
    """Narrow game-adapter port used by the reusable source survey loop."""

    def read_collection(self) -> CollectionObservation: ...

    def encountered_species_ref(self) -> str | None: ...

    def seek_encounter(self) -> None: ...

    def capture_encounter(self, species_ref: str) -> None: ...

    def flee_encounter(self) -> None: ...

    def switch_box(self, box_index: int) -> None: ...


@dataclass(frozen=True, slots=True)
class RedAreaExecutionPolicy:
    max_actions: int = 2_000
    max_encounters: int = 400
    capture_in_requirement_order: bool = False

    def __post_init__(self) -> None:
        for name in ("max_actions", "max_encounters"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.capture_in_requirement_order) is not bool:
            raise TypeError("capture_in_requirement_order must be a bool")


@dataclass(frozen=True, slots=True)
class RedAreaExecutionReport:
    source_id: str
    initial_missing_species_refs: tuple[str, ...]
    final_missing_species_refs: tuple[str, ...]
    actions_executed: int
    encounters_seen: int
    captures: int
    flees: int
    box_switches: int

    @property
    def passed(self) -> bool:
        return not self.final_missing_species_refs


def plan_red_acquisition(
    goal_species_ref: str,
    observation: CollectionObservation,
    catalog: RedAcquisitionCatalog | None = None,
) -> RedAcquisitionDecision:
    """Choose the next source, evolution, or trade toward one living target."""

    catalog = catalog or RED_ACQUISITION_CATALOG
    if goal_species_ref not in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species:
        raise ValueError("goal species must be one of the 120 coexisting living targets")
    counts = Counter(specimen.species_ref for specimen in observation.specimens)
    if counts[goal_species_ref]:
        method = catalog.method_for(goal_species_ref)
        return RedAcquisitionDecision(
            RedAcquisitionDirective.COMPLETE,
            goal_species_ref,
            goal_species_ref,
            method.source_id,
            method.consumes_species_ref,
            "living target is already retained",
        )
    return _plan_one_more(goal_species_ref, goal_species_ref, counts, observation, catalog)


def summarize_red_area_survey(
    source_id: str,
    observation: CollectionObservation,
    catalog: RedAcquisitionCatalog | None = None,
) -> RedAreaSurvey:
    """Report canonical direct targets still missing from one encounter area."""

    catalog = catalog or RED_ACQUISITION_CATALOG
    methods = catalog.methods_at_source(source_id)
    if not methods:
        raise ValueError("source_id is not present in the Red acquisition catalog")
    living = Counter(specimen.species_ref for specimen in observation.specimens)
    root_counts = catalog.required_root_acquisitions()
    requirements = tuple(
        RedAreaRequirement(
            method.species_ref,
            root_counts[method.species_ref],
            living[method.species_ref],
        )
        for method in methods
        if not method.transforms_precursor and method.species_ref in root_counts
    )
    return RedAreaSurvey(source_id, requirements)


def rank_red_sources(
    observation: CollectionObservation,
    *,
    kinds: frozenset[RedAcquisitionKind] | None = None,
    catalog: RedAcquisitionCatalog | None = None,
) -> tuple[RedSourcePriority, ...]:
    """Rank incomplete direct sources by useful retained specimens.

    The ranking is intentionally route-agnostic.  A chapter planner may filter
    it by acquisition kind and then combine it with reachability and resource
    costs.  Counting downstream-required duplicate roots makes a source with,
    for example, two required Metapod specimens more valuable than a naive
    one-species-per-source count would report.
    """

    catalog = catalog or RED_ACQUISITION_CATALOG
    selected_kinds = frozenset(RedAcquisitionKind) if kinds is None else kinds
    if not selected_kinds:
        return ()
    if any(not isinstance(kind, RedAcquisitionKind) for kind in selected_kinds):
        raise TypeError("kinds must contain only RedAcquisitionKind values")

    source_kinds: dict[str, RedAcquisitionKind] = {}
    for method in catalog.methods:
        if method.transforms_precursor or method.kind not in selected_kinds:
            continue
        previous = source_kinds.setdefault(method.source_id, method.kind)
        if previous is not method.kind:
            raise ValueError("one direct source cannot mix acquisition kinds")

    priorities: list[RedSourcePriority] = []
    for source_id, kind in source_kinds.items():
        survey = summarize_red_area_survey(source_id, observation, catalog)
        missing = tuple(item for item in survey.requirements if item.missing_count)
        if not missing:
            continue
        priorities.append(
            RedSourcePriority(
                source_id=source_id,
                kind=kind,
                missing_species_refs=tuple(item.species_ref for item in missing),
                missing_specimen_count=sum(item.missing_count for item in missing),
            )
        )
    return tuple(
        sorted(
            priorities,
            key=lambda item: (
                -item.missing_specimen_count,
                -len(item.missing_species_refs),
                item.source_id,
            ),
        )
    )


def plan_red_area_encounter(
    source_id: str,
    observation: CollectionObservation,
    *,
    encountered_species_ref: str | None = None,
    required_species_ref: str | None = None,
    catalog: RedAcquisitionCatalog | None = None,
) -> RedAreaDecision:
    """Seek, catch, flee, rotate storage, or stop within one source survey."""

    catalog = catalog or RED_ACQUISITION_CATALOG
    survey = summarize_red_area_survey(source_id, observation, catalog)
    if survey.complete:
        return RedAreaDecision(
            RedAreaDirective.STOP,
            source_id,
            None,
            None,
            "every root specimen assigned to this source is retained",
        )
    if encountered_species_ref is not None:
        if (
            required_species_ref is not None
            and encountered_species_ref != required_species_ref
        ):
            return RedAreaDecision(
                RedAreaDirective.FLEE_ENCOUNTER,
                source_id,
                encountered_species_ref,
                None,
                f"capture order currently requires {required_species_ref}",
            )
        requirement = next(
            (item for item in survey.requirements if item.species_ref == encountered_species_ref),
            None,
        )
        if requirement is not None and requirement.missing_count:
            if (
                observation.party_size >= observation.party_limit
                and not observation.current_box_has_room
            ):
                return RedAreaDecision(
                    RedAreaDirective.FLEE_ENCOUNTER,
                    source_id,
                    encountered_species_ref,
                    None,
                    "required encounter cannot be retained until storage is rotated",
                )
            return RedAreaDecision(
                RedAreaDirective.CAPTURE_ENCOUNTER,
                source_id,
                encountered_species_ref,
                observation.current_box_index,
                f"retain {requirement.missing_count} more specimen(s) required downstream",
            )
        return RedAreaDecision(
            RedAreaDirective.FLEE_ENCOUNTER,
            source_id,
            encountered_species_ref,
            None,
            "encounter does not advance this source's remaining requirements",
        )
    if observation.party_size >= observation.party_limit and not observation.current_box_has_room:
        next_box = observation.next_box_with_room
        if next_box is None:
            return RedAreaDecision(
                RedAreaDirective.MAKE_STORAGE_ROOM,
                source_id,
                survey.missing_species_refs[0],
                None,
                "party and all twelve boxes are full before the area survey completed",
            )
        return RedAreaDecision(
            RedAreaDirective.SWITCH_BOX,
            source_id,
            survey.missing_species_refs[0],
            next_box,
            "active box is full before seeking the next required encounter",
        )
    return RedAreaDecision(
        RedAreaDirective.SEEK_ENCOUNTER,
        source_id,
        survey.missing_species_refs[0],
        observation.current_box_index,
        "walk the canonical encounter terrain until a required species appears",
    )


def run_red_area_survey(
    source_id: str,
    executor: RedAreaExecutor,
    *,
    policy: RedAreaExecutionPolicy | None = None,
    catalog: RedAcquisitionCatalog | None = None,
) -> RedAreaExecutionReport:
    """Execute one bounded source survey through a semantic game adapter."""

    catalog = catalog or RED_ACQUISITION_CATALOG
    policy = policy or RedAreaExecutionPolicy()
    initial = summarize_red_area_survey(source_id, executor.read_collection(), catalog)
    encounters_seen = 0
    captures = 0
    flees = 0
    box_switches = 0

    for action_count in range(policy.max_actions + 1):
        observation = executor.read_collection()
        encountered = executor.encountered_species_ref()
        survey = summarize_red_area_survey(source_id, observation, catalog)
        required_species_ref = (
            survey.missing_species_refs[0]
            if policy.capture_in_requirement_order and survey.missing_species_refs
            else None
        )
        decision = plan_red_area_encounter(
            source_id,
            observation,
            encountered_species_ref=encountered,
            required_species_ref=required_species_ref,
            catalog=catalog,
        )
        if decision.directive is RedAreaDirective.STOP:
            final = summarize_red_area_survey(source_id, observation, catalog)
            return RedAreaExecutionReport(
                source_id,
                initial.missing_species_refs,
                final.missing_species_refs,
                action_count,
                encounters_seen,
                captures,
                flees,
                box_switches,
            )
        if action_count >= policy.max_actions:
            break
        if decision.directive is RedAreaDirective.SEEK_ENCOUNTER:
            executor.seek_encounter()
            if executor.encountered_species_ref() is not None:
                encounters_seen += 1
                if encounters_seen > policy.max_encounters:
                    raise RedAreaExecutionError(
                        f"{source_id} exceeded {policy.max_encounters} encountered Pokémon"
                    )
            continue
        if decision.directive is RedAreaDirective.CAPTURE_ENCOUNTER:
            species_ref = decision.species_ref
            if species_ref is None:
                raise RedAreaExecutionError("capture directive omitted its species")
            before = Counter(item.species_ref for item in observation.specimens)[species_ref]
            executor.capture_encounter(species_ref)
            after_observation = executor.read_collection()
            after = Counter(item.species_ref for item in after_observation.specimens)[species_ref]
            if after != before + 1 or executor.encountered_species_ref() is not None:
                raise RedAreaExecutionError(
                    f"{source_id} capture did not retain exactly one {species_ref}"
                )
            captures += 1
            continue
        if decision.directive is RedAreaDirective.FLEE_ENCOUNTER:
            executor.flee_encounter()
            if executor.encountered_species_ref() is not None:
                raise RedAreaExecutionError(f"{source_id} flee did not end the encounter")
            flees += 1
            continue
        if decision.directive is RedAreaDirective.SWITCH_BOX:
            if decision.box_index is None:
                raise RedAreaExecutionError("switch-box directive omitted its destination")
            before_species = Counter(item.species_ref for item in observation.specimens)
            executor.switch_box(decision.box_index)
            after_observation = executor.read_collection()
            after_species = Counter(item.species_ref for item in after_observation.specimens)
            if (
                after_observation.current_box_index != decision.box_index
                or before_species != after_species
            ):
                raise RedAreaExecutionError(
                    f"{source_id} box switch changed the retained collection"
                )
            box_switches += 1
            continue
        if decision.directive is RedAreaDirective.MAKE_STORAGE_ROOM:
            raise RedAreaExecutionError(
                f"{source_id} cannot continue because all verified storage is full"
            )
        raise RedAreaExecutionError(f"unsupported area directive {decision.directive}")

    raise RedAreaExecutionError(f"{source_id} exceeded {policy.max_actions} semantic actions")


def _plan_one_more(
    action_species_ref: str,
    goal_species_ref: str,
    counts: Counter[str],
    observation: CollectionObservation,
    catalog: RedAcquisitionCatalog,
) -> RedAcquisitionDecision:
    method = catalog.method_for(action_species_ref)
    if not method.transforms_precursor:
        if not method.repeatable and action_species_ref in observation.owned_species:
            return RedAcquisitionDecision(
                RedAcquisitionDirective.SOURCE_EXHAUSTED,
                goal_species_ref,
                action_species_ref,
                method.source_id,
                None,
                "non-repeatable source was already consumed and no living specimen remains",
            )
        return RedAcquisitionDecision(
            RedAcquisitionDirective.SEEK_SOURCE,
            goal_species_ref,
            action_species_ref,
            method.source_id,
            None,
            "obtain one more prerequisite specimen from its canonical source",
        )

    precursor = method.consumes_species_ref
    assert precursor is not None
    reserve = int(precursor in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
    if counts[precursor] <= reserve:
        return _plan_one_more(precursor, goal_species_ref, counts, observation, catalog)
    directive = (
        RedAcquisitionDirective.PERFORM_TRADE
        if method.kind is RedAcquisitionKind.IN_GAME_TRADE
        else RedAcquisitionDirective.EVOLVE_SPECIES
    )
    return RedAcquisitionDecision(
        directive,
        goal_species_ref,
        action_species_ref,
        method.source_id,
        precursor,
        "a retained surplus precursor is ready for transformation",
    )


def _method(
    number: int,
    kind: RedAcquisitionKind,
    source_id: str,
    minimum_level: int | None = None,
    maximum_level: int | None = None,
    *,
    consumes: int | None = None,
    item: str | None = None,
    repeatable: bool = True,
) -> RedAcquisitionMethod:
    return RedAcquisitionMethod(
        species_ref=red_species_ref(number),
        kind=kind,
        source_id=source_id,
        minimum_level=minimum_level,
        maximum_level=maximum_level,
        consumes_species_ref=None if consumes is None else red_species_ref(consumes),
        required_item_ref=item,
        repeatable=repeatable,
    )


_WILD_SOURCES = (
    (10, "wild:ViridianForest:grass", 3, 3),
    (11, "wild:ViridianForest:grass", 4, 4),
    (13, "wild:Route2:grass", 3, 5),
    (14, "wild:ViridianForest:grass", 4, 6),
    (16, "wild:Route1:grass", 2, 5),
    (17, "wild:Route14:grass", 28, 30),
    (19, "wild:Route1:grass", 2, 4),
    (20, "wild:Route16:grass", 23, 25),
    (21, "wild:Route22:grass", 3, 5),
    (22, "wild:Route18:grass", 25, 29),
    (23, "wild:Route4:grass", 6, 12),
    (24, "wild:Route23:grass", 41, 41),
    (25, "wild:ViridianForest:grass", 3, 5),
    (26, "wild:CeruleanCave1F:grass", 53, 53),
    (29, "wild:Route22:grass", 3, 4),
    (30, "wild:SafariZoneNorth:grass", 30, 30),
    (32, "wild:Route22:grass", 2, 4),
    (33, "wild:SafariZoneNorth:grass", 30, 30),
    (35, "wild:MtMoon1F:grass", 8, 8),
    (39, "wild:Route3:grass", 3, 7),
    (40, "wild:CeruleanCave2F:grass", 54, 54),
    (41, "wild:MtMoon1F:grass", 6, 11),
    (42, "wild:SeafoamIslands1F:grass", 29, 29),
    (43, "wild:Route24:grass", 12, 14),
    (44, "wild:Route12:grass", 28, 30),
    (46, "wild:MtMoon1F:grass", 8, 8),
    (47, "wild:SafariZoneEast:grass", 25, 25),
    (48, "wild:SafariZoneCenter:grass", 22, 22),
    (49, "wild:SafariZoneWest:grass", 31, 31),
    (50, "wild:DiglettsCave:grass", 15, 22),
    (51, "wild:DiglettsCave:grass", 29, 31),
    (54, "wild:SeafoamIslands1F:grass", 28, 28),
    (55, "wild:SeafoamIslands1F:grass", 38, 38),
    (56, "wild:Route5:grass", 10, 16),
    (58, "wild:Route8:grass", 15, 18),
    (63, "wild:Route24:grass", 8, 12),
    (64, "wild:CeruleanCave1F:grass", 49, 49),
    (66, "wild:RockTunnel1F:grass", 15, 17),
    (67, "wild:VictoryRoad2F:grass", 41, 41),
    (72, "wild:Route21:water", 5, 40),
    (74, "wild:MtMoonB1F:grass", 7, 9),
    (75, "wild:VictoryRoad1F:grass", 41, 41),
    (77, "wild:PokemonMansion1F:grass", 28, 34),
    (79, "wild:SeafoamIslandsB1F:grass", 28, 30),
    (80, "wild:SeafoamIslandsB2F:grass", 37, 37),
    (81, "wild:PowerPlant:grass", 21, 23),
    (82, "wild:PowerPlant:grass", 32, 35),
    (84, "wild:Route16:grass", 18, 22),
    (85, "wild:CeruleanCave1F:grass", 49, 49),
    (86, "wild:SeafoamIslandsB1F:grass", 28, 30),
    (87, "wild:SeafoamIslandsB3F:grass", 37, 37),
    (88, "wild:PokemonMansion1F:grass", 30, 30),
    (89, "wild:PokemonMansion2F:grass", 37, 37),
    (90, "wild:SeafoamIslands1F:grass", 28, 30),
    (92, "wild:PokemonTower3F:grass", 18, 24),
    (93, "wild:PokemonTower3F:grass", 25, 25),
    (95, "wild:RockTunnel1F:grass", 13, 15),
    (96, "wild:Route11:grass", 9, 15),
    (97, "wild:CeruleanCave1F:grass", 46, 46),
    (100, "wild:Route10:grass", 14, 17),
    (101, "wild:CeruleanCave2F:grass", 52, 52),
    (102, "wild:SafariZoneEast:grass", 23, 25),
    (104, "wild:PokemonTower3F:grass", 20, 22),
    (105, "wild:VictoryRoad2F:grass", 40, 40),
    (109, "wild:PokemonMansion2F:grass", 30, 34),
    (110, "wild:PokemonMansion1F:grass", 37, 37),
    (111, "wild:SafariZoneCenter:grass", 25, 25),
    (112, "wild:CeruleanCave2F:grass", 52, 52),
    (113, "wild:SafariZoneCenter:grass", 23, 23),
    (114, "wild:Route21:grass", 28, 32),
    (115, "wild:SafariZoneEast:grass", 25, 25),
    (116, "wild:SeafoamIslands1F:grass", 28, 30),
    (117, "wild:SeafoamIslandsB1F:grass", 37, 37),
    (120, "wild:SeafoamIslandsB1F:grass", 30, 30),
    (123, "wild:SafariZoneCenter:grass", 23, 23),
    (125, "wild:PowerPlant:grass", 33, 36),
    (128, "wild:SafariZoneWest:grass", 26, 26),
    (132, "wild:Route14:grass", 23, 23),
)

_FISHING_SOURCES = (
    (60, "fishing:good_rod:any_fishable_map", 10, 10),
    (61, "fishing:super_rod:CeladonCity", 23, 23),
    (98, "fishing:super_rod:Route4", 15, 15),
    (99, "fishing:super_rod:Route23", 23, 23),
    (118, "fishing:good_rod:any_fishable_map", 10, 10),
    (119, "fishing:super_rod:FuchsiaCity", 23, 23),
    (129, "fishing:super_rod:Route12", 5, 5),
)

_SPECIAL_METHODS = (
    _method(7, RedAcquisitionKind.GIFT, "gift:OakLab:Squirtle", 5, 5, repeatable=False),
    _method(
        83,
        RedAcquisitionKind.IN_GAME_TRADE,
        "trade:VermilionTradeHouse:SpearowForFarfetchd",
        consumes=21,
        repeatable=False,
    ),
    _method(106, RedAcquisitionKind.GIFT, "gift:FightingDojo:Hitmonlee", 30, 30, repeatable=False),
    _method(
        108,
        RedAcquisitionKind.IN_GAME_TRADE,
        "trade:Route18Gate2F:SlowbroForLickitung",
        consumes=80,
        repeatable=False,
    ),
    _method(
        122,
        RedAcquisitionKind.IN_GAME_TRADE,
        "trade:Route2TradeHouse:AbraForMrMime",
        consumes=63,
        repeatable=False,
    ),
    _method(
        124,
        RedAcquisitionKind.IN_GAME_TRADE,
        "trade:CeruleanTradeHouse:PoliwhirlForJynx",
        consumes=61,
        repeatable=False,
    ),
    _method(131, RedAcquisitionKind.GIFT, "gift:Silph7F:Lapras", 15, 15, repeatable=False),
    _method(133, RedAcquisitionKind.GIFT, "gift:CeladonMansion:Eevee", 25, 25, repeatable=False),
    _method(137, RedAcquisitionKind.PRIZE, "prize:GameCorner:Porygon", 26, 26),
    _method(138, RedAcquisitionKind.FOSSIL, "fossil:CinnabarLab:Helix", 30, 30, repeatable=False),
    _method(
        142, RedAcquisitionKind.FOSSIL, "fossil:CinnabarLab:OldAmber", 30, 30, repeatable=False
    ),
    _method(143, RedAcquisitionKind.STATIC, "static:Route12:Snorlax", 30, 30, repeatable=False),
    _method(144, RedAcquisitionKind.STATIC, "static:SeafoamB4F:Articuno", 50, 50, repeatable=False),
    _method(145, RedAcquisitionKind.STATIC, "static:PowerPlant:Zapdos", 50, 50, repeatable=False),
    _method(
        146, RedAcquisitionKind.STATIC, "static:VictoryRoad2F:Moltres", 50, 50, repeatable=False
    ),
    _method(147, RedAcquisitionKind.PRIZE, "prize:GameCorner:Dratini", 18, 18),
    _method(
        150, RedAcquisitionKind.STATIC, "static:CeruleanCaveB1F:Mewtwo", 70, 70, repeatable=False
    ),
)

_EVOLUTION_METHODS = (
    _method(8, RedAcquisitionKind.EVOLUTION, "evolution:level:16", 16, 100, consumes=7),
    _method(9, RedAcquisitionKind.EVOLUTION, "evolution:level:36", 36, 100, consumes=8),
    _method(12, RedAcquisitionKind.EVOLUTION, "evolution:level:10", 10, 100, consumes=11),
    _method(15, RedAcquisitionKind.EVOLUTION, "evolution:level:10", 10, 100, consumes=14),
    _method(18, RedAcquisitionKind.EVOLUTION, "evolution:level:36", 36, 100, consumes=17),
    _method(
        31,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:MoonStone",
        1,
        100,
        consumes=30,
        item="pokemon:red:item:moon_stone",
    ),
    _method(
        34,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:MoonStone",
        1,
        100,
        consumes=33,
        item="pokemon:red:item:moon_stone",
    ),
    _method(
        36,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:MoonStone",
        1,
        100,
        consumes=35,
        item="pokemon:red:item:moon_stone",
    ),
    _method(
        45,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:LeafStone",
        1,
        100,
        consumes=44,
        item="pokemon:red:item:leaf_stone",
    ),
    _method(57, RedAcquisitionKind.EVOLUTION, "evolution:level:28", 28, 100, consumes=56),
    _method(
        59,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:FireStone",
        1,
        100,
        consumes=58,
        item="pokemon:red:item:fire_stone",
    ),
    _method(
        62,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:WaterStone",
        1,
        100,
        consumes=61,
        item="pokemon:red:item:water_stone",
    ),
    _method(73, RedAcquisitionKind.EVOLUTION, "evolution:level:30", 30, 100, consumes=72),
    _method(78, RedAcquisitionKind.EVOLUTION, "evolution:level:40", 40, 100, consumes=77),
    _method(
        91,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:WaterStone",
        1,
        100,
        consumes=90,
        item="pokemon:red:item:water_stone",
    ),
    _method(
        103,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:LeafStone",
        1,
        100,
        consumes=102,
        item="pokemon:red:item:leaf_stone",
    ),
    _method(
        121,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:WaterStone",
        1,
        100,
        consumes=120,
        item="pokemon:red:item:water_stone",
    ),
    _method(130, RedAcquisitionKind.EVOLUTION, "evolution:level:20", 20, 100, consumes=129),
    _method(
        135,
        RedAcquisitionKind.EVOLUTION,
        "evolution:item:ThunderStone",
        1,
        100,
        consumes=133,
        item="pokemon:red:item:thunder_stone",
    ),
    _method(139, RedAcquisitionKind.EVOLUTION, "evolution:level:40", 40, 100, consumes=138),
    _method(148, RedAcquisitionKind.EVOLUTION, "evolution:level:30", 30, 100, consumes=147),
    _method(149, RedAcquisitionKind.EVOLUTION, "evolution:level:55", 55, 100, consumes=148),
)

RED_ACQUISITION_CATALOG = RedAcquisitionCatalog(
    methods=tuple(
        sorted(
            (
                *(
                    _method(
                        number,
                        (
                            RedAcquisitionKind.SAFARI
                            if "SafariZone" in source
                            else RedAcquisitionKind.WILD
                        ),
                        source,
                        low,
                        high,
                    )
                    for number, source, low, high in _WILD_SOURCES
                ),
                *(
                    _method(number, RedAcquisitionKind.FISHING, source, low, high)
                    for number, source, low, high in _FISHING_SOURCES
                ),
                *_SPECIAL_METHODS,
                *_EVOLUTION_METHODS,
            ),
            key=lambda method: red_species_number(method.species_ref),
        )
    )
)

if RED_ACQUISITION_CATALOG.reachable_registration_species() != frozenset(
    RED_SOLO_COLLECTION_CONTRACT.target_species
):
    raise AssertionError("maximal living plan must incidentally register all 124 Red targets")
