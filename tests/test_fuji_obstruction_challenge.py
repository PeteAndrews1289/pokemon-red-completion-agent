"""ROM-free Fuji contract-witness and unchanged-authority regressions."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_story_obstruction_challenge import fixture as obstruction_fixture

from pokemon_red_completion import red_player_early_story_options as p
from pokemon_red_completion.player_option_challenge import OptionChallenge


def fixture(monkeypatch):
    s = obstruction_fixture(monkeypatch)
    s.raw.map_id = 145
    s.contract = replace(s.contract, objective_id="rescue_fuji", map_id=145)
    s.runtime.adapter.graph.available_objectives = lambda _: (N(id="rescue_fuji"),)
    monkeypatch.setattr(p, "fuji_binding", lambda *args, **kwargs: None)
    monkeypatch.setattr(p, "marowak_pending", lambda raw: False)
    return s


def fuji(s, *, levels=(13,), trainer=None):
    return p.fuji_story_option(
        s.runtime,
        s.actions,
        route=s.route,
        battler="unchanged-wild-actor",
        trainer_battler=trainer,
        combat_levels=levels,
    )


@pytest.mark.parametrize("trainer", [None, "unchanged-trainer-actor"])
def test_fuji_fallback_quotes_only_the_admitted_trainer(monkeypatch, trainer):
    s = fixture(monkeypatch)
    binding, challenge = fuji(s, trainer=trainer)
    assert challenge == OptionChallenge.from_levels(
        combat_levels=(13,), opponent_levels=s.quote_levels
    )
    assert binding.binding_ref == s.binding.binding_ref
    assert binding.execute is s.binding.execute
    assert binding.verify is s.binding.verify
    assert binding.estimated_effort == s.binding.estimated_effort
    assert binding.estimated_risk == s.binding.estimated_risk
    assert binding.maximum_cash_debit == s.binding.maximum_cash_debit
    assert binding.story_unit == s.binding.story_unit
    assert binding.story_objective_ref == "rescue_fuji"
    assert s.quote_calls == [(s.route.rom, 202, 3)]
    assert s.calls[0]["battler"] == (
        "unchanged-wild-actor" if trainer is None else trainer
    )
    assert s.calls[0]["frontier"] is True
    assert s.calls[0]["allow_sequence"] is True
    assert s.calls[0]["destination_at"] is None
    assert s.actions.actions_executed == s.emulator.frame_count == 0
    assert s.state == b"observed-native-fixture"


def test_fuji_without_combat_roles_keeps_unknown_and_does_not_quote(monkeypatch):
    s = fixture(monkeypatch)
    binding, challenge = fuji(s, levels=())
    assert binding.binding_ref == s.binding.binding_ref
    assert challenge == OptionChallenge(True, False, 0.0, 0.0, 0.0)
    assert s.quote_calls == []
    assert s.actions.actions_executed == s.emulator.frame_count == 0


def test_fuji_without_an_admitted_obstruction_stays_absent(monkeypatch):
    s = fixture(monkeypatch)
    s.binding = None
    assert fuji(s) is None
    assert s.quote_calls == []
    assert s.actions.actions_executed == s.emulator.frame_count == 0


@pytest.mark.parametrize(
    "fault", ["missing_witness", "other_binding", "duplicate", "no_returned_binding"]
)
def test_fuji_rejects_nonmatching_obstruction_witness(monkeypatch, fault):
    s = fixture(monkeypatch)
    s.fault = fault
    with pytest.raises(ValueError, match="witness"):
        fuji(s)


@pytest.mark.parametrize("fault", ["source", "frames", "actions", "quote_frames"])
def test_fuji_preview_cannot_change_native_boundary(monkeypatch, fault):
    s = fixture(monkeypatch)
    s.fault = fault
    with pytest.raises(ValueError, match="native boundary"):
        fuji(s)


def test_fuji_noncombat_travel_retains_exact_old_descriptor(monkeypatch):
    s = fixture(monkeypatch)
    s.travel = replace(s.binding, binding_ref="private:noncombat-travel")
    binding, challenge = fuji(s)
    assert binding.binding_ref == s.travel.binding_ref
    assert binding.execute is s.travel.execute
    assert binding.verify is s.travel.verify
    assert challenge == OptionChallenge(False, False, 0.0, 0.0, 0.0)
    assert s.calls == [] and s.quote_calls == []


def test_fuji_ghost_keeps_existing_wild_actor_and_unknown_challenge(monkeypatch):
    s = fixture(monkeypatch)
    s.raw.map_id = 147
    monkeypatch.setattr(p, "marowak_pending", lambda raw: True)
    actors = []

    def ghost(*args, **kwargs):
        actors.append(kwargs["battler"])
        return s.binding

    monkeypatch.setattr(p, "marowak_binding", ghost)
    _, challenge = fuji(s, trainer="separate-trainer-actor")
    assert actors == ["unchanged-wild-actor"]
    assert challenge == OptionChallenge(True, False, 0.0, 0.0, 0.0)
    assert s.calls == [] and s.quote_calls == []
