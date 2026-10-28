from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_goal_skills import _raw, _Reader
from test_red_live_option_menu import _ordinary_bindings, _situation

import pokemon_red_completion.red_player_owned_machines as module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_machine_teaching import RedMachineLesson
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def fixture(monkeypatch, fault=None):
    raw = replace(_raw(), bag_items=((211, 2), (4, 3)), bag_item_ids=(211, 4),
                  party_moves=((70, 39, 145, 57),), party_pp=((15, 30, 30, 1),))
    reader = _Reader(raw=raw, ready=True)
    reader.read_pc_items = lambda: ()
    em = N(state=b"source", frame_count=0, pressed_buttons=(), exp=12345)
    em.save_state_bytes = lambda: em.state
    seen = []

    def action(a):
        seen.append(a)
        em.frame_count += a.repeat

    actions = CountingExecutor(N(execute=action))
    rt = N(reader=reader, emulator=em)
    monkeypatch.setattr(module, "PokemonRedPartyReader",
        lambda _em: N(read=lambda: N(members=(N(experience=em.exp),))))

    def plan(_rom, received, *, item_id, party_slot, replace_slot):
        assert received is reader
        if item_id != 211 or party_slot != 1 or replace_slot not in (2, 3):
            raise ValueError("incompatible/HM/wrong slot")
        return RedMachineLesson(item_id, party_slot, replace_slot, 28,
                                reader.raw.party_moves[0], 61)

    monkeypatch.setattr(module, "plan_machine_lesson", plan)

    def execute(_em, executor, _reader, lesson, *, rom):
        assert rom == b"fixture" and _em is em
        executor.execute(MacroAction(MacroActionKind.WAIT))
        moves, pp = list(reader.raw.party_moves[0]), list(reader.raw.party_pp[0])
        moves[lesson.replace_slot - 1], pp[lesson.replace_slot - 1] = 61, 20
        reader.raw = replace(reader.raw, party_moves=(tuple(moves),), party_pp=(tuple(pp),),
                             bag_items=((211, 1), (4, 3)))
        em.state = b"terminal"
        if fault == "cash":
            reader.raw = replace(reader.raw, player_money=123)
        elif fault == "hp":
            reader.raw = replace(reader.raw, party_hp=(179,))
        elif fault == "level":
            reader.raw = replace(reader.raw, party_levels=(56,))
        elif fault == "pp":
            reader.raw = replace(reader.raw, party_pp=((14, 20, 30, 1),))
        elif fault == "bag":
            reader.raw = replace(reader.raw, bag_items=((211, 1), (4, 2)))
        elif fault == "experience":
            em.exp += 1
        elif fault == "pc":
            reader.read_pc_items = lambda: ((211, 1),)
        elif fault == "input":
            raise RuntimeError("input failed")

    monkeypatch.setattr(module, "execute_machine_lesson", execute)
    return rt, actions, seen


