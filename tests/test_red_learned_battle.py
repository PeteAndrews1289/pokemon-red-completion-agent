import json
from dataclasses import replace

import pytest
from test_red_battle_scenario import Reader, _raw

import pokemon_red_completion.red_learned_battle as runtime
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleTurnExecution
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder


class LiveReader(Reader):
    def __init__(self):
        self.raw = replace(
            _raw(),
            active_party_moves=(33, 0, 5, 55),
            active_party_pp=(35, 0, 20, 25),
        )
        self.phase = BattleMenuPhase.MAIN

    def read(self):
        return self.raw

    def read_battle_menu_state(self, raw):
        return BattleMenuState(self.phase, selected_main_command=0)


class Executor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


class Ranker:
    def __init__(self, reader, output, choices):
        self.output = output
        self.choices = iter(choices)
        self.calls = []
        self.feature_names = prepare_red_battle_scenario(
            PokemonRedObservationEncoder(reader),
            reader.raw,
        ).features.feature_names

    def to_json(self):
        return '{"frozen": true}'

    def predict(self, vectors, *, legal_mask, current_pp):
        assert (self.output / f"step-{len(self.calls):03d}" / "query-started.json").exists()
        self.calls.append((vectors, current_pp))
        return next(self.choices)


def harness(tmp_path, monkeypatch, *, choices=(1,), fail_execution=False):
    reader, executor = LiveReader(), Executor()
    output = tmp_path / "run"
    model = Ranker(reader, output, choices)
    played = []

    def execute(_reader, _executor, *, selected_slot, **kwargs):
        index = len(played)
        saved = json.loads((output / f"step-{index:03d}" / "execution-started.json").read_text())
        assert saved["selected_slot"] == selected_slot
        played.append(selected_slot)
        before = reader.raw
        pp = list(before.battler_pp)
        pp[selected_slot - 1] -= 1
        reader.raw = replace(
            before,
            enemy_hp=max(0, before.enemy_hp - 30),
            active_party_pp=tuple(pp),
            battle_state=0 if before.enemy_hp == 30 else 1,
        )
        if fail_execution:
            raise RuntimeError("injected partial execution failure")
        return BattleTurnExecution(before, reader.raw, selected_slot, 2, 48, True)

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", execute)
    args = dict(
        output=output,
        reader=reader,
        executor=executor,
        encoder=PokemonRedObservationEncoder(reader),
        model=model,
        snapshot=lambda: repr(reader.raw).encode(),
        costs=lambda: {"actions": len(executor.actions)},
        setup=lambda: None,
        provenance={"partition": "correlated_development"},
        expected_map=reader.raw.map_id,
    )
    return args, reader, model, played


def test_real_candidate_slot_mapping_and_fresh_observation_each_turn(tmp_path, monkeypatch):
    args, reader, model, played = harness(tmp_path, monkeypatch, choices=(1, 0))
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "battle_exited"
    assert played == [3, 1]  # The second candidate is not physical slot two.
    assert result["model_queries"] == 2
    assert model.calls[0] != model.calls[1]
    assert result["teacher_battle_fallbacks"] == 0
    assert (args["output"] / "terminal.state").read_bytes() == repr(reader.raw).encode()
    choices = [row["choice"] for row in result["decisions"]]
    assert choices[0]["observation_sha256"] != choices[1]["observation_sha256"]


def test_no_alternatives_never_queries_or_attacks(tmp_path, monkeypatch):
    args, reader, model, played = harness(tmp_path, monkeypatch)
    reader.raw = replace(reader.raw, active_party_pp=(35, 0, 0, 0))
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "no_alternatives"
    assert not model.calls and not played


@pytest.mark.parametrize("candidate", [-1, 3, True])
def test_bad_prediction_is_retained_but_never_executed(tmp_path, monkeypatch, candidate):
    args, _, _, played = harness(tmp_path, monkeypatch, choices=(candidate,))
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "failed" and not played
    assert json.loads((args["output"] / "step-000/prediction.json").read_text()) == {
        "candidate_index": candidate,
    }


def test_choice_storage_failure_prevents_attack_and_retains_terminal(tmp_path, monkeypatch):
    args, _, _, played = harness(tmp_path, monkeypatch)
    original = runtime._record

    def record(path, value):
        if path.name == "execution-started.json":
            raise OSError("choice storage unavailable")
        original(path, value)

    monkeypatch.setattr(runtime, "_record", record)
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "failed" and not played
    assert (args["output"] / "terminal.state").exists()


def test_partial_failure_retains_actual_state_and_never_retries(tmp_path, monkeypatch):
    args, reader, _, played = harness(tmp_path, monkeypatch, fail_execution=True)
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "failed" and played == [3]
    assert reader.raw.enemy_hp == 30
    assert (args["output"] / "terminal.state").read_bytes() == repr(reader.raw).encode()
    with pytest.raises(FileExistsError):
        runtime.run_learned_battle(**args)
    assert played == [3]


def test_setup_failure_retained_without_model_query(tmp_path, monkeypatch):
    args, _, model, _ = harness(tmp_path, monkeypatch)

    def setup():
        raise RuntimeError("encounter bound exhausted")

    args["setup"] = setup
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "failed" and not model.calls
    assert (args["output"] / "terminal.state").exists()


def test_stale_state_after_query_cannot_execute(tmp_path, monkeypatch):
    args, reader, model, played = harness(tmp_path, monkeypatch)
    original = model.predict

    def predict(*pos, **kw):
        answer = original(*pos, **kw)
        reader.raw = replace(reader.raw, enemy_hp=20)
        return answer

    monkeypatch.setattr(model, "predict", predict)
    result = runtime.run_learned_battle(**args)
    assert result["stop_reason"] == "failed" and not played


def test_decision_cap_stops_an_active_battle(tmp_path, monkeypatch):
    args, _, _, played = harness(tmp_path, monkeypatch)
    result = runtime.run_learned_battle(**args, maximum_decisions=1)
    assert result["stop_reason"] == "decision_limit" and played == [3]
    assert result["terminal_facts"]["battle_state"] == 1


@pytest.mark.parametrize("failure", ["faint", "move_menu", "changed_pp"])
def test_settling_never_selects_an_unowned_move_or_switch(failure):
    reader, executor = LiveReader(), Executor()
    if failure == "faint":
        reader.raw = replace(reader.raw, active_party_hp=0)
    elif failure == "move_menu":
        reader.phase = BattleMenuPhase.MOVE
    else:

        def mutate(action):
            executor.actions.append(action)
            reader.raw = replace(reader.raw, active_party_pp=(34, 0, 20, 25))

        executor.execute = mutate
    with pytest.raises(RuntimeError):
        runtime.settle_learned_battle_boundary(
            reader,
            executor,
            expected_map=reader.raw.map_id,
        )
    assert all(
        action.kind in {MacroActionKind.CANCEL, MacroActionKind.WAIT} for action in executor.actions
    )
