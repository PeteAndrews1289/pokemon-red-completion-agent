import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref, pokemon_red_species_ref
from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import materialize_red_teacher_battle_practice as runner  # noqa: E402


def _bound(path, content):
    path.write_bytes(content)
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}


def _plan(tmp_path):
    state = b"retained source"
    state_hash = hashlib.sha256(state).hexdigest()
    root = "red-goal-root-practice-test"
    return {
        "schema": runner.SCHEMA,
        "source_commit": "a" * 40,
        "rom": _bound(tmp_path / "red.gb", b"ROM"),
        "source_state": _bound(tmp_path / "before.state", state),
        "source_query": _bound(
            tmp_path / "query.json",
            json.dumps({"state_sha256": state_hash, "observation_sha256": "b" * 64}).encode(),
        ),
        "source_episode": _bound(
            tmp_path / "episode.json",
            json.dumps(
                {
                    "schema": "pokemon.red.model-battle-train-episode-outcome.v1",
                    "root_lineage_id": root,
                    "completed_decisions": 1,
                }
            ).encode(),
        ),
        "source_observation_sha256": "b" * 64,
        "source_encounter_index": 0,
        "practice": {
            "source_state_sha256": state_hash,
            "root_lineage_id": root,
            "partition": "train",
            "actor_moves": [
                {"move_ref": pokemon_red_move_ref(33), "pp": 20},
                {"move_ref": pokemon_red_move_ref(70), "pp": 15},
            ],
            "opponent_hp": 50,
        },
        "output": str(tmp_path / "new-output"),
    }


def test_factory_plan_requires_clean_exact_source(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"dirty" if args[1] == "status" else b"a" * 40,
    )
    with pytest.raises(ValueError, match="commit teacher factory"):
        runner._authenticate(plan, b"plan")
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"c" * 40,
    )
    with pytest.raises(ValueError, match="source commit differs"):
        runner._authenticate(plan, b"plan")


def test_factory_plan_authenticates_retained_state_and_rejects_reuse(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"a" * 40,
    )
    _, spec, source, rom = runner._authenticate(plan, b"plan")
    assert isinstance(spec, BattlePracticeSpec)
    assert source == b"retained source"
    assert rom == b"ROM"
    with pytest.raises(ValueError, match="retained train decision"):
        runner._authenticate({**plan, "source_observation_sha256": "x" * 64}, b"plan")
    Path(plan["output"]).mkdir()
    with pytest.raises(ValueError, match="must be new"):
        runner._authenticate(plan, b"plan")


def test_action_free_preflight_does_not_write_artifacts(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    spec = BattlePracticeSpec.from_dict(plan["practice"])
    monkeypatch.setattr(runner, "_authenticate", lambda *_: (plan, spec, b"source", b"ROM"))

    class Emulator:
        frame_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def load_state_bytes(self, _payload):
            pass

        def _require_backend(self):
            return SimpleNamespace(memory={})

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setattr(runner, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setattr(runner, "RedPracticeCartridge", lambda _rom: object())
    monkeypatch.setattr(
        runner,
        "materialize_red_train_practice",
        lambda *_args, **_kwargs: SimpleNamespace(legal_move_count=2),
    )
    assert runner.run(plan_path, check_only=True)["controller_actions"] == 0
    assert not Path(plan["output"]).exists()


def test_trainer_plan_requires_authenticated_train_capture(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    source = Path(plan["source_state"]["path"]).read_bytes()
    manifest = build_battle_scenario_capture_payload(
        capture_id="train-trainer-source",
        root_lineage_id=plan["practice"]["root_lineage_id"],
        partition=ScenarioPartition.TRAIN,
        state_bytes=source,
        initial_observation_sha256="b" * 64,
        source_commit="c" * 40,
        expected_map=120,
        expected_battle_state=2,
    )
    plan.update(
        schema=runner.TRAINER_SCHEMA,
        source_capture_manifest=_bound(tmp_path / "before.state.json", manifest),
    )
    plan["practice"].update(
        battle_kind="trainer",
        opponent_species_ref=pokemon_red_species_ref(177),
        opponent_level=30,
        opponent_moves=[{"move_ref": pokemon_red_move_ref(55), "pp": 25}],
        opponent_party_count=1,
    )
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"ROM").hexdigest())
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kwargs: b"" if args[1] == "status" else b"a" * 40,
    )
    _, spec, authenticated_source, _ = runner._authenticate(plan, b"plan")
    assert spec.battle_kind == "trainer"
    assert authenticated_source == source
    with pytest.raises(ValueError, match="authenticated train trainer capture"):
        runner._authenticate(
            {**plan, "practice": {**plan["practice"], "root_lineage_id": "different-root"}},
            b"plan",
        )


