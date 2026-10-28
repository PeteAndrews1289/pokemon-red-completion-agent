from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.surge as surge
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import BattleMenuPhase, ItemId, RawGameState
from pokemon_red_completion.red_one_off_capture import OneOffCapturePaused, OneOffCaptureRequest


class Sim:
    def __init__(self, monkeypatch, *, balls=3, capture=True):
        self.raw = RawGameState(
            True,
            83,
            4,
            10,
            1,
            1,
            party_species_ids=(28,),
            party_pp=((15, 10, 15, 25),),
            player_money=30620,
            enemy_species_id=75,
            enemy_level=50,
            enemy_hp=150,
            enemy_max_hp=150,
            active_party_hp=206,
            active_party_max_hp=206,
        )
        self.bag = {ItemId.GREAT_BALL: balls, ItemId.MASTER_BALL: 1, ItemId.FULL_HEAL: 1}
        self.owned = frozenset({9})
        self.box = []
        self.phase = BattleMenuPhase.MAIN
        self.ready = False
        self.capture = capture
        self.ball = None
        self.spends = 0
        self.commands = []
        self.after_throw = lambda: None
        self.executor = CountingExecutor(self)
        monkeypatch.setattr(surge, "_bag", lambda _: self.bag)
        monkeypatch.setattr(
            surge, "_navigate_main", lambda _e, _r, target: self.commands.append(target)
        )
        monkeypatch.setattr(surge, "_select_bag_item", self.select)
        monkeypatch.setattr(surge, "_flee", lambda *_: pytest.fail("Run must never be called"))

    def select(self, _em, _ex, ball):
        self.ball = ball

    def execute(self, action):
        if action.kind is MacroActionKind.CONFIRM and self.ball is not None:
            self.bag[self.ball] -= 1
            self.ball = None
            self.spends += 1
            if self.capture:
                if self.raw.party_count < 6:
                    self.raw = replace(
                        self.raw,
                        battle_state=0,
                        party_count=self.raw.party_count + 1,
                        party_species_ids=self.raw.party_species_ids + (75,),
                        party_pp=self.raw.party_pp + ((15, 40, 0, 0),),
                    )
                else:
                    self.raw = replace(self.raw, battle_state=0)
                    self.box.append(75)
                self.owned = self.owned | {145}
                self.ready = True
            self.after_throw()

    def read(self):
        return self.raw

    def read_pokedex_state(self):
        return NS(owned_species=self.owned)

    def read_all_box_states(self):
        return NS(current_box_index=0, boxes=(NS(species_ids=tuple(self.box)),))

    def read_wild_capture_identity(self):
        return (
            NS(original_species_id=self.raw.enemy_species_id)
            if self.raw.battle_state == 1
            else None
        )

    def read_battle_menu_state(self, _raw):
        return NS(phase=self.phase)

    def read_input_readiness(self):
        return NS(ready=self.ready)

    def read_bottom_dialogue_box_visible(self):
        return False

    def run(
        self,
        *,
        throws=3,
        ball=ItemId.GREAT_BALL,
        prepare=None,
        log=None,
        budget=None,
        replacement=None,
    ):
        return surge._try_catch_wild(
            self,
            self.executor,
            self,
            75,
            "one-off test",
            max_throws=throws,
            before_throw=prepare,
            record_decision=log,
            one_off_request=OneOffCaptureRequest(75, 50, ball),
            one_off_budget=budget,
            select_replacement=replacement,
        )


def test_success_requires_exact_species_registration_and_specimen(monkeypatch):
    s = Sim(monkeypatch)
    rows = []
    assert s.run(log=rows.append)
    assert s.spends == 1 and s.commands == [1]
    assert s.bag[ItemId.MASTER_BALL] == 1
    assert rows[0]["learned"] is False and rows[0]["target_hp"] == 150


def test_master_ball_is_explicit_and_skips_preparation(monkeypatch):
    s = Sim(monkeypatch)
    assert s.run(ball=ItemId.MASTER_BALL, prepare=lambda: pytest.fail("unnecessary setup"))
    assert s.bag[ItemId.GREAT_BALL] == 3 and s.bag[ItemId.MASTER_BALL] == 0


