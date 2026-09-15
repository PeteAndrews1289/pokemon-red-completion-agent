from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_battle_contingency as contingency
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError,
    BattleRuntimeTimeoutError,
    BattleRuntimeTiming,
    bind_battle_policy_override,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.cartridge_qualification import (
    QualificationCampaign,
    QualificationLimits,
    run_qualification_case,
)
from pokemon_red_completion.executor import ControllerTiming
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.private_artifacts import initialize_private_root


def raw_state(**changes):
    return replace(RawGameState(
        game_started=True, map_id=22, player_x=4, player_y=8, battle_state=1,
        party_count=2, party_species_ids=(0x3B, 0xB1), party_levels=(25, 25),
        party_hp=(44, 60), party_max_hp=(60, 70), party_status=(0, 0),
        party_moves=((89, 45, 91, 28), (55, 33, 0, 0)),
        party_pp=((10, 0, 0, 0), (20, 20, 0, 0)),
        active_party_index=0, active_party_hp=44, active_party_max_hp=60,
        active_party_status=0, active_party_moves=(89, 45, 91, 28),
        active_party_pp=(10, 0, 0, 0), enemy_species_id=0x24,
        enemy_level=20, enemy_hp=34, enemy_max_hp=34, bag_items=(),
        player_attack_stage=7, player_accuracy_stage=7, enemy_defense_stage=7,
    ), **changes)


class Simulation:
    """Exercise real shared turn and switch executors using synthetic menu responses."""

    def __init__(self, raw=None, *, damage=0, reserve_damage=34):
        self.raw = raw or raw_state()
        self.damage = damage
        self.reserve_damage = reserve_damage
        self.stage = "main"
        self.command = 0
        self.cursor = 0
        self.slot = 1
        self.actions = []
        self.frame_count = 0
        self.buttons = set()
        self.pending_button = None
        self.partial_switch = False

    def read(self):
        return self.raw

    def read_battle_menu_state(self, raw):
        if self.stage == "main":
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=self.command)
        if self.stage == "move":
            return BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=self.slot)
        return BattleMenuState(BattleMenuPhase.UNKNOWN)

    def read_input_readiness(self):
        return InputReadiness(0, 0, 0, 0, 0, 0)

    def read_u8(self, address):
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        if address == RamAddress.PARTY_COUNT:
            return self.raw.party_count
        for index, hp in enumerate(self.raw.party_hp):
            base = int(RamAddress.PARTY_MON_1_HP) + index * 44
            if address == base:
                return hp >> 8
            if address == base + 1:
                return hp & 255
        raise AssertionError(f"unexpected read {address}")

    def press(self, button):
        self.buttons.add(button)
        self.pending_button = button

    def release(self, button):
        self.buttons.remove(button)

    def tick(self, frames):
        if self.partial_switch and self.stage == "switching":
            self.frame_count += 1
            raise OSError("partial switch tick")
        self.frame_count += frames
        button, self.pending_button = self.pending_button, None
        if button:
            if button in ("a", "b"):
                self.execute(MacroAction(
                    MacroActionKind.CONFIRM if button == "a" else MacroActionKind.CANCEL,
                ))
            else:
                self.execute(MacroAction(MacroActionKind.MOVE, button))
        else:
            self.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))

    def execute(self, action):
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            if self.stage == "switching":
                index = 1
                self.raw = replace(
                    self.raw, active_party_index=index,
                    active_party_hp=self.raw.party_hp[index],
                    active_party_max_hp=self.raw.party_max_hp[index],
                    active_party_status=self.raw.party_status[index],
                    active_party_moves=self.raw.party_moves[index],
                    active_party_pp=self.raw.party_pp[index],
                )
                self.stage, self.command = "main", 0
            return
        if action.kind is MacroActionKind.MOVE:
            if self.stage == "main":
                self.command = 2 if action.value == "right" else 0
            elif self.stage == "party":
                self.cursor += 1 if action.value == "down" else -1
            elif self.stage == "submenu":
                self.cursor = 0
            elif self.stage == "move":
                self.slot += 1 if action.value == "down" else -1
            return
        if action.kind is MacroActionKind.CANCEL:
            if self.stage == "move":
                self.stage, self.command = "main", 0
            return
        assert action.kind is MacroActionKind.CONFIRM
        if self.stage == "after_move":
            self.stage, self.command = "main", 0
        elif self.stage == "main":
            self.stage = "party" if self.command == 2 else "move"
            self.cursor, self.slot = 0, 1
        elif self.stage == "party":
            assert self.cursor == 1
            self.stage, self.cursor = "submenu", 1
        elif self.stage == "submenu":
            assert self.cursor == 0
            self.stage = "switching"
        elif self.stage == "move":
            pp = list(self.raw.battler_pp)
            pp[self.slot - 1] -= 1
            party_pp = list(self.raw.party_pp)
            party_pp[self.raw.active_party_index] = tuple(pp)
            damage = self.damage if self.raw.active_party_index == 0 else self.reserve_damage
            hp = max(0, self.raw.enemy_hp - damage)
            self.raw = replace(self.raw, active_party_pp=tuple(pp), party_pp=tuple(party_pp),
                               enemy_hp=hp, battle_state=1 if hp else 0)
            self.stage = "after_move"


