from types import SimpleNamespace

from prepare_red_natural_qualification import (
    field_executor, late_slot_source, open_buy_list, retained_uncaught_field, safe_weakening, weakening_enabled,
)


def test_field_executor_uses_established_menu_timing_and_literal_waits():
    timing = field_executor(object()).timing
    assert (timing.press_frames, timing.release_frames, timing.wait_frames) == (8, 16, 1)


def test_late_slot_setup_is_idempotent_after_retained_approach_failure():
    raw = SimpleNamespace(party_count=6, party_levels=(16, 6, 11, 8, 8, 8),
                          party_max_hp=(49, 21, 31, 24, 25, 23))
    assert late_slot_source(raw) == 0
    raw.party_levels = (8, 6, 11, 8, 8, 16)
    raw.party_max_hp = (23, 21, 31, 24, 25, 49)
    assert late_slot_source(raw) == 5


def test_lost_encounter_recovery_preserves_resources_and_rejects_blackout_or_battle():
    before = SimpleNamespace(battle_state=1, map_id=59, player_money=1000,
        party_species_ids=(177, 107), bag_items=((4, 7),), party_hp=(39, 23))
    values = vars(before) | {"battle_state": 0, "party_hp": (36, 18)}
    assert retained_uncaught_field(before, SimpleNamespace(**values))
    for change in ({"battle_state": 1}, {"map_id": 68}, {"player_money": 500},
                   {"bag_items": ((4, 6),)}, {"party_species_ids": (177, 107, 107)},
                   {"party_hp": (0, 0)}):
        assert not retained_uncaught_field(before, SimpleNamespace(**(values | change)))


def test_failed_weakening_stays_disabled_in_all_later_preparation_phases():
    assert weakening_enabled(None)
    assert not weakening_enabled({"error": {"message": "weakening failed"}})
    assert not weakening_enabled({"capture_weakening_enabled": False, "error": None})


def test_mart_interaction_precedes_reading_uninitialized_field_cursor():
    from pokemon_red_completion.actions import MacroActionKind
    events = []
    def read():
        assert [e.kind for e in events] == [MacroActionKind.INTERACT, MacroActionKind.WAIT]
        return SimpleNamespace(top_x=5, top_y=4)
    open_buy_list(SimpleNamespace(execute=events.append), SimpleNamespace(read_menu_cursor_state=read))


def sample(**changes):
    values = dict(battle_state=1, enemy_hp=31, enemy_max_hp=31, enemy_defense_stage=7,
        enemy_species_id=107, enemy_level=11, party_species_ids=(179, 107),
        party_hp=(49, 21), party_max_hp=(49, 21), party_status=(0, 0), active_party_index=0,
        player_attack_stage=7, party_moves=((33, 39, 145, 55), (141, 0, 0, 0)),
        party_pp=((35, 30, 30, 25), (15, 0, 0, 0)), party_stats=((26, 34, 25, 29), (11, 9, 12, 10)),
        party_levels=(16, 6))
    return SimpleNamespace(**(values | changes))


def test_conservative_weakener_uses_supported_reserve_not_lead_or_status():
    choice = safe_weakening(sample(), {107: (40, 45, 35, 55, 40)})
    assert choice is not None
    upper, member, slot = choice
    assert (member, slot) == (1, 0)
    assert 0 < upper < 31


def test_weakening_abstains_on_low_target_hp_or_unqualified_state():
    for changes in (dict(enemy_hp=5), dict(enemy_defense_stage=6), dict(battle_state=2),
                    dict(party_status=(0, 8)), dict(party_hp=(49, 0)),
                    dict(party_pp=((35, 30, 30, 25), (0, 0, 0, 0))),
                    dict(party_moves=((33, 39, 145, 55), (120, 0, 0, 0)))):
        assert safe_weakening(sample(**changes), {107: (40, 45, 35, 55, 40)}) is None