def test_box_transfer_waits_for_field_before_reading_intermediate_structures(monkeypatch):
    from pokemon_red_completion.observation import SemanticStateError
    s = Sim(monkeypatch)
    s.raw = replace(s.raw, party_count=6, party_species_ids=(28,) * 6,
                    party_pp=((15, 10, 15, 25),) * 6)
    original_read = s.read_all_box_states
    original_execute = s.execute
    unsettled_reads = []

    def read_boxes():
        if s.spends and s.raw.battle_state:
            unsettled_reads.append(True)
            raise SemanticStateError("box records are being copied")
        return original_read()

    def pending():
        s.raw = replace(s.raw, battle_state=1)
        s.ready = False

    def execute(action):
        original_execute(action)
        if action.kind is MacroActionKind.CANCEL:
            s.raw = replace(s.raw, battle_state=0)
            s.ready = True

    s.read_all_box_states = read_boxes
    s.after_throw = pending
    s.execute = execute
    assert s.run() and s.box == [75] and s.spends == 1
    assert not unsettled_reads


def test_corrupt_box_at_final_field_is_not_ignored(monkeypatch):
    from pokemon_red_completion.observation import SemanticStateError
    s = Sim(monkeypatch)
    original = s.read_all_box_states

    def boxes():
        if s.spends:
            raise SemanticStateError("still inconsistent at settled field")
        return original()

    s.read_all_box_states = boxes
    with pytest.raises(SemanticStateError, match="settled field"):
        s.run()
    assert s.spends == 1


def test_pending_capture_transfer_has_a_finite_cancel_only_bound(monkeypatch):
    s = Sim(monkeypatch)
    def pending():
        s.raw = replace(s.raw, battle_state=1)
        s.ready = False
    s.after_throw = pending
    with pytest.raises(OneOffCapturePaused, match="transfer settlement bound"):
        s.run()
    assert s.spends == 1 and s.commands == [1]


def test_failed_write_ahead_intent_commits_but_sends_no_ball_input(monkeypatch):
    from pokemon_red_completion.red_one_off_capture import OneOffCaptureBudget, run_one_off_capture

    s = Sim(monkeypatch)
    budget = OneOffCaptureBudget(OneOffCaptureRequest(75, 50, ItemId.GREAT_BALL), 3, 3)

    def fail(value):
        assert value.throws_committed == 1
        raise OSError("disk unavailable")

    with pytest.raises(OSError):
        run_one_off_capture(
            s, s.executor, s, budget.request, max_throws=3, budget=budget, commit_throw=fail
        )
    assert budget.throws_committed == 1 and not s.commands and s.spends == 0
    with pytest.raises(OneOffCapturePaused, match="ball count"):
        run_one_off_capture(s, s.executor, s, budget.request, max_throws=3, budget=budget)


@pytest.mark.parametrize("balls,throws", [(1, 5), (3, 1), (25, 21)])
def test_budget_exhaustion_preserves_encounter_without_flee(monkeypatch, balls, throws):
    s = Sim(monkeypatch, balls=balls, capture=False)
    with pytest.raises(OneOffCapturePaused, match="budget exhausted"):
        s.run(throws=throws)
    assert s.raw.battle_state == 1
    assert s.spends == min(balls, throws)
    assert s.bag[ItemId.MASTER_BALL] == 1
    assert set(s.commands) == {1}


def test_no_balls_stops_before_any_input(monkeypatch):
    s = Sim(monkeypatch, balls=0)
    with pytest.raises(OneOffCapturePaused, match="unavailable"):
        s.run()
    assert not s.commands and s.executor.actions_executed == 0


@pytest.mark.parametrize(
    "fault", ["species", "level", "trainer", "dead", "move", "full", "owned", "pp"]
)
def test_bad_entry_zero_input(monkeypatch, fault):
    s = Sim(monkeypatch)
    if fault == "species":
        s.raw = replace(s.raw, enemy_species_id=74)
    elif fault == "level":
        s.raw = replace(s.raw, enemy_level=49)
    elif fault == "trainer":
        s.raw = replace(s.raw, battle_state=2)
    elif fault == "dead":
        s.raw = replace(s.raw, active_party_hp=0)
    elif fault == "move":
        s.phase = BattleMenuPhase.MOVE
    elif fault == "full":
        s.raw = replace(s.raw, party_count=6, party_species_ids=(28,) * 6)
        s.box = [28] * 20
    elif fault == "owned":
        s.owned |= {145}
    else:
        s.raw = replace(s.raw, party_pp=None)
    with pytest.raises(OneOffCapturePaused):
        s.run()
    assert s.executor.actions_executed == 0 and not s.commands