def controller(sim, events=None):
    record = (events if events is not None else []).append
    return contingency.RedBattleContingency(sim, sim, sim, record)


def spend(c, sim, *, delta=1, damage=0, slot=1):
    c._selected(sim.raw, slot)
    pp = list(sim.raw.battler_pp)
    pp[slot - 1] -= delta
    sim.raw = replace(sim.raw, active_party_pp=tuple(pp), enemy_hp=sim.raw.enemy_hp - damage)
    return c._intervene(sim.raw)


@pytest.mark.parametrize("initial_pp", [0, 1, 10, 74])
def test_real_turn_and_switch_runtime_settles_with_one_bounded_switch(initial_pp):
    sim = Simulation(raw_state(active_party_pp=(initial_pp, 0, 0, 0)))
    events = []
    c = controller(sim, events)
    final = c.run(lambda raw: 1, expected_map=22)
    assert final.battle_state == 0
    assert c.switches_claimed == c.switches_completed == 1
    assert events[0]["reason"] == ("no_hp_progress" if initial_pp & 63 > 4 else "no_usable_pp")
    assert [e["event"] for e in events] == [
        "contingency_needed", "switch_claimed", "switch_completed",
    ]
    assert final.active_party_index == 1
    assert len(sim.actions) < 100
    with pytest.raises(contingency.BattleContingencyError, match="already consumed"):
        c.run(lambda raw: 1, expected_map=22)


def test_productive_battle_never_switches():
    sim = Simulation(damage=10)
    c = controller(sim)
    assert c.run(lambda raw: 1, expected_map=22).battle_state == 0
    assert c.switches_claimed == 0


def test_no_pp_spend_never_counts_as_a_stall_and_hp_decrease_resets():
    sim = Simulation()
    c = controller(sim)
    assert not c._intervene(sim.raw)
    for _ in range(20):
        assert not spend(c, sim, delta=0)
    assert c.stalled_turns == 0
    for _ in range(3):
        assert not spend(c, sim)
    assert c.stalled_turns == 3
    assert not spend(c, sim, damage=1)
    assert c.stalled_turns == 0


def test_second_stall_stops_without_a_second_switch_or_move():
    sim = Simulation(reserve_damage=0)
    events = []
    c = controller(sim, events)
    with pytest.raises(contingency.BattleContingencyError, match="budget exhausted"):
        c.run(lambda raw: 1, expected_map=22)
    assert c.switches_claimed == c.switches_completed == 1
    assert sim.raw.battler_pp[0] == 16  # Four reserve attacks, no fifth selection.
    assert events[-1]["reason"] == "no_hp_progress"


