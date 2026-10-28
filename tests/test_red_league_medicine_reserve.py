"""The temporary rule buys native medicine; it never becomes learned authority."""

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_player_league_options as module
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
    require_resupply_only_profile_transition,
)
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


@dataclass
class Runtime:
    profile: object
    reader: object


def runtime(full=0, revives=0, cash=15000, location=MapId.INDIGO_PLATEAU_LOBBY,
            full_heals=0):
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="medicine-safeguard-test", providers=(
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE, {}),
            (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, dict(
                map_id=int(MapId.INDIGO_PLATEAU_LOBBY), player_x=2, player_y=5,
                interaction_direction="left", affordable_ball_purchase=True,
                resource_choice_variants=True, purchases=[dict(absolute_index=0,
                    item_id=2, quantity=5, unit_price=1200)],
            )),
            (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
        ),
    ))
    raw = SimpleNamespace(bag_items=((16, full), (53, revives), (52, full_heals)),
                          player_money=cash,
                          map_id=int(location), battle_state=0, event_flags=bytes(320))
    return Runtime(profile, SimpleNamespace(read=lambda: raw))


@pytest.mark.parametrize("full,revives,count", [(0, 0, 4), (3, 0, 3), (4, 1, 1), (4, 2, 0)])
def test_supported_lots_preserve_all_other_providers(full, revives, count):
    rt = runtime(full, revives)
    original = rt.profile
    profiles = module.league_medicine_profiles(rt)
    assert len(profiles) == count and rt.profile is original
    for profile in profiles:
        require_resupply_only_profile_transition(original, profile)
        parameters = _thaw(profile.providers[1].parameters)
        purchase = parameters["purchases"][0]
        assert purchase["item_id"] in (16, 53)
        assert purchase["absolute_index"] == {16: 2, 53: 5}[purchase["item_id"]]
        assert purchase["unit_price"] == {16: 3000, 53: 1500}[purchase["item_id"]]
        assert "affordable_ball_purchase" not in parameters
        assert "resource_choice_variants" not in parameters
    assert original.providers[1].parameters["purchases"][0]["item_id"] == 2


@pytest.mark.parametrize("target", [True, None, -1, 100, "4"])
def test_reserve_targets_are_explicit_stack_counts(target):
    with pytest.raises(ValueError, match="integer stack"):
        module.league_medicine_profiles(runtime(), full_restore_target=target)


def test_shop_indices_cannot_be_reused_for_another_mart():
    rt = runtime()
    providers = []
    for spec in rt.profile.providers:
        parameters = _thaw(spec.parameters)
        if spec.kind is GoalKind.RESUPPLY:
            parameters["map_id"] = int(MapId.CERULEAN_MART)
        providers.append((spec.kind, spec.mechanic, parameters))
    rt.profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=rt.profile.profile_id, providers=tuple(providers),
    ))
    with pytest.raises(ValueError, match="configured Indigo"):
        module.league_medicine_profiles(rt)


def selector(monkeypatch, rt, *, fault=None, frontier=True, balanced=False,
             full_heal_target=0, revive_target=2, minimum_revive_coverage=0):
    monkeypatch.setattr(module, "_field_ready", lambda _: True)
    monkeypatch.setattr(module, "live_league_player_target", lambda *_a, **_kw:
                        module.LEAGUE_PLAYER_TARGETS[0] if frontier else None)

    class Router:
        def __init__(self, supplied, *_args, **_kwargs):
            self.runtime = supplied

        def enumerate_routed_kinds(self, *_args):
            raw = self.runtime.reader.read()
            spec = self.runtime.profile.providers[1].parameters["purchases"][0]
            held = dict(raw.bag_items).get(spec["item_id"], 0)
            quantity, price = spec["quantity"], spec["unit_price"]
            if raw.player_money < quantity * price:
                return SimpleNamespace(bindings=())
            reserve = GoalResourceReserve("recovery", held, held + quantity, quantity)
            quote = GoalResourceQuote(raw.player_money, quantity * price, (reserve,))
            if fault == "funds":
                quote = replace(quote, available_funds=raw.player_money + 1)
            if fault == "class":
                quote = replace(quote, reserves=(replace(reserve, resource="capture"),))
            if fault == "stock":
                quote = replace(quote, reserves=(replace(reserve, available=held + 1),))
            binding = SimpleNamespace(kind=GoalKind.RESUPPLY, resource_quote=quote,
                                      item_id=spec["item_id"], quantity=quantity)
            return SimpleNamespace(bindings=(binding,))

    monkeypatch.setattr(module, "RedResourceGoalRouter", Router)
    records = []
    binding = module.league_medicine_reserve_binding(
        rt, None, route_world=None, observation=SimpleNamespace(input_ready=True),
        balanced_first_lots=balanced,
        full_heal_target=full_heal_target,
        revive_target=revive_target, minimum_revive_coverage=minimum_revive_coverage,
        record=lambda name, value: records.append((name, value)),
    )
    return binding, records