def test_trainer_plan_rechecks_semantic_source_before_teacher_writes(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan["schema"] = runner.TRAINER_SCHEMA
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    spec = BattlePracticeSpec.from_dict(plan["practice"])
    monkeypatch.setattr(runner, "_authenticate", lambda *_: (plan, spec, b"source", b"ROM"))

    class Emulator:
        frame_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def load_state_bytes(self, _payload):
            pass

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setattr(
        runner,
        "PokemonRedStateReader",
        lambda _emulator: SimpleNamespace(read=lambda: object()),
    )
    monkeypatch.setattr(runner, "_bound_file", lambda *_args: b"manifest")
    monkeypatch.setattr(
        runner,
        "parse_battle_scenario_capture_manifest",
        lambda _payload: SimpleNamespace(
            initial_observation_sha256="a" * 64, observation_schema=None
        ),
    )
    monkeypatch.setattr(runner, "RedPracticeCartridge", lambda _rom: object())
    monkeypatch.setattr(
        runner.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader, **_kwargs: object(),
    )
    monkeypatch.setattr(
        runner,
        "prepare_red_battle_scenario",
        lambda *_args, **_kwargs: SimpleNamespace(initial_observation_sha256="b" * 64),
    )
    monkeypatch.setattr(
        runner,
        "materialize_red_train_practice",
        lambda *_args, **_kwargs: pytest.fail("teacher wrote before source verification"),
    )
    with pytest.raises(ValueError, match="semantic observation differs"):
        runner.run(plan_path, check_only=True)


def test_trainer_materializer_accepts_exact_rich_source_observation(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan["schema"] = runner.TRAINER_SCHEMA
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    spec = BattlePracticeSpec.from_dict(plan["practice"])
    monkeypatch.setattr(runner, "_authenticate", lambda *_: (plan, spec, b"source", b"ROM"))

    class Emulator:
        frame_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def load_state_bytes(self, _payload):
            pass

        def _require_backend(self):
            return SimpleNamespace(memory={})

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setattr(
        runner, "PokemonRedStateReader", lambda _emulator: SimpleNamespace(read=lambda: object())
    )
    monkeypatch.setattr(runner, "_bound_file", lambda *_args: b"manifest")
    monkeypatch.setattr(
        runner, "parse_battle_scenario_capture_manifest",
        lambda _payload: SimpleNamespace(
            initial_observation_sha256="a" * 64,
            observation_schema=OBSERVATION_SCHEMA_V2,
        ),
    )
    monkeypatch.setattr(
        runner, "RedPracticeCartridge",
        lambda _rom: SimpleNamespace(public_base_stats={}),
    )
    seen = {}

    def encoder(_reader, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(runner.PokemonRedObservationEncoder, "from_state_reader", encoder)
    monkeypatch.setattr(
        runner,
        "prepare_red_battle_scenario",
        lambda *_args, **_kwargs: SimpleNamespace(initial_observation_sha256="a" * 64),
    )
    monkeypatch.setattr(
        runner,
        "materialize_red_train_practice",
        lambda *_args, **_kwargs: SimpleNamespace(
            legal_move_count=2, configuration_sha256="b" * 64
        ),
    )
    assert runner.run(plan_path, check_only=True)["controller_actions"] == 0
    assert seen == {"include_battle_stats": True, "public_species_base_stats": {}}
