"""Continue a retained zero-item learned League battle without re-entering it."""

from .actions import MacroAction, MacroActionKind
from .battle_runtime import BattleRuntimeTiming
from .observation import event_flag_is_set
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_league_funding import _ROOMS, _room_quote
from .red_league_funding_execution import RedLeagueFundingBattleResult
from .red_learned_league import learned_league_controller


def continue_league_room_battle(runtime, actions, world, objective_id, *, maximum_decisions=80):
    """Caller authenticates the consumed goal's parent and retains every failure.

    This does not admit a fresh retry or change weights. Recoverable faints
    require the prospectively bound recovery contract; the default stays strict.
    The active cartridge identity and ROM
    quote are checked again before the first model query.
    """
    actor = learned_league_controller(runtime)
    if actor is None:
        raise ValueError("League continuation requires explicit frozen K")
    matches = [row for row in _ROOMS if row[0] == objective_id]
    if len(matches) != 1:
        raise ValueError("unsupported retained League room")
    _, room, event, final_class = matches[0]
    reader = runtime.reader
    before = runtime.adapter.observe()
    raw = before.raw
    if raw.battle_state != 2 or raw.map_id != room or raw.event_flags is None:
        raise ValueError("continuation is not the retained active League room")
    quote = _room_quote(world.rom, raw.event_flags, objective_id, room, event, final_class)
    identity = (quote.opponent_id, quote.opponent_id - 200, quote.trainer_set)
    if reader.read_active_trainer_identity() != identity:
        raise ValueError("retained League trainer identity differs from cartridge")
    if (
        type(raw.player_money) is not int
        or raw.player_money + quote.expected_victory_money > 999999
    ):
        raise ValueError("retained League money unavailable or capped")
    actor.require_party_hp(raw)
    started_actions, started_frames = actions.actions_executed, runtime.emulator.frame_count

    def preserve(current):
        if (
            current.map_id != room
            or current.party_count != raw.party_count
            or current.party_species_ids != raw.party_species_ids
            or current.bag_items != raw.bag_items
            or current.badge_bits != raw.badge_bits
        ):
            raise ValueError("retained League battle lost protected party or resources")
        actor.require_party_hp(current)

    def guard(current):
        preserve(current)
        if current.battle_state != 2 or reader.read_active_trainer_identity() != identity:
            raise ValueError("retained League combat boundary changed")

    actor.battler._play(
        reader,
        actions,
        expected_map=int(room),
        timing=BattleRuntimeTiming(max_runtime_pulses=1600),
        label="retained learned League battle",
        decision_guard=guard,
        resume=True,
        require_win=True,
        authority="frozen-k-league-development-continuation",
        maximum_decisions=maximum_decisions,
        allow_immune_switch_recovery=actor.allow_immune_switch_recovery,
    )
    expected_money = raw.player_money + quote.expected_victory_money
    for _ in range(81):
        current = reader.read()
        preserve(current)
        if current.battle_state or current.battle_result != 0:
            raise ValueError("retained League battle did not end in a field victory")
        if (
            current.player_money == expected_money
            and event_flag_is_set(current.event_flags, event)
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
        ):
            after = runtime.adapter.observe()
            if dependency_specimen_ledger(
                after.collection_observation
            ) != dependency_specimen_ledger(before.collection_observation):
                raise ValueError("retained League battle changed specimen inventory")
            return RedLeagueFundingBattleResult(
                objective_id,
                raw.player_money,
                current.player_money,
                quote.expected_victory_money,
                actions.actions_executed - started_actions,
                runtime.emulator.frame_count - started_frames,
            )
        if reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible():
            raise ValueError("retained League field settled without its payout/event")
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
    raise ValueError("retained League settlement exceeded its bound")