@pytest.mark.parametrize("changes", [
    {"party_hp": (44, 0)}, {"party_status": (0, 8)},
    {"party_levels": (25, 1)}, {"party_pp": ((10, 0, 0, 0), (0, 0, 0, 0))},
    {"party_moves": ((89, 45, 91, 28), (89, 91, 0, 0))},  # Immune ground attacks.
    {"party_moves": ((89, 45, 91, 28), (45, 28, 0, 0))},  # Status-only reserve.
    {"party_moves": ((89, 45, 91, 28), (120, 153, 0, 0))},  # Sacrificial moves.
])
def test_ineligible_reserves_fail_before_switch_input(changes):
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0), **changes))
    c = controller(sim)
    with pytest.raises(contingency.BattleContingencyError, match="no eligible"):
        c.run(lambda raw: 1, expected_map=22)
    assert sim.actions == [] and c.switches_claimed == 0


@pytest.mark.parametrize("changes,match", [
    ({"active_party_moves": (55, 33, 0, 0)}, "replacement"),
    ({"active_party_index": 1}, "replacement"),
    ({"active_party_pp": (8, 0, 0, 0)}, "PP transition"),
    ({"enemy_species_id": 0xA5}, "encounter changed"),
    ({"map_id": 6}, "encounter changed"),
    ({"bag_items": ((1, 2),)}, "spend items"),
])
def test_unqualified_transitions_stop(changes, match):
    sim = Simulation()
    c = controller(sim)
    assert not c._intervene(sim.raw)
    c._selected(sim.raw, 1)
    sim.raw = replace(sim.raw, **changes)
    with pytest.raises(contingency.BattleContingencyError, match=match):
        c._intervene(sim.raw)
    assert sim.actions == []


def test_disabled_only_remaining_move_triggers_switch():
    sim = Simulation(raw_state(player_disabled_move_slot=1, player_disable_turns=2))
    c = controller(sim)
    assert c._intervene(sim.raw)
    assert c.switches_completed == 1


@pytest.mark.parametrize("move", [33, 45, 91])
def test_no_hp_progress_is_a_budget_rule_even_for_misses_or_status_moves(move):
    sim = Simulation(raw_state(active_party_moves=(move, 0, 0, 0)))
    events = []
    c = controller(sim, events)
    assert not c._intervene(sim.raw)
    for _ in range(3):
        assert not spend(c, sim)
    assert spend(c, sim)
    assert events[0]["reason"] == "no_hp_progress"
    assert not any("immune" in str(event) or "miss" in str(event) for event in events)


def test_same_hp_different_enemy_does_not_join_stall_histories():
    sim = Simulation()
    c = controller(sim)
    c._intervene(sim.raw)
    for _ in range(3):
        spend(c, sim)
    sim.raw = replace(sim.raw, enemy_species_id=0xA5)
    with pytest.raises(contingency.BattleContingencyError, match="encounter changed"):
        c._intervene(sim.raw)
    assert c.switches_claimed == 0


@pytest.mark.parametrize("field", ["active_party_hp", "active_party_moves", "active_party_pp"])
def test_missing_active_evidence_never_falls_back_to_first_party(field):
    sim = Simulation(raw_state(
        **{field: None}, first_party_hp=44, first_party_moves=(33, 0, 0, 0),
        first_party_pp=(0, 0, 0, 0),
    ))
    with pytest.raises(contingency.BattleContingencyError, match="observed wild MAIN"):
        controller(sim)._intervene(sim.raw)
    assert sim.actions == []


