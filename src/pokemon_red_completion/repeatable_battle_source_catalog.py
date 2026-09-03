"""Strict private source catalog for repeatable battle scenario planning."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattleScenarioCoverage,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

REPEATABLE_BATTLE_SOURCE_CATALOG_SCHEMA = (
    "pokemon-private-repeatable-battle-source-catalog-v1"
)
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_CATALOG_BYTES = 4 * 1024 * 1024
_MAXIMUM_SCENARIOS = 10_000


class RepeatableBattleSourceCatalogError(ValueError):
    """Raised when a private source catalog is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class RepeatableBattleSourceSpec:
    source_id: str
    source_lineage_id: str
    partition: ScenarioPartition
    state_path: Path
    source_commit: str


@dataclass(frozen=True, slots=True)
class RepeatableBattleSourceCatalog:
    seed: int
    training_scenarios: int
    development_scenarios: int
    wait_frame_offsets: tuple[int, ...]
    train_minimum: RepeatableBattleScenarioCoverage
    development_minimum: RepeatableBattleScenarioCoverage
    sources: tuple[RepeatableBattleSourceSpec, ...]

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:  # noqa: E721
            raise RepeatableBattleSourceCatalogError("source catalog seed is invalid")
        for value, subject in (
            (self.training_scenarios, "training"),
            (self.development_scenarios, "development"),
        ):
            if type(value) is not int or not 1 <= value <= _MAXIMUM_SCENARIOS:  # noqa: E721
                raise RepeatableBattleSourceCatalogError(
                    f"source catalog {subject} scenario count is invalid"
                )
        if (
            not self.wait_frame_offsets
            or len(self.wait_frame_offsets) != len(set(self.wait_frame_offsets))
            or self.wait_frame_offsets != tuple(sorted(self.wait_frame_offsets))
            or any(
                type(value) is not int or not 0 <= value <= 4096  # noqa: E721
                for value in self.wait_frame_offsets
            )
        ):
            raise RepeatableBattleSourceCatalogError(
                "source catalog timing offsets are invalid"
            )
        if not self.sources or len(self.sources) > _MAXIMUM_SCENARIOS:
            raise RepeatableBattleSourceCatalogError("source catalog roster is invalid")
        lineage_partitions: dict[str, ScenarioPartition] = {}
        for source in self.sources:
            prior = lineage_partitions.setdefault(
                source.source_lineage_id, source.partition
            )
            if prior is not source.partition:
                raise RepeatableBattleSourceCatalogError(
                    "source lineage crosses train and development"
                )

    def source(self, source_id: str) -> RepeatableBattleSourceSpec:
        matches = tuple(item for item in self.sources if item.source_id == source_id)
        if len(matches) != 1:
            raise RepeatableBattleSourceCatalogError(
                "source identity is absent or ambiguous"
            )
        return matches[0]


def parse_repeatable_battle_source_catalog(
    payload: bytes,
) -> RepeatableBattleSourceCatalog:
    """Parse the private path-bearing catalog without opening any source state."""

    if not isinstance(payload, bytes):
        raise TypeError("repeatable battle source catalog must be bytes")
    if not 1 <= len(payload) <= _MAXIMUM_CATALOG_BYTES:
        raise RepeatableBattleSourceCatalogError("source catalog size is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "seed",
            "training_scenarios",
            "development_scenarios",
            "wait_frame_offsets",
            "minimum_coverage",
            "sources",
        }:
            raise RepeatableBattleSourceCatalogError(
                "source catalog fields are invalid"
            )
        if value["schema"] != REPEATABLE_BATTLE_SOURCE_CATALOG_SCHEMA:
            raise RepeatableBattleSourceCatalogError(
                "source catalog schema is invalid"
            )
        minimum = value["minimum_coverage"]
        if not isinstance(minimum, dict) or set(minimum) != {"train", "development"}:
            raise RepeatableBattleSourceCatalogError(
                "source catalog coverage requirements are invalid"
            )
        rows = value["sources"]
        if not isinstance(rows, list) or not rows:
            raise RepeatableBattleSourceCatalogError(
                "source catalog has no source rows"
            )
        sources = tuple(_parse_source(row) for row in rows)
        source_ids = tuple(item.source_id for item in sources)
        if len(source_ids) != len(set(source_ids)):
            raise RepeatableBattleSourceCatalogError(
                "source catalog identities repeat"
            )
        offsets = value["wait_frame_offsets"]
        if not isinstance(offsets, list):
            raise RepeatableBattleSourceCatalogError(
                "source catalog timing offsets are invalid"
            )
        return RepeatableBattleSourceCatalog(
            seed=value["seed"],
            training_scenarios=value["training_scenarios"],
            development_scenarios=value["development_scenarios"],
            wait_frame_offsets=tuple(offsets),
            train_minimum=_parse_coverage(minimum["train"]),
            development_minimum=_parse_coverage(minimum["development"]),
            sources=sources,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, RepeatableBattleSourceCatalogError):
            raise
        raise RepeatableBattleSourceCatalogError("source catalog is invalid") from error


def _parse_source(value: object) -> RepeatableBattleSourceSpec:
    if not isinstance(value, dict) or set(value) != {
        "source_id",
        "source_lineage_id",
        "partition",
        "state_path",
        "source_commit",
    }:
        raise RepeatableBattleSourceCatalogError("source row fields are invalid")
    for name in ("source_id", "source_lineage_id"):
        item = value[name]
        if not isinstance(item, str) or _SAFE_ID.fullmatch(item) is None:
            raise RepeatableBattleSourceCatalogError(f"source row {name} is invalid")
    commit = value["source_commit"]
    if not isinstance(commit, str) or _GIT_COMMIT.fullmatch(commit) is None:
        raise RepeatableBattleSourceCatalogError("source row commit is invalid")
    path = value["state_path"]
    if (
        not isinstance(path, str)
        or not path
        or "\x00" in path
        or not Path(path).is_absolute()
    ):
        raise RepeatableBattleSourceCatalogError("source row path is invalid")
    try:
        partition = ScenarioPartition(value["partition"])
    except ValueError:
        raise RepeatableBattleSourceCatalogError(
            "source row partition is invalid"
        ) from None
    if partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise RepeatableBattleSourceCatalogError(
            "source row partition must be train or development"
        )
    return RepeatableBattleSourceSpec(
        source_id=value["source_id"],
        source_lineage_id=value["source_lineage_id"],
        partition=partition,
        state_path=Path(path),
        source_commit=commit,
    )


def _parse_coverage(value: object) -> RepeatableBattleScenarioCoverage:
    fields = {
        "scenarios",
        "source_lineages",
        "source_states",
        "party_menus",
        "semantic_setups",
        "venues",
        "battle_kinds",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise RepeatableBattleSourceCatalogError(
            "coverage requirement fields are invalid"
        )
    return RepeatableBattleScenarioCoverage(**value)


__all__ = [
    "REPEATABLE_BATTLE_SOURCE_CATALOG_SCHEMA",
    "RepeatableBattleSourceCatalog",
    "RepeatableBattleSourceCatalogError",
    "RepeatableBattleSourceSpec",
    "parse_repeatable_battle_source_catalog",
]
