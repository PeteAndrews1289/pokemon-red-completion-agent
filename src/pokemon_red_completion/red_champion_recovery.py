"""Preparation and genuine-loss gates for the bounded earned Champion attempt.

These are support decisions, not a learned resource policy or battle admission.
The battle lifecycle must first authenticate its outcome and retained endpoint.
"""

from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .red_faint_recovery import plan_faint_aware_recovery
from .red_goal_skills import _raw_party_fully_restored


def owned_champion_revive(raw, *, items_used=0):
    """Permit exactly one owned Revive, never a second preparation item."""
    if type(items_used) is not int or items_used != 0:
        raise ValueError("Champion preparation item budget is consumed")
    choice = plan_faint_aware_recovery(raw)
    if (
        choice is None or choice.item != ItemId.REVIVE
        or dict(raw.bag_items).get(int(ItemId.REVIVE)) != 1
        or raw.party_hp[choice.party_index] != 0
    ):
        raise ValueError("Champion preparation requires its single owned Revive")
    return choice


def require_champion_loss_recovery(completion, raw, *, starting_money, input_ready):
    """No timeout, victory, unresolved battle or forced loss can trigger recovery."""
    if (
        completion is None or completion.outcome != "lost"
        or completion.field_ready is not True
        or completion.episode.battle_won is not False
        or completion.episode.stop_reason != "party_defeated"
        or type(starting_money) is not int or not 0 <= starting_money <= 999999
        or completion.money_delta != starting_money // 2 - starting_money
        or raw.player_money != starting_money // 2
        or raw.map_id != MapId.INDIGO_PLATEAU or raw.battle_state != 0
        # The native blackout scripts may clear wBattleResult before readiness.
        # The authenticated lifecycle/episode and exact cash loss own the verdict.
        or raw.battle_result not in (0, 1) or input_ready is not True
        or not _raw_party_fully_restored(raw)
        or raw.event_flags is None
        or event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
    ):
        raise ValueError("recovery requires a verified native Champion blackout")
