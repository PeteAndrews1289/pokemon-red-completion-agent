from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_cerulean_branches as b
from pokemon_red_completion.goal_manager import GoalKind


def fixture(
    monkeypatch,
    *,
    map_id=3,
    available=("help_bill", "defeat_misty"),
    rival=False,
    battler_for_objective=None,
):
    flags = bytearray(256)
    if rival:
        flags[152 // 8] |= 1 << (152 % 8)
    raw = N(map_id=map_id, event_flags=bytes(flags))
    rt = N(
        reader=N(read=lambda: raw),
        adapter=N(
            observe=lambda: N(raw=raw, game_state=None),
            graph=N(available_objectives=lambda _: tuple(N(id=o) for o in available)),
        ),
    )
    calls = []

    def binding(label):
        calls.append(label)
        return _binding(GoalKind.ADVANCE_STORY, binding_ref=label, calls=[])

    monkeypatch.setattr(b, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        b, "story_travel_binding", lambda *a, **k: binding(k["objective_id"] + ":travel")
    )
    monkeypatch.setattr(b, "cerulean_rival_binding", lambda *a, **k: binding("rival"))
    monkeypatch.setattr(b, "bill_interaction_binding", lambda *a, **k: binding("bill-phase"))
    monkeypatch.setattr(b, "story_battle_binding", lambda *a, **k: binding("misty"))
    monkeypatch.setattr(b, "cerulean_rival_contract", lambda *a: N(trainer_identity=(225, 25, 8)))
    monkeypatch.setattr(b, "MISTY_REWARD", N(contract=lambda *a: N(trainer_identity=(235, 35, 1))))
    monkeypatch.setattr(
        b,
        "trainer_party_quote",
        lambda rom, cls, team: N(
            party=tuple(N(level=n) for n in ((18, 21) if cls == 235 else (18, 15, 15, 17)))
        ),
    )

    def observe():
        return b.cerulean_story_options(
            rt,
            N(),
            route=N(rom=b"rom"),
            battler=N(),
            combat_levels=(17,),
            battler_for_objective=battler_for_objective,
        )

    return observe, calls


def test_both_branches_are_available_without_fixed_order_and_bill_exposes_its_rival(monkeypatch):
    observe, calls = fixture(monkeypatch)
    options = observe()
    assert {o.objective_id for o in options} == {"help_bill", "defeat_misty"}
    assert all(o.binding.story_objective_ref == o.objective_id for o in options)
    assert calls == ["defeat_misty:travel", "rival"]
    by_goal = {o.objective_id: o for o in options}
    assert by_goal["help_bill"].challenge.opponent_fraction == 4 / 6
    assert by_goal["help_bill"].challenge.maximum_level_deficit == 0.01
    assert not by_goal["defeat_misty"].challenge.combat_required


def test_inside_gym_previews_actual_misty_not_whole_chapter(monkeypatch):
    observe, calls = fixture(monkeypatch, map_id=65)
    options = observe()
    assert calls == ["misty", "help_bill:travel"]
    assert options[0].challenge.opponent_fraction == 2 / 6
    assert options[0].challenge.maximum_level_deficit == 0.04


@pytest.mark.parametrize("available", [("help_bill",), ("defeat_misty",), ()])
def test_completion_of_either_branch_does_not_force_the_other_unfinished(monkeypatch, available):
    observe, _ = fixture(monkeypatch, available=available)
    assert {o.objective_id for o in observe()} == set(available)


def test_defeated_rival_is_not_replayed(monkeypatch):
    observe, calls = fixture(monkeypatch, rival=True)
    observe()
    assert "rival" not in calls and "help_bill:travel" in calls


def test_bill_room_offers_native_phase_not_automatic_chapter(monkeypatch):
    observe, calls = fixture(monkeypatch, map_id=88)
    observe()
    assert "bill-phase" in calls and "rival" not in calls


@pytest.mark.parametrize(
    "map_id,objective,seam",
    [
        (65, "defeat_misty", "story_battle_binding"),
        (3, "help_bill", "cerulean_rival_binding"),
    ],
)
def test_private_actor_dispatch_does_not_change_story_choices(monkeypatch, map_id, objective, seam):
    actors = {"defeat_misty": object(), "help_bill": object()}
    observed = []
    observe, _ = fixture(monkeypatch, map_id=map_id, battler_for_objective=actors.__getitem__)

    def capture(*args, **kwargs):
        observed.append(kwargs["battler"])
        return _binding(GoalKind.ADVANCE_STORY, binding_ref="captured", calls=[])

    monkeypatch.setattr(b, seam, capture)
    rows = observe()
    assert observed == [actors[objective]]
    assert {row.objective_id for row in rows} == set(actors)


def test_invalid_actor_dispatch_refuses_before_observation():
    with pytest.raises(TypeError, match="dispatch must be callable"):
        b.cerulean_story_options(
            N(), N(), route=N(), battler=N(), combat_levels=(), battler_for_objective={}
        )