@pytest.mark.parametrize("cash,item,quantity", [(9000, 16, 2), (4000, 16, 1), (2000, 53, 1)])
def test_only_actual_affordable_lots_are_selected(monkeypatch, cash, item, quantity):
    rt = runtime(cash=cash)
    binding, records = selector(monkeypatch, rt)
    assert (binding.item_id, binding.quantity) == (item, quantity)
    assert not records[0][1]["learned_procurement"]
    assert not records[0][1]["reserve_satisfied"]
    assert rt.reader.read().player_money == cash


@pytest.mark.parametrize("cash,full,revives,item,quantity", [
    (6393, 0, 0, 53, 1), (4893, 0, 1, 16, 1), (1893, 1, 1, 53, 1),
    (4500, 0, 0, 53, 1), (3000, 0, 1, 16, 1), (6000, 2, 0, 53, 1),
    (4500, 2, 1, 16, 1), (2000, 0, 0, 53, 1),
])
def test_balanced_opt_in_covers_missing_roles_before_topping_up(
    monkeypatch, cash, full, revives, item, quantity,
):
    rt = runtime(full=full, revives=revives, cash=cash)
    binding, records = selector(monkeypatch, rt, balanced=True)
    assert (binding.item_id, binding.quantity) == (item, quantity)
    assert binding.resource_quote.purchase_cost <= cash
    assert records[0][1]["balanced_first_lots"] is True
    assert records[0][1]["learned_procurement"] is False
    assert rt.reader.read().player_money == cash


def test_balanced_coverage_remains_pre_entry_only(monkeypatch):
    assert selector(monkeypatch, runtime(location=MapId.LORELEIS_ROOM), balanced=True)[0] is None
    assert selector(monkeypatch, runtime(), frontier=False, balanced=True)[0] is None


def test_balanced_coverage_permission_is_not_coerced():
    with pytest.raises(TypeError, match="explicit boolean"):
        module.league_medicine_reserve_binding(
            None, None, route_world=None, observation=None, balanced_first_lots=1,
        )


@pytest.mark.parametrize("cash,full,revives,cures,item,quantity", [
    (4500, 0, 0, 2, 53, 1), (3000, 0, 1, 2, 16, 1),
    (6000, 1, 1, 2, 53, 2), (1500, 1, 5, 2, 53, 1),
    (6000, 1, 6, 2, 16, 2), (3600, 1, 1, 0, 52, 1),
])
def test_extended_revival_coverage_keeps_first_hp_then_covers_later_faints(
    monkeypatch, cash, full, revives, cures, item, quantity,
):
    rt = runtime(full=full, revives=revives, cash=cash, full_heals=cures)
    binding, records = selector(monkeypatch, rt, balanced=True, revive_target=6,
                                full_heal_target=2, minimum_revive_coverage=6)
    assert (binding.item_id, binding.quantity) == (item, quantity)
    assert binding.resource_quote.purchase_cost == quantity * {16: 3000, 53: 1500, 52: 600}[item]
    assert binding.resource_quote.purchase_cost <= cash
    assert records[0][1]["minimum_revive_coverage"] == 6
    assert not records[0][1]["learned_procurement"]
    assert rt.reader.read().player_money == cash


