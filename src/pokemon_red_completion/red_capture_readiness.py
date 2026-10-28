"""Prospective capture readiness, separate from learned selection and execution.

The report exposes facts and unknowns. Its optional pressure projection uses the
existing model schema; it does not give the frozen model new item/move identities.
Reserve targets are declared support budgets, never guaranteed capture odds.
"""

from dataclasses import asdict, dataclass, replace

from .goal_manager import GoalKind, GoalUnavailableReason
from .observation import ItemId
from .party import StatusCondition
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_capture_support import red_capture_status_options
from .red_goal_manager import RedGoalBindingOffer

ORDINARY_BALLS = (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL)


def carried_static_capture_allocation(
    ball, bag, *, minimum_throws=8, maximum_throws=24
):
    """Use observed carried stock within a finite one-off allocation.

    This neither buys balls nor guarantees capture. Sparse stock stays blocked;
    extra carried ordinary balls need not be discarded behind an eight-throw cap.
    """
    if (
        not isinstance(ball, ItemId) or ball not in ORDINARY_BALLS
        or type(bag) is not dict
        or type(minimum_throws) is not int or type(maximum_throws) is not int
        or not 1 <= minimum_throws <= maximum_throws <= 99
    ):
        raise ValueError("static capture allocation requires declared ordinary stock bounds")
    stock = bag.get(int(ball), 0)
    if type(stock) is not int or not 0 <= stock <= 99:
        raise ValueError("static capture ball stock is malformed")
    return min(stock, maximum_throws) if stock >= minimum_throws else None


def carried_static_capture_choice(bag):
    """Keep ordinary-ball preference, but only among sufficient finite lots.

    A few Ultra Balls must not hide eight owned Great Balls. The same eight-ball
    admission and twenty-four-throw limit apply; the Master Ball is never used.
    """
    choices = tuple(
        (ball, carried_static_capture_allocation(ball, bag))
        for ball in (ItemId.ULTRA_BALL, ItemId.GREAT_BALL, ItemId.POKE_BALL)
    )
    return next(((ball, count) for ball, count in choices if count is not None), None)


@dataclass(frozen=True, slots=True)
class CapturePreparationBudget:
    ball: ItemId
    throws: int
    reserve: int
    require_status: bool = False

    def __post_init__(self):
        if self.ball not in ORDINARY_BALLS or not isinstance(self.ball, ItemId):
            raise ValueError("ordinary preparation must not allocate the Master Ball")
        if (
            type(self.throws) is not int
            or type(self.reserve) is not int
            or not 1 <= self.throws <= self.reserve <= 99
            or type(self.require_status) is not bool
        ):
            raise ValueError("capture preparation requires finite explicit budgets")


@dataclass(frozen=True, slots=True)
class CaptureReadiness:
    ordinary_stock: tuple[tuple[str, int], ...]
    master_balls: int
    selected_stock: int
    allocated_throws: int
    reserve_target: int
    cash: int | None
    immediate_slots: int
    healthy_members: int
    living_members: int
    party_hp_ratios: tuple[float, ...]
    status_options: tuple[dict, ...]
    usable_status: bool
    target_available: bool | None
    safe_weakening: str
    hard_blocks: tuple[str, ...]
    risks: tuple[str, ...]

    def public_dict(self):
        return {
            "schema": "pokemon.red.capture-readiness.v1",
            **asdict(self),
            "capture_guaranteed": False,
            "learned_ball_selection": False,
            "survivable_turns": None,
        }


def assess_capture_readiness(observation, budget, *, target_available=None, enemy_species_id=None):
    if not isinstance(budget, CapturePreparationBudget):
        raise TypeError("readiness needs a capture preparation budget")
    if target_available is not None and type(target_available) is not bool:
        raise TypeError("target availability must be observed or unknown")
    raw = observation.raw
    if raw.bag_items is None:
        raise ValueError("capture readiness needs observed inventory")
    bag = dict(raw.bag_items)
    if len(bag) != len(raw.bag_items) or any(
        type(n) is not int or not 1 <= n <= 99 for n in bag.values()
    ):
        raise ValueError("capture readiness inventory is malformed")
    stock = bag.get(int(budget.ball), 0)
    members = observation.party.members
    options = []
    eligible = {
        (o.party_slot, o.move_slot)
        for o in red_capture_status_options(observation.party, enemy_species_id=enemy_species_id)
    }
    for member in members:
        for slot, move in enumerate(member.moves, 1):
            if not move.is_known:
                continue
            condition = RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(move.move_id))
            if condition is None:
                continue
            options.append(
                {
                    "condition": condition,
                    "pp": move.current_pp,
                    "hp_ratio": member.hp_ratio,
                    "usable": (member.slot, slot) in eligible
                    and member.status is StatusCondition.HEALTHY
                    and member.hp_ratio > 0.5,
                }
            )
    usable = any(o["usable"] for o in options)
    blocks, risks = [], []
    if raw.battle_state or not observation.input_ready:
        blocks.append("field_not_ready")
    if target_available is not True:
        blocks.append("target_unavailable" if target_available is False else "target_unknown")
    if observation.immediate_capture_slots <= 0:
        blocks.append("storage_full")
    if stock < budget.throws:
        blocks.append("allocated_ball_stock_missing")
    if not any(m.hp > 0 for m in members):
        blocks.append("no_living_party")
    if budget.require_status and not usable:
        blocks.append("required_status_support_missing")
    if stock < budget.reserve:
        risks.append("below_declared_reserve")
    if not usable:
        risks.append("no_ready_status_helper")
    if any(m.hp_ratio < 1 or m.status is not StatusCondition.HEALTHY for m in members):
        risks.append("party_needs_recovery")
    # Pre-encounter enemy stats/HP are not observed. Do not certify nonlethal
    # damage from species/level alone; the existing live weakening guard decides.
    risks.append("nonlethal_weakening_unverified_before_encounter")
    return CaptureReadiness(
        tuple((b.name.lower(), bag.get(int(b), 0)) for b in ORDINARY_BALLS),
        bag.get(int(ItemId.MASTER_BALL), 0),
        stock,
        budget.throws,
        budget.reserve,
        raw.player_money,
        observation.immediate_capture_slots,
        sum(m.hp == m.max_hp and m.status is StatusCondition.HEALTHY for m in members),
        sum(m.hp > 0 for m in members),
        tuple(m.hp_ratio for m in members),
        tuple(options),
        usable,
        target_available,
        "unknown_until_live_damage_check",
        tuple(blocks),
        tuple(risks),
    )


