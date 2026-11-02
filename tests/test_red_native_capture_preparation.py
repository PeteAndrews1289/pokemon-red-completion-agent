"""Field-item pickup and native TM-teaching tests, separate from escort preparation."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import CurrentMapObject, RawGameState
from pokemon_red_completion.red_field_item import RedFieldItem, collect_visible_field_item
from pokemon_red_completion.red_machine_teaching import execute_machine_lesson, plan_machine_lesson


@pytest.mark.parametrize(
    "phase,active,battle,expected",
    [
        ("party", True, 0, ("party", 0)),
        ("forget", True, 0, ("forget", 0)),
        ("yes_no", True, 0, ("yes_no", 0)),
        ("forget", False, 0, None),
        ("party", True, 1, None),
        ("other", True, 0, None),
    ],
)
def test_machine_input_requires_live_cursor_and_matching_text(phase, active, battle, expected):
    from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress

    base = int(RamAddress.TILE_MAP)
    menus = {"party": (1, 0, 1), "forget": (8, 5, 3), "yes_no": (8, 15, 1), "other": (8, 5, 3)}
    menu = menus[phase]
    memory = {
        RamAddress.IS_IN_BATTLE: battle,
        RamAddress.PARTY_COUNT: 2,
        RamAddress.TOP_MENU_ITEM_Y: menu[0],
        RamAddress.TOP_MENU_ITEM_X: menu[1],
        RamAddress.MAX_MENU_ITEM: menu[2],
        RamAddress.CURRENT_MENU_ITEM: 0,
        RamAddress.MENU_CURSOR_LOCATION: base & 255,
        int(RamAddress.MENU_CURSOR_LOCATION) + 1: base >> 8,
        base: 0xED if active else 0,
    }
    text = {"party": "Choose", "forget": "forgotten", "yes_no": "make room", "other": "Choose"}[
        phase
    ]
    for i, char in enumerate(text):
        memory[base + 260 + i] = (
            ord(char) - ord("A") + 0x80
            if char.isupper()
            else ord(char) - ord("a") + 0xA0
            if char.islower()
            else 0x7F
        )
    assert (
        PokemonRedStateReader(
            NS(read_u8=lambda at: memory.get(at, 0))
        ).read_machine_learning_input()
        == expected
    )


class World:
    def __init__(self):
        self.raw = RawGameState(
            True,
            35,
            10,
            6,
            1,
            0,
            party_species_ids=(104,),
            party_moves=((33, 28, 98, 84),),
            party_pp=((35, 15, 30, 30),),
            party_hp=(156,),
            party_levels=(55,),
            player_money=30620,
            bag_items=((3, 20),),
        )
        self.objects = (CurrentMapObject(8, 61, (5, 10), 0, 0),)
        self.facing = "up"
        self.count = 0
        self.phase = None
        self.mutation = lambda: None
        self.choices = []

    def read(self):
        return self.raw

    def read_current_map_objects(self):
        return self.objects

    def read_player_facing(self):
        return self.facing

    def read_input_readiness(self):
        return NS(ready=True)

    def read_bottom_dialogue_box_visible(self):
        return False

    def read_all_box_states(self):
        return ()

    def read_pokedex_state(self):
        return frozenset({135})

    def read_pc_items(self):
        return ()

    def read_machine_learning_input(self):
        return self.phase

    def execute(self, action):
        self.count += 1
        if action.kind is MacroActionKind.INTERACT:
            self.raw = replace(self.raw, bag_items=self.raw.bag_items + ((245, 1),))
            self.objects = ()
            self.mutation()


TARGET = RedFieldItem(245, 35, 8, 61, (5, 10))


def test_item_pickup_exact_gain_and_removal():
    world = World()
    collect_visible_field_item(world, world, TARGET)
    assert dict(world.raw.bag_items)[245] == 1 and world.count > 0


@pytest.mark.parametrize("fault", ["facing", "absent", "bag", "map", "battle"])
def test_item_pickup_bad_entry_zero_input(fault):
    w = World()
    if fault == "facing":
        w.facing = "left"
    elif fault == "absent":
        w.objects = ()
    elif fault == "bag":
        w.raw = replace(w.raw, bag_items=tuple((i, 1) for i in range(1, 21)))
    elif fault == "map":
        w.raw = replace(w.raw, map_id=41)
    else:
        w.raw = replace(w.raw, battle_state=1)
    with pytest.raises(ValueError):
        collect_visible_field_item(w, w, TARGET)
    assert not w.count


@pytest.mark.parametrize("fault", ["money", "pp", "bag", "battle"])
def test_item_pickup_protected_drift(fault):
    w = World()

    def mutate():
        if fault == "money":
            w.raw = replace(w.raw, player_money=0)
        elif fault == "pp":
            w.raw = replace(w.raw, party_pp=((1, 1, 1, 1),))
        elif fault == "bag":
            w.raw = replace(w.raw, bag_items=((245, 1),))
        else:
            w.raw = replace(w.raw, battle_state=1)

    w.mutation = mutate
    with pytest.raises(RuntimeError):
        collect_visible_field_item(w, w, TARGET)


def machine(monkeypatch):
    import pokemon_red_completion.lavender as menus
    import pokemon_red_completion.red_machine_teaching as m
    import pokemon_red_completion.surge as surge

    w = World()
    w.raw = replace(w.raw, bag_items=((3, 20), (245, 1)))
    monkeypatch.setattr(m, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        m, "RedPracticeCartridge", lambda _: NS(species=lambda _: NS(tmhm_moves=(86,)))
    )
    monkeypatch.setattr(menus, "_open_bag", lambda *_: None)
    monkeypatch.setattr(menus, "_select_bag_item", lambda *_: None)
    monkeypatch.setattr(menus, "_close_menus", lambda *_: None)
    monkeypatch.setattr(menus, "_select_cursor", lambda _a, _e, slot, _t: w.choices.append(slot))

    def pulse(*args, **kwargs):
        w.count += 1
        if w.phase is None:
            w.phase = ("party", 0)
        elif w.phase[0] == "party":
            w.phase = ("forget", 0)
        else:
            w.phase = None
            w.raw = replace(
                w.raw,
                party_moves=((86, 28, 98, 84),),
                party_pp=((20, 15, 30, 30),),
                bag_items=((3, 20),),
            )
            w.mutation()

    monkeypatch.setattr(surge, "_pulse", pulse)
    return w


def test_explicit_tm_replacement_with_exact_pp_and_inventory(monkeypatch):
    w = machine(monkeypatch)
    lesson = plan_machine_lesson(b"rom", w, item_id=245, party_slot=1, replace_slot=1)
    execute_machine_lesson(w, w, w, lesson, rom=b"rom")
    assert w.choices == [0, 0] and w.raw.party_moves[0][0] == 86


@pytest.mark.parametrize("item,move,pp", [(196, 15, 30), (245, 86, 20)])
def test_empty_slot_lesson_preserves_hm_but_consumes_tm(monkeypatch, item, move, pp):
    import pokemon_red_completion.red_machine_teaching as m
    import pokemon_red_completion.surge as surge

    w = machine(monkeypatch)
    bag = ((item, 1),)
    w.raw = replace(w.raw, party_moves=((33, 0, 0, 0),), party_pp=((35, 0, 0, 0),), bag_items=bag)
    monkeypatch.setattr(
        m, "RedPracticeCartridge", lambda _: NS(species=lambda _: NS(tmhm_moves=(move,)))
    )

    def pulse(*a, **k):
        w.count += 1
        if w.phase is None:
            w.phase = ("party", 0)
        else:
            w.phase = None
            w.raw = replace(
                w.raw,
                party_moves=((33, move, 0, 0),),
                party_pp=((35, pp, 0, 0),),
                bag_items=bag if item < 201 else (),
            )

    monkeypatch.setattr(surge, "_pulse", pulse)
    lesson = plan_machine_lesson(b"rom", w, item_id=item, party_slot=1, replace_slot=2)
    execute_machine_lesson(w, w, w, lesson, rom=b"rom")
    assert w.choices == [0]
    assert w.raw.bag_items == (bag if item < 201 else ())


@pytest.mark.parametrize("moves,slot", [((33, 0, 0, 0), 3), ((33, 0, 28, 0), 2)])
def test_machine_rejects_noncontiguous_empty_slot(monkeypatch, moves, slot):
    w = machine(monkeypatch)
    w.raw = replace(w.raw, party_moves=(moves,))
    with pytest.raises(ValueError):
        plan_machine_lesson(b"rom", w, item_id=245, party_slot=1, replace_slot=slot)
    assert w.count == 0


@pytest.mark.parametrize("fault", ["owned", "compatible", "hm", "redundant", "slot", "partial"])
def test_tm_lesson_invalid_plan_zero_input(monkeypatch, fault):
    w = machine(monkeypatch)
    if fault == "owned":
        w.raw = replace(w.raw, bag_items=())
    elif fault == "compatible":
        import pokemon_red_completion.red_machine_teaching as m

        monkeypatch.setattr(
            m, "RedPracticeCartridge", lambda _: NS(species=lambda _: NS(tmhm_moves=()))
        )
    elif fault == "hm":
        w.raw = replace(w.raw, party_moves=((57, 28, 98, 84),))
    elif fault == "redundant":
        w.raw = replace(w.raw, party_moves=((86, 28, 98, 84),))
    elif fault == "partial":
        w.raw = replace(w.raw, party_moves=((33, 0, 0, 0),))
    with pytest.raises(ValueError):
        plan_machine_lesson(
            b"rom", w, item_id=245, party_slot=2 if fault == "slot" else 1, replace_slot=1
        )
    assert not w.count


@pytest.mark.parametrize("fault", ["pp", "money", "species"])
def test_tm_lesson_result_drift_not_success(monkeypatch, fault):
    w = machine(monkeypatch)
    lesson = plan_machine_lesson(b"rom", w, item_id=245, party_slot=1, replace_slot=1)

    def mutate():
        if fault == "pp":
            w.raw = replace(w.raw, party_pp=((1, 15, 30, 30),))
        elif fault == "money":
            w.raw = replace(w.raw, player_money=0)
        else:
            w.raw = replace(w.raw, party_species_ids=(28,))

    w.mutation = mutate
    with pytest.raises(RuntimeError):
        execute_machine_lesson(w, w, w, lesson, rom=b"rom")
