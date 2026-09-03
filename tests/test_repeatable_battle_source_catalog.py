from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.repeatable_battle_source_catalog import (
    RepeatableBattleSourceCatalogError,
    parse_repeatable_battle_source_catalog,
)


def _payload(tmp_path: Path, **changes: object) -> bytes:
    coverage = {
        "scenarios": 1,
        "source_lineages": 1,
        "source_states": 1,
        "party_menus": 1,
        "semantic_setups": 1,
        "venues": 1,
        "battle_kinds": 1,
    }
    value: dict[str, object] = {
        "schema": "pokemon-private-repeatable-battle-source-catalog-v1",
        "seed": 1289,
        "training_scenarios": 2,
        "development_scenarios": 1,
        "wait_frame_offsets": [0, 37],
        "minimum_coverage": {"train": coverage, "development": coverage},
        "sources": [
            {
                "source_id": "train-a",
                "source_lineage_id": "lineage-a",
                "partition": "train",
                "state_path": str(tmp_path / "train.state"),
                "source_commit": "a" * 40,
            }
        ],
    }
    value.update(changes)
    return json.dumps(value).encode("ascii")


def test_source_catalog_accepts_a_strict_absolute_private_roster(tmp_path: Path) -> None:
    catalog = parse_repeatable_battle_source_catalog(_payload(tmp_path))

    assert catalog.seed == 1289
    assert catalog.source("train-a").state_path == tmp_path / "train.state"


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"seed": True}, "seed"),
        ({"training_scenarios": 0}, "training scenario"),
        ({"wait_frame_offsets": [37, 0]}, "timing offsets"),
    ),
)
def test_source_catalog_rejects_invalid_plan_dimensions(
    tmp_path: Path,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(RepeatableBattleSourceCatalogError, match=message):
        parse_repeatable_battle_source_catalog(_payload(tmp_path, **changes))


def test_source_catalog_rejects_a_relative_state_path(tmp_path: Path) -> None:
    value = json.loads(_payload(tmp_path))
    value["sources"][0]["state_path"] = "relative.state"

    with pytest.raises(RepeatableBattleSourceCatalogError, match="path"):
        parse_repeatable_battle_source_catalog(json.dumps(value).encode("ascii"))
