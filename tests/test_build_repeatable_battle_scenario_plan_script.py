from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
    parse_repeatable_battle_scenario_plan,
)

SCRIPT = runpy.run_path("scripts/build_repeatable_battle_scenario_plan.py")
GLOBALS = SCRIPT["_run"].__globals__
BuildError = SCRIPT["RepeatableBattleScenarioPlanBuildError"]


def _catalog(paths: tuple[Path, ...]) -> dict[str, object]:
    sources = []
    for index, path in enumerate(paths):
        partition = "train" if index < 2 else "development"
        sources.append(
            {
                "source_id": f"source-{index}",
                "source_lineage_id": f"{partition}-lineage-{index}",
                "partition": partition,
                "state_path": str(path),
                "source_commit": "a" * 40,
            }
        )
    minimum = {
        "scenarios": 4,
        "source_lineages": 2,
        "source_states": 2,
        "party_menus": 2,
        "semantic_setups": 4,
        "venues": 2,
        "battle_kinds": 1,
    }
    return {
        "schema": "pokemon-private-repeatable-battle-source-catalog-v1",
        "seed": 1289,
        "training_scenarios": 6,
        "development_scenarios": 6,
        "wait_frame_offsets": [0, 37],
        "minimum_coverage": {"train": minimum, "development": minimum},
        "sources": sources,
    }


def _args(tmp_path: Path, catalog_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        source_catalog=catalog_path,
        private_plan=tmp_path / "private-plan.json",
        public_summary=tmp_path / "public-summary.json",
        rom=None,
    )


def test_builder_inventories_without_actions_and_emits_path_free_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = tuple(tmp_path / f"source-{index}.state" for index in range(4))
    for index, path in enumerate(paths):
        path.write_bytes(f"state-{index}".encode("ascii"))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog(paths)), encoding="utf-8")
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda value: Path("red.gb"))
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="f" * 64),
    )

    def inspect(state_bytes: bytes, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs["session_factory"]
        source_id = kwargs["source_id"]
        ordinal = int(source_id.rsplit("-", 1)[1])
        return RepeatableBattleSourceObservation(
            source_id=source_id,
            source_lineage_id=kwargs["source_lineage_id"],
            partition=kwargs["partition"],
            state_sha256=hashlib.sha256(state_bytes).hexdigest(),
            source_commit=kwargs["source_commit"],
            expected_map=22,
            source_kind=RepeatableBattleSourceKind.FIELD,
            active_party_index=None,
            reachable_venue_ids=("digletts_cave", "route_11"),
            party_options=(
                RepeatableBattlePartyOption(0, f"{ordinal + 1:x}" * 64, 3, 1.0),
                RepeatableBattlePartyOption(1, f"{ordinal + 5:x}" * 64, 2, 0.8),
            ),
        )

    monkeypatch.setitem(GLOBALS, "inspect_repeatable_red_battle_source", inspect)
    args = _args(tmp_path, catalog_path)

    summary = SCRIPT["_run"](args)

    plan = parse_repeatable_battle_scenario_plan(args.private_plan.read_bytes())
    assert len(plan.assignments) == 12
    assert summary["inventory_actions"] == 0
    assert summary["inventory_frames"] == 0
    assert summary["source_count"] == 4
    encoded = args.public_summary.read_text("ascii")
    assert str(tmp_path) not in encoded
    assert all(str(path) not in encoded for path in paths)


def test_builder_fails_closed_before_overwriting_frozen_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = tuple(tmp_path / f"source-{index}.state" for index in range(4))
    for index, path in enumerate(paths):
        path.write_bytes(f"state-{index}".encode("ascii"))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog(paths)), encoding="utf-8")
    args = _args(tmp_path, catalog_path)
    args.private_plan.write_text("already frozen", encoding="ascii")
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda value: Path("red.gb"))
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="f" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "inspect_repeatable_red_battle_source",
        lambda state_bytes, **kwargs: pytest.fail("inventory should not be needed"),
    )

    with pytest.raises(BuildError, match="already exists"):
        SCRIPT["_write_new"](args.private_plan, b"replacement", mode=0o600)