def test_reserve_ranking_moves_with_party_permutation():
    raw = raw_state(party_count=3, party_species_ids=(0x3B, 0xB1, 0xA5),
                    party_levels=(25, 25, 1), party_hp=(44, 60, 30),
                    party_max_hp=(60, 70, 30), party_status=(0, 0, 0),
                    party_moves=((89, 45, 91, 28), (55, 33, 0, 0), (33, 0, 0, 0)),
                    party_pp=((10, 0, 0, 0), (20, 20, 0, 0), (20, 0, 0, 0)))
    assert contingency._reserve(raw) == 1
    permuted = replace(raw, **{
        name: tuple(getattr(raw, name)[i] for i in (0, 2, 1))
        for name in ("party_species_ids", "party_levels", "party_hp", "party_max_hp",
                     "party_status", "party_moves", "party_pp")
    })
    assert contingency._reserve(permuted) == 2


@pytest.mark.parametrize("change", ["state", "menu", "sink"])
def test_claim_failure_or_stale_state_sends_no_switch_input(change):
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0)))
    events = []
    def record(event):
        events.append(event)
        if event["event"] == "switch_claimed":
            if change == "state":
                sim.raw = replace(sim.raw, active_party_hp=43)
            elif change == "menu":
                sim.stage = "party"
            else:
                raise OSError("storage failure")
    c = contingency.RedBattleContingency(sim, sim, sim, record)
    with pytest.raises((contingency.BattleContingencyError, OSError)):
        c.run(lambda raw: 1, expected_map=22)
    assert c.switches_claimed == 1 and c.switches_completed == 0
    assert sim.actions == []


@pytest.mark.parametrize("change", ["wrong_target", "dead_target", "unknown_menu", "item"])
def test_unsettled_switch_never_records_completion(monkeypatch, change):
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0)))
    events = []
    c = controller(sim, events)
    def faulty_switch(*args, **kwargs):
        sim.raw = replace(sim.raw, active_party_index=1, active_party_hp=60,
                          active_party_moves=(55, 33, 0, 0), active_party_pp=(20, 20, 0, 0))
        if change == "wrong_target":
            sim.raw = replace(sim.raw, active_party_index=0)
        elif change == "dead_target":
            sim.raw = replace(sim.raw, active_party_hp=0)
        elif change == "unknown_menu":
            sim.stage = "party"
        else:
            sim.raw = replace(sim.raw, bag_items=((1, 1),))
    monkeypatch.setattr(contingency, "switch_active_battler", faulty_switch)
    with pytest.raises(contingency.BattleContingencyError):
        c.run(lambda raw: 1, expected_map=22)
    assert c.switches_claimed == 1 and c.switches_completed == 0
    assert events[-1]["event"] == "switch_claimed"


def test_intervention_shares_the_existing_runtime_pulse_limit():
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0)))
    c = controller(sim)
    with pytest.raises(BattleRuntimeTimeoutError):
        c.run(lambda raw: pytest.fail("no attack budget left"), expected_map=22,
              timing=BattleRuntimeTiming(max_runtime_pulses=1))
    assert c.switches_completed == 1


def test_learned_override_is_refused_before_input():
    sim = Simulation()
    class Policy:
        def choose_move(self, observation, fallback):
            pytest.fail("learner must not be queried")
    with (bind_battle_policy_override(Policy()),
          pytest.raises(contingency.BattleContingencyError, match="learned actor")):
        controller(sim).run(lambda raw: 1, expected_map=22)
    assert sim.actions == []


@pytest.mark.parametrize("value", [1, None, "yes"])
def test_shared_runtime_refuses_nonboolean_intervention_results(value):
    sim = Simulation()
    with pytest.raises(BattleRuntimeError, match="boolean"):
        run_adaptive_wild_battle(sim, sim, lambda raw: 1, expected_map=22,
                                main_menu_intervention=lambda raw: value)
    assert sim.actions == []