def test_inventory_is_read_only_distinct_and_preserves_hms(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")
    assert len(rows) == 2 and not seen and rt.emulator.state == b"source"
    assert all(r.binding.kind is GoalKind.DEVELOP_TEAM for r in rows)
    assert len({r.binding.binding_ref for r in rows}) == 2
    assert len({r.candidate.features.dependency_unlock_gain for r in rows}) == 2
    assert all(r.candidate.features.completion_gain == 0 for r in rows)
    assert all(r.candidate.challenge.combat_required is False for r in rows)


def test_machine_rows_pass_the_actual_mixed_policy_boundary(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")
    options = build_red_live_option_set(
        situation=_situation(resources=0.1),
        binding_set=_ordinary_bindings([]),
        supplements=rows,
        model_feature_version=7,
        ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(58, ()),
        target_cash=0,
        force_resource_safety=False,
    )
    assert {r.binding.binding_ref for r in rows} <= {
        binding.binding_ref for binding in options.bindings
    }
    assert not seen and rt.emulator.state == b"source"


def test_machine_receipt_consumes_exactly_one_owned_item_and_preserves_progress(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    row = module.owned_machine_options(rt, actions, rom=b"fixture")[0]
    report = row.binding.execute()
    assert row.binding.verify(report).status.value == "succeeded"
    assert report.evidence["machine_consumed"] == 1
    assert report.evidence["xp_gained"] == report.evidence["registrations_gained"] == 0
    assert not report.evidence["objective_completed"]
    assert rt.reader.raw.party_moves[0] == (70, 61, 145, 57)
    assert rt.reader.raw.party_pp[0] == (15, 20, 30, 1)
    assert actions.actions_executed == 1
    with pytest.raises(ValueError, match="stale or consumed"):
        row.binding.execute()
    assert len(seen) == 1
    rt.emulator.state = b"changed"
    assert row.binding.verify(report).status.value == "failed"


@pytest.mark.parametrize("fault", ["cash", "hp", "level", "pp", "bag", "experience", "pc", "input"])
def test_failed_or_unexplained_machine_effects_are_not_retried(monkeypatch, fault):
    rt, actions, seen = fixture(monkeypatch, fault)
    binding = module.owned_machine_options(rt, actions, rom=b"fixture")[0].binding
    with pytest.raises(RuntimeError):
        binding.execute()
    with pytest.raises(ValueError, match="stale or consumed"):
        binding.execute()
    assert len(seen) == 1


@pytest.mark.parametrize("fault", ["start", "unready", "battle", "held", "stale"])
def test_machine_boundary_never_guesses_control_or_reuses_stale_offer(monkeypatch, fault):
    rt, actions, seen = fixture(monkeypatch)
    binding = module.owned_machine_options(rt, actions, rom=b"fixture")[0].binding
    if fault == "start":
        rt.reader.start_menu = True
    elif fault == "unready":
        rt.reader.ready = False
    elif fault == "battle":
        rt.reader.raw = replace(rt.reader.raw, battle_state=2)
    elif fault == "held":
        rt.emulator.pressed_buttons = ("a",)
    else:
        rt.emulator.state = b"changed"
    if fault != "stale":
        assert module.owned_machine_options(rt, actions, rom=b"fixture") == ()
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not seen


def test_machine_rows_use_the_same_cached_inventory_and_descriptor_guards(monkeypatch):
    rt, actions, _ = fixture(monkeypatch)
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")
    base = _ordinary_bindings([])
    inventory = NativeStoryBranchInventory(lambda *_: base, lambda *_: (),
                                          enumerate_owned_machines=lambda *_: rows)
    observation = N(situation=_situation())
    ordinary = inventory.enumerate(rt, actions, observation)
    extra = inventory.supplements(rt, actions, observation, ordinary)
    assert extra == rows
    descriptors = inventory.challenges(rt, ordinary, extra, N(state=b"source"))
    assert set(descriptors) == {r.binding.binding_ref for r in rows}
    with pytest.raises(ValueError, match="observed executors"):
        inventory.challenges(rt, ordinary, extra, N(state=b"other"))


@pytest.mark.parametrize("fault", ["mutable", "kind", "duplicate", "mutation"])
def test_invalid_or_mutating_machine_inventory_fails_closed(monkeypatch, fault):
    rt, actions, _ = fixture(monkeypatch)
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")

    def machines(*_):
        if fault == "mutation":
            rt.emulator.state = b"other"
        if fault == "mutable":
            return list(rows)
        if fault == "kind":
            return (replace(rows[0], binding=replace(rows[0].binding, kind=GoalKind.RESUPPLY, cash_outcome=None)),)
        return (rows[0], rows[0]) if fault == "duplicate" else rows

    inventory = NativeStoryBranchInventory(lambda *_: _ordinary_bindings([]), lambda *_: (),
                                          enumerate_owned_machines=machines)
    with pytest.raises(ValueError):
        inventory.enumerate(rt, actions, N(situation=_situation()))
    assert inventory._observed is None


def test_capacity_is_not_damage_and_does_not_value_unexpressible_status_or_ohko():
    assert module.direct_attack_capacity(28, (39, 32, 120, 0), (30, 5, 5, 0)) == 0
    assert module.direct_attack_capacity(28, (61, 0, 0, 0), (20, 0, 0, 0)) == 1950

def fly_fixture(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, bag_items=((197, 1), (4, 3)), badge_bits=255)

    def plan(_rom, reader, *, item_id, party_slot, replace_slot):
        if item_id != 197 or party_slot != 1 or replace_slot not in (2, 3):
            raise ValueError("incompatible, redundant or HM")
        return RedMachineLesson(item_id, party_slot, replace_slot, 28,
                                reader.raw.party_moves[0], 19)
    monkeypatch.setattr(module, "plan_machine_lesson", plan)

    def execute(em, executor, reader, lesson, *, rom):
        executor.execute(MacroAction(MacroActionKind.WAIT))
        moves, pp = list(reader.raw.party_moves[0]), list(reader.raw.party_pp[0])
        moves[lesson.replace_slot-1], pp[lesson.replace_slot-1] = 19, 15
        reader.raw = replace(reader.raw, party_moves=(tuple(moves),), party_pp=(tuple(pp),))
        em.state = b"terminal-fly"
    monkeypatch.setattr(module, "execute_machine_lesson", execute)
    return rt, actions, seen


def test_fly_lesson_is_default_off_and_explicit_dependency_not_attack_gain(monkeypatch):
    rt, actions, seen = fly_fixture(monkeypatch)
    assert module.owned_machine_options(rt, actions, rom=b"fixture") == ()
    rows = module.owned_machine_options(rt, actions, rom=b"fixture",
                                       include_fly_lesson=True, include_attack_lessons=False)
    assert len(rows) == 2 and not seen
    assert all(r.candidate.features.dependency_unlock_gain == 1 for r in rows)
    report = rows[0].binding.execute()
    assert rows[0].binding.verify(report).status.value == "succeeded"
    assert dict(rt.reader.raw.bag_items) == {197: 1, 4: 3}
    assert report.evidence["machine_consumed"] == 0
    assert report.evidence["field_move_unlocked"] == 19
    assert rt.reader.raw.party_moves[0] == (70, 19, 145, 57)
    assert module.owned_machine_options(rt, actions, rom=b"fixture",
                                       include_fly_lesson=True) == ()


def test_fly_lesson_requires_real_badge_and_never_substitutes_a_compatible_member(monkeypatch):
    rt, actions, seen = fly_fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, badge_bits=0)
    assert module.owned_machine_options(rt, actions, rom=b"fixture",
                                       include_fly_lesson=True) == ()
    rt.reader.raw = replace(rt.reader.raw, badge_bits=255)
    monkeypatch.setattr(module, "plan_machine_lesson",
                        lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("incompatible")))
    assert module.owned_machine_options(rt, actions, rom=b"fixture",
                                       include_fly_lesson=True) == ()
    assert not seen


@pytest.mark.parametrize("option", ["include_fly_lesson", "include_attack_lessons"])
def test_machine_permissions_are_explicit_booleans(monkeypatch, option):
    rt, actions, _ = fixture(monkeypatch)
    with pytest.raises(ValueError, match="permissions"):
        module.owned_machine_options(rt, actions, rom=b"fixture", **{option: 1})


def test_pp_capacity_decrease_does_not_hide_legal_move_tradeoff(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    moves, pp = (44, 39, 61, 55), (25, 30, 20, 25)
    rt.reader.raw = replace(rt.reader.raw, bag_items=((213, 1),),
        bag_item_ids=(213,), party_moves=(moves,), party_pp=(pp,))

    def plan(_rom, reader, *, item_id, party_slot, replace_slot):
        if (item_id, party_slot, replace_slot) != (213, 1, 4):
            raise ValueError("incompatible, redundant or protected slot")
        return RedMachineLesson(item_id, party_slot, replace_slot, 28, moves, 58)

    monkeypatch.setattr(module, "plan_machine_lesson", plan)
    assert module.direct_attack_capacity(28, moves, pp) == 4950
    assert module.direct_attack_capacity(28, (44, 39, 61, 58), (25, 30, 20, 10)) == 4400
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")
    assert len(rows) == 1 and not seen and rt.emulator.state == b"source"
    row = rows[0]
    assert row.candidate.features.completion_gain == 0
    assert row.candidate.features.dependency_unlock_gain == 0
    assert row.candidate.challenge.opposition_known is False
    assert row.binding.maximum_cash_debit == 0
    assert rt.reader.raw.bag_items == ((213, 1),)


def test_depleted_replacement_still_has_finite_nonnegative_descriptive_gain(monkeypatch):
    rt, actions, seen = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, party_pp=((0, 0, 0, 0),))
    rows = module.owned_machine_options(rt, actions, rom=b"fixture")
    assert len(rows) == 2 and not seen
    assert all(0 <= r.candidate.features.dependency_unlock_gain <= 1 for r in rows)