def test_fixed_cash_coverage_does_not_claim_future_income_or_satisfied_hp_reserve(monkeypatch):
    rt = runtime(cash=13000, full_heals=2)
    raw = rt.reader.read()
    lots = []
    for _ in range(12):
        binding, records = selector(monkeypatch, rt, balanced=True, revive_target=6,
                                    full_heal_target=2, minimum_revive_coverage=6)
        if binding is None:
            break
        lots.append((binding.item_id, binding.quantity))
        stock = dict(raw.bag_items)
        stock[binding.item_id] += binding.quantity
        raw.bag_items = tuple(stock.items())
        raw.player_money -= binding.resource_quote.purchase_cost
    else:
        pytest.fail("finite actual coverage did not settle")
    assert lots == [(53, 1), (16, 1), (53, 2), (53, 2), (53, 1)]
    assert dict(raw.bag_items) == {16: 1, 53: 6, 52: 2} and raw.player_money == 1000
    assert not records[0][1]["reserve_satisfied"]
    assert not records[0][1]["purchase_available"]


@pytest.mark.parametrize("coverage", [True, None, -1, 7, "6", 1.5])
def test_extended_revive_coverage_rejects_implicit_or_excessive_counts(coverage):
    with pytest.raises(ValueError, match="balanced explicit stack"):
        module.league_medicine_reserve_binding(
            None, None, route_world=None, observation=None, balanced_first_lots=True,
            revive_target=6, minimum_revive_coverage=coverage,
        )


def test_extended_revive_coverage_requires_opt_in_and_keeps_locked_room_guard(monkeypatch):
    with pytest.raises(ValueError, match="balanced explicit stack"):
        selector(monkeypatch, runtime(), revive_target=6, minimum_revive_coverage=6)
    assert selector(monkeypatch, runtime(location=MapId.LORELEIS_ROOM), balanced=True,
                    revive_target=6, minimum_revive_coverage=6)[0] is None
    assert selector(monkeypatch, runtime(), frontier=False, balanced=True,
                    revive_target=6, minimum_revive_coverage=6)[0] is None
    # A larger declared target alone must not change default purchase ordering.
    binding, _ = selector(monkeypatch, runtime(full=1, revives=1), balanced=True,
                          revive_target=6)
    assert (binding.item_id, binding.quantity) == (16, 2)


def test_opted_in_full_heal_uses_actual_indigo_slot_and_price():
    profiles = module.league_medicine_profiles(runtime(), full_heal_target=2)
    purchases = [profile.providers[1].parameters["purchases"][0] for profile in profiles]
    cures = [purchase for purchase in purchases if purchase["item_id"] == 52]
    assert [(p["absolute_index"], p["quantity"], p["unit_price"]) for p in cures] == [
        (4, 1, 600), (4, 2, 600),
    ]
    assert {p["item_id"] for p in purchases} == {16, 53, 52}
    assert len(module.league_medicine_profiles(runtime())) == 4


@pytest.mark.parametrize("target", [True, None, -1, 100, "2"])
def test_status_reserve_target_is_an_explicit_stack_count(target):
    with pytest.raises(ValueError, match="integer stack"):
        module.league_medicine_profiles(runtime(), full_heal_target=target)


@pytest.mark.parametrize("cash,full,revives,cures,item,quantity", [
    (1722, 2, 1, 0, 52, 1), (1122, 2, 1, 1, 52, 1),
    (4500, 0, 0, 0, 53, 1), (3000, 0, 1, 0, 16, 1),
    (2000, 0, 0, 0, 53, 1), (600, 2, 1, 0, 52, 1),
])
def test_status_cure_coverage_preserves_first_hp_and_revive_lots(
    monkeypatch, cash, full, revives, cures, item, quantity,
):
    rt = runtime(full=full, revives=revives, cash=cash, full_heals=cures)
    binding, records = selector(monkeypatch, rt, balanced=True, full_heal_target=2)
    assert (binding.item_id, binding.quantity) == (item, quantity)
    assert binding.resource_quote.purchase_cost <= cash
    assert records[0][1]["supplied_targets"]["full_heal"] == 2
    assert records[0][1]["learned_procurement"] is False
    assert rt.reader.read().player_money == cash


