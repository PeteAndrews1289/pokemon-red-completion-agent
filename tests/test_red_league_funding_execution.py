from __future__ import annotations

from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_league_funding_execution as execution
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FlyReceipt
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.red_league_funding import (
    RedLeagueBattleQuote,
    RedLeagueFundingQualification,
    RedLeagueSupplyPlan,
)


class _Delegate:
    def execute(self, _action):
        return None


class _Emulator:
    def __init__(self):
        self.frame_count = 0
        self.pressed_buttons = set()

    def press(self, button):
        self.pressed_buttons.add(button)

    def release(self, button):
        self.pressed_buttons.discard(button)

    def tick(self, frames):
        self.frame_count += frames


def _qualification() -> RedLeagueFundingQualification:
    return RedLeagueFundingQualification(
        exit_plan=SimpleNamespace(steps=("out",)),
        fly_town=9,
        fly_landing=(6, 9),
        supply=RedLeagueSupplyPlan(
            route=SimpleNamespace(steps=("shop",)),
            sales=(),
            full_restores_purchased=0,
        ),
        entry_plan=SimpleNamespace(steps=("in", "up")),
        battles=tuple(
            RedLeagueBattleQuote(objective, 201, index, payout, 50 + index)
            for index, (objective, payout) in enumerate(
                (
                    ("defeat_lorelei", 100),
                    ("defeat_bruno", 200),
                    ("defeat_agatha", 300),
                    ("defeat_lance", 400),
                    ("defeat_champion", 500),
                ),
                start=1,
            )
        ),
        supported_attack_pp=50,
        opponent_attack_demands=26,
    )


def _runtime():
    flags = bytearray(320)
    for flag in (
        EventFlag.BEAT_LORELEI,
        EventFlag.BEAT_BRUNO,
        EventFlag.BEAT_AGATHA,
        EventFlag.BEAT_LANCES_ROOM_TRAINER,
        EventFlag.BEAT_LANCE,
        EventFlag.BEAT_CHAMPION_RIVAL,
    ):
        flags[int(flag) // 8] |= 1 << (int(flag) % 8)
    raw = SimpleNamespace(
        map_id=89,
        player_money=500,
        bag_items=((1, 2),),
        badge_bits=255,
        party_species_ids=(28, 64),
        party_hp=(200, 180),
        party_pp=((10, 10, 10, 10), (10, 10, 10, 10)),
        party_status=(0, 0),
        event_flags=bytes(flags),
        player_y=3,
        player_x=3,
        battle_state=0,
    )
    observed = SimpleNamespace(
        raw=raw,
        input_ready=True,
        game_state=SimpleNamespace(facts=frozenset()),
        collection_observation=SimpleNamespace(),
    )
    return SimpleNamespace(
        adapter=SimpleNamespace(observe=lambda: observed),
        reader=SimpleNamespace(read=lambda: raw),
        emulator=_Emulator(),
    ), observed


def _binding(runtime, qualification):
    return execution.RedLeagueFundingExecutionBinding(
        runtime.adapter.observe(), qualification,
    )


def _actions(runtime):
    return CountingExecutor(FrameSafeExecutor(runtime.emulator))


def _route_success(observed, qualification):
    def route(plan, *args, **kwargs):
        if plan is qualification.supply.route:
            observed.raw.map_id = 174
            observed.raw.player_y, observed.raw.player_x = (5, 2)
        return SimpleNamespace(passed=True)

    return route


@pytest.fixture(autouse=True)
def _scripted_arrival(monkeypatch):
    monkeypatch.setattr(
        execution, "trainer_room_arrival", lambda *args: SimpleNamespace(steps=6),
    )


def test_execution_composes_five_quoted_battles_without_training(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    actions = _actions(runtime)
    world = SimpleNamespace(rom=b"rom", replanner=lambda: object())
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    routes = []

    def route(plan, *args, **kwargs):
        routes.append((plan, kwargs.get("limits")))
        if plan is qualification.supply.route:
            observed.raw.map_id = 174
            observed.raw.player_y, observed.raw.player_x = (5, 2)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(execution, "execute_route", route)
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())

    class Port:
        def __init__(self, *args):
            pass

        def execute(self, action):
            observed.raw.map_id = 9
            observed.raw.player_y, observed.raw.player_x = qualification.fly_landing
            return Gen1FlyReceipt(5, 9, 0, 0, (9,))

    monkeypatch.setattr(execution, "Gen1FieldMovePort", Port)
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))
    monkeypatch.setattr(
        execution,
        "CompletionReferee",
        lambda: SimpleNamespace(inspect=lambda state: SimpleNamespace(complete=True)),
    )

    def run_battle(runtime, actions, world, objective_id, expected_money, *policy):
        before = runtime.adapter.observe().raw.player_money
        runtime.adapter.observe().raw.player_money += expected_money
        if objective_id == "defeat_champion":
            runtime.adapter.observe().raw.party_species_ids = (64, 28)
        return execution.RedLeagueFundingBattleResult(
            objective_id, before, before + expected_money, expected_money, 0, 0
        )

    monkeypatch.setattr(execution, "_run_battle", run_battle)
    result = execution.execute_red_league_funding(
        runtime, actions, world, _binding(runtime, qualification),
    )
    assert result.observed_gross_income == 1_500
    assert result.public_dict()["training_examples"] == 0
    assert result.public_dict()["postgame_reset_proven"] is False
    assert [row.objective_id for row in result.battles] == [
        quote.objective_id for quote in qualification.battles
    ]
    assert routes[0] == (qualification.exit_plan, None)
    assert routes[1] == (qualification.supply.route, None)
    assert routes[2][0] is qualification.entry_plan
    assert routes[2][1].transition_settle_frames >= 6 * 24 + 120


