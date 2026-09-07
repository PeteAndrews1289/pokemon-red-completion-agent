from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_native_boxed_evolution import runtime_fixture

import pokemon_red_completion.red_native_boxed_evolution as native_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_collection import RedCurrentBoxState, red_internal_species_id
from pokemon_red_completion.red_team_training import EvolutionTrainingPaused


@pytest.mark.parametrize("source,target,level", [(77, 78, 40), (16, 17, 18)])
@pytest.mark.parametrize("mode", ["complete", "stalled", "lost", "fainted", "exception", "bounded"])
def test_complete_option_checks_every_quantum(tmp_path, monkeypatch, source, target, level, mode):
    runtime, reader, _ = runtime_fixture(
        tmp_path,
        source=source,
        target=target,
        evolution_level=level,
    )
    source_id, target_id = red_internal_species_id(source), red_internal_species_id(target)
    reader.raw = replace(
        reader.raw,
        map_id=22,
        party_species_ids=(*reader.raw.party_species_ids[:5], source_id),
        party_levels=(63, 55, 55, 55, 55, 35),
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(RedCurrentBoxState(0, (source_id,), (30,)), *reader.boxes.boxes[1:]),
    )
    progress = {"xp": 1000, "calls": 0, "actions": 0}

    def read_party():
        party = runtime.adapter.observe().party
        return replace(
            party, members=tuple(replace(m, experience=progress["xp"]) for m in party.members)
        )

    monkeypatch.setattr(
        native_module, "PokemonRedPartyReader", lambda _: SimpleNamespace(read=read_party)
    )
    monkeypatch.setattr(
        native_module, "wild_tables", lambda _: {22: [(10, red_internal_species_id(19))]}
    )

    def action(_):
        progress["actions"] += 1

    def train(actions, *args, **kwargs):
        progress["calls"] += 1
        actions.execute(MacroAction(MacroActionKind.WAIT))
        if mode == "exception":
            raise RuntimeError("retained component failure")
        if mode == "fainted":
            reader.raw = replace(reader.raw, party_hp=(*reader.raw.party_hp[:5], 0))
        if mode == "lost":
            reader.boxes = replace(
                reader.boxes,
                boxes=(RedCurrentBoxState(0, (), ()), *reader.boxes.boxes[1:]),
            )
        if mode != "stalled":
            progress["xp"] += 200
        if mode == "complete" and progress["calls"] == 3:
            reader.raw = replace(
                reader.raw,
                party_species_ids=(*reader.raw.party_species_ids[:5], target_id),
            )
            return None, 1, 0
        raise EvolutionTrainingPaused(4, 1)

    monkeypatch.setattr(native_module.context, "run_red_team_balancing", train)
    retained = []
    native = native_module.bind_native_boxed_evolution(
        runtime,
        SimpleNamespace(rom=b"fixture"),
        maximum_quanta=3,
        retain_quantum=lambda: retained.append(progress["calls"]),
    )
    actions = CountingExecutor(SimpleNamespace(execute=action))
    if mode in {"stalled", "lost", "fainted", "exception"}:
        match = (
            "XP progress"
            if mode == "stalled"
            else "component failure"
            if mode == "exception"
            else "collection or safety"
        )
        with pytest.raises(RuntimeError, match=match):
            native.party_level_evolution_executor(source_id, target_id, actions)
        assert progress["calls"] == 1
    else:
        report = native.party_level_evolution_executor(source_id, target_id, actions)
        assert progress["calls"] == report.actions_executed == 3
        if mode == "complete":
            assert report.evidence["completed_training_battles"] == 9
            assert "evolution_partial" not in report.evidence
            assert reader.boxes.boxes[0].species_ids == (source_id,)
        else:
            assert report.evidence["completed_training_battles"] == 12
            assert report.evidence["evolution_partial"] is True
    assert progress["actions"] == progress["calls"]
    assert retained == ([1, 2, 3] if mode in {"complete", "bounded"} else [])


@pytest.mark.parametrize("limit", [0, 129, True, 1.0])
def test_complete_option_rejects_invalid_quantum_bounds(tmp_path, limit):
    runtime, _, _ = runtime_fixture(tmp_path)
    with pytest.raises(ValueError, match="quantum limit"):
        native_module.bind_native_boxed_evolution(runtime, object(), maximum_quanta=limit)