def capture_preparation_situation(observation, readiness):
    """Existing resource/storage pressures, normalized to this declared goal.

    This prospective capture menu measures ordinary-ball reserve, not the legacy
    minimum of balls and general healing items. Missing Potions alone does not
    mean no capture supplies when a free Center is available. Selected ball stock
    still gates its exact executor allocation. Safety/control gates are unchanged;
    zero ordinary balls still produces full resource pressure. Detailed facts are
    logged, not secretly appended to an old model's feature vector.
    """
    return replace(
        observation.situation,
        resource_pressure=1
        - min(1, sum(n for _, n in readiness.ordinary_stock) / readiness.reserve_target),
        storage_pressure=max(
            observation.situation.storage_pressure, float(readiness.immediate_slots <= 0)
        ),
    )


def build_capture_preparation_options(
    observation, readiness, bindings, *, model_feature_version, ordering_seed_sha256, supplements=()
):
    """Join genuine existing bindings to the frozen model, without selecting.

    Detailed readiness remains diagnostic evidence. The current model consumes only
    its existing normalized resource/storage pressures and independently costed
    bindings. Fewer than two alternatives is not reported as a learned decision.
    """
    from .red_live_option_menu import build_red_live_option_set

    economy = observation.economy_snapshot()
    return build_red_live_option_set(
        situation=capture_preparation_situation(observation, readiness),
        binding_set=bindings,
        supplements=supplements,
        model_feature_version=model_feature_version,
        ordering_seed_sha256=ordering_seed_sha256,
        economy_snapshot=economy,
        target_cash=observation.raw.player_money if economy is not None else None,
    )


@dataclass(frozen=True, slots=True)
class ReadinessGuardedCaptureProvider:
    """Guard an existing capture binding; never choose a preparation alternative."""

    provider: object
    adapter: object
    assess: object
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def offer(self, observation):
        if observation != self.adapter.observe():
            raise ValueError("capture readiness observation is stale")
        readiness = self.assess(observation)
        if readiness.hard_blocks:
            reason = (
                GoalUnavailableReason.STORAGE_BLOCKED
                if "storage_full" in readiness.hard_blocks
                else GoalUnavailableReason.NO_LEGAL_TARGET
                if "target_unavailable" in readiness.hard_blocks
                else GoalUnavailableReason.WORLD_STATE_UNKNOWN
                if "target_unknown" in readiness.hard_blocks
                else GoalUnavailableReason.MISSING_RESOURCE
            )
            return RedGoalBindingOffer.unavailable(self.kind, reason)
        offer = self.provider.offer(observation)
        if offer.binding is None:
            return offer
        binding = offer.binding

        def execute():
            fresh = self.adapter.observe()
            if fresh != observation or self.assess(fresh) != readiness:
                raise ValueError("capture readiness changed before execution")
            return binding.execute()

        return RedGoalBindingOffer.available(replace(binding, execute=execute))


def capture_reserve_purchase(observation, budget, mart):
    """Derive an exact affordable ordinary-ball reserve order, without travel.

    The supplied existing Mart provider owns actual stock/price/boundary. Its offer
    or router must still prove reachability. No sale, speculative income or refill.
    Returns (provider or None, path-free quote) even when purchase is unavailable.
    """
    from .red_goal_skills import RedMartResupplyGoalProvider

    if not isinstance(mart, RedMartResupplyGoalProvider) or len(mart.purchases) != 1:
        raise TypeError("capture reserve needs a single existing Mart purchase")
    purchase = mart.purchases[0]
    if purchase.item is not budget.ball or mart.funding_sale is not None:
        raise ValueError("reserve purchase cannot change ball or sell inventory")
    bag = dict(observation.raw.bag_items or ())
    stock = bag.get(int(budget.ball), 0)
    missing = max(0, budget.reserve - stock)
    cash = observation.raw.player_money
    quantity = min(
        missing,
        purchase.quantity,
        99 - stock,
        cash // purchase.unit_price if cash is not None else 0,
    )
    reason = (
        "inventory_unknown"
        if observation.raw.bag_items is None
        else "reserve_satisfied"
        if not missing
        else "bag_full"
        if not stock and len(bag) >= 20
        else "funds_unknown"
        if cash is None
        else "unaffordable"
        if not quantity
        else None
    )
    quote = {
        "selected_stock": stock,
        "reserve_target": budget.reserve,
        "missing_quantity": missing,
        "unit_price": purchase.unit_price,
        "available_funds": cash,
        "full_reserve_cost": missing * purchase.unit_price,
        "affordable_quantity": 0 if reason else quantity,
        "purchase_cost": 0 if reason else quantity * purchase.unit_price,
        "unavailable_reason": reason,
        "reachability_proved": False,
    }
    if reason:
        return None, quote
    return replace(
        mart,
        purchases=(replace(purchase, quantity=quantity),),
        affordable_ball_purchase=False,
        reserve_targets=((budget.ball, stock + quantity),),
    ), quote
