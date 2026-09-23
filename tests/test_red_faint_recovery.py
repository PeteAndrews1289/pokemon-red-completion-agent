from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _payload, _provider, _supply_transition_profile
from test_red_goal_skills import _ActionPort, _adapter, _raw, _Reader

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import ItemId, MenuCursorState
from pokemon_red_completion.red_faint_recovery import (
    FieldRecoveryChoice,
    RedFaintAwareFieldRestoreGoalProvider,
    RedFaintRecoveryError,
    field_bag_row,
    plan_faint_aware_recovery,
    verify_field_recovery,
)
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    bind_faint_aware_field_restore_profile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_skills import RedFieldRestoreGoalProvider


@pytest.mark.parametrize("count,row", [(6, 1), (7, 2)])
def test_start_layout_selects_item_without_assuming_pokedex(count, row):
    assert field_bag_row(MenuCursorState(0, 0, count, 11, 2)) == row


@pytest.mark.parametrize(
    "menu",
    [
        MenuCursorState(0, 0, 3, 5, 12),
        MenuCursorState(0, 0, 7, 10, 2),
        MenuCursorState(0, 0, 5, 11, 2),
        MenuCursorState(6, 0, 6, 11, 2),
    ],
)
def test_other_or_invalid_menus_are_not_start(menu):
    with pytest.raises(RedFaintRecoveryError, match="START"):
        field_bag_row(menu)


@pytest.mark.parametrize("count,row", [(6, 1), (7, 2)])
def test_bag_opener_uses_observed_cursor_and_confirms_only_item(monkeypatch, count, row):
    import pokemon_red_completion.red_faint_recovery as module

    cursor = [0]
    calls = []
    reader = SimpleNamespace(
        read_menu_cursor_state=lambda: MenuCursorState(cursor[0], 0, count, 11, 2)
    )

    def pulse(actions, kind, value=None, **kwargs):
        calls.append(kind)
        if kind is MacroActionKind.MOVE:
            cursor[0] += 1 if value == "down" else -1
        if kind is MacroActionKind.CONFIRM:
            assert cursor[0] == row

    monkeypatch.setattr(module, "_pulse", pulse)
    module._open_bag(None, reader, None, module.DEFAULT_LAVENDER_TIMING)
    assert calls == [MacroActionKind.OPEN_MENU] + [MacroActionKind.MOVE] * row + [
        MacroActionKind.CONFIRM
    ]


def raw_party(*, hp=(100, 0), maximum=(180, 101), status=(0, 0), bag=((53, 2), (18, 1))):
    return replace(
        _raw(hp=hp[0]),
        party_count=2,
        party_species_ids=(28, 97),
        party_levels=(45, 45),
        party_hp=hp,
        party_max_hp=maximum,
        party_status=status,
        party_moves=((57, 58, 55, 0),) * 2,
        party_pp=((15, 10, 5, 0),) * 2,
        bag_items=bag,
        bag_item_ids=tuple(i for i, _ in bag),
    )


def apply_choice(raw, choice):
    hp, status = list(raw.party_hp), list(raw.party_status)
    hp[choice.party_index], status[choice.party_index] = choice.expected_hp, choice.expected_status
    bag = tuple((i, left) for i, qty in raw.bag_items if (left := qty - int(i == choice.item)))
    return replace(
        raw,
        party_hp=tuple(hp),
        party_status=tuple(status),
        bag_items=bag,
        bag_item_ids=tuple(i for i, _ in bag),
    )


@pytest.mark.parametrize("maximum,expected", [(100, 50), (101, 50), (511, 255)])
def test_revive_exact_half_hp_preserves_status(maximum, expected):
    raw = raw_party(maximum=(180, maximum), status=(0, 8))
    choice = plan_faint_aware_recovery(raw)
    assert choice == FieldRecoveryChoice(1, ItemId.REVIVE, expected, 8)
    verify_field_recovery(choice, raw, apply_choice(raw, choice))


def test_partial_hp_recovery_and_fainted_sibling_are_supported_without_revive():
    raw = raw_party(bag=((20, 1),))
    choice = plan_faint_aware_recovery(raw)
    assert choice == FieldRecoveryChoice(0, ItemId.POTION, 120, 0)
    verify_field_recovery(choice, raw, apply_choice(raw, choice))


@pytest.mark.parametrize(
    "changes",
    [
        {"party_hp": (0, 0)},
        {"party_hp": (True, 0)},
        {"party_hp": (-1, 0)},
        {"party_hp": (181, 0)},
        {"party_max_hp": (180, 1)},
        {"party_status": (0,)},
        {"party_count": True},
        {"party_count": 7},
        {"battle_state": 2},
        {"bag_items": ((53, 1), (53, 2))},
        {"bag_items": ((53, 0),)},
        {"bag_items": ((53, True),)},
        {"bag_items": None},
    ],
)
def test_malformed_or_blackout_boundary_rejected(changes):
    with pytest.raises(RedFaintRecoveryError):
        plan_faint_aware_recovery(replace(raw_party(), **changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"player_money": 123},
        {"party_hp": (99, 50)},
        {"party_hp": (100, 101)},
        {"party_status": (8, 0)},
        {"party_pp": ((1, 0, 0, 0),) * 2},
        {"party_moves": ((33, 0, 0, 0),) * 2},
        {"party_levels": (46, 45)},
        {"party_species_ids": (28, 98)},
        {"party_max_hp": (181, 101)},
        {"map_id": 2},
        {"player_x": 99},
        {"battle_state": 2},
        {"bag_items": ((18, 1),)},
        {"bag_items": ((53, 1),)},
        {"bag_item_ids": (18, 53)},
    ],
)
def test_verifier_rejects_wrong_effect_or_unrelated_mutation(changes):
    raw = raw_party()
    choice = plan_faint_aware_recovery(raw)
    with pytest.raises(RedFaintRecoveryError):
        verify_field_recovery(choice, raw, replace(apply_choice(raw, choice), **changes))


