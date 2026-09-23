from __future__ import annotations

import json
from types import SimpleNamespace

import capture_fresh_red_trainer_train_batch as sources
import materialize_red_teacher_battle_practice as factory
import pytest
import run_red_six_party_assisted_pilot as pilot

from pokemon_red_completion import red_battle_practice_factory as adapter
from pokemon_red_completion.battle_practice_factory import (
    AssistedDevelopmentPracticeSpec,
    BattlePracticeError,
    BattlePracticeSpec,
)
from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.scenario_lab import ScenarioPartition


class Cartridge:
    species_ids = (2, 5, 8, 17, 20, 25, 27)

    def species(self, number):
        return SimpleNamespace(national_number=number, internal_id=number,
                               trainer_stats=lambda _level: SimpleNamespace(max_hp=60))


def report(boot=3300):
    return {
        "partition": "development", "fresh_power_on": True, "boot_frames": boot,
        "root_lineage_id": f"fresh-red-lab-rival-development-boot{boot}",
        "origin_state_sha256": "a" * 64, "battle_state_sha256": "b" * 64,
        "first_party_ot_id": 123,
    }


def spec_dict(boot=3300, count=6):
    return pilot.practice(Cartridge(), boot=boot, count=count, source=report(boot))


@pytest.mark.parametrize("boot", pilot.BOOTS)
@pytest.mark.parametrize("count", pilot.PARTY_SIZES)
def test_declared_conditions_preserve_partition_and_actual_late_slot(boot, count):
    spec = AssistedDevelopmentPracticeSpec.from_dict(spec_dict(boot, count))
    assert spec.partition is ScenarioPartition.DEVELOPMENT
    assert len(spec.party_reserves) == count - 1
    assert [r.party_slot for r in spec.party_reserves] == list(range(2, count + 1))
    assert spec.party_reserves[-1].national_number == 25
    assert all(m.pp == 0 for m in spec.actor_moves) == (boot == 3500)
    assert spec.actor_level == spec.opponent_level == 20
    for reserve in spec.opponent_reserves:
        for move in reserve.moves:
            assert move.pp == pilot.PokemonRedBattleCatalog().resolve_move(move.move_ref).max_pp
    with pytest.raises(BattlePracticeError, match="train-only"):
        BattlePracticeSpec.from_dict(spec_dict(boot, count))


@pytest.mark.parametrize("partition", ("train", "test"))
def test_development_spec_rejects_other_partitions(partition):
    with pytest.raises(BattlePracticeError, match="development-only"):
        AssistedDevelopmentPracticeSpec.from_dict({**spec_dict(), "partition": partition})


def test_train_entry_rejects_development_before_reading_or_writing():
    spec = AssistedDevelopmentPracticeSpec.from_dict(spec_dict())
    with pytest.raises(BattlePracticeError, match="TRAIN materialization"):
        adapter.materialize_red_train_practice(None, None, spec)
    train = BattlePracticeSpec.from_dict({**spec_dict(), "partition": "train"})
    with pytest.raises(BattlePracticeError, match="explicit development"):
        adapter.materialize_red_assisted_development_practice(None, None, train, cartridge=None)


def test_development_receipt_is_truthful_and_hashes_differ():
    dev = AssistedDevelopmentPracticeSpec.from_dict(spec_dict())
    train = BattlePracticeSpec.from_dict({**spec_dict(), "partition": "train"})
    assert dev.configuration_sha256 != train.configuration_sha256
    receipt = adapter.RedPracticeReceipt(
        source_state_sha256="a" * 64, root_lineage_id="fresh-source",
        configuration_sha256=dev.configuration_sha256,
        actor_species_id=5, actor_level=20, opponent_species_id=8, opponent_level=20,
        actor_move_ids=(52, 10), actor_pp=(10, 10), opponent_hp=60, opponent_max_hp=60,
        observation_sha256="b" * 64, legal_move_count=2, battle_kind="trainer",
        player_party_count=6, partition=ScenarioPartition.DEVELOPMENT,
    ).public_dict()
    assert receipt["partition"] == "development"
    assert receipt["fit_allowed"] is False
    assert receipt["natural_battle_qualification"] is False
    assert receipt["new_independent_upstream_roots"] == 0


@pytest.mark.parametrize("field", ("origin_state_sha256", "battle_state_sha256",
                                   "root_lineage_id", "first_party_ot_id"))
def test_new_source_rejects_reused_physical_ancestry(field):
    previous = {**report(3500), "origin_state_sha256": "c" * 64,
                "battle_state_sha256": "d" * 64, "first_party_ot_id": 321}
    candidate = report()
    candidate[field] = previous[field]
    with pytest.raises(ValueError, match="physical ancestry"):
        pilot.validate_new_source(candidate, {"manifests": []}, [previous])