def test_status_cure_reserve_is_pre_entry_only_and_never_fakes_completion(monkeypatch):
    assert selector(monkeypatch, runtime(location=MapId.AGATHAS_ROOM),
                    balanced=True, full_heal_target=2)[0] is None
    binding, records = selector(monkeypatch, runtime(full=4, revives=2, cash=599),
                                balanced=True, full_heal_target=2)
    assert binding is None and not records[0][1]["reserve_satisfied"]
    assert not records[0][1]["purchase_available"]
    binding, records = selector(monkeypatch, runtime(full=4, revives=2, full_heals=2),
                                balanced=True, full_heal_target=2)
    assert binding is None and records[0][1]["reserve_satisfied"]


@pytest.mark.parametrize("fault", ["funds", "class", "stock"])
def test_wrong_quotes_never_become_a_support_purchase(monkeypatch, fault):
    with pytest.raises(ValueError, match="actual affordable recovery"):
        selector(monkeypatch, runtime(), fault=fault)


def test_unaffordable_reserve_is_not_claimed_satisfied(monkeypatch):
    binding, records = selector(monkeypatch, runtime(cash=100))
    assert binding is None and not records[0][1]["reserve_satisfied"]
    assert not records[0][1]["purchase_available"]
    binding, records = selector(monkeypatch, runtime(full=4, revives=2))
    assert binding is None and records[0][1]["reserve_satisfied"]


def test_rule_does_not_admit_returning_from_a_locked_room(monkeypatch):
    assert selector(monkeypatch, runtime(location=MapId.LORELEIS_ROOM))[0] is None
    assert selector(monkeypatch, runtime(), frontier=False)[0] is None


def test_safeguard_permission_is_not_coerced():
    with pytest.raises(TypeError, match="explicit boolean"):
        module.league_medicine_reserve_binding(
            None, None, route_world=None, observation=None, development_retry_reentry=1,
        )


def native_binding(kind=GoalKind.RESUPPLY, resource="recovery"):
    return ExecutableGoalBinding("native-medicine", kind, .1, .1,
        lambda: GoalExecutionReport(0, 0, {}), lambda _: GoalVerification.succeeded(),
        resource_quote=GoalResourceQuote(15000, 6000, (
            GoalResourceReserve(resource, 0, 2, 2),
        )) if kind is GoalKind.RESUPPLY else None)


def base_inventory(binding):
    return GoalBindingSet((binding.opportunity, GoalOpportunity(
        "blocked", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
    )), (binding,))


def test_guard_exposes_exactly_one_support_binding_with_no_strategy_query():
    reserve = native_binding()
    base = base_inventory(native_binding(GoalKind.ADVANCE_STORY))
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: pytest.fail("no invented strategy menu during support"),
        enumerate_medicine_reserve=lambda *_: reserve,
    )
    observed = inventory.enumerate(rt, None, None)
    assert observed.bindings == (reserve,)
    assert sum(o.availability is GoalAvailability.AVAILABLE for o in observed.opportunities) == 1
    assert inventory.supplements(rt, None, None, observed) == ()
    assert inventory.challenges(rt, observed, (), SimpleNamespace(state=b"origin")) == {}


def test_satisfied_guard_returns_normal_strategy_and_control_recovery_has_priority():
    base = base_inventory(native_binding(GoalKind.ADVANCE_STORY))
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: (), enumerate_medicine_reserve=lambda *_: None,
    )
    # A fresh empty branch observer legitimately removes the stale story binding.
    assert inventory.enumerate(rt, None, SimpleNamespace(situation=None)).bindings == ()
    recovery = base_inventory(native_binding(GoalKind.RECOVER_CONTROL))
    inventory = NativeStoryBranchInventory(
        lambda *_: recovery, lambda *_: (),
        enumerate_medicine_reserve=lambda *_: pytest.fail("settle controls before shopping"),
    )
    observed = inventory.enumerate(rt, None, SimpleNamespace(situation=None))
    assert observed.bindings == recovery.bindings


@pytest.mark.parametrize("bad", ["untyped", "capture", "story"])
def test_guard_cannot_smuggle_another_supplied_strategy(bad):
    proposed = {"untyped": "not a binding", "capture": native_binding(resource="capture"),
                "story": native_binding(GoalKind.ADVANCE_STORY)}[bad]
    base = base_inventory(native_binding(GoalKind.ADVANCE_STORY))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: (), enumerate_medicine_reserve=lambda *_: proposed,
    )
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    with pytest.raises(ValueError, match="quoted native purchase"):
        inventory.enumerate(rt, None, None)


