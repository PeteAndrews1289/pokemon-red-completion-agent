"""Prospective, title-neutral plans for repeatable battle scenario generation.

The plan separates cheap scenario multiplicity from evaluation independence.  Many
natural battle states may be generated from one restored game, but every child
retains that source's lineage and partition.  Timing variants therefore increase
training density without manufacturing independent development evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

REPEATABLE_BATTLE_SCENARIO_PLAN_SCHEMA = (
    "pokemon.core.battle.repeatable-scenario-plan.v1"
)
REPEATABLE_BATTLE_SCENARIO_COVERAGE_SCHEMA = (
    "pokemon.core.battle.repeatable-scenario-coverage.v1"
)
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ALLOWED_VENUES = frozenset(
    {"route_11", "digletts_cave", "pokemon_mansion_1f"}
)
_DEFAULT_WAIT_FRAMES = (0, 37, 83, 149, 223)
_MAXIMUM_SCENARIOS = 10_000
_MAXIMUM_PLAN_BYTES = 16 * 1024 * 1024


class RepeatableBattleScenarioFactoryError(ValueError):
    """Raised when scenario supply cannot preserve the experiment boundary."""


class RepeatableBattleSourceKind(StrEnum):
    """The authentic controller boundary exposed by one source state."""

    FIELD = "field"
    TRAINER_BATTLE = "trainer_battle"


class RepeatableBattleScenarioKind(StrEnum):
    """The resulting title-neutral battle family."""

    WILD = "wild"
    TRAINER = "trainer"


@dataclass(frozen=True, slots=True)
class RepeatableBattlePartyOption:
    """One living party member whose damaging menu is useful to the move ranker."""

    party_index: int
    menu_semantic_sha256: str
    supported_move_count: int
    hp_ratio: float

    def __post_init__(self) -> None:
        if type(self.party_index) is not int or not 0 <= self.party_index < 6:  # noqa: E721
            raise RepeatableBattleScenarioFactoryError("party index is invalid")
        _require_sha256(self.menu_semantic_sha256, "party menu")
        if (
            type(self.supported_move_count) is not int  # noqa: E721
            or not 2 <= self.supported_move_count <= 4
        ):
            raise RepeatableBattleScenarioFactoryError(
                "party option needs two through four supported moves"
            )
        if (
            isinstance(self.hp_ratio, bool)
            or not isinstance(self.hp_ratio, (int, float))
            or not math.isfinite(float(self.hp_ratio))
            or not 0.0 < float(self.hp_ratio) <= 1.0
        ):
            raise RepeatableBattleScenarioFactoryError("party HP ratio is invalid")

    def private_dict(self) -> dict[str, object]:
        return {
            "party_index": self.party_index,
            "menu_semantic_sha256": self.menu_semantic_sha256,
            "supported_move_count": self.supported_move_count,
            "hp_ratio": float(self.hp_ratio),
        }


@dataclass(frozen=True, slots=True)
class RepeatableBattleSourceObservation:
    """Action-free authentication of one private source state."""

    source_id: str
    source_lineage_id: str
    partition: ScenarioPartition
    state_sha256: str
    source_commit: str
    expected_map: int
    source_kind: RepeatableBattleSourceKind
    active_party_index: int | None
    reachable_venue_ids: tuple[str, ...]
    party_options: tuple[RepeatableBattlePartyOption, ...]

    def __post_init__(self) -> None:
        _require_safe_id(self.source_id, "source")
        _require_safe_id(self.source_lineage_id, "source lineage")
        if self.partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise RepeatableBattleScenarioFactoryError(
                "source partition must be train or development"
            )
        _require_sha256(self.state_sha256, "source state")
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise RepeatableBattleScenarioFactoryError("source commit is invalid")
        if type(self.expected_map) is not int or not 0 <= self.expected_map <= 0xFF:  # noqa: E721
            raise RepeatableBattleScenarioFactoryError("source map is invalid")
        if not isinstance(self.source_kind, RepeatableBattleSourceKind):
            raise RepeatableBattleScenarioFactoryError("source kind is invalid")
        if self.active_party_index is not None and (
            type(self.active_party_index) is not int  # noqa: E721
            or not 0 <= self.active_party_index < 6
        ):
            raise RepeatableBattleScenarioFactoryError(
                "active party index is invalid"
            )
        if not self.party_options:
            raise RepeatableBattleScenarioFactoryError(
                "source has no useful living party options"
            )
        indices = tuple(item.party_index for item in self.party_options)
        if len(indices) != len(set(indices)) or indices != tuple(sorted(indices)):
            raise RepeatableBattleScenarioFactoryError(
                "party options must be unique and ordered"
            )
        if any(not isinstance(item, RepeatableBattlePartyOption) for item in self.party_options):
            raise RepeatableBattleScenarioFactoryError("party option is invalid")
        venues = self.reachable_venue_ids
        if len(venues) != len(set(venues)) or venues != tuple(sorted(venues)):
            raise RepeatableBattleScenarioFactoryError(
                "reachable venues must be unique and ordered"
            )
        if any(venue not in _ALLOWED_VENUES for venue in venues):
            raise RepeatableBattleScenarioFactoryError("reachable venue is unsupported")
        if self.source_kind is RepeatableBattleSourceKind.FIELD:
            if self.active_party_index is not None or not venues:
                raise RepeatableBattleScenarioFactoryError(
                    "field source boundary is inconsistent"
                )
        elif venues or self.active_party_index is None:
            raise RepeatableBattleScenarioFactoryError(
                "trainer source boundary is inconsistent"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_lineage_id": self.source_lineage_id,
            "partition": self.partition.value,
            "state_sha256": self.state_sha256,
            "source_commit": self.source_commit,
            "expected_map": self.expected_map,
            "source_kind": self.source_kind.value,
            "active_party_index": self.active_party_index,
            "reachable_venue_ids": list(self.reachable_venue_ids),
            "party_options": [item.private_dict() for item in self.party_options],
        }


@dataclass(frozen=True, slots=True)
class RepeatableBattleScenarioAssignment:
    """One frozen natural scenario request, retaining its true source lineage."""

    scenario_id: str
    source_id: str
    source_lineage_id: str
    partition: ScenarioPartition
    source_state_sha256: str
    source_commit: str
    scenario_kind: RepeatableBattleScenarioKind
    party_index: int
    menu_semantic_sha256: str
    venue_id: str | None
    pre_encounter_wait_frames: int

    def __post_init__(self) -> None:
        for value, subject in (
            (self.scenario_id, "scenario"),
            (self.source_id, "source"),
            (self.source_lineage_id, "source lineage"),
        ):
            _require_safe_id(value, subject)
        if self.partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise RepeatableBattleScenarioFactoryError(
                "scenario partition must be train or development"
            )
        _require_sha256(self.source_state_sha256, "source state")
        _require_sha256(self.menu_semantic_sha256, "party menu")
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise RepeatableBattleScenarioFactoryError("source commit is invalid")
        if not isinstance(self.scenario_kind, RepeatableBattleScenarioKind):
            raise RepeatableBattleScenarioFactoryError("scenario kind is invalid")
        if type(self.party_index) is not int or not 0 <= self.party_index < 6:  # noqa: E721
            raise RepeatableBattleScenarioFactoryError("party index is invalid")
        if (
            type(self.pre_encounter_wait_frames) is not int  # noqa: E721
            or not 0 <= self.pre_encounter_wait_frames <= 4096
        ):
            raise RepeatableBattleScenarioFactoryError(
                "pre-encounter wait is invalid"
            )
        if self.scenario_kind is RepeatableBattleScenarioKind.WILD:
            if self.venue_id not in _ALLOWED_VENUES:
                raise RepeatableBattleScenarioFactoryError(
                    "wild scenario needs a supported venue"
                )
        elif self.venue_id is not None:
            raise RepeatableBattleScenarioFactoryError(
                "trainer scenario cannot name a wild venue"
            )

    @property
    def semantic_setup_sha256(self) -> str:
        """Hash the intervention while retaining the true parent state identity."""

        return canonical_sha256(
            {
                "schema": "pokemon.core.battle.repeatable-semantic-setup.v1",
                "source_state_sha256": self.source_state_sha256,
                "scenario_kind": self.scenario_kind.value,
                "party_menu_sha256": self.menu_semantic_sha256,
                "venue_id": self.venue_id,
                "pre_encounter_wait_frames": self.pre_encounter_wait_frames,
            }
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "source_id": self.source_id,
            "source_lineage_id": self.source_lineage_id,
            "partition": self.partition.value,
            "source_state_sha256": self.source_state_sha256,
            "source_commit": self.source_commit,
            "scenario_kind": self.scenario_kind.value,
            "party_index": self.party_index,
            "menu_semantic_sha256": self.menu_semantic_sha256,
            "venue_id": self.venue_id,
            "pre_encounter_wait_frames": self.pre_encounter_wait_frames,
            "semantic_setup_sha256": self.semantic_setup_sha256,
        }


@dataclass(frozen=True, slots=True)
class RepeatableBattleScenarioCoverage:
    scenarios: int
    source_lineages: int
    source_states: int
    party_menus: int
    semantic_setups: int
    venues: int
    battle_kinds: int

    def __post_init__(self) -> None:
        values = (
            self.scenarios,
            self.source_lineages,
            self.source_states,
            self.party_menus,
            self.semantic_setups,
            self.venues,
            self.battle_kinds,
        )
        if any(type(value) is not int or value < 0 for value in values):  # noqa: E721
            raise RepeatableBattleScenarioFactoryError("coverage value is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": REPEATABLE_BATTLE_SCENARIO_COVERAGE_SCHEMA,
            "scenarios": self.scenarios,
            "source_lineages": self.source_lineages,
            "source_states": self.source_states,
            "party_menus": self.party_menus,
            "semantic_setups": self.semantic_setups,
            "venues": self.venues,
            "battle_kinds": self.battle_kinds,
        }


@dataclass(frozen=True, slots=True)
class RepeatableBattleScenarioPlan:
    """A complete private plan whose public summary contains only aggregate facts."""

    seed: int
    assignments: tuple[RepeatableBattleScenarioAssignment, ...]

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:  # noqa: E721
            raise RepeatableBattleScenarioFactoryError("plan seed is invalid")
        if not self.assignments or len(self.assignments) > _MAXIMUM_SCENARIOS:
            raise RepeatableBattleScenarioFactoryError("scenario count is invalid")
        if any(
            not isinstance(item, RepeatableBattleScenarioAssignment)
            for item in self.assignments
        ):
            raise RepeatableBattleScenarioFactoryError("scenario assignment is invalid")
        identifiers = tuple(item.scenario_id for item in self.assignments)
        setups = tuple(item.semantic_setup_sha256 for item in self.assignments)
        if len(identifiers) != len(set(identifiers)):
            raise RepeatableBattleScenarioFactoryError("scenario identities repeat")
        if len(setups) != len(set(setups)):
            raise RepeatableBattleScenarioFactoryError("semantic scenario setups repeat")
        for subject, values in (
            (
                "source lineage",
                _partition_sets(self.assignments, lambda item: item.source_lineage_id),
            ),
            (
                "source state",
                _partition_sets(self.assignments, lambda item: item.source_state_sha256),
            ),
            (
                "scenario identity",
                _partition_sets(self.assignments, lambda item: item.scenario_id),
            ),
        ):
            if values[0] & values[1]:
                raise RepeatableBattleScenarioFactoryError(
                    f"{subject} crosses train and development"
                )
        if any(
            not any(item.partition is partition for item in self.assignments)
            for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)
        ):
            raise RepeatableBattleScenarioFactoryError(
                "plan needs train and development scenarios"
            )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def partition_assignments(
        self, partition: ScenarioPartition
    ) -> tuple[RepeatableBattleScenarioAssignment, ...]:
        if partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise RepeatableBattleScenarioFactoryError("partition is unsupported")
        return tuple(item for item in self.assignments if item.partition is partition)

    def coverage(self, partition: ScenarioPartition) -> RepeatableBattleScenarioCoverage:
        rows = self.partition_assignments(partition)
        return RepeatableBattleScenarioCoverage(
            scenarios=len(rows),
            source_lineages=len({item.source_lineage_id for item in rows}),
            source_states=len({item.source_state_sha256 for item in rows}),
            party_menus=len({item.menu_semantic_sha256 for item in rows}),
            semantic_setups=len({item.semantic_setup_sha256 for item in rows}),
            venues=len({item.venue_id for item in rows if item.venue_id is not None}),
            battle_kinds=len({item.scenario_kind for item in rows}),
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": REPEATABLE_BATTLE_SCENARIO_PLAN_SCHEMA,
            "seed": self.seed,
            "assignments": [item.private_dict() for item in self.assignments],
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.battle.repeatable-scenario-plan-summary.v1",
            "plan_sha256": self.sha256,
            "seed": self.seed,
            "train": self.coverage(ScenarioPartition.TRAIN).public_dict(),
            "development": self.coverage(
                ScenarioPartition.DEVELOPMENT
            ).public_dict(),
            "source_paths": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes": 0,
            "model_fits": 0,
            "authority_promoted": False,
        }


def build_repeatable_battle_scenario_plan(
    sources: tuple[RepeatableBattleSourceObservation, ...],
    *,
    seed: int,
    training_scenarios: int,
    development_scenarios: int,
    wait_frame_offsets: tuple[int, ...] = _DEFAULT_WAIT_FRAMES,
) -> RepeatableBattleScenarioPlan:
    """Build a deterministic, coverage-seeking plan without executing a game."""

    if not sources or any(
        not isinstance(item, RepeatableBattleSourceObservation) for item in sources
    ):
        raise RepeatableBattleScenarioFactoryError("scenario sources are invalid")
    if type(seed) is not int or seed < 0:  # noqa: E721
        raise RepeatableBattleScenarioFactoryError("plan seed is invalid")
    for value, subject in (
        (training_scenarios, "training"),
        (development_scenarios, "development"),
    ):
        if type(value) is not int or not 1 <= value <= _MAXIMUM_SCENARIOS:  # noqa: E721
            raise RepeatableBattleScenarioFactoryError(
                f"{subject} scenario count is invalid"
            )
    _validate_wait_offsets(wait_frame_offsets)
    source_ids = tuple(item.source_id for item in sources)
    if len(source_ids) != len(set(source_ids)):
        raise RepeatableBattleScenarioFactoryError("source identities repeat")
    state_partition = _source_partition_sets(
        sources, lambda item: item.state_sha256
    )
    lineage_partition = _source_partition_sets(
        sources, lambda item: item.source_lineage_id
    )
    if state_partition[0] & state_partition[1]:
        raise RepeatableBattleScenarioFactoryError(
            "source state crosses train and development"
        )
    if lineage_partition[0] & lineage_partition[1]:
        raise RepeatableBattleScenarioFactoryError(
            "source lineage crosses train and development"
        )

    selected: list[RepeatableBattleScenarioAssignment] = []
    for partition, count in (
        (ScenarioPartition.TRAIN, training_scenarios),
        (ScenarioPartition.DEVELOPMENT, development_scenarios),
    ):
        candidates = _candidate_assignments(
            tuple(item for item in sources if item.partition is partition),
            seed=seed,
            wait_frame_offsets=wait_frame_offsets,
        )
        selected.extend(_select_balanced(candidates, count=count, seed=seed))
    return RepeatableBattleScenarioPlan(seed=seed, assignments=tuple(selected))


def parse_repeatable_battle_scenario_plan(
    payload: bytes,
) -> RepeatableBattleScenarioPlan:
    """Strictly parse a canonical private plan produced before execution."""

    if not isinstance(payload, bytes):
        raise TypeError("repeatable battle scenario plan must be bytes")
    if not 1 <= len(payload) <= _MAXIMUM_PLAN_BYTES:
        raise RepeatableBattleScenarioFactoryError("scenario plan size is invalid")
    try:
        value = json.loads(payload.decode("ascii"))
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "seed",
            "assignments",
        }:
            raise RepeatableBattleScenarioFactoryError(
                "scenario plan fields are invalid"
            )
        if value["schema"] != REPEATABLE_BATTLE_SCENARIO_PLAN_SCHEMA:
            raise RepeatableBattleScenarioFactoryError(
                "scenario plan schema is invalid"
            )
        rows = value["assignments"]
        if not isinstance(rows, list):
            raise RepeatableBattleScenarioFactoryError(
                "scenario assignments are invalid"
            )
        assignments = tuple(_parse_assignment(row) for row in rows)
        plan = RepeatableBattleScenarioPlan(seed=value["seed"], assignments=assignments)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, RepeatableBattleScenarioFactoryError):
            raise
        raise RepeatableBattleScenarioFactoryError("scenario plan is invalid") from error
    if payload != _canonical_payload(plan.private_dict()):
        raise RepeatableBattleScenarioFactoryError("scenario plan is not canonical")
    return plan


def require_repeatable_battle_scenario_coverage(
    plan: RepeatableBattleScenarioPlan,
    *,
    train_minimum: RepeatableBattleScenarioCoverage,
    development_minimum: RepeatableBattleScenarioCoverage,
) -> None:
    """Fail closed unless both partitions meet every prospective minimum."""

    if not isinstance(plan, RepeatableBattleScenarioPlan):
        raise TypeError("plan must be a RepeatableBattleScenarioPlan")
    for partition, minimum in (
        (ScenarioPartition.TRAIN, train_minimum),
        (ScenarioPartition.DEVELOPMENT, development_minimum),
    ):
        if not isinstance(minimum, RepeatableBattleScenarioCoverage):
            raise TypeError("coverage minimum is invalid")
        actual = plan.coverage(partition)
        shortfalls = tuple(
            name
            for name in (
                "scenarios",
                "source_lineages",
                "source_states",
                "party_menus",
                "semantic_setups",
                "venues",
                "battle_kinds",
            )
            if getattr(actual, name) < getattr(minimum, name)
        )
        if shortfalls:
            raise RepeatableBattleScenarioFactoryError(
                f"{partition.value} scenario coverage is insufficient: "
                + ", ".join(shortfalls)
            )


def _candidate_assignments(
    sources: tuple[RepeatableBattleSourceObservation, ...],
    *,
    seed: int,
    wait_frame_offsets: tuple[int, ...],
) -> tuple[RepeatableBattleScenarioAssignment, ...]:
    candidates: list[RepeatableBattleScenarioAssignment] = []
    for source in sources:
        combinations: Iterable[
            tuple[
                RepeatableBattleScenarioKind,
                RepeatableBattlePartyOption,
                str | None,
                int,
            ]
        ]
        if source.source_kind is RepeatableBattleSourceKind.FIELD:
            combinations = (
                (RepeatableBattleScenarioKind.WILD, option, venue, wait)
                for option in source.party_options
                for venue in source.reachable_venue_ids
                for wait in wait_frame_offsets
            )
        else:
            combinations = (
                (RepeatableBattleScenarioKind.TRAINER, option, None, wait)
                for option in source.party_options
                for wait in (
                    (0,)
                    if option.party_index == source.active_party_index
                    else wait_frame_offsets
                )
            )
        for kind, option, venue, wait in combinations:
            identity = canonical_sha256(
                {
                    "schema": "pokemon.core.battle.repeatable-assignment-id.v1",
                    "seed": seed,
                    "source_state_sha256": source.state_sha256,
                    "source_lineage_id": source.source_lineage_id,
                    "scenario_kind": kind.value,
                    "party_index": option.party_index,
                    "menu_semantic_sha256": option.menu_semantic_sha256,
                    "venue_id": venue,
                    "pre_encounter_wait_frames": wait,
                }
            )
            candidates.append(
                RepeatableBattleScenarioAssignment(
                    scenario_id=f"repeatable-battle-{source.partition.value}-{identity[:20]}",
                    source_id=source.source_id,
                    source_lineage_id=source.source_lineage_id,
                    partition=source.partition,
                    source_state_sha256=source.state_sha256,
                    source_commit=source.source_commit,
                    scenario_kind=kind,
                    party_index=option.party_index,
                    menu_semantic_sha256=option.menu_semantic_sha256,
                    venue_id=venue,
                    pre_encounter_wait_frames=wait,
                )
            )
    return tuple(candidates)


def _select_balanced(
    candidates: tuple[RepeatableBattleScenarioAssignment, ...],
    *,
    count: int,
    seed: int,
) -> tuple[RepeatableBattleScenarioAssignment, ...]:
    if len(candidates) < count:
        raise RepeatableBattleScenarioFactoryError(
            "scenario source capacity is smaller than the requested partition"
        )
    remaining = list(candidates)
    selected: list[RepeatableBattleScenarioAssignment] = []
    lineage_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    menu_counts: Counter[str] = Counter()
    venue_counts: Counter[str | None] = Counter()
    kind_counts: Counter[RepeatableBattleScenarioKind] = Counter()
    while len(selected) < count:
        def rank(item: RepeatableBattleScenarioAssignment) -> tuple[int, str]:
            novelty = (
                64 * int(lineage_counts[item.source_lineage_id] == 0)
                + 32 * int(state_counts[item.source_state_sha256] == 0)
                + 24 * int(menu_counts[item.menu_semantic_sha256] == 0)
                + 16 * int(kind_counts[item.scenario_kind] == 0)
                + 8 * int(venue_counts[item.venue_id] == 0)
                - 8 * lineage_counts[item.source_lineage_id]
                - 4 * state_counts[item.source_state_sha256]
                - 2 * menu_counts[item.menu_semantic_sha256]
                - kind_counts[item.scenario_kind]
                - venue_counts[item.venue_id]
            )
            tie = hashlib.sha256(f"{seed}:{item.scenario_id}".encode("ascii")).hexdigest()
            return novelty, tie

        chosen = max(remaining, key=rank)
        remaining.remove(chosen)
        selected.append(chosen)
        lineage_counts[chosen.source_lineage_id] += 1
        state_counts[chosen.source_state_sha256] += 1
        menu_counts[chosen.menu_semantic_sha256] += 1
        venue_counts[chosen.venue_id] += 1
        kind_counts[chosen.scenario_kind] += 1
    return tuple(selected)


def _parse_assignment(value: object) -> RepeatableBattleScenarioAssignment:
    fields = {
        "scenario_id",
        "source_id",
        "source_lineage_id",
        "partition",
        "source_state_sha256",
        "source_commit",
        "scenario_kind",
        "party_index",
        "menu_semantic_sha256",
        "venue_id",
        "pre_encounter_wait_frames",
        "semantic_setup_sha256",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise RepeatableBattleScenarioFactoryError(
            "scenario assignment fields are invalid"
        )
    assignment = RepeatableBattleScenarioAssignment(
        scenario_id=value["scenario_id"],
        source_id=value["source_id"],
        source_lineage_id=value["source_lineage_id"],
        partition=ScenarioPartition(value["partition"]),
        source_state_sha256=value["source_state_sha256"],
        source_commit=value["source_commit"],
        scenario_kind=RepeatableBattleScenarioKind(value["scenario_kind"]),
        party_index=value["party_index"],
        menu_semantic_sha256=value["menu_semantic_sha256"],
        venue_id=value["venue_id"],
        pre_encounter_wait_frames=value["pre_encounter_wait_frames"],
    )
    if value["semantic_setup_sha256"] != assignment.semantic_setup_sha256:
        raise RepeatableBattleScenarioFactoryError(
            "scenario semantic setup digest differs"
        )
    return assignment


def _canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _partition_sets(
    assignments: tuple[RepeatableBattleScenarioAssignment, ...],
    value: Callable[[RepeatableBattleScenarioAssignment], object],
) -> tuple[set[object], set[object]]:
    return (
        {
            value(item)
            for item in assignments
            if item.partition is ScenarioPartition.TRAIN
        },
        {
            value(item)
            for item in assignments
            if item.partition is ScenarioPartition.DEVELOPMENT
        },
    )


def _source_partition_sets(
    sources: tuple[RepeatableBattleSourceObservation, ...],
    value: Callable[[RepeatableBattleSourceObservation], object],
) -> tuple[set[object], set[object]]:
    return (
        {
            value(item)
            for item in sources
            if item.partition is ScenarioPartition.TRAIN
        },
        {
            value(item)
            for item in sources
            if item.partition is ScenarioPartition.DEVELOPMENT
        },
    )


def _validate_wait_offsets(values: tuple[int, ...]) -> None:
    if (
        not isinstance(values, tuple)
        or not values
        or len(values) != len(set(values))
        or values != tuple(sorted(values))
        or any(type(value) is not int or not 0 <= value <= 4096 for value in values)  # noqa: E721
    ):
        raise RepeatableBattleScenarioFactoryError(
            "wait-frame offsets must be unique ordered bounded integers"
        )


def _require_safe_id(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RepeatableBattleScenarioFactoryError(f"{subject} identity is invalid")


def _require_sha256(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RepeatableBattleScenarioFactoryError(f"{subject} digest is invalid")


__all__ = [
    "REPEATABLE_BATTLE_SCENARIO_COVERAGE_SCHEMA",
    "REPEATABLE_BATTLE_SCENARIO_PLAN_SCHEMA",
    "RepeatableBattlePartyOption",
    "RepeatableBattleScenarioAssignment",
    "RepeatableBattleScenarioCoverage",
    "RepeatableBattleScenarioFactoryError",
    "RepeatableBattleScenarioKind",
    "RepeatableBattleScenarioPlan",
    "RepeatableBattleSourceKind",
    "RepeatableBattleSourceObservation",
    "build_repeatable_battle_scenario_plan",
    "parse_repeatable_battle_scenario_plan",
    "require_repeatable_battle_scenario_coverage",
]