def test_new_source_rejects_inventory_overlap_and_no_output_retry(tmp_path):
    pilot.validate_new_source(report(), {"manifests": []}, [])
    row = {"root_lineage_id": "prior", "state_sha256": "b" * 64,
           "source_state_sha256": "c" * 64}
    with pytest.raises(ValueError, match="physical ancestry"):
        pilot.validate_new_source(report(), {"manifests": [row]}, [])
    pilot.write_new(tmp_path / "claim.json", {"claimed": True})
    with pytest.raises(FileExistsError):
        pilot.write_new(tmp_path / "claim.json", {"claimed": False})


@pytest.mark.parametrize("parent", ({}, {"source_state_sha256": None}))
def test_legacy_missing_parent_keeps_state_and_root_excluded(parent):
    row = {"root_lineage_id": "legacy-root", "state_sha256": "c" * 64, **parent}
    inventory = {"manifests": [row]}
    assert pilot.inventory_ancestry(inventory) == ({"c" * 64}, {"legacy-root"})
    pilot.validate_new_source(report(), inventory, [])
    with pytest.raises(ValueError, match="physical ancestry"):
        pilot.validate_new_source({**report(), "origin_state_sha256": "c" * 64}, inventory, [])
    with pytest.raises(ValueError, match="physical ancestry"):
        pilot.validate_new_source({**report(), "root_lineage_id": "legacy-root"}, inventory, [])


@pytest.mark.parametrize("parent", ("", "invalid", 123))
def test_present_invalid_parent_is_not_silently_treated_as_missing(parent):
    with pytest.raises(ValueError, match="ancestry hash"):
        pilot.inventory_ancestry({"manifests": [{
            "root_lineage_id": "legacy-root", "state_sha256": "c" * 64,
            "source_state_sha256": parent,
        }]})


def test_materializer_explicit_development_schema_and_source_partition(tmp_path, monkeypatch):
    monkeypatch.setattr(factory.subprocess, "check_output",
                        lambda args, **_kw: b"" if args[1] == "status" else b"a" * 40)
    rom = tmp_path / "rom"
    rom.write_bytes(b"rom")
    state = tmp_path / "source.state"
    state.write_bytes(b"source")
    monkeypatch.setattr(factory, "ROM_SHA256", pilot.binding(rom)["sha256"])
    practice = {**spec_dict(), "source_state_sha256": pilot.binding(state)["sha256"]}
    manifest = tmp_path / "source.state.json"

    def source(partition):
        manifest.write_bytes(build_battle_scenario_capture_payload(
            capture_id="fresh-source", root_lineage_id=practice["root_lineage_id"],
            partition=partition, state_bytes=b"source", initial_observation_sha256="b" * 64,
            source_commit="a" * 40, expected_map=40, expected_battle_state=2,
            observation_schema=factory.OBSERVATION_SCHEMA_V2,
        ))
        return pilot.binding(manifest)

    plan = {
        "schema": factory.DEVELOPMENT_SCHEMA, "source_commit": "a" * 40,
        "rom": pilot.binding(rom), "source_state": pilot.binding(state),
        "source_capture_manifest": source(ScenarioPartition.DEVELOPMENT),
        "practice": practice, "observation_schema": factory.OBSERVATION_SCHEMA_V2,
        "fit_allowed": False, "natural_battle_qualification": False,
        "output": str(tmp_path / "output"),
    }
    assert isinstance(factory._authenticate(plan, b"plan")[1], AssistedDevelopmentPracticeSpec)
    with pytest.raises(ValueError, match="explicit exclusions"):
        factory._authenticate({**plan, "fit_allowed": True}, b"plan")
    with pytest.raises(ValueError, match="authenticated train trainer capture"):
        factory._authenticate({**plan, "source_capture_manifest": source(ScenarioPartition.TRAIN)},
                              b"plan")
    with pytest.raises(BattlePracticeError, match="train-only"):
        factory._authenticate({**plan, "schema": factory.TRAINER_SCHEMA}, b"plan")


