"""Measure what a training area actually fields, rather than recalling it.

The repository declares no wild encounter tables, and it should not: a table
copied from a guide is an assertion, and the whole point of this project is
that assertions about the game get checked against the game.  So bands are
harvested from encounters the agent really had.

The summary is deliberately not a bare minimum and maximum.  Diglett's Cave
fields Diglett from the mid teens and Dugtrio around thirty; reduced to
``15-31`` it looks unusable for a level-twenty trainee, when in truth all but
a few percent of its encounters suit that trainee exactly.  A band therefore
carries both the level most encounters stay under and the rare ceiling, so
venue selection can plan for the common case and let the escape path handle
the outlier — which is what the escape path is for.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.party import MAX_LEVEL, MIN_LEVEL
from pokemon_red_completion.team_training import GrindingArea

WILD_BATTLE_STATE = 1
TRAINER_BATTLE_STATE = 2

ENCOUNTER_LOG_VARIABLE = "POKEMON_RED_ENCOUNTER_LOG"

#: Below this many samples an area's band is a rumour, not a measurement. Nine
#: of the twenty-one areas in the first harvest sat at four samples or fewer,
#: and one of those reported a single level as its whole band.
MINIMUM_TRUSTED_SAMPLES = 20

#: The share of encounters a training plan is expected to handle directly; the
#: remainder is what fleeing exists for.
TYPICAL_ENCOUNTER_SHARE = 0.9


class EncounterLogError(RuntimeError):
    """Raised when a harvest log cannot be trusted to describe real encounters."""


def encounter_log_path() -> Path | None:
    """Where to append harvested encounters, or ``None`` when not harvesting.

    Recording is opt-in.  An earlier version wrote to a hard-coded path on
    every run whether or not anyone wanted the data, which is both a surprise
    and a slow way to reach a file nobody reads.
    """

    configured = os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip()
    return Path(configured) if configured else None


def is_wild_encounter(raw: object) -> bool:
    """Whether this observation is a real wild encounter worth recording.

    Trainer battles share the battle flag but not the level distribution, and
    counting them inflates an area's band with whatever the route's trainers
    happen to carry.  Battle memory also lags the flag by a few frames, so the
    first reads of any battle report species zero at level zero.
    """

    if getattr(raw, "battle_state", None) != WILD_BATTLE_STATE:
        return False
    species = getattr(raw, "enemy_species_id", None)
    level = getattr(raw, "enemy_level", None)
    if not isinstance(species, int) or species <= 0:
        return False
    return isinstance(level, int) and MIN_LEVEL <= level <= MAX_LEVEL


@dataclass(frozen=True, slots=True)
class EncounterBand:
    """What one area was measured to field, and how well it was measured."""

    map_id: int
    samples: int
    minimum_level: int
    typical_maximum_level: int
    observed_maximum_level: int
    species_ids: tuple[int, ...]
    #: Sorted labels for the conditions in force while these encounters were
    #: seen, empty where the title has none to report.
    #:
    #: Red has none: its encounter tables do not vary, so every row belongs to
    #: the same table and merging them is correct. From Gen 2 a route fields
    #: different species by time of day. Keying a band on the map alone would
    #: average two tables into a band describing neither, and would do it
    #: silently -- there is no error to notice, just a wrong number. Carrying
    #: the key now means a second adapter reports conditions and gets separate
    #: bands, instead of discovering the merge from a training run that will
    #: not converge.
    conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.samples <= 0:
            raise EncounterLogError("a band must rest on at least one sample")
        levels = (
            self.minimum_level,
            self.typical_maximum_level,
            self.observed_maximum_level,
        )
        if any(not MIN_LEVEL <= level <= MAX_LEVEL for level in levels):
            raise EncounterLogError(f"band for map {self.map_id:#04x} holds an invalid level")
        if not self.minimum_level <= self.typical_maximum_level <= self.observed_maximum_level:
            raise EncounterLogError(f"band for map {self.map_id:#04x} is not ordered")
        if not isinstance(self.conditions, tuple) or any(
            not isinstance(label, str) or not label.strip() for label in self.conditions
        ):
            raise EncounterLogError("band conditions must be a tuple of non-empty labels")
        if tuple(sorted(set(self.conditions))) != self.conditions:
            raise EncounterLogError("band conditions must be sorted and unique")

    @property
    def is_trusted(self) -> bool:
        """Whether enough encounters were seen for the band to mean anything."""

        return self.samples >= MINIMUM_TRUSTED_SAMPLES

    @property
    def has_rare_ceiling(self) -> bool:
        """Whether a few encounters run well above the rest.

        These are the ones that force a flee, and an area is not disqualified
        by having them.
        """

        return self.observed_maximum_level > self.typical_maximum_level

    def as_record(self) -> dict[str, object]:
        """A portable row, sample count included so it can be argued with."""

        return {
            "map_id": self.map_id,
            "samples": self.samples,
            "trusted": self.is_trusted,
            "minimum_level": self.minimum_level,
            "typical_maximum_level": self.typical_maximum_level,
            "observed_maximum_level": self.observed_maximum_level,
            "species_ids": list(self.species_ids),
            "conditions": list(self.conditions),
        }


def read_encounter_log(path: Path) -> Iterator[Mapping[str, object]]:
    """Yield the wild encounters in a harvest log, skipping anything else."""

    if not path.exists():
        raise EncounterLogError(
            f"no encounter log at {path}. Set {ENCOUNTER_LOG_VARIABLE} and take a run first."
        )
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise EncounterLogError(f"{path} line {number} is not valid JSON") from error
        if not isinstance(entry, dict):
            raise EncounterLogError(f"{path} line {number} is not an encounter record")
        yield entry


def summarize_encounters(entries: Iterable[Mapping[str, object]]) -> tuple[EncounterBand, ...]:
    """Reduce raw encounter rows to one band per area, ordered by map."""

    levels: dict[tuple[int, tuple[str, ...]], list[int]] = {}
    species: dict[tuple[int, tuple[str, ...]], Counter[int]] = {}
    for entry in entries:
        if not is_wild_encounter(_Row(entry)):
            continue
        map_id = entry["map_id"]
        level = entry["enemy_level"]
        species_id = entry["enemy_species"]
        if (
            not isinstance(map_id, int)
            or not isinstance(level, int)
            or not isinstance(species_id, int)
        ):
            continue
        raw_conditions = entry.get("conditions", ())
        conditions = (
            tuple(sorted(str(label) for label in raw_conditions))
            if isinstance(raw_conditions, (list, tuple))
            else ()
        )
        key = (map_id, conditions)
        levels.setdefault(key, []).append(level)
        species.setdefault(key, Counter())[species_id] += 1
    return tuple(
        _band(key, sorted(observed), species[key]) for key, observed in sorted(levels.items())
    )


def _band(
    key: tuple[int, tuple[str, ...]], levels: Sequence[int], species: Counter[int]
) -> EncounterBand:
    map_id, conditions = key
    return EncounterBand(
        map_id=map_id,
        conditions=conditions,
        samples=len(levels),
        minimum_level=levels[0],
        typical_maximum_level=_percentile(levels, TYPICAL_ENCOUNTER_SHARE),
        observed_maximum_level=levels[-1],
        species_ids=tuple(sorted(species)),
    )


def _percentile(sorted_levels: Sequence[int], share: float) -> int:
    """The level at or below which ``share`` of encounters fall.

    Nearest-rank, so the answer is always a level that was really observed.
    """

    rank = max(1, min(len(sorted_levels), round(share * len(sorted_levels))))
    return sorted_levels[rank - 1]


def load_measured_bands(path: Path) -> tuple[EncounterBand, ...]:
    """Read a dated evidence file back into bands."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EncounterLogError(f"no measured bands at {path}") from error
    except json.JSONDecodeError as error:
        raise EncounterLogError(f"{path} is not valid JSON") from error
    rows = document.get("bands") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise EncounterLogError(f"{path} does not hold a band list")
    return tuple(
        EncounterBand(
            map_id=int(row["map_id"]),
            samples=int(row["samples"]),
            minimum_level=int(row["minimum_level"]),
            typical_maximum_level=int(row["typical_maximum_level"]),
            observed_maximum_level=int(row["observed_maximum_level"]),
            species_ids=tuple(int(value) for value in row.get("species_ids", ())),
            conditions=tuple(sorted(str(label) for label in row.get("conditions", ()))),
        )
        for row in rows
    )