def test_execution_attaches_partial_progress_after_irreversible_battles(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    actions = _actions(runtime)
    world = SimpleNamespace(rom=b"rom", replanner=lambda: object())
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    monkeypatch.setattr(
        execution, "execute_route", _route_success(observed, qualification),
    )
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())

    class Port:
        def __init__(self, *args):
            pass

        def execute(self, action):
            observed.raw.map_id = 9
            observed.raw.player_y, observed.raw.player_x = qualification.fly_landing
            return Gen1FlyReceipt(5, 9, 0, 0, (9,))

    monkeypatch.setattr(execution, "Gen1FieldMovePort", Port)
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))

    calls = 0

    def run_battle(runtime, actions, world, objective_id, expected_money, *policy):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("observed battle failure")
        before = runtime.adapter.observe().raw.player_money
        runtime.adapter.observe().raw.player_money += expected_money
        return execution.RedLeagueFundingBattleResult(
            objective_id, before, before + expected_money, expected_money, 0, 0
        )

    monkeypatch.setattr(execution, "_run_battle", run_battle)
    with pytest.raises(execution.RedLeagueFundingExecutionError) as caught:
        execution.execute_red_league_funding(
            runtime, actions, world, _binding(runtime, qualification),
        )
    assert caught.value.reason == "defeat_agatha failed"
    assert caught.value.progress is not None
    assert caught.value.progress.phase == "battle:defeat_agatha"
    assert caught.value.progress.observed_money == 800
    assert [row.objective_id for row in caught.value.progress.completed_battles] == [
        "defeat_lorelei",
        "defeat_bruno",
    ]
    assert caught.value.progress.public_dict()["retry_authorized"] is False


def test_execution_requalifies_before_any_input(monkeypatch):
    qualification = _qualification()
    runtime, _ = _runtime()
    actions = _actions(runtime)
    changed = RedLeagueFundingQualification(
        qualification.exit_plan,
        8,
        qualification.fly_landing,
        qualification.supply,
        qualification.entry_plan,
        qualification.battles,
        qualification.supported_attack_pp,
        qualification.opponent_attack_demands,
    )
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: changed)
    with pytest.raises(execution.RedLeagueFundingExecutionError, match="changed before input"):
        execution.execute_red_league_funding(
            runtime,
            actions,
            SimpleNamespace(rom=b"rom"),
            _binding(runtime, qualification),
        )
    assert actions.actions_executed == 0


