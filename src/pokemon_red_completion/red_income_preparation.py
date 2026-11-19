"""Quote existing preparation for an otherwise unfundable earned rematch."""
from .red_learned_league import learned_league_controller
from .red_league_funding import RedLeagueFundingError
from .red_league_funding_execution import bind_red_league_funding_execution
from .red_resource_economy import red_economy_snapshot


def qualified_income_preparation_levels(
    runtime, actions, world, *, missing_reserve_cost, collection_cash_target,
    bootstrap_targets, ordinary_income_peers, party_ready,
):
    """Return quoted opposition; never choose a trainee, target level or input.

    Keep every existing entry/reserve qualifier. This only reconnects optional
    member preparation when story completion hides the renewable battle need,
    ordinary trainer income is exhausted, and owned-stock eligibility is absent.
    """
    observed = runtime.adapter.observe()
    if not observed.input_ready:
        return None
    completed = runtime.adapter.graph.completed_ids(observed.game_state)
    if "enter_hall_of_fame" not in completed:
        return None
    controller = learned_league_controller(runtime)
    if (
        controller is None
        or getattr(controller, "income_owned_stock_bootstrap", False) is not True
        or getattr(controller, "income_reuse", None) is None
    ):
        return None
    raw = runtime.reader.read()
    if raw.battle_state or raw.badge_bits != 255 or not party_ready(raw):
        return None
    economy = red_economy_snapshot(raw)
    if economy is None:
        return None
    target = collection_cash_target(runtime, economy, world)
    if type(target) is not int or target <= economy.cash:
        return None
    if missing_reserve_cost(raw) <= economy.cash or bootstrap_targets(runtime) is not None:
        return None
    if ordinary_income_peers(runtime, actions, world):
        return None
    try:
        qualification = bind_red_league_funding_execution(runtime, world).qualification
    except RedLeagueFundingError:
        return None
    levels = tuple(b.maximum_opponent_level for b in qualification.battles)
    if not levels or any(type(level) is not int or not 1 <= level <= 100 for level in levels):
        raise ValueError("income preparation requires actual cartridge opposition")
    return levels


NATIVE_OWNED_STOCK_MODE = "native_qualified_existing_stock_v1"

def declared_native_owned_stock_income(plan, *, production_train_scope=None):
    """Explicit copy-only applicability; old plans retain the old reserve rule."""
    spec = plan.get("native_owned_stock_income")
    if spec is None:
        return None
    if production_train_scope is not None:
        from .red_scoped_train_composition import ProductionSequenceTrainScope
        if type(production_train_scope) is not ProductionSequenceTrainScope:
            raise TypeError("typed production TRAIN sequence scope required")
        production_train_scope.require_plan(plan)
    if ((plan.get("partition") != "development" and production_train_scope is None)
            or plan.get("owned_stock_income_bootstrap") is not True
            or type(spec) is not dict or set(spec) != {"mode", "reason"}
            or spec["mode"] != NATIVE_OWNED_STOCK_MODE
            or type(spec["reason"]) is not str or not spec["reason"].strip()):
        raise ValueError("native owned-stock income requires explicit DEVELOPMENT scope")
    return dict(spec)


def configure_native_owned_stock_income(backend, plan, *, production_train_scope=None):
    """Retain default procurement; optionally expose the qualified owned-stock peer.

    This supplies no action ordering, level target, medicine or game input. The
    native entry/party/PP qualifier and existing income/loss/return executor remain.
    The pre-existing minimum reserve is used only on a declared DEVELOPMENT copy;
    it is not a new survival guarantee or learned procurement claim.
    """
    from dataclasses import replace
    from .goal_manager import GoalKind
    from .red_player_field_goals import _field_ready, _raw_party_fully_restored
    from .red_learned_league import FrozenLeagueController
    from .red_league_funding_execution import ScopedLeagueIncomeReuse
    from .observation import ItemId

    spec = declared_native_owned_stock_income(plan, production_train_scope=production_train_scope)
    current = getattr(backend, "income_with_existing_reserve", None)
    if current is None:
        if spec is None:
            return
        raise ValueError("backend lacks the retained income reserve provider")
    original = getattr(current, "native_owned_stock_original", current)
    if spec is None:
        backend.income_with_existing_reserve = original
        return

    def with_owned_stock(runtime, actions, route, binding):
        prior = original(runtime, actions, route, binding)
        if prior is not None:
            return prior
        controller = learned_league_controller(runtime)
        if (not isinstance(controller, FrozenLeagueController)
                or getattr(controller, "income_owned_stock_bootstrap", False) is not True
                or type(getattr(controller, "income_reuse", None)) is not ScopedLeagueIncomeReuse):
            return None
        controller.require_identity()
        raw = runtime.reader.read()
        completed = runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state)
        if (raw.badge_bits != 255 or "enter_hall_of_fame" not in completed
                or not _field_ready(runtime) or not _raw_party_fully_restored(raw)
                or type(raw.player_money) is not int or raw.player_money < 0):
            return None
        stock = dict(raw.bag_items or ())
        # Same (0 Restore,1 Revive,1 Full Heal) minimum already present in the
        # legacy owned-stock rule. Every additional owned item stays usable.
        if (stock.get(int(ItemId.REVIVE), 0) < 1
                or stock.get(int(ItemId.FULL_HEAL), 0) < 1):
            return None
        try:
            qualification = bind_red_league_funding_execution(runtime, route.route_world).qualification
        except RedLeagueFundingError:
            return None
        if (binding.kind is not GoalKind.RESUPPLY or binding.resource_quote is None
                or qualification.expected_net_income <= 0
                or binding.resource_quote.expected_income != qualification.expected_net_income):
            raise ValueError("native owned-stock income lost its original qualified quote")
        record = getattr(actions, "record_diagnostic_event", None)
        if callable(record):
            record("native_owned_stock_income_offer", dict(
                mode=spec["mode"], native_entry_party_PP_qualified=True,
                reserve_source="existing_owned_stock", minimum_targets=[0, 1, 1],
                owned_revives=stock.get(int(ItemId.REVIVE), 0),
                owned_full_heals=stock.get(int(ItemId.FULL_HEAL), 0),
                owned_full_restores=stock.get(int(ItemId.FULL_RESTORE), 0),
                expected_income=qualification.expected_net_income,
                supplied_applicability_not_learned=True, no_inputs=True,
                old_reserve_offer_unavailable=True, all_other_actions_retained=True,
            ))
        return replace(binding, binding_ref=binding.binding_ref + ":native-qualified-owned-stock-v1")

    with_owned_stock.native_owned_stock_original = original
    backend.income_with_existing_reserve = with_owned_stock
