from dataclasses import dataclass
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_story_funding as funding
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)


@pytest.mark.parametrize('fault', [
    None, 'center', 'battle', 'no_living', 'unready', 'weak_lead', 'unknown_level',
])
def test_field_recovery_only_quotes_local_safe_trainers(monkeypatch, fault):
    raw = NS(map_id=141 if fault == 'center' else 21, battle_state=2 if fault == 'battle' else 0,
        party_hp=(0, 0) if fault == 'no_living' else (128, 0), first_party_hp=128,
        first_party_level=None if fault == 'unknown_level' else 20 if fault == 'weak_lead' else 41,
        player_money=11555)
    reader = NS(read=lambda: raw, read_input_readiness=lambda: NS(ready=fault != 'unready'),
        read_current_map_objects=lambda: (), read_current_map_blocks=lambda: ())
    world = NS(with_current_blocks=lambda _: 'world')
    route = NS(route_world=world)
    candidate = NS(trainer=NS(defeated=False), quote=NS(party=(NS(level=19),),
        expected_money_after=lambda cash: cash+665))
    monkeypatch.setattr(funding, 'Gen1TraversalObserver',
                        lambda *a, **k: NS(observe=lambda: 'observed'))
    monkeypatch.setattr(funding, 'Gen1TrainerSightProjector', lambda *a, **k: None)
    monkeypatch.setattr(funding, 'trainer_headers', lambda *a, **k: ())
    monkeypatch.setattr(funding, 'map_object_events', lambda *a: ())
    monkeypatch.setattr(funding, 'trainer_sight_zones', lambda *a: 'zones')
    def local(rom, current_world, observed, zones):
        assert (rom, current_world, observed, zones) == (b'rom', 'world', 'observed', 'zones')
        return (candidate,)
    monkeypatch.setattr(funding, 'local_trainer_funding_candidates', local)
    result = funding.field_story_funding_candidates(b'rom', reader, route)
    assert result == (() if fault else (candidate,))


@pytest.mark.parametrize("status", [GoalDecisionOutcome.SUCCEEDED, GoalDecisionOutcome.FAILED])
def test_recovery_uses_general_provider_and_checks_verdict(monkeypatch, status):
    calls = []
    live = NS(raw=NS())
    adapter = NS(observe=lambda: live)
    monkeypatch.setattr(funding, "_raw_party_fully_restored", lambda _: False)
    binding = NS(execute=lambda: calls.append("heal"), verify=lambda _: NS(status=status))
    monkeypatch.setattr(funding, "RedCenterRestoreGoalProvider",
                        lambda *a, **k: NS(offer=lambda _: NS(binding=binding)))
    if status is GoalDecisionOutcome.SUCCEEDED:
        funding.restore_story_team(None, NS(execute=lambda _: None), None, adapter)
    else:
        with pytest.raises(RuntimeError, match="did not verify"):
            funding.restore_story_team(None, NS(execute=lambda _: None), None, adapter)
    assert calls == ["heal"]


@pytest.mark.parametrize("field_home", [None, 141, 1])
@pytest.mark.parametrize("failure", [None, "actor", "return_bag", "stale", "unqualified"])
def test_income_requires_k_and_preserves_earned_state_without_teacher(
    monkeypatch, tmp_path, failure, field_home,
):
    raw = NS(party_count=4, player_money=8280, map_id=141, player_x=3, player_y=3,
             bag_items=((19, 4),), party_species_ids=(28, 64, 59, 104),
             party_hp=(125, 59, 37, 68), party_max_hp=(125, 59, 37, 68),
             party_status=(0, 0, 0, 0), battle_state=0)
    current = [raw if failure != "stale" else NS()]
    reader = NS(read=lambda: current[0], read_input_readiness=lambda: NS(ready=True))
    emulator = NS(pressed_buttons=frozenset())
    target = NS(trainer=NS(map_id=19, event_flag=123), approach=NS(terminal_at=(2, 3)),
                interaction_facing=NS(value="up"), quote=NS(expected_victory_money=1540))
    battler = FrozenTrainerBattler(None, None, tmp_path, "a"*40, "root", "b"*64, {},
        model_sha256=FROZEN_K_SHA256, qualification_sha256=K_QUALIFICATION_SHA256)
    if failure == "unqualified":
        battler.qualification_sha256 = None
    calls = []

    @dataclass(frozen=True)
    class Route:
        destination_map: int = 0
        destination_at: tuple = ()
        full_event_offsets: bool = False
        observe_terrain: bool = False
        excluded_maps: frozenset = frozenset()

        def __call__(self, *args):
            calls.append("route")
            if self.destination_map == 141:
                current[0] = NS(**{**raw.__dict__, "player_money": 9820,
                    "bag_items": () if failure == "return_bag" else raw.bag_items})

    monkeypatch.setattr(funding.RedVermilionGroundTransition, "from_rom", lambda _: Route())
    monkeypatch.setattr(funding, "story_funding_candidates", lambda *a: (target,))
    monkeypatch.setattr(funding, "field_story_funding_candidates", lambda *a: (target,))
    monkeypatch.setattr(funding, "_face_trainer_boundary", lambda *a: None)
    monkeypatch.setattr(funding, "restore_story_team", lambda *a: calls.append("heal"))

    def battle(*args, **kwargs):
        assert kwargs["battle_runner_override"].__self__ is battler
        assert kwargs["story_income_recovery"] is True
        with pytest.raises(RuntimeError, match="scripted attack"):
            kwargs["move_slot_policy"](raw)
        calls.append("battle")
        if failure == "actor":
            raise RuntimeError("actor failure retained")
        return NS(initial_money=8280, final_money=9820, payout=1540,
                  ordinary_victory_money=1540, pay_day_money=0)

    monkeypatch.setattr(funding, "run_prepared_trainer_funding", battle)
    kwargs = dict(rom=b"rom", reader=reader, actions=object(), emulator=emulator, adapter=object(),
                  battler=battler, target=target, source_raw=raw, target_cash=12950,
                  record=lambda *a: None, field_recovery_home=field_home)
    if failure or field_home == 1:
        with pytest.raises((ValueError, RuntimeError)):
            funding.execute_story_trainer_income(**kwargs)
        if failure in {"stale", "unqualified"}:
            assert not calls
        if failure == "actor" and field_home != 1:
            assert calls == ["route", "battle"]
    else:
        result = funding.execute_story_trainer_income(**kwargs)
        assert result["net_income"] == 1540 and result["sales"] == 0
        assert result["model_goal_queries"] == 0
        assert calls == ["route", "battle", "route", "heal"]