def fixture(monkeypatch, *, fault=None):
    reader = _Reader(raw=raw_party(), ready=True)
    port = _ActionPort(reader)
    provider = RedFaintAwareFieldRestoreGoalProvider(
        CountingExecutor(port), reader, port, _adapter(reader)
    )
    calls = []
    import pokemon_red_completion.red_faint_recovery as module

    for name in ("_open_bag", "_select_bag_item", "_select_cursor"):
        monkeypatch.setattr(module, name, lambda *args, **kwargs: None)

    def pulse(actions, *args, **kwargs):
        calls.append("confirm")
        actions.execute(MacroAction(MacroActionKind.WAIT))
        if len(calls) == 3 and fault != "unconsumed":
            reader.raw = apply_choice(reader.raw, plan_faint_aware_recovery(reader.raw))
            if fault == "wrong_hp":
                reader.raw = replace(reader.raw, party_hp=(100, 51))
            if fault == "double_spend":
                reader.raw = replace(reader.raw, bag_items=((18, 1),), bag_item_ids=(18,))

    monkeypatch.setattr(module, "_pulse", pulse)
    monkeypatch.setattr(module, "_close_menus", lambda *args, **kwargs: None)
    return provider, reader, calls


def test_actual_offer_is_single_use_and_verifies_partial_revive(monkeypatch):
    provider, reader, calls = fixture(monkeypatch)
    offer = provider.offer(provider.adapter.observe())
    assert offer.binding is not None and not calls
    report = offer.binding.execute()
    assert provider.actions.actions_executed == 3
    assert reader.raw.party_hp == (100, 50)
    assert report.evidence["learned_authority"] == "goal_choice_only"
    assert not report.evidence["whole_party_restored"]
    assert offer.binding.verify(report).status.value == "succeeded"
    with pytest.raises(RedFaintRecoveryError, match="already consumed"):
        offer.binding.execute()
    assert len(calls) == 3


@pytest.mark.parametrize("fault", ["wrong_hp", "double_spend", "unconsumed"])
def test_item_error_never_retries_a_consumed_item(monkeypatch, fault):
    provider, reader, calls = fixture(monkeypatch, fault=fault)
    binding = provider.offer(provider.adapter.observe()).binding
    with pytest.raises(RedFaintRecoveryError):
        binding.execute()
    assert len(calls) == (27 if fault == "unconsumed" else 3)
    with pytest.raises(RedFaintRecoveryError, match="already consumed"):
        binding.execute()


def test_stale_offer_fails_before_input_and_stays_consumed(monkeypatch):
    provider, reader, calls = fixture(monkeypatch)
    binding = provider.offer(provider.adapter.observe()).binding
    reader.raw = replace(reader.raw, player_money=22)
    with pytest.raises(RedFaintRecoveryError, match="origin changed"):
        binding.execute()
    with pytest.raises(RedFaintRecoveryError, match="already consumed"):
        binding.execute()
    assert not calls


def test_legacy_rejects_faints_and_opt_in_factory_preserves_other_providers(monkeypatch):
    provider, reader, calls = fixture(monkeypatch)
    observation = provider.adapter.observe()
    assert (
        RedFieldRestoreGoalProvider._plan(observation, affordable_single_item=True)[1]
        is GoalUnavailableReason.MISSING_CAPABILITY
    )
    original = _supply_transition_profile()
    updated = bind_faint_aware_field_restore_profile(original)
    assert original.providers[1].parameters == {}
    assert updated.providers[0] == original.providers[0]
    assert updated.providers[2:] == original.providers[2:]
    runtime = SimpleNamespace(reader=reader, emulator=provider.emulator, adapter=provider.adapter)
    bound = _build_provider(runtime, updated.providers[1], provider.actions)
    assert isinstance(bound, RedFaintAwareFieldRestoreGoalProvider)
    assert bound.offer(observation).binding is not None
    assert not calls


@pytest.mark.parametrize(
    "params",
    [
        {"affordable_single_item": True, "allow_fainted_recovery": 1},
        {"affordable_single_item": False, "allow_fainted_recovery": True},
        {"affordable_single_item": True, "allow_fainted_recovery": False},
        {
            "affordable_single_item": True,
            "allow_fainted_recovery": True,
            "include_pp_fallback": True,
        },
    ],
)
def test_ambiguous_or_conflicting_profile_rejected(params):
    with pytest.raises(RedGoalContextProfileError):
        parse_red_goal_context_profile(
            _payload(_provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, params))
        )
