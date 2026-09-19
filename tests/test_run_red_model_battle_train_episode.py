import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_model_battle_train_episode as runner  # noqa: E402
from test_red_model_battle_episode import binding  # noqa: E402


def test_plan_rejects_dirty_or_changed_code_before_inputs(monkeypatch):
    plan = {"schema": runner.SCHEMA, "source_commit": "a" * 40}
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"dirty" if args[1] == "status" else b"a" * 40,
    )
    with pytest.raises(ValueError, match="commit bounded implementation"):
        runner._authenticate(plan, b"{}")
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"b" * 40,
    )
    with pytest.raises(ValueError, match="source commit differs"):
        runner._authenticate(plan, b"{}")


def test_input_hash_and_hard_limits(tmp_path):
    source = tmp_path / "source.state"
    source.write_bytes(b"source")
    record = {"path": str(source), "sha256": hashlib.sha256(b"source").hexdigest()}
    assert runner._file(record, "source") == b"source"
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash differs"):
        runner._file(record, "source")
    limits = {
        "maximum_encounters": 3,
        "maximum_decisions": 12,
        "maximum_decisions_per_encounter": 8,
        "maximum_actions": 1600,
        "maximum_frames": 150000,
        "maximum_encounter_walks": 128,
    }
    assert runner._limits(limits) == limits
    with pytest.raises(ValueError, match="maximum_actions"):
        runner._limits({**limits, "maximum_actions": 1601})


def test_claim_uses_logical_and_physical_source_identity(monkeypatch):
    source = binding()
    claims = []

    class Ledger:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def claim(self, pair):
            claims.append(pair)

    monkeypatch.setattr(runner, "open_fixed_account_claim_registry", lambda: Path("/fake"))
    monkeypatch.setattr(runner, "claim_first_pair_registry", lambda _: Ledger())
    digest = runner._claim(source, b"precommitted plan", "a" * 40)
    assert len(claims) == 1
    assert claims[0].physical_root_sha256 == source.root_consumption_sha256
    assert claims[0].logical_root_sha256 == runner.canonical_sha256(
        {"root_lineage_id": source.root_lineage_id}
    )
    assert claims[0].claim_sha256 == digest


def test_source_movement_settles_only_with_bounded_neutral_wait():
    class Reader:
        def __init__(self):
            self.ready = False
            self.map_id = runner.MapId.CINNABAR_POKECENTER

        def read(self):
            return SimpleNamespace(map_id=self.map_id, battle_state=0, player_x=3, player_y=3)

        def read_input_readiness(self):
            return SimpleNamespace(
                ready=self.ready,
                joy_ignore=0,
                simulated_joypad_index=0,
                npc_movement_script_table=0,
                player_moving_direction=0 if self.ready else 1,
                status_flags_5=0,
                movement_flags=0,
                walk_counter=0,
            )

    class Actions:
        def __init__(self, reader):
            self.reader = reader
            self.calls = []

        def execute(self, action):
            self.calls.append(action)
            self.reader.ready = True

    reader = Reader()
    actions = Actions(reader)
    runner._await_source_field_input(reader, actions)
    assert len(actions.calls) == 1
    assert actions.calls[0].kind is runner.MacroActionKind.WAIT
    assert actions.calls[0].repeat == 16

    reader.ready = False
    reader.map_id = runner.MapId.POKEMON_MANSION_1F
    with pytest.raises(ValueError, match="left the declared Center"):
        runner._await_source_field_input(reader, actions)
    assert len(actions.calls) == 1
    assert not runner._movement_settling_only(
        SimpleNamespace(
            joy_ignore=1,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            status_flags_5=0,
            movement_flags=0,
            walk_counter=0,
        )
    )


def test_action_free_preflight_cannot_claim_or_start_episode(tmp_path, monkeypatch):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps({"output": str(tmp_path / "episode"), "rom": {"path": "unused"}})
    )
    source = binding()
    limits = runner._limits(
        {
            "maximum_encounters": 2,
            "maximum_decisions": 4,
            "maximum_decisions_per_encounter": 3,
            "maximum_actions": 100,
            "maximum_frames": 1000,
            "maximum_encounter_walks": 4,
        }
    )
    monkeypatch.setattr(
        runner,
        "_authenticate",
        lambda *args: (source, b"state", b"{}", b"rom", limits, "a" * 40),
    )
    monkeypatch.setattr(
        runner.MaskedMLPMoveRanker,
        "from_dict",
        lambda _: object(),
    )

    class Emulator:
        frame_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def load_state_bytes(self, data):
            assert data == b"state"

        def read_u8(self, address):
            assert address == runner.RamAddress.CURRENT_MAP_TILESET
            return 6

    emulator = Emulator()
    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *args, **kwargs: emulator)

    class Reader:
        def __init__(self, controller):
            assert controller is emulator

        def read(self):
            return SimpleNamespace(
                map_id=runner.MapId.CINNABAR_POKECENTER,
                player_x=3,
                player_y=3,
                party_count=1,
                party_hp=(100,),
                party_moves=((1, 2, 0, 0),),
                party_pp=((10, 10, 0, 0),),
            )

        def read_last_blackout_map(self):
            return 8

        def read_input_readiness(self):
            return SimpleNamespace(
                ready=True,
                joy_ignore=0,
                simulated_joypad_index=0,
                npc_movement_script_table=0,
                status_flags_5=0,
                movement_flags=0,
                walk_counter=0,
            )

    monkeypatch.setattr(runner, "PokemonRedStateReader", Reader)
    monkeypatch.setattr(
        runner,
        "battle_scenario_source_venue",
        lambda *args, **kwargs: SimpleNamespace(
            source_map=int(runner.MapId.CINNABAR_POKECENTER),
            encounter_map=int(runner.MapId.POKEMON_MANSION_1F),
            venue_id="pokemon_mansion_1f",
        ),
    )
    monkeypatch.setattr(runner, "red_battle_supported_move_count", lambda *args: 2)
    monkeypatch.setattr(runner, "open_fixed_account_claim_registry", lambda: Path("/fake"))

    class Lease:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(
        runner, "fixed_account_claim_registry_lease", lambda *args, **kwargs: Lease()
    )
    monkeypatch.setattr(runner, "root_claim_is_available", lambda *args: True)
    monkeypatch.setattr(runner, "_claim", lambda *args: pytest.fail("preflight claimed a root"))
    monkeypatch.setattr(
        runner,
        "run_model_battle_train_episode",
        lambda **kwargs: pytest.fail("preflight started an episode"),
    )
    result = runner.run(plan_path, check_only=True)
    assert result["status"] == "action_free_preflight_passed"
    assert result["root_claims_created"] == result["controller_actions"] == 0
    assert not (tmp_path / "episode").exists()
