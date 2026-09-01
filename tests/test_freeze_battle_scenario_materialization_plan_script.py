from __future__ import annotations

import runpy
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioMaterializationPlan,
)
from pokemon_red_completion.blaine import (
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.observation import RawGameState

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "freeze_battle_scenario_materialization_plan.py")
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=1,
        player_x=0,
        player_y=0,
        party_count=4,
        battle_state=0,
        party_species_ids=(1, 2, 3, 4),
        party_levels=(20, 22, 20, 20),
        party_hp=(40, 40, 0, 40),
        party_max_hp=(50, 50, 50, 50),
        party_status=(0, 0, 0, 0),
        party_moves=(
            (1, 2, 0, 0),
            (1, 2, 3, 0),
            (1, 2, 3, 4),
            (1, 0, 0, 0),
        ),
        party_pp=(
            (10, 10, 0, 0),
            (10, 10, 10, 0),
            (10, 10, 10, 10),
            (10, 0, 0, 0),
        ),
    )


def test_freezer_accepts_only_whole_bank_inputs_not_selected_roots() -> None:
    options = SCRIPT["_parser"]()._option_string_actions

    assert "--state-bank" in options
    assert "--capture-directory" in options
    assert "--source-state" not in options
    assert "--source-slot-id" not in options
    assert "--party-slot" not in options
    assert "--venue" not in options


def test_route_11_party_slots_require_two_moves_and_full_band_level_safety() -> None:
    slots = SCRIPT["_eligible_party_slots"](
        _raw(),
        venue=ROUTE_11_TRAINING_VENUE,
    )

    assert [(item.party_slot, item.level, item.usable_move_count) for item in slots] == [
        (1, 20, 2)
    ]


def test_mansion_party_slots_use_the_same_full_band_level_contract() -> None:
    raw = _raw()
    raw = replace(raw, party_levels=(30, 44, 30, 30))

    slots = SCRIPT["_eligible_party_slots"](
        raw,
        venue=MANSION_TRAINING_VENUE,
    )

    assert [(item.party_slot, item.level) for item in slots] == [(1, 30)]


def test_party_slots_require_two_model_supported_attacks_not_merely_pp() -> None:
    raw = replace(
        _raw(),
        party_levels=(20, 20, 20, 20),
        party_moves=((1, 39, 45, 0), (1, 2, 39, 0), (1, 2, 3, 4), (1, 0, 0, 0)),
        party_pp=((10, 10, 10, 0), (10, 10, 10, 0), (10, 10, 10, 10), (10, 0, 0, 0)),
    )

    slots = SCRIPT["_eligible_party_slots"](
        raw,
        venue=ROUTE_11_TRAINING_VENUE,
    )

    assert [(item.party_slot, item.usable_move_count) for item in slots] == [(2, 2)]


def test_party_observation_rejects_incomplete_parallel_arrays() -> None:
    raw = _raw()
    raw = replace(
        raw,
        party_pp=raw.party_pp[:-1] if raw.party_pp is not None else None,
    )

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeError"],
        match="party observation",
    ):
        SCRIPT["_eligible_party_slots"](
            raw,
            venue=ROUTE_11_TRAINING_VENUE,
        )


def test_capture_directory_must_be_private_owned_and_not_rom_adjacent(
    tmp_path: Path,
) -> None:
    project_root = SCRIPT["PROJECT_ROOT"]
    rom_directory = tmp_path / "roms"
    rom_directory.mkdir(mode=0o700)
    rom_path = rom_directory / "Pokemon Red.gb"
    rom_path.write_bytes(b"rom")

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeError"],
        match="cannot be authenticated",
    ):
        SCRIPT["_private_capture_directory"](
            rom_directory,
            rom_path=rom_path,
        )
    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeError"],
        match="cannot be authenticated",
    ):
        SCRIPT["_private_capture_directory"](
            project_root,
            rom_path=rom_path,
        )