def test_exact_binding_is_action_free_and_changed_origin_is_consumed(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    actions = _actions(runtime)
    world = SimpleNamespace(rom=b"rom")
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    binding = execution.bind_red_league_funding_execution(
        runtime, world, expected_qualification=qualification,
    )
    assert not binding.claimed
    assert actions.actions_executed == runtime.emulator.frame_count == 0
    changed_raw = SimpleNamespace(**vars(observed.raw))
    changed_raw.player_money += 1
    runtime.adapter.observe = lambda: SimpleNamespace(
        raw=changed_raw,
        game_state=observed.game_state,
        collection_observation=observed.collection_observation,
    )
    with pytest.raises(execution.RedLeagueFundingExecutionError, match="exact origin"):
        execution.execute_red_league_funding(runtime, actions, world, binding)
    assert binding.claimed
    assert actions.actions_executed == runtime.emulator.frame_count == 0
    with pytest.raises(execution.RedLeagueFundingExecutionError, match="already claimed"):
        execution.execute_red_league_funding(runtime, actions, world, binding)


def test_execution_allows_historical_facts_when_current_cycle_requalifies(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    observed.game_state.facts = frozenset({"league:lorelei_defeated"})
    actions = _actions(runtime)
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    monkeypatch.setattr(execution, "execute_route", _route_success(observed, qualification))
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))
    monkeypatch.setattr(
        execution,
        "CompletionReferee",
        lambda: SimpleNamespace(inspect=lambda state: SimpleNamespace(complete=True)),
    )

    class Port:
        def __init__(self, *args):
            pass

        def execute(self, action):
            observed.raw.player_y, observed.raw.player_x = qualification.fly_landing
            return Gen1FlyReceipt(5, 9, 0, 0, (9,))

    monkeypatch.setattr(execution, "Gen1FieldMovePort", Port)

    def run_battle(runtime, actions, world, objective_id, expected_money, *policy):
        before = runtime.adapter.observe().raw.player_money
        runtime.adapter.observe().raw.player_money += expected_money
        return execution.RedLeagueFundingBattleResult(
            objective_id, before, before + expected_money, expected_money, 0, 0
        )

    monkeypatch.setattr(execution, "_run_battle", run_battle)
    result = execution.execute_red_league_funding(
        runtime,
        actions,
        SimpleNamespace(rom=b"rom", replanner=lambda: object()),
        _binding(runtime, qualification),
    )
    assert result.observed_gross_income == 1_500


@pytest.mark.parametrize("objective", ["defeat_lorelei", "defeat_champion"])
def test_run_battle_always_uses_current_cycle_rematch_mode(monkeypatch, objective):
    runtime, _ = _runtime()
    actions = CountingExecutor(_Delegate())
    seen = []

    class Skill:
        def __init__(self, *args, **kwargs):
            seen.append(kwargs)

        def availability(self, state):
            return SimpleNamespace(executable=True)

        def execute(self):
            runtime.adapter.observe().raw.player_money += 100
            return SimpleNamespace(
                actions_executed=0,
                frames_executed=0,
                evidence={"bag_items_spent": 0},
            )

    if objective == "defeat_champion":
        monkeypatch.setattr(execution, "RedCartridgeChampionSkill", Skill)
    else:
        monkeypatch.setattr(execution, "RedCartridgeLoreleiSkill", Skill)
    execution._run_battle(
        runtime, actions, object(), objective, 100, "damage-bounded-zero-item", 0,
    )
    expected = {
        "recovery_controller": "damage-bounded-zero-item",
        "maximum_full_restores": 0,
        "rematch": True,
    }
    if objective != "defeat_champion":
        expected["objective_id"] = "defeat_lorelei"
    assert seen == [expected]