def frozen_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "revision", lambda: "a" * 40)
    inventory = tmp_path / "inventory.json"
    inventory.write_text("{}")
    output = tmp_path / "pilot"
    output.mkdir()
    cells = []
    for boot in pilot.BOOTS:
        for count in pilot.PARTY_SIZES:
            directory = output / f"{boot}-{count}"
            directory.mkdir()
            pilot.write_new(directory / "materialized.json", {"partition": "development"})
            pilot.write_new(directory / "plan.json", {
                "outcome_model": {"sha256": pilot.MODEL_SHA256},
                "output": str(directory / "episode"),
            })
            cells.append({"boot": boot, "party_count": count,
                          "plan": pilot.binding(directory / "plan.json"),
                          "materialization": pilot.binding(directory / "materialized.json")})
    pilot.write_new(output / "protocol.json", {
        "source_commit": "a" * 40, "output": str(output),
        "inventory": pilot.binding(inventory),
    })
    pilot.write_new(output / "freeze.json", {
        "protocol": pilot.binding(output / "protocol.json"), "cells": cells,
    })
    pilot.write_new(tmp_path / "assisted-six-party-20260920-freeze.json",
                    pilot.binding(output / "freeze.json"))
    return SimpleNamespace(output=output, inventory=inventory)


@pytest.mark.parametrize("stop", ("battle_won", "party_defeated", "decision_budget"))
def test_campaign_reads_full_receipt_retains_losses_and_stops_invalid_terminal(
    tmp_path, monkeypatch, stop
):
    args = frozen_campaign(tmp_path, monkeypatch)
    calls = []

    def run(path, check_only=False):
        if check_only:
            return {}
        calls.append(path)
        directory = pilot.Path(json.loads(path.read_bytes())["output"])
        directory.mkdir()
        (directory / "final.state").write_bytes(b"endpoint")
        pilot.write_new(directory / "outcome.json", {
            "stop_reason": stop, "teacher_queries": 0, "memory_write_actions": 0,
            "metrics": {"invalid_action_failures": 0}, "decision_count": 3,
            "final_state_sha256": pilot.binding(directory / "final.state")["sha256"],
        })
        return {"status": "runner_summary_not_full_report"}

    monkeypatch.setattr(pilot.player, "run", run)
    monkeypatch.setattr(pilot, "verify_trainer_practice_event_log",
                        lambda _p: {"complete": True, "terminal_event": "run_finished"})
    if stop == "decision_budget":
        with pytest.raises(ValueError, match="remaining cells"):
            pilot.evaluate(args)
        assert len(calls) == 1
        assert (args.output / "evaluation-failure.json").exists()
    else:
        assert pilot.evaluate(args)["status"] == "bounded_pilot_completed"
        assert len(calls) == 6
    with pytest.raises(FileExistsError):
        pilot.evaluate(args)
    assert len(calls) == (1 if stop == "decision_budget" else 6)


def test_source_setup_failure_retains_actual_endpoint(tmp_path, monkeypatch):
    class Emulator:
        frame_count = 0
        pressed_buttons = set()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def save_state_bytes(self):
            return b"actual-failure-endpoint"

    monkeypatch.setattr(sources, "PyBoyAdapter", lambda *_a, **_kw: Emulator())
    with (
        pytest.raises(ValueError, match="setup failure"),
        sources._source_session(tmp_path / "rom", tmp_path),
    ):
        raise ValueError("setup failure")
    assert (tmp_path / "failed-source.state").read_bytes() == b"actual-failure-endpoint"
    assert json.loads((tmp_path / "source-failure.json").read_bytes())["error_type"] == "ValueError"


def retained_preparation(tmp_path, monkeypatch):
    output = tmp_path / "pilot"
    output.mkdir()
    inventory = tmp_path / "inventory.json"
    inventory.write_text('{"manifests": []}')
    original = {"source_commit": "a" * 40, "templates": ["unchanged"]}
    pilot.write_new(output / "protocol.json", original)
    pilot.write_new(tmp_path / "assisted-six-party-20260920-preparation-claim.json", original)
    pilot.write_new(output / "preparation-failure.json", {
        "stage": "source-3300", "error_type": "KeyError", "error": "'source_state_sha256'",
        "completed_sources": 0, "completed_cells": 0, "retry_allowed": False, "global_stop": True,
    })
    source = output / "source-3300"
    source.mkdir()
    (source / "origin.state").write_bytes(b"origin")
    (source / "source.state").write_bytes(b"source")
    r = {**report(), "source_commit": "a" * 40, "model_queries": 0,
         "origin_state_sha256": pilot.binding(source / "origin.state")["sha256"],
         "battle_state_sha256": pilot.binding(source / "source.state")["sha256"]}
    (source / "source.state.json").write_bytes(build_battle_scenario_capture_payload(
        capture_id=r["root_lineage_id"], root_lineage_id=r["root_lineage_id"],
        partition=ScenarioPartition.DEVELOPMENT, state_bytes=b"source",
        source_state_sha256=r["origin_state_sha256"], initial_observation_sha256="b" * 64,
        source_commit="a" * 40, expected_map=40, expected_battle_state=2,
    ))
    pilot.write_new(source / "outcome.json", r)
    monkeypatch.setattr(pilot, "ORIGINAL_PROTOCOL_SHA256",
                        pilot.binding(output / "protocol.json")["sha256"])
    monkeypatch.setattr(pilot, "RETAINED_HASHES", {
        name: pilot.binding(source / name)["sha256"]
        for name in ("origin.state", "source.state", "source.state.json")
    })
    monkeypatch.setattr(pilot, "prior_sources", lambda _inventory: [])
    return SimpleNamespace(output=output, inventory=inventory), {
        **original, "source_commit": "c" * 40
    }