def test_guard_cannot_change_native_state_while_observing():
    state = [b"origin"]
    reserve = native_binding()
    def mutated(*_):
        state[0] = b"changed"
        return reserve
    inventory = NativeStoryBranchInventory(
        lambda *_: base_inventory(native_binding(GoalKind.ADVANCE_STORY)), lambda *_: (),
        enumerate_medicine_reserve=mutated,
    )
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: state[0]))
    with pytest.raises(ValueError, match="changed native state"):
        inventory.enumerate(rt, None, None)


@pytest.mark.parametrize("fault", (None, "remote", "locked", "restored", "unready", "blocked"))
def test_healing_support_is_only_a_real_first_room_indigo_nurse(monkeypatch, fault):
    rt = runtime(location=MapId.VERMILION_CITY if fault == "remote" else MapId.INDIGO_PLATEAU)
    rt.reader.read_league_challenge_started = lambda: True
    monkeypatch.setattr(module, "_field_ready", lambda _: fault != "unready")
    monkeypatch.setattr(module, "_raw_party_fully_restored", lambda _: fault == "restored")
    monkeypatch.setattr(module, "live_league_player_target", lambda *a, **k:
                        module.LEAGUE_PLAYER_TARGETS[1 if fault == "locked" else 0])
    original = replace(native_binding(GoalKind.RESTORE_TEAM), maximum_cash_debit=0)
    quoted = []
    def nurse(*args, **kwargs):
        quoted.append(kwargs)
        return None if fault == "blocked" else original
    monkeypatch.setattr(module, "routed_restoration_binding", nurse)
    records = []
    binding = module.league_pre_entry_healing_binding(
        rt, None, route="actual-route", development_retry_reentry=True,
        record=lambda name, value: records.append((name, value)))
    assert (binding is not None) is (fault is None)
    assert not records
    if fault in (None, "blocked"):
        assert quoted == [dict(home_map=174, route="actual-route", include_indigo_lobby=True,
                               observe_trainer_hazards=True)]
    else:
        assert not quoted
    if binding is not None:
        assert binding.kind is GoalKind.RESTORE_TEAM
        assert binding.binding_ref.startswith("league-pre-entry-healing:")
        report = binding.execute()
        assert report.evidence["learned_healing"] is False
        assert records[0][0] == "league-pre-entry-healing"
        assert binding.verify(report) == original.verify(report)


@pytest.mark.parametrize("anchor", [7,9])
def test_healthy_first_room_guard_requires_indigo_anchor_only_when_declared(monkeypatch,anchor):
    rt=runtime(location=MapId.INDIGO_PLATEAU)
    rt.reader.read_last_blackout_map=lambda:anchor
    rt.reader.read_league_challenge_started=lambda:False
    monkeypatch.setattr(module,"_field_ready",lambda _:True)
    monkeypatch.setattr(module,"_raw_party_fully_restored",lambda _:True)
    monkeypatch.setattr(module,"live_league_player_target",
        lambda *a,**k:module.LEAGUE_PLAYER_TARGETS[0])
    calls=[]
    original=replace(native_binding(GoalKind.RESTORE_TEAM),maximum_cash_debit=0)
    monkeypatch.setattr(module,"routed_restoration_binding",
        lambda *a,**k:calls.append(k) or original)
    binding=module.league_pre_entry_healing_binding(rt,None,route="native",
        development_retry_reentry=True,require_indigo_checkpoint=True)
    assert (binding is not None) is (anchor != 9)
    if anchor != 9:
        assert calls[0]["require_indigo_checkpoint"] is True
    else:
        assert not calls


def test_healing_guard_has_no_model_query_and_does_not_change_purchase_guard():
    healing = replace(native_binding(GoalKind.RESTORE_TEAM),
                      binding_ref="league-pre-entry-healing:native", maximum_cash_debit=0)
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    base = base_inventory(native_binding(GoalKind.ADVANCE_STORY))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: pytest.fail("nurse is disclosed support"),
        enumerate_league_healing=lambda *_: healing,
        enumerate_medicine_reserve=lambda *_: pytest.fail("heal before shopping"))
    observed = inventory.enumerate(rt, None, None)
    assert observed.bindings == (healing,)
    assert inventory.supplements(rt, None, None, observed) == ()
    assert inventory.challenges(rt, observed, (), SimpleNamespace(state=b"origin")) == {}