def test_frame_boundary_failure_retains_structured_progress(monkeypatch):
    qualification = _qualification()
    runtime, _ = _runtime()

    actions = _actions(runtime)
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))

    def route(plan, bounded, *args, **kwargs):
        bounded.execute(execution.MacroAction(execution.MacroActionKind.WAIT, repeat=6))
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(execution, "execute_route", route)
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())
    with pytest.raises(execution.RedLeagueFundingExecutionError) as caught:
        execution.execute_red_league_funding(
            runtime,
            actions,
            SimpleNamespace(rom=b"rom", replanner=lambda: object()),
            _binding(runtime, qualification),
            maximum_frames=5,
        )
    assert caught.value.progress is not None
    assert caught.value.progress.phase == "center_exit"
    assert caught.value.progress.frames == 0
    assert caught.value.progress.actions_attempted == 1
    assert caught.value.progress.completed_battles == ()


def test_progress_survives_a_reader_failure_while_reporting_the_original_fault(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    actions = _actions(runtime)
    world = SimpleNamespace(rom=b"rom", replanner=lambda: object())
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    monkeypatch.setattr(execution, "execute_route", _route_success(observed, qualification))
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))

    class Port:
        def __init__(self, *args):
            pass

        def execute(self, action):
            observed.raw.player_y, observed.raw.player_x = qualification.fly_landing
            return Gen1FlyReceipt(5, 9, 0, 0, (9,))

    monkeypatch.setattr(execution, "Gen1FieldMovePort", Port)
    def lost_battle(*args):
        runtime.reader.read = lambda: (_ for _ in ()).throw(OSError("reader unavailable"))
        raise RuntimeError("lost")

    monkeypatch.setattr(execution, "_run_battle", lost_battle)
    with pytest.raises(execution.RedLeagueFundingExecutionError) as caught:
        execution.execute_red_league_funding(
            runtime, actions, world, _binding(runtime, qualification),
        )
    assert caught.value.reason == "defeat_lorelei failed"
    assert caught.value.progress is not None
    assert caught.value.progress.phase == "battle:defeat_lorelei"
    assert caught.value.progress.observed_money == 500


def test_terminal_observation_failure_retains_all_five_completed_battles(monkeypatch):
    qualification = _qualification()
    runtime, observed = _runtime()
    actions = _actions(runtime)
    world = SimpleNamespace(rom=b"rom", replanner=lambda: object())
    monkeypatch.setattr(execution, "qualify_red_league_funding", lambda *args: qualification)
    monkeypatch.setattr(execution, "execute_route", _route_success(observed, qualification))
    monkeypatch.setattr(execution, "Gen1TraversalObserver", lambda *args: object())
    monkeypatch.setattr(execution, "dependency_specimen_ledger", lambda *args: ("same",))

    class Port:
        def __init__(self, *args):
            pass

        def execute(self, action):
            observed.raw.player_y, observed.raw.player_x = qualification.fly_landing
            return Gen1FlyReceipt(5, 9, 0, 0, (9,))

    monkeypatch.setattr(execution, "Gen1FieldMovePort", Port)
    calls = 0

    def battle(runtime, actions, world, objective_id, expected_money, *policy):
        nonlocal calls
        calls += 1
        before = observed.raw.player_money
        observed.raw.player_money += expected_money
        if calls == 5:
            runtime.adapter.observe = lambda: (_ for _ in ()).throw(OSError("terminal lost"))
        return execution.RedLeagueFundingBattleResult(
            objective_id, before, before + expected_money, expected_money, 0, 0
        )

    monkeypatch.setattr(execution, "_run_battle", battle)
    with pytest.raises(execution.RedLeagueFundingExecutionError) as caught:
        execution.execute_red_league_funding(
            runtime, actions, world, _binding(runtime, qualification),
        )
    assert caught.value.progress is not None
    assert caught.value.progress.phase == "terminal"
    assert len(caught.value.progress.completed_battles) == 5
    assert caught.value.progress.observed_money == 2_000


def test_execution_rejects_invalid_hard_bounds_before_input():
    qualification = _qualification()
    runtime, _ = _runtime()
    actions = CountingExecutor(_Delegate())
    with pytest.raises(ValueError, match="maximum_actions"):
        execution.execute_red_league_funding(
            runtime,
            actions,
            SimpleNamespace(rom=b"rom"),
            _binding(runtime, qualification),
            maximum_actions=0,
        )
    assert actions.actions_executed == 0