def test_plan_output_must_be_new_and_inside_the_bound_capture_directory(
    tmp_path: Path,
) -> None:
    capture_directory = tmp_path / "captures"
    capture_directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    accepted = SCRIPT["_private_new_plan"](
        capture_directory / "plan.json",
        capture_directory=capture_directory.resolve(),
    )
    assert accepted == (capture_directory / "plan.json").resolve()

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeError"],
        match="output is unavailable",
    ):
        SCRIPT["_private_new_plan"](
            outside / "plan.json",
            capture_directory=capture_directory.resolve(),
        )


def test_exclusive_plan_write_is_owner_only_and_rejects_replacement(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "plan.json"
    payload = b"private-plan\n"

    SCRIPT["_write_exclusive"](destination, payload)

    assert destination.read_bytes() == payload
    assert destination.stat().st_mode & 0o077 == 0
    with pytest.raises(SCRIPT["BattleScenarioMaterializationFreezeError"]):
        SCRIPT["_write_exclusive"](destination, payload)


def test_freeze_rejects_any_preexisting_planned_capture_output(tmp_path: Path) -> None:
    capture_directory = tmp_path.resolve()
    plan_destination = capture_directory / "plan.json"
    plan = cast(
        BattleScenarioMaterializationPlan,
        SimpleNamespace(
            assignments=(
                SimpleNamespace(
                    state_filename="capture-01.state",
                    manifest_filename="capture-01.state.json",
                ),
            )
        ),
    )

    SCRIPT["_require_new_assignment_outputs"](
        plan,
        capture_directory=capture_directory,
        plan_destination=plan_destination,
    )
    (capture_directory / "capture-01.state").write_bytes(b"already here")

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeError"],
        match="not new and private",
    ):
        SCRIPT["_require_new_assignment_outputs"](
            plan,
            capture_directory=capture_directory,
            plan_destination=plan_destination,
        )


def test_freeze_holds_the_shared_claim_lease_through_durable_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    globals_ = SCRIPT["_freeze_under_shared_lease"].__globals__
    active = {"lease": False}
    writes: list[bytes] = []

    @contextmanager
    def lease(path: Path, *, exclusive: bool):
        assert path == Path("claims")
        assert exclusive is False
        active["lease"] = True
        try:
            yield
        finally:
            active["lease"] = False

    class Emulator:
        frame_count = 0
        pressed_buttons: frozenset[str] = frozenset()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    roots = tuple(SimpleNamespace(binding=SimpleNamespace()) for _ in range(7))
    scan = SimpleNamespace(roots=roots)
    candidate = SimpleNamespace()
    plan = cast(
        BattleScenarioMaterializationPlan,
        SimpleNamespace(
            assignments=(),
            canonical_bytes=lambda: b"private-plan\n",
        ),
    )
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_lease", lease)
    monkeypatch.setitem(globals_, "PyBoyAdapter", lambda path: Emulator())
    monkeypatch.setitem(
        globals_,
        "_observe_root",
        lambda *args, **kwargs: SimpleNamespace(
            claim_available=True,
            materialization_eligible=True,
            venue_id="route_11",
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_candidate_from_loaded_root",
        lambda *args, **kwargs: candidate,
    )

    def build(**kwargs: object) -> BattleScenarioMaterializationPlan:
        assert active["lease"] is True
        assert len(kwargs["candidates"]) == 7  # type: ignore[arg-type]
        return plan

    monkeypatch.setitem(globals_, "build_battle_scenario_materialization_plan", build)
    monkeypatch.setitem(
        globals_,
        "_require_new_assignment_outputs",
        lambda *args, **kwargs: active["lease"] is True
        or pytest.fail("lease released before output check"),
    )

    def write(path: Path, payload: bytes) -> None:
        assert active["lease"] is True
        assert path == tmp_path / "plan.json"
        writes.append(payload)

    monkeypatch.setitem(globals_, "_write_exclusive", write)

    frozen, available = SCRIPT["_freeze_under_shared_lease"](
        scan=scan,
        registry_path=Path("claims"),
        rom_path=Path("rom"),
        plan_id="plan",
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        rom_sha256="c" * 64,
        capture_directory=tmp_path,
        capture_directory_sha256="d" * 64,
        destination=tmp_path / "plan.json",
    )

    assert frozen is plan
    assert available == 7
    assert writes == [b"private-plan\n"]
    assert active["lease"] is False
