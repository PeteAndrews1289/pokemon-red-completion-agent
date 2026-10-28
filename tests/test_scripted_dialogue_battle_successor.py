"""An observed dialogue successor must use its own configured, bounded handler."""

from dataclasses import dataclass, field, replace
from typing import cast

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler, Gen1TraversalObserver,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.route_executor import (
    InterruptionReceipt, RouteExecutionError, RouteExecutionLimits, TraversalSnapshot,
    _pending_verified_interruption, _wait_until_ready,
)


@dataclass
class DialogueStartsBattle:
    reader: FakeReader
    battle_state: int = 2
    relocated: bool = False
    actions: list = field(default_factory=list)

    def execute(self, action):
        self.actions.append(action)
        if isinstance(action, MacroAction) and action.kind is MacroActionKind.CANCEL:
            self.reader.raw = replace(self.reader.raw, battle_state=self.battle_state,
                                     player_y=7 if self.relocated else 8)
            self.reader.dialogue_visible = False
        return action


def prepared(*, battle=2, trainers=1, flees=1, relocated=False):
    reader = FakeReader(raw(), ready=False, dialogue_visible=True)
    actions = DialogueStartsBattle(reader, battle, relocated)
    handler = Gen1RouteInterruptionHandler(
        cast(object, actions), reader_as_real(reader),
        maximum_flees=flees, maximum_trainer_battles=trainers,
        stabilization_frames=24, maximum_scripted_dialogues=1,
    )
    snapshot = TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "scripted_dialogue")
    return reader, actions, handler, snapshot


@pytest.mark.parametrize("battle,expected", [(1, "wild_battle"), (2, "battle:2")])
def test_dialogue_reports_observed_pending_battle_without_claiming_free_control(battle, expected):
    reader, actions, handler, snapshot = prepared(battle=battle)
    receipt = handler.handle(snapshot)
    observed = Gen1TraversalObserver(reader_as_real(reader)).observe()
    assert not observed.ready and observed.interruption == expected
    assert receipt.kind == "scripted_dialogue"
    assert receipt.details["pending_interruption_kind"] == expected
    assert receipt.details["battle_started_during_dialogue"] is True
    assert "battle_outcome" not in receipt.details
    assert _pending_verified_interruption(receipt, observed)
    assert not _pending_verified_interruption(receipt, replace(observed, interruption="other"))
    assert len(handler.scripted_dialogue_evidence) == 1
    assert not handler.trainer_evidence and not handler.wild_evidence
    assert [a.kind for a in actions.actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]


@pytest.mark.parametrize("fault", ["no_trainer", "trainer_exhausted", "no_flee", "relocated", "unknown"])
def test_undeclared_exhausted_or_relocated_battle_stays_an_error(fault):
    reader, actions, handler, snapshot = prepared(
        battle=1 if fault == "no_flee" else 3 if fault == "unknown" else 2,
        trainers=0 if fault == "no_trainer" else 1,
        flees=0 if fault == "no_flee" else 1,
        relocated=fault == "relocated",
    )
    if fault == "trainer_exhausted":
        handler.trainer_evidence.append(InterruptionReceipt(
            kind="trainer_engagement", resumed_map=snapshot.map_id,
            resumed_at=snapshot.at, details={"verified": True},
        ))
    with pytest.raises(RouteExecutionError, match="entered a battle"):
        handler.handle(snapshot)
    assert not handler.scripted_dialogue_evidence
    assert reader.raw.battle_state != 0
    assert len(actions.actions) == 2


@pytest.mark.parametrize("budget", [1, 2])
def test_route_spends_separate_interruption_budget_for_actual_battle(monkeypatch, budget):
    reader, actions, handler, snapshot = prepared()
    calls = []

    def finish(*_args, **_kwargs):
        calls.append("existing_trainer_executor")
        reader.raw = replace(reader.raw, battle_state=0)
        reader.ready = True
        return reader.raw

    monkeypatch.setattr("pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle", finish)
    observer = Gen1TraversalObserver(reader_as_real(reader))
    args = (snapshot, actions, observer, handler, RouteExecutionLimits(max_interruptions=budget))
    if budget == 1:
        with pytest.raises(RouteExecutionError, match="interruption budget"):
            _wait_until_ready(*args, used_interruptions=0)
        assert calls == [] and not handler.trainer_evidence
    else:
        terminal, receipts, _ = _wait_until_ready(*args, used_interruptions=0)
        assert terminal.ready and calls == ["existing_trainer_executor"]
        assert [r.kind for r in receipts] == ["scripted_dialogue", "trainer_engagement"]
        assert len(handler.trainer_evidence) == 1
