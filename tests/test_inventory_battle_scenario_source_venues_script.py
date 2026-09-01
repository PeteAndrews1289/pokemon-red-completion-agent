from __future__ import annotations

import hashlib
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_outcome_batch import FRESH_TRAIN_CONTEXTS
from pokemon_red_completion.gen1_field_moves import FLY_MOVE_ID
from pokemon_red_completion.observation import Badge, MapId, RamAddress, RawGameState

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "inventory_battle_scenario_source_venues.py")
)


def test_inventory_accepts_only_a_whole_state_bank_not_selected_roots() -> None:
    options = INVENTORY["_parser"]()._option_string_actions

    assert "--state-bank" in options
    assert "--source-state" not in options
    assert "--root-lineage-id" not in options
    assert "--partition" not in options
    assert "--source-location" not in options


@pytest.mark.parametrize(
    ("counts", "expected"),
    (
        ({"pokemon_mansion_1f": FRESH_TRAIN_CONTEXTS}, False),
        ({"pokemon_mansion_1f": 6, "route_11": 1}, True),
        ({"pokemon_mansion_1f": 5, "digletts_cave": 2}, True),
        ({"route_11": 3, "digletts_cave": 3}, False),
    ),
)
def test_inventory_capacity_enforces_count_and_venue_diversity(
    counts: dict[str, int],
    expected: bool,
) -> None:
    assert INVENTORY["_venue_capacity"](INVENTORY["Counter"](counts)) is expected


def test_inventory_hash_joins_the_whole_bank_without_trusting_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payloads = {
        "train-a": b"state-a",
        "train-b": b"state-b",
        "development-a": b"state-c",
    }
    entries = tuple(
        SimpleNamespace(
            slot_id=name,
            capture_id=name,
            state_sha256=hashlib.sha256(payload).hexdigest(),
        )
        for name, payload in payloads.items()
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "unrelated-name.state").write_bytes(payloads["train-a"])
    (nested / "another-name.state").write_bytes(payloads["train-b"])
    (nested / "validation-copy.state").write_bytes(payloads["development-a"])
    (nested / "unmatched.state").write_bytes(b"not in the catalog")
    registry = SimpleNamespace(
        assignment=lambda slot_id: SimpleNamespace(
            partition="validation" if slot_id.startswith("development") else "train"
        )
    )
    catalog = SimpleNamespace(entries=entries)
    script_globals = INVENTORY["_open_all_catalog_train_roots"].__globals__
    observed: list[tuple[str, str]] = []

    def authenticate(state_sha256: str, **kwargs: object) -> SimpleNamespace:
        del kwargs
        entry = next(item for item in entries if item.state_sha256 == state_sha256)
        observed.append((entry.slot_id, state_sha256))
        return SimpleNamespace(
            source_slot_id=entry.slot_id,
            source_state_sha256=state_sha256,
            root_consumption_sha256=hashlib.sha256(
                f"root:{entry.slot_id}".encode("ascii")
            ).hexdigest(),
        )

    monkeypatch.setitem(
        script_globals,
        "authenticate_battle_scenario_source_binding",
        authenticate,
    )

    scan = INVENTORY["_open_all_catalog_train_roots"](
        tmp_path,
        catalog=catalog,
        registry=registry,
    )

    assert [root.binding.source_slot_id for root in scan.roots] == ["train-a", "train-b"]
    assert scan.state_files_hashed == 4
    assert scan.matching_state_file_copies == 2
    assert scan.missing_catalog_train_roots == 0
    assert observed == [
        ("train-a", hashlib.sha256(b"state-a").hexdigest()),
        ("train-b", hashlib.sha256(b"state-b").hexdigest()),
    ]


def test_inventory_reports_a_missing_catalog_train_state_without_inventing_it(
    tmp_path: Path,
) -> None:
    entry = SimpleNamespace(
        slot_id="train-a",
        capture_id="train-a",
        state_sha256=hashlib.sha256(b"state-a").hexdigest(),
    )
    registry = SimpleNamespace(assignment=lambda slot_id: SimpleNamespace(partition="train"))
    catalog = SimpleNamespace(entries=(entry,))

    scan = INVENTORY["_open_all_catalog_train_roots"](
        tmp_path,
        catalog=catalog,
        registry=registry,
    )

    assert scan.roots == ()
    assert scan.state_files_hashed == 0
    assert scan.matching_state_file_copies == 0
    assert scan.missing_catalog_train_roots == 1