def test_exact_state_resume_keeps_old_claim_and_failure_and_is_one_shot(tmp_path, monkeypatch):
    args, protocol = retained_preparation(tmp_path, monkeypatch)
    failure = pilot.binding(args.output / "preparation-failure.json")
    result = pilot.resume_first_source(args, protocol)
    assert result["boot_frames"] == 3300
    assert protocol["continuation"]["first_source_replayed"] is False
    assert pilot.binding(args.output / "preparation-failure.json") == failure
    assert (tmp_path / "assisted-six-party-20260920-resume-claim.json").exists()
    protocol.pop("continuation")
    with pytest.raises(FileExistsError):
        pilot.resume_first_source(args, protocol)


@pytest.mark.parametrize("mutation", ("conditions", "source_bytes", "second_started", "failure"))
def test_resume_rejects_changed_conditions_artifacts_or_failure(tmp_path, monkeypatch, mutation):
    args, protocol = retained_preparation(tmp_path, monkeypatch)
    if mutation == "conditions":
        protocol["templates"] = ["easier"]
    elif mutation == "source_bytes":
        (args.output / "source-3300/source.state").write_bytes(b"changed")
    elif mutation == "second_started":
        (args.output / "source-3500").mkdir()
    else:
        (args.output / "preparation-failure.json").write_text("{}")
    with pytest.raises(ValueError):
        pilot.resume_first_source(args, protocol)
    assert not (tmp_path / "assisted-six-party-20260920-resume-claim.json").exists()


def test_resumed_preparation_only_captures_second_start_and_freezes_six_cases(
    tmp_path, monkeypatch
):
    args = SimpleNamespace(output=tmp_path / "pilot", inventory=tmp_path / "inventory.json",
                           model=tmp_path / "model.json", rom=tmp_path / "rom")
    args.output.mkdir()
    pilot.write_new(args.output / "protocol.json", {"original": "preserved"})
    args.inventory.write_text('{"manifests": []}')
    args.model.write_text('{"train_root_ids": []}')
    args.rom.write_bytes(b"ROM")
    monkeypatch.setattr(pilot, "revision", lambda: "c" * 40)
    monkeypatch.setattr(pilot, "INVENTORY_SHA256", pilot.binding(args.inventory)["sha256"])
    monkeypatch.setattr(pilot, "MODEL_SHA256", pilot.binding(args.model)["sha256"])
    monkeypatch.setattr(factory, "ROM_SHA256", pilot.binding(args.rom)["sha256"])
    monkeypatch.setattr(pilot, "prior_sources", lambda _i: [])
    monkeypatch.setattr(pilot, "RedPracticeCartridge", lambda _r: Cartridge())
    monkeypatch.setattr(pilot, "resume_first_source", lambda _a, _p: report())
    source = args.output / "source-3300"
    source.mkdir()
    (source / "source.state").write_bytes(b"source")
    (source / "source.state.json").write_bytes(b"manifest")
    captures = []

    def capture(_rom, _payload, boot, _commit, **_kw):
        captures.append(boot)
        r = {**report(boot), "origin_state_sha256": "c" * 64,
             "battle_state_sha256": "d" * 64, "first_party_ot_id": 321}
        return b"origin-3500", b"source-3500", b"manifest-3500", r

    def materialize(path):
        plan = json.loads(path.read_bytes())
        out = pilot.Path(plan["output"])
        out.mkdir()
        (out / "assisted.state").write_bytes(b"assisted")
        (out / "assisted.state.json").write_bytes(b"manifest")
        pilot.write_new(out / "outcome.json", {"partition": "development"})

    monkeypatch.setattr(sources, "_capture_one", capture)
    monkeypatch.setattr(factory, "run", materialize)
    assert pilot.prepare(args, resume=True)["cells"] == 6
    assert captures == [3500]
    assert json.loads((args.output / "protocol.json").read_bytes()) == {"original": "preserved"}
    frozen = json.loads((args.output / "freeze.json").read_bytes())
    assert len(frozen["cells"]) == 6
    assert frozen["protocol"]["path"].endswith("resumed-protocol.json")
