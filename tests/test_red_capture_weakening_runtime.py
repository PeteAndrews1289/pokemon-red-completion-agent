from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.observation import BattleMenuPhase, RawGameState, SemanticStateError
from pokemon_red_completion.red_capture_weakening import safe_special_capture_move
from pokemon_red_completion.red_capture_weakening_runtime import (
    living_capture_weakener,
    prepare_nonlethal_capture,
)


def world(monkeypatch):
    import pokemon_red_completion.red_capture_weakening_runtime as m

    w = NS(
        raw=RawGameState(
            True,
            83,
            4,
            10,
            1,
            1,
            party_species_ids=(104,),
            party_pp=((19, 15, 30, 30),),
            active_party_index=0,
            active_party_hp=156,
            active_party_level=55,
            active_party_moves=(86, 28, 98, 84),
            active_party_pp=(19, 15, 30, 30),
            enemy_hp=153,
            enemy_level=50,
            player_money=30000,
            bag_items=((3, 20),),
        ),
        enemy_status=64,
        replies=(84, 65, 97, 0),
        count=0,
        mutation=lambda: None,
        executed=True,
    )
    w.read = lambda: w.raw
    w.read_pokedex_state = lambda: frozenset({9})
    w.read_all_box_states = lambda: ()
    w.read_wild_capture_identity = lambda: NS(original_species_id=75)
    w.read_battle_menu_state = lambda _: NS(phase=BattleMenuPhase.MAIN)
    w.read_enemy_capture_status = lambda: w.enemy_status
    w.read_enemy_capture_moves = lambda: w.replies
    w.read_enemy_capture_pp = lambda: (15, 20, 10, 0)
    w.read_wild_special_damage_inputs = lambda _: (152, 130, ("electric",), ("electric", "flying"))

    def turn(*a, **k):
        assert k["selected_slot"] == 4
        w.count += 1
        pp = list(w.raw.party_pp[0])
        pp[3] -= int(w.executed)
        w.raw = replace(
            w.raw,
            enemy_hp=w.raw.enemy_hp - (30 if w.executed else 0),
            party_pp=(tuple(pp),),
            active_party_pp=tuple(pp),
        )
        w.mutation()
        return NS(move_executed=w.executed)

    monkeypatch.setattr(m, "execute_bounded_battle_move_turn", turn)
    return w


def run(w, **kwargs):
    return prepare_nonlethal_capture(w, w, internal_species=75, level=50, **kwargs)


def test_paralysis_side_effect_requires_explicit_opt_in(monkeypatch):
    w = world(monkeypatch)
    raw = w.raw
    inputs = w.read_wild_special_damage_inputs(raw)
    assert safe_special_capture_move(raw, inputs) is None
    slot, upper = safe_special_capture_move(raw, inputs, allow_paralysis_side_effect=True)
    assert slot == 4 and 0 < upper < 153
    assert (
        safe_special_capture_move(
            replace(raw, enemy_hp=upper), inputs, allow_paralysis_side_effect=True
        )
        is None
    )


def test_bounded_damage_pp_and_native_turns(monkeypatch):
    w = world(monkeypatch)
    out = run(w)
    assert out.attempts == 3 and out.damage == 90 and w.raw.enemy_hp == 63
    assert w.raw.party_pp[0][3] == 27
    assert all(t["upper_damage"] >= t["damage"] > 0 and t["critical_included"] for t in out.turns)


def test_nonexecuted_paralysis_turns_spend_attempt_not_pp(monkeypatch):
    w = world(monkeypatch)
    w.executed = False
    out = run(w, maximum_attempts=2)
    assert out.attempts == 2 and out.damage == 0 and w.raw.party_pp[0][3] == 30


@pytest.mark.parametrize("points", [None,(0,0,0,0)])
def test_unknown_or_exhausted_reply_pp_abstains_before_struggle_risk(monkeypatch, points):
    w = world(monkeypatch)
    w.read_enemy_capture_pp = lambda: points
    out = run(w)
    assert out.attempts == w.count == 0
    assert out.stop_reason == "unobserved_or_exhausted_enemy_reply_pp"


@pytest.mark.parametrize("moves", [None, (), (29, 44)])
def test_unobserved_reply_moves_abstain_without_inputs(monkeypatch, moves):
    w = world(monkeypatch)
    w.replies = moves
    out = run(w)
    assert out.attempts == w.count == 0
    assert out.stop_reason == "unobserved_or_exhausted_enemy_reply_pp"


def weakener_party():
    return NS(
        active_party_index=0,
        party_moves=((84, 0, 0, 0),) * 4,
        party_pp=((10, 0, 0, 0),) * 4,
        party_hp=(100, 60, 60, 60),
        party_max_hp=(100, 100, 100, 100),
        party_levels=(10, 30, 20, 20),
        party_status=(0, 0, 0, 0),
    )


def test_weakener_proposes_lowest_level_eligible_not_current_member():
    assert living_capture_weakener(weakener_party()) == 2