@pytest.mark.parametrize("bad", ("cash", "kind", "unscoped", "untyped"))
def test_healing_guard_refuses_unrelated_or_paid_supplied_actions(bad):
    proposed = replace(native_binding(GoalKind.RESTORE_TEAM),
                       binding_ref="league-pre-entry-healing:native", maximum_cash_debit=0)
    if bad == "cash":
        proposed = replace(proposed, maximum_cash_debit=1)
    elif bad == "kind":
        proposed = replace(proposed, kind=GoalKind.ADVANCE_STORY)
    elif bad == "unscoped":
        proposed = replace(proposed, binding_ref="ordinary-healing")
    else:
        proposed = "not a binding"
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    inventory = NativeStoryBranchInventory(
        lambda *_: base_inventory(native_binding(GoalKind.ADVANCE_STORY)), lambda *_: (),
        enumerate_league_healing=lambda *_: proposed)
    with pytest.raises(ValueError, match="free native nurse"):
        inventory.enumerate(rt, None, None)


def test_healing_support_does_not_preempt_control_recovery_or_mutate_enumeration():
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    control = base_inventory(native_binding(GoalKind.RECOVER_CONTROL))
    inventory = NativeStoryBranchInventory(
        lambda *_: control, lambda *_: (),
        enumerate_league_healing=lambda *_: pytest.fail("recover controls first"))
    observed = inventory.enumerate(rt, None, SimpleNamespace(situation=None))
    assert observed.bindings == control.bindings
    with pytest.raises(TypeError, match="explicit support observer"):
        NativeStoryBranchInventory(lambda *_: control, lambda *_: (), enumerate_league_healing=True)


@pytest.mark.parametrize("fault", (None, "remote", "locked", "unready",
                                   "space", "stock", "blocked"))
def test_medicine_capacity_stores_only_completed_keys_before_first_entry(monkeypatch, fault):
    from pokemon_red_completion import red_story_item_storage as storage

    rt = runtime(location=MapId.VERMILION_CITY if fault == "remote" else MapId.INDIGO_PLATEAU_LOBBY)
    raw = rt.reader.read()
    raw.bag_items = tuple((i, 1) for i in range(80, 100))
    if fault == "space":
        raw.bag_items = raw.bag_items[:18]
    elif fault == "stock":
        raw.bag_items = ((16, 4), (53, 2)) + raw.bag_items[:18]
    monkeypatch.setattr(module, "_field_ready", lambda _: fault != "unready")
    monkeypatch.setattr(module, "live_league_player_target", lambda *a, **k:
                        module.LEAGUE_PLAYER_TARGETS[1 if fault == "locked" else 0])
    original = replace(native_binding(GoalKind.MANAGE_STORAGE), maximum_cash_debit=0)
    calls, records = [], []
    def capacity(*args, **kwargs):
        calls.append(kwargs)
        return None if fault == "blocked" else original
    monkeypatch.setattr(storage, "completed_key_storage_binding", capacity)
    binding = module.league_medicine_capacity_binding(rt, None, route="native-route",
        observation=SimpleNamespace(input_ready=True),
        record=lambda name, value: records.append((name, value)))
    assert (binding is not None) is (fault is None)
    assert calls == ([dict(route="native-route", reserved_slots=2, include_indigo_lobby=True,
                          allow_spare_tm_storage=True)]
                     if fault in (None, "blocked") else [])
    assert not records
    if binding is not None:
        assert binding.binding_ref.startswith("league-medicine-capacity:")
        report = binding.execute()
        assert report.evidence["support"] == "approved_league_medicine_capacity"
        assert report.evidence["learned_item_selection"] is False
        assert records[0][0] == "league-medicine-capacity"
        assert binding.verify(report) == original.verify(report)