def grinding_areas(
    bands: Iterable[EncounterBand],
    area_names: Mapping[int, str],
    healer_map_ids: Iterable[int] = (),
) -> tuple[GrindingArea, ...]:
    """Convert trusted bands into venues the training policy can choose from.

    Untrusted bands are dropped rather than downgraded.  An area seen four
    times has no band worth planning against, and offering one anyway is how a
    guess acquires the authority of a measurement.
    """

    healers = frozenset(healer_map_ids)
    return tuple(
        GrindingArea(
            area_id=area_names.get(band.map_id, f"map_{band.map_id:#04x}"),
            minimum_encounter_level=band.minimum_level,
            maximum_encounter_level=band.typical_maximum_level,
            has_nearby_healer=band.map_id in healers,
            rare_maximum_encounter_level=band.observed_maximum_level,
            measured_samples=band.samples,
            conditions=band.conditions,
        )
        for band in bands
        if band.is_trusted
    )


class _Row:
    """Adapts a log record to the attribute shape ``is_wild_encounter`` reads."""

    __slots__ = ("battle_state", "enemy_species_id", "enemy_level")

    def __init__(self, entry: Mapping[str, object]) -> None:
        self.battle_state = entry.get("battle_state")
        self.enemy_species_id = entry.get("enemy_species")
        self.enemy_level = entry.get("enemy_level")