@pytest.mark.parametrize("field,value", [
    ("party_hp", (100, 50, 0, 50)),
    ("party_status", (0, 8, 16, 64)),
    ("party_pp", ((10, 0, 0, 0), (0, 0, 0, 0), (64, 0, 0, 0), (0, 0, 0, 0))),
    ("party_moves", ((84, 0, 0, 0), (29, 0, 0, 0), (29, 0, 0, 0), (29, 0, 0, 0))),
    ("party_levels", None),
    ("party_levels", (10,)),
])
def test_weakener_never_proposes_unhealthy_unsupported_or_unknown_member(field, value):
    raw = weakener_party()
    setattr(raw, field, value)
    assert living_capture_weakener(raw) is None


@pytest.mark.parametrize("permission", [1, None, "yes"])
def test_switch_permission_is_explicit_boolean(monkeypatch, permission):
    w = world(monkeypatch)
    with pytest.raises(ValueError, match="explicit"):
        run(w, allow_weakener_switch=permission)
    assert w.count == 0


def test_opt_in_switch_needs_guarded_emulator_before_input(monkeypatch):
    w = world(monkeypatch)
    with pytest.raises(ValueError, match="guarded emulator"):
        run(w, allow_weakener_switch=True)
    assert w.count == 0


@pytest.mark.parametrize("reply", [29, 44, 133, 105, 156])
def test_known_flinch_special_boost_and_healing_replies_keep_nonlethal_bounds(monkeypatch, reply):
    w = world(monkeypatch)
    w.replies = (reply, 0, 0, 0)
    w.raw = replace(w.raw, enemy_max_hp=153)
    out = run(w, maximum_attempts=1)
    assert out.attempts == 1 and out.damage == 30
    assert out.turns[0]["critical_included"] and out.turns[0]["hp_net_change"] == -30


def test_healing_reply_records_net_recovery_and_stops_without_negative_damage(monkeypatch):
    w = world(monkeypatch)
    w.replies = (156, 0, 0, 0)
    w.raw = replace(w.raw, enemy_hp=120, enemy_max_hp=153)
    w.mutation = lambda: setattr(w, "raw", replace(w.raw, enemy_hp=153))
    out = run(w)
    assert out.attempts == 1 and out.damage == 0 and out.stop_reason == "target_healed"
    assert out.turns[0]["hp_net_change"] == 33 and out.turns[0]["enemy_hp_restored"]
    assert w.raw.party_pp[0][3] == 29


def test_healing_reply_requires_an_observed_hp_ceiling_before_input(monkeypatch):
    w = world(monkeypatch)
    w.replies = (156, 0, 0, 0)
    out = run(w)
    assert out.attempts == 0 and out.stop_reason == "unproven_enemy_healing_limit"
    assert w.count == 0


@pytest.mark.parametrize("fault", ["unoffered_heal", "ceiling_exceeded", "ceiling_changed"])
def test_healing_support_does_not_allow_unproved_hp_changes(monkeypatch, fault):
    w = world(monkeypatch)
    w.raw = replace(w.raw, enemy_max_hp=153)
    w.replies = (156, 0, 0, 0) if fault != "unoffered_heal" else (29, 0, 0, 0)
    def mutate():
        w.raw = replace(w.raw, **(
            dict(enemy_hp=154) if fault == "ceiling_exceeded" else
            dict(enemy_max_hp=154) if fault == "ceiling_changed" else
            dict(enemy_hp=154)
        ))
    w.mutation = mutate
    with pytest.raises(RuntimeError):
        run(w)


@pytest.mark.parametrize(
    "fault",
    [
        "poison",
        "burn",
        "unknown_status",
        "reply_debuff",
        "reply_recoil",
        "no_safe_move",
        "volatile",
    ],
)
def test_abstains_without_inputs_for_unproven_safety(monkeypatch, fault):
    w = world(monkeypatch)
    if fault == "poison":
        w.enemy_status = 8
    if fault == "burn":
        w.enemy_status = 16
    if fault == "unknown_status":
        w.enemy_status = None
    if fault == "reply_debuff":
        w.replies = (43, 0, 0, 0)
    if fault == "reply_recoil":
        w.replies = (36, 0, 0, 0)
    if fault == "no_safe_move":
        w.raw = replace(w.raw, enemy_hp=1)
    if fault == "volatile":

        def fail(_):
            raise SemanticStateError("confused")

        w.read_wild_special_damage_inputs = fail
    out = run(w)
    assert out.attempts == 0 and out.damage == 0 and w.count == 0


@pytest.mark.parametrize(
    "fault", ["ko", "excess_damage", "pp", "bag", "money", "species", "map", "target", "battle"]
)
def test_rejects_unsafe_or_unaccounted_native_outcome(monkeypatch, fault):
    w = world(monkeypatch)

    def mutate():
        changes = {
            "ko": dict(enemy_hp=0),
            "excess_damage": dict(enemy_hp=1),
            "pp": dict(party_pp=((1, 1, 1, 1),)),
            "bag": dict(bag_items=()),
            "money": dict(player_money=1),
            "species": dict(party_species_ids=(28,)),
            "map": dict(map_id=41),
            "battle": dict(battle_state=0),
        }.get(fault, {})
        w.raw = replace(w.raw, **changes)
        if fault == "target":
            w.read_wild_capture_identity = lambda: NS(original_species_id=74)

    w.mutation = mutate
    with pytest.raises(RuntimeError):
        run(w)
    assert w.count == 1
