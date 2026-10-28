"""Resume an already native-engaged ordinary trainer; no new challenge or teacher."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_trainer_sight import static_trainer_sight_zones, trainer_headers
from .gen1_traversal import map_object_events
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import (
    ExecutableGoalBinding, GoalExecutionReport, GoalRecoveryRequired, GoalVerification,
)
from .observation import (
    CERULEAN_RIVAL_TRIGGER_XS,
    CERULEAN_RIVAL_TRIGGER_Y,
    EventFlag,
    MapId,
    event_flag_is_set,
)
from .red_player_field_goals import _field_ready
from .red_scoped_training_battlers import resolve_story_battler
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .route_executor import (
    InterruptionReceipt,
    RouteExecutionError,
    RouteExecutionFailureReason,
)

SETTLED_ROUTE_TRAINER_LOSS_SCHEMA = "pokemon.red.settled-route-trainer-loss.v1"
SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA = "pokemon.red.settled-route-trainer-recovery.v1"
_LEAGUE_CONTEXTS = frozenset({
    "defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance", "defeat_champion",
})


class SettledNativeTrainerLoss(RouteExecutionError):
    """A verified native blackout interrupts transport, not an execution defect.

    The route still fails. Only Red's semantic transport may convert this exact
    loss into a measured failed goal; arbitrary route errors remain exceptions.
    """

    failure_reason = GoalFailureReason.RESOURCE_LOST

    def __init__(self, report, *, cash_before, cash_after):
        super().__init__(
            "learned resource trainer lost; retain verified native blackout",
            reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED,
        )
        self.report = report
        self.evidence = dict(
            schema=SETTLED_ROUTE_TRAINER_LOSS_SCHEMA,
            verified=True,
            learned_combat=True,
            support="already_engaged_native_trainer",
            source_sha256=report.evidence["source_sha256"],
            terminal_sha256=report.evidence["terminal_sha256"],
            cash_before=cash_before,
            cash_after=cash_after,
            cash_lost=cash_before - cash_after,
            actions=report.actions_executed,
            frames=report.frames_executed,
            battle={key: report.evidence["battle"][key] for key in (
                "schema", "outcome", "field_ready", "money_delta",
            )},
            objective_completed=False,
            reward=None,
        )


class SettledNativeTrainerRecovery(RouteExecutionError, GoalRecoveryRequired):
    """A verified win stops transport for ordinary recovery, without losing credit."""

    failure_reason = GoalFailureReason.RECOVERY_REQUIRED

    def __init__(self, report, *, cash_before, cash_after, party_hp):
        super().__init__("verified trainer exit needs native faint recovery",
                         reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED)
        self.report = report
        self.evidence = dict(
            schema=SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA, verified=True,
            learned_combat=True, support=report.evidence.get("support"),
            source_sha256=report.evidence.get("source_sha256"),
            terminal_sha256=report.evidence.get("terminal_sha256"),
            cash_before=cash_before, cash_after=cash_after,
            actions=report.actions_executed, frames=report.frames_executed,
            party_hp=list(party_hp), battle=dict(report.evidence.get("battle", {})),
        )


def settled_route_trainer_recovery_evidence(evidence):
    """Require exact native win, payout, terminal identity and a surviving party."""
    import re
    from collections.abc import Mapping

    if not isinstance(evidence, Mapping):
        return False
    battle, hp = evidence.get("battle"), evidence.get("party_hp")
    return (
        evidence.get("schema") == SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA
        and evidence.get("verified") is True and evidence.get("learned_combat") is True
        and evidence.get("support") == "already_engaged_native_trainer"
        and all(isinstance(evidence.get(key), str)
                and re.fullmatch(r"[0-9a-f]{64}", evidence[key])
                for key in ("source_sha256", "terminal_sha256"))
        and all(type(evidence.get(key)) is int and 0 <= evidence[key] <= 999999
                for key in ("cash_before", "cash_after"))
        and all(type(evidence.get(key)) is int and evidence[key] > 0
                for key in ("actions", "frames"))
        and isinstance(hp, (tuple, list)) and 1 <= len(hp) <= 6
        and all(type(value) is int and value >= 0 for value in hp)
        and 0 in hp and any(value > 0 for value in hp)
        and isinstance(battle, Mapping)
        and battle.get("schema") == "pokemon.red.learned-trainer-completion.v1"
        and battle.get("outcome") == "won" and battle.get("field_ready") is True
        and type(battle.get("money_delta")) is int
        and 0 <= battle["money_delta"] == evidence["cash_after"] - evidence["cash_before"]
    )


def settled_route_trainer_stop_evidence(evidence):
    return (settled_route_trainer_loss_evidence(evidence)
            or settled_route_trainer_recovery_evidence(evidence))


def settled_route_trainer_loss_evidence(evidence):
    """Validate the narrow diagnostic certificate; never select an action."""
    import re
    from collections.abc import Mapping

    if not isinstance(evidence, Mapping):
        return False
    battle = evidence.get("battle")
    return (
        evidence.get("schema") == SETTLED_ROUTE_TRAINER_LOSS_SCHEMA
        and evidence.get("verified") is True
        and evidence.get("learned_combat") is True
        and evidence.get("support") == "already_engaged_native_trainer"
        and evidence.get("objective_completed") is False
        and evidence.get("reward") is None
        and all(isinstance(evidence.get(key), str)
                and re.fullmatch(r"[0-9a-f]{64}", evidence[key]) for key in (
                    "source_sha256", "terminal_sha256"))
        and all(type(evidence.get(key)) is int and 0 <= evidence[key] <= 999999
                for key in ("cash_before", "cash_after", "cash_lost"))
        and evidence["cash_after"] == evidence["cash_before"] // 2
        and evidence["cash_lost"] == evidence["cash_before"] - evidence["cash_after"]
        and all(type(evidence.get(key)) is int and evidence[key] > 0
                for key in ("actions", "frames"))
        and isinstance(battle, Mapping)
        and battle.get("schema") == "pokemon.red.learned-trainer-completion.v1"
        and battle.get("outcome") == "lost"
        and battle.get("field_ready") is True
        and type(battle.get("money_delta")) is int
        and battle["money_delta"] == -evidence["cash_lost"]
    )


def engaged_story_contract(reader, rom, *, objective_id, ordinary_transport_context=False,
                           dojo_master_transport=False):
    raw = reader.read()
    if type(dojo_master_transport) is not bool:
        raise ValueError("Dojo transport recovery must be explicit")
    if dojo_master_transport:
        if (objective_id not in _LEAGUE_CONTEXTS | {"cross_victory_road"} or raw.badge_bits != 255
                or raw.map_id != int(MapId.FIGHTING_DOJO)):
            return None
        from .red_scripted_story_trainer import (
            dojo_master_contract,
            dojo_master_introduction_contract,
        )

        if raw.battle_state == 2:
            if reader.read_active_trainer_identity() != (224,24,1):
                return None
            contract = dojo_master_contract(rom,raw)
        else:
            contract = dojo_master_introduction_contract(rom,reader)
        return None if contract is None else replace(contract,objective_id=objective_id)
    if type(ordinary_transport_context) is not bool:
        raise ValueError("ordinary transport context must be explicit")
    if ordinary_transport_context:
        # An unfinished League objective can label unavoidable transport,
        # but an ordinary sight trainer is not a League-room victory.
        if objective_id not in _LEAGUE_CONTEXTS:
            raise ValueError("ordinary transport override requires a League accounting context")
        from .red_player_league_options import CHAMPION_PLAYER_TARGET, LEAGUE_PLAYER_TARGETS

        if raw.map_id in {int(t.room) for t in LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,)}:
            return None
        if raw.battle_state == 2:
            identity = reader.read_active_trainer_identity()
        elif raw.battle_state == 0 and reader.trainer_engagement_active():
            _, _, cls, team = reader.read_trainer_battle_identity()
            identity = (cls, cls - 200, team)
        else:
            return None
        return _ordinary_sight_contract(rom, raw, identity, objective_id)
    if objective_id in _LEAGUE_CONTEXTS:
        from .red_player_league_options import engaged_league_contract

        retained = engaged_league_contract(reader, rom, include_champion=True)
        if retained is None or retained[0].objective_id != objective_id:
            return None
        return retained[1]
    if objective_id == "help_bill" and raw.map_id == int(MapId.CERULEAN_CITY):
        from .red_player_cerulean_rival import cerulean_rival_contract

        if raw.battle_state == 2:
            # A different Cerulean trainer is not this scripted rival.
            if reader.read_active_trainer_identity()[:2] == (225, 25):
                contract = cerulean_rival_contract(rom, reader)
                if reader.read_active_trainer_identity() != contract.trainer_identity:
                    raise ValueError("retained Cerulean rival identity differs")
                return contract
        elif (
            raw.battle_state == 0
            and raw.player_y == CERULEAN_RIVAL_TRIGGER_Y
            and raw.player_x in CERULEAN_RIVAL_TRIGGER_XS
            and reader.read_bottom_dialogue_box_visible()
            and reader.read_cascade_state(raw).local_script == 1
            and not event_flag_is_set(raw.event_flags, EventFlag.BEAT_CERULEAN_RIVAL)
        ):
            # The already-triggered native introduction can be reached by
            # a training walk too. Finish it, without supplying a new approach.
            return cerulean_rival_contract(rom, reader)
    if (
        objective_id == "cross_victory_road"
        and raw.map_id == int(MapId.ROUTE_22)
    ):
        from .red_player_route22_rival import (
            retained_second_route22_contract,
            route22_rival_contract,
        )

        if raw.battle_state == 2:
            contract = route22_rival_contract(rom, reader)
            if reader.read_active_trainer_identity() != contract.trainer_identity:
                raise ValueError("retained Route22 rival identity differs")
            return contract
        introduction = retained_second_route22_contract(rom, reader)
        if introduction is not None:
            return introduction
    if raw.map_id == int(MapId.ROUTE_22):
        from .red_player_route22_rival import retained_first_route22_contract

        first = retained_first_route22_contract(rom, reader, objective_id=objective_id)
        if first is not None:
            return first
    if objective_id == "help_bill" and raw.map_id == int(MapId.ROUTE_24):
        from .red_scripted_story_trainer import (
            nugget_rocket_contract,
            nugget_rocket_introduction_contract,
        )

        if raw.battle_state == 2 and reader.read_active_trainer_identity() == (230, 30, 6):
            return nugget_rocket_contract(rom, raw)
        if raw.battle_state == 0:
            introduction = nugget_rocket_introduction_contract(rom, reader)
            if introduction is not None:
                return introduction
    if (
        objective_id == "rescue_fuji"
        and raw.map_id == 143
        and (
            raw.battle_state == 2
            or reader.trainer_engagement_active()
            or (
                raw.battle_state == 0
                and (raw.player_y, raw.player_x) in {(5, 15), (6, 14)}
                and reader.read_bottom_dialogue_box_visible()
                and not event_flag_is_set(raw.event_flags, 239)
            )
        )
    ):
        from .red_scripted_story_trainer import tower_rival_contract

        return tower_rival_contract(rom, reader)
    if (
        objective_id == "clear_rocket_hideout"
        and raw.battle_state == 2
        and (raw.map_id, reader.read_active_trainer_identity())
        in {(135, (230, 30, 7)), (202, (229, 29, 1))}
    ):
        from .red_scripted_story_trainer import hideout_scripted_contract

        return hideout_scripted_contract(rom, raw)
    if (
        objective_id == "reach_vermilion"
        and raw.map_id == int(MapId.CERULEAN_CITY)
        and (raw.battle_state == 2 or reader.trainer_engagement_active())
    ):
        from .red_scripted_story_trainer import cerulean_thief_contract

        return cerulean_thief_contract(rom, reader)
    if raw.battle_state == 2:
        identity = reader.read_active_trainer_identity()
    elif raw.battle_state == 0 and reader.trainer_engagement_active():
        _, _, cls, team = reader.read_trainer_battle_identity()
        identity = (cls, cls - 200, team)
    else:
        return None
    if objective_id in {"defeat_brock", "defeat_misty", "defeat_surge"}:
        from .red_gym_reward import BROCK_REWARD, MISTY_REWARD, SURGE_REWARD

        reward = next(r for r in (BROCK_REWARD, MISTY_REWARD, SURGE_REWARD)
                      if r.objective_id == objective_id)
        if raw.map_id == reward.map_id and identity == (
            reward.trainer_class, reward.trainer_class - 200, reward.trainer_set,
        ):
            return reward.contract(rom, raw)
    if (objective_id == 'postgame_collection'
            and raw.map_id == int(MapId.FIGHTING_DOJO) and identity == (224,24,1)):
        from .red_scripted_story_trainer import dojo_master_contract
        return dojo_master_contract(rom,raw)
    if objective_id == "defeat_erika" and raw.map_id == int(MapId.CELADON_GYM):
        from .red_gym_reward import ERIKA_REWARD

        if identity == (
            ERIKA_REWARD.trainer_class,
            ERIKA_REWARD.trainer_class - 200,
            ERIKA_REWARD.trainer_set,
        ):
            # Leaders have scripted reward events, not ordinary sight headers.
            return ERIKA_REWARD.contract(rom, raw)
    if objective_id == "defeat_sabrina" and raw.map_id == int(MapId.SAFFRON_GYM):
        from .red_sabrina_continuation import sabrina_contract

        if identity == (240, 40, 1):
            return sabrina_contract(rom, raw)
    if objective_id == "defeat_koga" and raw.map_id == int(MapId.FUCHSIA_GYM):
        from .red_gym_reward import KOGA_REWARD

        if identity == (238, 38, 1):
            return KOGA_REWARD.contract(rom, raw)
    if objective_id == "defeat_blaine" and raw.map_id == int(MapId.CINNABAR_GYM):
        from .red_gym_reward import BLAINE_REWARD

        if identity == (239, 39, 1):
            return BLAINE_REWARD.contract(rom, raw)
    if objective_id == "defeat_giovanni" and raw.map_id == int(MapId.VIRIDIAN_GYM):
        from .red_gym_reward import GIOVANNI_REWARD

        if identity == (229, 29, 3):
            return GIOVANNI_REWARD.contract(rom, raw)
    if (
        objective_id == "liberate_silph"
        and raw.map_id == int(MapId.SILPH_CO_11F)
        and identity == (229, 29, 2)
        and not event_flag_is_set(raw.event_flags, EventFlag.BEAT_SILPH_CO_GIOVANNI)
    ):
        # Giovanni is a scripted object, not an ordinary trainer sight header.
        # The existing contract authenticates object3 and its cartridge roster.
        from .red_silph_continuation import silph_continuation_contract

        return silph_continuation_contract(rom, raw, "giovanni")
    return _ordinary_sight_contract(rom, raw, identity, objective_id)


def _ordinary_sight_contract(rom, raw, identity, objective_id):
    """Require exactly one real undefeated sight trainer; never a scripted substitute."""
    zones = static_trainer_sight_zones(
        trainer_headers(rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(rom, {raw.map_id}),
        raw.event_flags,
    )
    matches = [
        z
        for z in zones
        if not z.defeated and (z.trainer_class, z.trainer_class - 200, z.trainer_set) == identity
    ]
    if len(matches) != 1:
        raise ValueError("engaged trainer must have one undefeated cartridge identity")
    return StoryTrainerContract.from_cartridge(
        rom,
        raw,
        objective_id=objective_id,
        battle_plan_id="retained-native-engagement",
        map_id=raw.map_id,
        defeated_event=matches[0].event_flag,
    )


def retained_ordinary_transport_binding(runtime, actions, *, rom, battler):
    """Settle an already engaged ordinary trainer under a legal story context.

    The context labels unavoidable recovery, not a selected destination. Only
    one undefeated cartridge sight identity is admitted; the exact Dojo Master
    uses its existing scripted adapter. This never approaches a trainer or
    grants chapter completion, and the existing battler admission still applies.
    """
    raw = runtime.reader.read()
    if raw.map_id == int(MapId.FIGHTING_DOJO) and raw.badge_bits == 255:
        before = runtime.adapter.observe()
        if "cross_victory_road" in {
            o.id for o in runtime.adapter.graph.available_objectives(before.game_state)
        }:
            # This available objective labels already-triggered native control;
            # the exact Master contract supplies no approach or chapter credit.
            binding = engaged_story_binding(runtime, actions, rom=rom, battler=battler,
                objective_id="cross_victory_road", dojo_master_transport=True)
            if binding is not None:
                return binding
    if raw.battle_state == 2:
        identity = runtime.reader.read_active_trainer_identity()
    elif raw.battle_state == 0 and runtime.reader.trainer_engagement_active():
        _, _, cls, team = runtime.reader.read_trainer_battle_identity()
        identity = (cls, cls - 200, team)
    else:
        return None
    before = runtime.adapter.observe()
    contexts = runtime.adapter.graph.available_objectives(before.game_state)
    if not contexts:
        return None
    zones = static_trainer_sight_zones(
        trainer_headers(rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(rom, {raw.map_id}), raw.event_flags,
    )
    matches = [z for z in zones if not z.defeated and
               (z.trainer_class, z.trainer_class - 200, z.trainer_set) == identity]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("ordinary transport trainer must have one undefeated identity")
    # This is only an accounting context. The normal retained-native contract
    # has no chapter reward and the binding remains compulsory control support.
    objective_id = contexts[0].id
    keywords = {"objective_id": objective_id}
    if objective_id in _LEAGUE_CONTEXTS:
        keywords["ordinary_transport_context"] = True
    contract = engaged_story_contract(runtime.reader, rom, **keywords)
    if contract is None or contract.battle_plan_id != "retained-native-engagement":
        return None
    return engaged_story_binding(runtime, actions, rom=rom, battler=battler, **keywords)


def engaged_story_binding(
    runtime,
    actions,
    *,
    rom,
    battler,
    objective_id,
    allow_postgame_collection=False,
    progress_objective_ref=None,
    ordinary_transport_context=False,
    dojo_master_transport=False,
    allow_retained_tower=False,
):
    """An unavoidable continuation is support; battle decisions remain learned."""
    if type(allow_postgame_collection) is not bool:
        raise ValueError("postgame engagement recovery must be explicit")
    if type(ordinary_transport_context) is not bool:
        raise ValueError("ordinary transport context must be explicit")
    if type(dojo_master_transport) is not bool:
        raise ValueError("Dojo transport recovery must be explicit")
    if type(allow_retained_tower) is not bool:
        raise ValueError("retained Tower recovery must be explicit")
    contract_keywords = {"objective_id": objective_id}
    if ordinary_transport_context:
        contract_keywords["ordinary_transport_context"] = True
    if dojo_master_transport:
        contract_keywords["dojo_master_transport"] = True
    before = runtime.adapter.observe()
    context_ref = objective_id if progress_objective_ref is None else progress_objective_ref
    if context_ref != objective_id:
        from .red_player_league_options import (
            engaged_league_contract,
            league_native_prerequisite,
        )

        retained = engaged_league_contract(runtime.reader, rom, include_champion=True)
        if (
            retained is None
            or retained[0].objective_id != objective_id
            or not league_native_prerequisite(retained[0], context_ref)
        ):
            return None
    available = context_ref in {
        o.id for o in runtime.adapter.graph.available_objectives(before.game_state)
    }
    postgame = (
        allow_postgame_collection
        and objective_id == "postgame_collection"
        and {"defeat_champion", "enter_hall_of_fame"}
        <= set(runtime.adapter.graph.completed_ids(before.game_state))
    )
    contract = None
    if allow_retained_tower:
        # A collection walk can trigger this battle before the Silph Scope
        # unlocks the full Fuji quest. Finishing an already active native
        # trainer is compulsory control recovery, not a new quest selection.
        if (objective_id != "rescue_fuji" or context_ref != objective_id
                or ordinary_transport_context or dojo_master_transport
                or allow_postgame_collection):
            raise ValueError("retained Tower recovery requires its exact compulsory context")
        raw = runtime.reader.read()
        if raw.map_id != int(MapId.POKEMON_TOWER_2F) or raw.battle_state != 2:
            return None
        contract = engaged_story_contract(runtime.reader, rom, **contract_keywords)
        if contract is None:
            return None
        if (contract.objective_id != "rescue_fuji" or contract.battle_plan_id != "tower-rival"
                or contract.map_id != int(MapId.POKEMON_TOWER_2F)
                or contract.defeated_event != int(EventFlag.BEAT_POKEMON_TOWER_RIVAL)
                or runtime.reader.read_active_trainer_identity() != contract.trainer_identity):
            raise ValueError("retained Tower recovery contract differs")
    if not available and not postgame and contract is None:
        return None
    if contract is None:
        contract = engaged_story_contract(runtime.reader, rom, **contract_keywords)
    if contract is None:
        return None
    reward = None
    if objective_id in {"defeat_brock", "defeat_misty", "defeat_surge"} and (
        contract.battle_plan_id == objective_id
    ):
        from .red_gym_reward import BROCK_REWARD, MISTY_REWARD, SURGE_REWARD

        reward = next(r for r in (BROCK_REWARD, MISTY_REWARD, SURGE_REWARD)
                      if r.objective_id == objective_id)
        if contract != reward.contract(rom, runtime.reader.read()):
            raise ValueError("retained early leader reward contract differs")
    if objective_id == "defeat_erika" and contract.battle_plan_id == "defeat_erika":
        from .red_gym_reward import ERIKA_REWARD

        if contract != ERIKA_REWARD.contract(rom, runtime.reader.read()):
            raise ValueError("retained leader reward contract differs")
        reward = ERIKA_REWARD
    if objective_id == "defeat_sabrina" and contract.battle_plan_id == "sabrina":
        from .red_gym_reward import SABRINA_REWARD
        from .red_sabrina_continuation import sabrina_contract

        if contract != sabrina_contract(rom, runtime.reader.read()):
            raise ValueError("retained Sabrina reward contract differs")
        reward = SABRINA_REWARD
    if objective_id == "defeat_koga" and contract.battle_plan_id == "defeat_koga":
        from .red_gym_reward import KOGA_REWARD

        if contract != KOGA_REWARD.contract(rom, runtime.reader.read()):
            raise ValueError("retained Koga reward contract differs")
        reward = KOGA_REWARD
    if objective_id == "defeat_blaine" and contract.battle_plan_id == "defeat_blaine":
        from .red_gym_reward import BLAINE_REWARD

        if contract != BLAINE_REWARD.contract(rom, runtime.reader.read()):
            raise ValueError("retained Blaine reward contract differs")
        reward = BLAINE_REWARD
    if objective_id == "defeat_giovanni" and contract.battle_plan_id == "defeat_giovanni":
        from .red_gym_reward import GIOVANNI_REWARD

        if contract != GIOVANNI_REWARD.contract(rom, runtime.reader.read()):
            raise ValueError("retained Giovanni reward contract differs")
        reward = GIOVANNI_REWARD
    actor = resolve_story_battler(battler, contract)
    controller = FrozenStoryBattleController(actor, (contract,), evolution_rom=rom)
    source = runtime.emulator.save_state_bytes()
    used, terminal, result = False, None, None

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("retained engagement is stale or consumed")
        if engaged_story_contract(runtime.reader, rom, **contract_keywords) != contract:
            raise ValueError("retained engagement identity changed")
        if resolve_story_battler(battler, contract) is not actor:
            raise ValueError("retained engagement actor changed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        entry = runtime.reader.read()
        for _ in range(32):
            raw = runtime.reader.read()
            if raw.battle_state == 2:
                break
            if raw.battle_state or raw.map_id != contract.map_id:
                raise ValueError("unexpected retained trainer introduction")
            if contract.battle_plan_id in {
                "retained-route22-first-rival", "route22-rival-gate",
            } and (
                engaged_story_contract(runtime.reader, rom, **contract_keywords) != contract
                or any(getattr(raw, key) != getattr(entry, key) for key in (
                        "party_count", "party_species_ids", "party_levels", "party_hp",
                        "party_moves", "party_pp", "party_status", "bag_items",
                        "player_money", "badge_bits", "event_flags",
                ))
            ):
                encounter = ("first" if contract.battle_plan_id == "retained-route22-first-rival"
                             else "second")
                raise ValueError(f"{encounter} Route22 rival introduction changed protected state")
            actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=144))
        else:
            raise RuntimeError("retained trainer introduction exceeded bound")
        if contract.battle_plan_id == "scripted-nugget-rocket":
            from .red_scripted_story_trainer import nugget_rocket_contract

            if nugget_rocket_contract(rom, runtime.reader.read()) != contract:
                raise ValueError("Nugget reward/live trainer handoff differs")
        result = controller.run(
            runtime.reader,
            actions,
            objective_id=objective_id,
            battle_plan_id=contract.battle_plan_id,
            expected_map=contract.map_id,
        )
        reward_evidence = None
        if reward is not None and result.outcome == "won" and result.field_ready:
            reward_evidence = reward.settle(
                runtime.reader, actions, before=entry, victory_money=result.money_delta
            )
        if (
            result.outcome not in {"won", "lost"}
            or not result.field_ready
            or not _field_ready(runtime)
        ):
            raise RuntimeError("retained trainer battle did not settle")
        if reward_evidence is not None:
            objective = runtime.adapter.graph.objective(objective_id)
            runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                battle=result.public_dict(),
                support="already_engaged_native_trainer",
                progress_objective=context_ref,
                native_prerequisite=objective_id if context_ref != objective_id else None,
                objective_completed=reward_evidence is not None,
                reward=reward_evidence,
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
                **(dict(compulsory_tower_recovery=True, quest_prerequisite_available=available)
                   if allow_retained_tower else {}),
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if result.outcome == "lost":
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        from .red_eventless_trainer import eventless_battle_finished

        proved = (
            event_flag_is_set(runtime.reader.read().event_flags, contract.defeated_event)
            if contract.defeated_event is not None
            else eventless_battle_finished(runtime.reader, contract.trainer_identity, won=True)
        )
        if not proved:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:retained-engagement:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.3,
        0.4,
        execute,
        verify,
    )


@dataclass(slots=True)
class EngagedStoryRouteHandler:
    """Connect an exact learned engagement to an already selected route.

    Wild/text mechanics stay with the existing handler. This never approaches a
    trainer or chooses a new destination. A loss remains a failed route and a
    native recovery state; it is not retried or hidden inside transport.
    """

    inner: object
    reader: object
    binding_factory: Callable[[], ExecutableGoalBinding | None]
    maximum_trainers: int = 8
    trainer_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)

    def __post_init__(self):
        if not callable(self.binding_factory) or not callable(getattr(self.inner, "handle", None)):
            raise TypeError("learned route requires an existing handler and exact binding factory")
        # Keep the historical default, but allow a declared long transport to
        # cross more native trainers. Input/frame/wall and exact-win guards
        # remain independent; this count is not a party-health heuristic.
        if type(self.maximum_trainers) is not int or not 1 <= self.maximum_trainers <= 32:
            raise ValueError("learned route trainer allowance must be1..32")

    @property
    def handled_hazard_kinds(self):
        return frozenset(getattr(self.inner, "handled_hazard_kinds", ())) | {"trainer_sight"}

    @property
    def handled_interruption_kinds(self):
        return frozenset(getattr(self.inner, "handled_interruption_kinds", ())) | {
            "trainer_engagement", "battle:2", "scripted_dialogue",
        }

    def observe_native_field_boundary(self) -> None:
        from .route_executor import observe_native_field_boundary

        observe_native_field_boundary(self.inner)

    @property
    def verified_trainer_income(self):
        """Only independently verified native wins contribute route proceeds."""
        total = 0
        for receipt in self.trainer_evidence:
            battle = receipt.details['battle']
            amount = battle.get('money_delta')
            if (receipt.details.get('verified') is not True or battle.get('outcome') != 'won'
                    or type(amount) is not int or amount < 0):
                raise RouteExecutionError('learned route payout lacks native win evidence')
            total += amount
        return total

    def handle(self, interruption):
        receipt = self._handle_current(interruption)
        native_pending = getattr(self.reader, "trainer_engagement_active", None)
        if (not callable(native_pending) or native_pending() is not True
                or not isinstance(receipt, InterruptionReceipt)
                or receipt.details.get("verified") is not True):
            return receipt
        after = self.reader.read()
        if (after.battle_state != 0
                or (after.map_id, (after.player_y, after.player_x))
                != (receipt.resumed_map, receipt.resumed_at)
                or receipt.details.get("pending_interruption_kind")
                not in {None, "trainer_engagement"}):
            raise RouteExecutionError(
                "native trainer successor differs from its verified field boundary",
                reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED,
            )
        # The receipt certifies its own finished mechanic. The live native
        # trainer is a separate compulsory interruption at the identical tile;
        # its existing binding and battler must verify/handle it independently.
        return replace(receipt, details={
            **receipt.details, "pending_interruption_kind": "trainer_engagement",
        })

    def _handle_current(self, interruption):
        scripted = interruption.interruption == "scripted_dialogue"
        if not scripted and interruption.interruption not in {"trainer_engagement", "battle:2"}:
            return self.inner.handle(interruption)
        before = self.reader.read()
        cash_before = getattr(before, "player_money", None)
        if (before.map_id, (before.player_y, before.player_x)) != (
            interruption.map_id,
            interruption.at,
        ):
            raise RouteExecutionError("learned resource trainer boundary drifted")
        binding = self.binding_factory()
        # Scripted trainers may show introduction text before the battle or
        # sight-engagement flag is armed. Only the existing exact native
        # contract may own that text; ordinary dialogue stays with the inner
        # handler, and an unrecognized introduction is never guessed.
        if scripted and binding is None:
            return self.inner.handle(interruption)
        if len(self.trainer_evidence) >= self.maximum_trainers:
            raise RouteExecutionError("learned resource transport exhausted its trainer allowance")
        if (
            binding is None
            or binding.kind is not GoalKind.RECOVER_CONTROL
            or not binding.binding_ref.startswith("pokemon.red:retained-engagement:")
        ):
            raise RouteExecutionError("resource trainer lacks an exact learned engagement")
        report = binding.execute()
        verdict = binding.verify(report)
        battle = report.evidence.get("battle", {})
        if (
            verdict.status is GoalDecisionOutcome.FAILED
            and verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
            and report.evidence.get("support") == "already_engaged_native_trainer"
            and report.evidence.get("source_sha256")
            == binding.binding_ref.removeprefix("pokemon.red:retained-engagement:")
            and report.evidence.get("objective_completed") is False
            and report.evidence.get("reward") is None
            and isinstance(report.evidence.get("terminal_sha256"), str)
            and battle.get("schema") == "pokemon.red.learned-trainer-completion.v1"
            and battle.get("outcome") == "lost"
            and battle.get("field_ready") is True
        ):
            after = self.reader.read()
            if (
                not after.battle_state
                and self.reader.read_input_readiness().ready
                and not self.reader.read_bottom_dialogue_box_visible()
                and type(cash_before) is int
                and type(after.player_money) is int
            ):
                loss = SettledNativeTrainerLoss(
                    report, cash_before=cash_before, cash_after=after.player_money,
                )
                if settled_route_trainer_loss_evidence(loss.evidence):
                    raise loss
        if verdict.status is not GoalDecisionOutcome.SUCCEEDED or battle.get("outcome") != "won":
            raise RouteExecutionError("learned resource trainer did not win;retain native setback")
        after = self.reader.read()
        if (
            after.battle_state
            or (after.map_id, (after.player_y, after.player_x))
            != (interruption.map_id, interruption.at)
            or not self.reader.read_input_readiness().ready
            or self.reader.read_bottom_dialogue_box_visible()
        ):
            raise RouteExecutionError("learned resource trainer did not restore its route boundary")
        receipt = InterruptionReceipt(
            kind="trainer_engagement",
            resumed_map=after.map_id,
            resumed_at=(after.player_y, after.player_x),
            details=dict(
                battle_started=True,
                verified=True,
                learned_combat=True,
                support="already_engaged_native_trainer",
                binding_ref=binding.binding_ref,
                battle=dict(battle),
            ),
        )
        self.trainer_evidence.append(receipt)
        pending_field_trainer = getattr(self.reader, "trainer_engagement_active", None)
        if not (callable(pending_field_trainer) and pending_field_trainer() is True):
            self.observe_native_field_boundary()
        # Never walk onward with a fainted party after a verified learned win.
        # An adjacent native trainer still owns control and must settle first.
        hp = getattr(after, "party_hp", None)
        pending = getattr(self.reader, "trainer_engagement_active", None)
        if hp is not None and any(value <= 0 for value in hp) and not (
            callable(pending) and pending() is True
        ):
            stop = SettledNativeTrainerRecovery(
                report, cash_before=cash_before, cash_after=after.player_money, party_hp=hp,
            )
            if (len(hp) != getattr(after, "party_count", None)
                    or not settled_route_trainer_recovery_evidence(stop.evidence)
                    or report.evidence.get("source_sha256")
                    != binding.binding_ref.removeprefix("pokemon.red:retained-engagement:")):
                raise RouteExecutionError("trainer recovery lacks a verified living field party")
            raise stop
        return receipt