@pytest.mark.parametrize("partial", [False, True])
def test_real_switch_and_shared_runtime_reopen_inside_journal(tmp_path, partial):
    root, repo = tmp_path / "private", tmp_path / "repo"
    root.mkdir()
    repo.mkdir()
    store = initialize_private_root(root, repository_root=repo, allow_same_device=True)
    limits = QualificationLimits(200, 200000)
    budget = QualificationCampaign(limits, maximum_cases=1)
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0)))
    sim.partial_switch = partial
    def execute(journal):
        journal.enter_phase("battle")
        executor = journal.executor(sim, ControllerTiming(press_frames=2, release_frames=1))
        c = contingency.RedBattleContingency(
            sim, sim, executor, lambda event: journal.append("contingencies", event),
        )
        final = c.run(lambda raw: 1, expected_map=22)
        assert final.battle_state == 0
        journal.enter_phase("terminal")
        return {"status": "settled", "switches": c.switches_completed}
    if partial:
        with pytest.raises(OSError, match="partial switch tick"):
            run_qualification_case(store, "switch", {}, limits=limits,
                                   campaign=budget, execute=execute)
        evidence = store.read_failed_episode_diagnostic("switch").failure_diagnostic
        assert evidence["diagnostic"]["phase"] == "contingency_switch"
        assert evidence["cost_known"] is True
        assert evidence["emulator_frames"] == sim.frame_count
        assert evidence["actions_attempted"] == evidence["actions_completed"] + 1
        assert budget.closed and not sim.buttons
        events = list(store.open_failed_episode("switch").iter_stream("contingencies"))
        assert events[-1]["event"] == "switch_claimed"
    else:
        result = run_qualification_case(store, "switch", {}, limits=limits,
                                        campaign=budget, execute=execute)
        assert result["emulator_frames"] == sim.frame_count > 0
        assert result["actions_attempted"] == result["actions_completed"] > 0
        events = list(store.open_episode("switch").iter_stream("contingencies"))
        assert events[-1]["event"] == "switch_completed"


def test_integrated_qualification_records_new_policy_and_real_switch(tmp_path, monkeypatch):
    from test_red_repeatable_battle_scenario_runtime import (
        MATERIALIZER_COMMIT,
        STATE_BYTES,
        _assignment,
        _source,
    )

    import pokemon_red_completion.red_battle_cartridge_qualification as qualification
    root, repo = tmp_path / "private", tmp_path / "repo"
    root.mkdir()
    repo.mkdir()
    store = initialize_private_root(root, repository_root=repo, allow_same_device=True)
    sim = Simulation(raw_state(active_party_pp=(0, 0, 0, 0)))
    sim.load_state_bytes = lambda _: None
    @contextmanager
    def factory():
        yield sim
    def materialize(*args, phase_observer, **kwargs):
        for phase in ("source_inspection", "relocation", "encounter_setup"):
            phase_observer(phase)
        return SimpleNamespace(state_bytes=b"synthetic", expected_map=22)
    monkeypatch.setattr(qualification, "materialize_repeatable_red_battle_scenario", materialize)
    monkeypatch.setattr(qualification, "PokemonRedStateReader", lambda session: sim)
    monkeypatch.setattr(qualification, "strongest_usable_move_slot", lambda raw: 1)
    limits = QualificationLimits(200, 200000)
    result = qualification.qualify_repeatable_red_wild_battle(
        store, "integrated-switch", _source(), _assignment(_source()), STATE_BYTES,
        rom_bytes=b"synthetic", materializer_source_commit=MATERIALIZER_COMMIT,
        session_factory=factory, limits=limits,
        campaign=QualificationCampaign(limits, maximum_cases=1),
        policy=contingency.CONTINGENCY_POLICY,
    )
    assert result["emulator_frames"] == sim.frame_count > 0
    reader = store.open_episode("integrated-switch")
    assignment = list(reader.iter_stream("assignment"))[0]
    assert assignment["policy"] == contingency.CONTINGENCY_POLICY
    assert list(reader.iter_stream("contingencies"))[-1]["event"] == "switch_completed"
    selections = list(reader.iter_stream("selections"))
    assert len(selections) == 1 and selections[0]["active_party_index"] == 1
