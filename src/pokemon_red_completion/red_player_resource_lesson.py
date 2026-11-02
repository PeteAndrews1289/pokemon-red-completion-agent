"""Prospective native resource/acquisition evidence, not retroactive labels."""

from .goal_manager import GoalKind
from .red_goal_skills import _CAPTURE_ITEMS, _RECOVERY_ITEMS
from .red_player_economy import restore_snapshot, semantic_facts
from .red_player_lesson import validate_snapshot
from .resource_economy_observation import economy_outcome

RESOURCE_LESSON_KINDS = frozenset({GoalKind.RESUPPLY, GoalKind.ACQUIRE_SPECIES})


def _check_inventory_counts(snapshot, observation):
    inventory = dict(snapshot.inventory)
    facts = semantic_facts(observation)
    for key, items in (("capture_item_count", _CAPTURE_ITEMS),
                       ("recovery_item_count", _RECOVERY_ITEMS)):
        if facts.get(key) != sum(inventory.get(f"red-item-{int(i):03d}", 0) for i in items):
            raise ValueError("resource lesson inventory differs from semantic counts")


def validate_resource_lesson(plan, question):
    opportunity = question.opportunities[plan["selected_index"]]
    lesson = plan["player_lesson"]
    if (opportunity.kind not in RESOURCE_LESSON_KINDS or not isinstance(lesson, dict)
        or set(lesson) != {"before", "target"}):
        raise ValueError("resource lesson declaration differs")
    members = validate_snapshot(lesson["before"], plan["before"])
    before = restore_snapshot(plan["economy_before"])
    if before is None:
        raise ValueError("resource lesson requires observed economy")
    _check_inventory_counts(before, plan["before"])
    quote = opportunity.resource_quote
    if opportunity.kind is GoalKind.ACQUIRE_SPECIES:
        target = {"resource": "native_acquisition"}
    else:
        if (quote is None or quote.available_funds != before.cash or quote.funding_proceeds
            or quote.available_recovery_units is not None):
            raise ValueError("resource lesson requires a bound purchase or earning quote")
        target = {"resource": "earn_cash" if quote.expected_income else "purchase_stock"}
    if lesson["target"] != target:
        raise ValueError("resource lesson target differs from selected offer")
    return members, before, opportunity


def verify_resource_lesson(plan, result, question):
    old, before, opportunity = validate_resource_lesson(plan, question)
    new = validate_snapshot(result["player_lesson"], result["after"])
    opening, terminal = plan["player_lesson"]["before"], result["player_lesson"]
    if (opening["objective_catalog"] != terminal["objective_catalog"]
        or not set(opening["completed_objectives"]) <= set(terminal["completed_objectives"])
        or not old.keys() <= new.keys()
        or any(old[k].species_id != new[k].species_id or old[k].level > new[k].level
               or old[k].experience > new[k].experience for k in old)):
        raise ValueError("resource lesson lost its party or story evidence")
    after = restore_snapshot(result["economy_after"])
    measured = economy_outcome(before, after, target_cash=plan["target_cash"])
    if measured is None:
        raise ValueError("resource lesson lacks terminal economy")
    _check_inventory_counts(after, result["after"])
    if result["succeeded"]:
        if terminal["in_battle"] or not semantic_facts(result["after"])["input_ready"]:
            raise ValueError("resource lesson needs a settled field boundary")
        if opportunity.kind is GoalKind.RESUPPLY:
            quote = opportunity.resource_quote
            if quote.expected_income:
                if measured.cash_delta <= 0:
                    raise ValueError("earning lesson lacks actual net income")
            else:
                if (measured.cash_delta != -quote.purchase_cost
                    or measured.net_item_decrease
                    or measured.net_item_increase != sum(r.purchased for r in quote.reserves)):
                    raise ValueError("purchase lesson differs from bound cost and stock")
                # Verify which resource class changed, not merely item totals.
                for reserve in quote.reserves:
                    key = ("capture_item_count" if reserve.resource == "capture"
                           else "recovery_item_count")
                    a, b = semantic_facts(plan["before"]), semantic_facts(result["after"])
                    if (a.get(key) != reserve.available
                        or b.get(key) != reserve.available + reserve.purchased):
                        raise ValueError("purchased resource class differs")
    return measured