@pytest.mark.parametrize(
    "fault", ["wrong_species", "missing_flag", "extra_ball", "money", "wrong_map"]
)
def test_bad_capture_outcome_not_counted(monkeypatch, fault):
    s = Sim(monkeypatch)

    def corrupt():
        if fault == "wrong_species":
            s.box[:] = [74]
        elif fault == "missing_flag":
            s.owned = frozenset({9})
        elif fault == "extra_ball":
            s.bag[ItemId.GREAT_BALL] -= 1
        elif fault == "money":
            s.raw = replace(s.raw, player_money=0)
        else:
            s.raw = replace(s.raw, map_id=41)

    s.after_throw = corrupt
    with pytest.raises(OneOffCapturePaused):
        s.run()


@pytest.mark.parametrize("fault", ["faint", "pp", "ko"])
def test_failed_throw_cannot_silently_issue_attack_or_switch(monkeypatch, fault):
    s = Sim(monkeypatch, capture=False)

    def corrupt():
        if fault == "faint":
            s.raw = replace(s.raw, active_party_hp=0)
        elif fault == "pp":
            s.raw = replace(s.raw, party_pp=((14, 10, 15, 25),))
        else:
            s.raw = replace(s.raw, enemy_hp=0)

    s.after_throw = corrupt
    with pytest.raises(OneOffCapturePaused):
        s.run()
    assert s.spends == 1


@pytest.mark.parametrize("fault", ["damage", "bag", "exit", "identity"])
def test_preparation_drift_refused_before_ball(monkeypatch, fault):
    s = Sim(monkeypatch)

    def prepare():
        if fault == "damage":
            s.raw = replace(s.raw, enemy_hp=1)
        elif fault == "bag":
            s.bag[ItemId.MASTER_BALL] = 0
        elif fault == "identity":
            s.raw = replace(s.raw, enemy_species_id=74)
        else:
            return False
        return True

    with pytest.raises(OneOffCapturePaused):
        s.run(prepare=prepare)
    assert s.spends == 0


def test_native_exit_is_not_a_capture(monkeypatch):
    s = Sim(monkeypatch, capture=False)

    def exit_battle():
        s.raw = replace(s.raw, battle_state=0)
        s.ready = True

    s.after_throw = exit_battle
    assert s.run() is False


def test_caught_party_append_before_battle_flag_clears(monkeypatch):
    s = Sim(monkeypatch)

    def pending():
        s.raw = replace(s.raw, battle_state=1)
        s.ready = False

    s.after_throw = pending
    original = s.execute

    def execute(action):
        original(action)
        if action.kind is MacroActionKind.CANCEL:
            s.raw = replace(s.raw, battle_state=0)
            s.ready = True

    s.execute = execute
    assert s.run()
    assert s.spends == 1 and s.commands == [1]


def test_full_party_capture_goes_to_current_box(monkeypatch):
    s = Sim(monkeypatch)
    s.raw = replace(
        s.raw, party_count=6, party_species_ids=(28,) * 6, party_pp=((15, 10, 15, 25),) * 6
    )
    assert s.run()
    assert s.box == [75] and s.raw.party_count == 6


@pytest.mark.parametrize("throws", [0, -1, True, 100])
def test_invalid_budget_rejected(monkeypatch, throws):
    s = Sim(monkeypatch)
    with pytest.raises(ValueError):
        s.run(throws=throws)
    assert s.executor.actions_executed == 0



def test_outer_capture_guard_accepts_observed_opponent_rest_before_ball(monkeypatch):
    s = Sim(monkeypatch)
    s.raw = replace(s.raw, enemy_hp=47)
    s.read_enemy_capture_moves = lambda: (29,133,156,0)
    s.read_enemy_capture_status = lambda: 2
    def rest():
        s.raw = replace(s.raw, enemy_hp=150)
        return True
    assert s.run(prepare=rest)
    assert s.spends == 1 and s.bag[ItemId.MASTER_BALL] == 1


@pytest.mark.parametrize('hp,status,moves', [
    (46,2,(29,133,156,0)),(100,2,(29,133,156,0)),
    (150,0,(29,133,156,0)),(150,3,(29,133,156,0)),(150,2,(29,133,0,0)),
])
def test_outer_capture_guard_rejects_unexplained_hp_change_before_ball(monkeypatch,hp,status,moves):
    s = Sim(monkeypatch)
    s.raw = replace(s.raw, enemy_hp=47)
    s.read_enemy_capture_moves = lambda:moves
    s.read_enemy_capture_status = lambda:status
    def unexplained():
        s.raw = replace(s.raw, enemy_hp=hp)
        return True
    with pytest.raises(OneOffCapturePaused, match='target HP'):
        s.run(prepare=unexplained)
    assert s.spends == 0 and not s.commands