@pytest.mark.parametrize('full_heal_target', [0, 2])
def test_capacity_counts_explicit_status_reserve_without_changing_default(
    monkeypatch, full_heal_target,
):
    from pokemon_red_completion import red_story_item_storage as storage

    rt = runtime(location=MapId.INDIGO_PLATEAU_LOBBY)
    rt.reader.read().bag_items = ((16,4),(53,6))+tuple((i,1) for i in range(80,98))
    monkeypatch.setattr(module, '_field_ready', lambda _: True)
    monkeypatch.setattr(module, 'live_league_player_target',
                        lambda *_a, **_k: module.LEAGUE_PLAYER_TARGETS[0])
    calls=[]
    original=replace(native_binding(GoalKind.MANAGE_STORAGE),maximum_cash_debit=0)
    monkeypatch.setattr(storage,'completed_key_storage_binding',
        lambda *_a, **kwargs: calls.append(kwargs) or original)
    binding=module.league_medicine_capacity_binding(rt,None,route='native-route',
        observation=SimpleNamespace(input_ready=True),revive_target=6,
        full_heal_target=full_heal_target)
    assert (binding is not None) is bool(full_heal_target)
    assert [row['reserved_slots'] for row in calls] == ([1] if full_heal_target else [])


def test_capacity_guard_is_free_support_and_preserves_strategy_after_it():
    reserve = replace(native_binding(GoalKind.MANAGE_STORAGE),
                      binding_ref="league-medicine-capacity:native", maximum_cash_debit=0)
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: b"origin"))
    base = base_inventory(native_binding(GoalKind.ADVANCE_STORY))
    inventory = NativeStoryBranchInventory(
        lambda *_: base, lambda *_: pytest.fail("capacity is explicitly disclosed support"),
        enumerate_league_capacity=lambda *_: reserve,
        enumerate_medicine_reserve=lambda *_: pytest.fail("store keys before purchase"))
    observed = inventory.enumerate(rt, None, None)
    assert observed.bindings == (reserve,)
    assert inventory.supplements(rt, None, None, observed) == ()
    assert inventory.challenges(rt, observed, (), SimpleNamespace(state=b"origin")) == {}
    control = base_inventory(native_binding(GoalKind.RECOVER_CONTROL))
    inventory = NativeStoryBranchInventory(lambda *_: control, lambda *_: (),
        enumerate_league_capacity=lambda *_: pytest.fail("controls before PC"))
    observed = inventory.enumerate(rt, None, SimpleNamespace(situation=None))
    assert observed.bindings == control.bindings
    inventory = NativeStoryBranchInventory(lambda *_: base, lambda *_: (),
        enumerate_league_capacity=lambda *_: None)
    assert inventory.enumerate(rt, None, SimpleNamespace(situation=None)).bindings == ()


@pytest.mark.parametrize("fault", ("cash", "kind", "scope", "untyped", "mutated"))
def test_capacity_guard_does_not_admit_other_supplied_actions(fault):
    state = [b"origin"]
    binding = replace(native_binding(GoalKind.MANAGE_STORAGE),
                      binding_ref="league-medicine-capacity:native", maximum_cash_debit=0)
    if fault == "cash":
        binding = replace(binding, maximum_cash_debit=1)
    elif fault == "kind":
        binding = replace(binding, kind=GoalKind.ADVANCE_STORY)
    elif fault == "scope":
        binding = replace(binding, binding_ref="ordinary-storage")
    elif fault == "untyped":
        binding = "not a binding"
    def supplied(*_):
        if fault == "mutated":
            state[0] = b"changed"
        return binding
    inventory = NativeStoryBranchInventory(
        lambda *_: base_inventory(native_binding(GoalKind.ADVANCE_STORY)), lambda *_: (),
        enumerate_league_capacity=supplied)
    rt = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: state[0]))
    with pytest.raises(ValueError, match="changed native state|free native key storage"):
        inventory.enumerate(rt, None, None)


def test_capacity_permission_is_not_coerced():
    with pytest.raises(TypeError, match="explicit boolean"):
        module.league_medicine_capacity_binding(None, None, route=None, observation=None,
                                               development_retry_reentry=1)
    with pytest.raises(TypeError, match="explicit support observer"):
        NativeStoryBranchInventory(lambda *_: None, lambda *_: (), enumerate_league_capacity=True)