def test_inventory_observes_map_and_availability_without_advancing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=2,
        party_hp=(40, 0),
        battle_state=0,
    )

    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()

        def __init__(self) -> None:
            self.loads: list[bytes] = []

        def load_state_bytes(self, payload: bytes) -> None:
            self.loads.append(payload)

        def read_u8(self, address: int) -> int:
            assert address == RamAddress.CURRENT_MAP_TILESET
            return 0

    emulator = Emulator()
    script_globals = INVENTORY["_observe_root"].__globals__
    monkeypatch.setitem(
        script_globals,
        "PokemonRedStateReader",
        lambda current: SimpleNamespace(
            read=lambda: raw,
            read_last_blackout_map=lambda: int(MapId.VERMILION_CITY),
        ),
    )
    monkeypatch.setitem(
        script_globals,
        "root_claim_is_available",
        lambda path, identity: path == Path("claims") and identity == "root",
    )
    root = SimpleNamespace(
        state_bytes=b"state",
        binding=SimpleNamespace(root_consumption_sha256="root"),
    )

    observed = INVENTORY["_observe_root"](
        root,
        emulator=emulator,
        registry_path=Path("claims"),
    )

    assert emulator.loads == [b"state"]
    assert observed.map_label == "route_11"
    assert observed.venue_id == "route_11"
    assert observed.relocation_required is False
    assert observed.route_11_relocation_ready is True
    assert observed.materialization_eligible is True


def test_inventory_counts_only_capable_celadon_roots_as_route_11_supply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capable = RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=1,
        battle_state=0,
        party_hp=(40,),
        party_moves=((FLY_MOVE_ID, 0, 0, 0),),
        badge_bits=int(Badge.THUNDER),
    )

    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()

        def load_state_bytes(self, payload: bytes) -> None:
            del payload

        def read_u8(self, address: int) -> int:
            assert address == RamAddress.CURRENT_MAP_TILESET
            return 6

    current = {"raw": capable}
    globals_ = INVENTORY["_observe_root"].__globals__
    monkeypatch.setitem(
        globals_,
        "PokemonRedStateReader",
        lambda emulator: SimpleNamespace(
            read=lambda: current["raw"],
            read_last_blackout_map=lambda: int(MapId.CELADON_CITY),
        ),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: True)
    root = SimpleNamespace(
        state_bytes=b"state",
        binding=SimpleNamespace(root_consumption_sha256="root"),
    )

    eligible = INVENTORY["_observe_root"](
        root,
        emulator=Emulator(),
        registry_path=Path("claims"),
    )
    current["raw"] = replace(capable, party_hp=(0,))
    rejected = INVENTORY["_observe_root"](
        root,
        emulator=Emulator(),
        registry_path=Path("claims"),
    )

    assert eligible.venue_id == "route_11"
    assert eligible.relocation_required is True
    assert eligible.fly_relocation_ready is True
    assert eligible.ground_relocation_ready is False
    assert eligible.route_11_relocation_ready is True
    assert eligible.materialization_eligible is True
    assert rejected.venue_id is None
    assert rejected.relocation_required is False
    assert rejected.fly_relocation_ready is False
    assert rejected.ground_relocation_ready is False
    assert rejected.route_11_relocation_ready is False
    assert rejected.materialization_eligible is False


def test_inventory_reports_only_available_unsupported_relocation_supply() -> None:
    observed_type = INVENTORY["_ObservedTrainRoot"]
    observed = (
        observed_type(
            map_label="lavender_pokecenter",
            venue_id=None,
            relocation_required=False,
            fly_relocation_ready=False,
            ground_relocation_ready=True,
            route_11_relocation_ready=True,
            claim_available=True,
            safe_nonbattle=True,
            living_party_member_available=True,
        ),
        observed_type(
            map_label="fuchsia_city",
            venue_id=None,
            relocation_required=False,
            fly_relocation_ready=True,
            ground_relocation_ready=False,
            route_11_relocation_ready=True,
            claim_available=False,
            safe_nonbattle=True,
            living_party_member_available=True,
        ),
        observed_type(
            map_label="celadon_pokecenter",
            venue_id="route_11",
            relocation_required=True,
            fly_relocation_ready=True,
            ground_relocation_ready=False,
            route_11_relocation_ready=True,
            claim_available=True,
            safe_nonbattle=True,
            living_party_member_available=True,
        ),
    )

    counts = INVENTORY["_available_unsupported_capability_counts"](
        observed,
        "route_11_relocation_ready",
    )

    assert counts == {"lavender_pokecenter": 1}


def test_inventory_rejects_any_advanced_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=1,
        party_hp=(40,),
        battle_state=0,
    )
    emulator = SimpleNamespace(
        frame_count=1,
        pressed_buttons=frozenset(),
        load_state_bytes=lambda payload: None,
        read_u8=lambda address: 0,
    )
    script_globals = INVENTORY["_observe_root"].__globals__
    monkeypatch.setitem(
        script_globals,
        "PokemonRedStateReader",
        lambda current: SimpleNamespace(
            read=lambda: raw,
            read_last_blackout_map=lambda: int(MapId.VERMILION_CITY),
        ),
    )
    monkeypatch.setitem(
        script_globals,
        "root_claim_is_available",
        lambda *args: True,
    )
    root = SimpleNamespace(
        state_bytes=b"state",
        binding=SimpleNamespace(root_consumption_sha256="root"),
    )

    with pytest.raises(
        INVENTORY["BattleScenarioSourceInventoryError"],
        match="controller boundary",
    ):
        INVENTORY["_observe_root"](
            root,
            emulator=emulator,
            registry_path=Path("claims"),
        )
