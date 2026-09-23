"""Opt-in, resource-admitted story alternatives for the existing mixed menu.

This is a Red adapter, not a route or new policy. It covers the existing
Celadon Erika, Fuji and Saffron chapters plus explicitly observed preinstalled
Ice Beam Silph entry. Other chapters fail closed. No historical menu changes.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

from .erika import EARLY_ERIKA_ICE_BEAM_LINEAGES, early_erika_party_supported
from .goal_manager import GoalKind
from .goal_manager_runtime import GoalBindingSet, GoalExecutionReport
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .objective_skills import ObjectiveSkillRegistry
from .observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    EventFlag,
    ItemId,
    MapId,
    event_flag_is_set,
)
from .red_goal_manager import RedGoalObservation, RedStoryGoalBindingProvider
from .red_live_option_menu import RedLiveSupplementalOption, supplemental_live_option
from .saffron import EEVEE, FRESH_WATER_PRICE, JOLTEON, THUNDER_STONE_PRICE
from .silph import (
    X_ACCURACY_REPLACEMENT_PRICE,
    X_SPECIAL_PRICE,
    X_SPECIAL_PURCHASE_QUANTITY,
)
from .tower import (
    HIDEOUT_SUPER_POTION_RESERVE,
    QUALIFIED_TOWER_SPECIAL_MOVES,
    party_core_intact,
    tower_party_supported,
)


@dataclass(frozen=True)
class StoryResourceAdmission:
    executable: bool
    reason: str
    planned_spend: int = 0
    scripted_support: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.executable) is not bool or not self.reason:
            raise ValueError("story admission needs an explicit result and reason")
        if type(self.planned_spend) is not int or self.planned_spend < 0:
            raise ValueError("story spending must be a nonnegative integer")
        if not self.executable and (self.planned_spend or self.scripted_support):
            raise ValueError("blocked story cannot advertise a spend or support plan")


def admit_red_story_resources(
    observation: RedGoalObservation, objective_id: str,
    *, silph_gift_received: bool | None = None,
) -> StoryResourceAdmission:
    """Check observed entry resources without reading memory or issuing input.

    These checks supplement, never replace, graph legality and skill availability.
    They establish starting compatibility, not a guarantee of chapter success.
    Missing telemetry and unrepresented chapter variants fail closed.
    """
    raw = observation.raw
    def blocked(reason: str) -> StoryResourceAdmission:
        return StoryResourceAdmission(False, reason)
    if objective_id not in {"defeat_erika", "rescue_fuji", "reach_saffron", "liberate_silph"}:
        return blocked("unsupported_resource_contract")
    center = (MapId.SAFFRON_POKECENTER if objective_id == "liberate_silph"
              else MapId.CELADON_POKECENTER)
    if not observation.input_ready or raw.battle_state != 0 or (
        raw.map_id, raw.player_x, raw.player_y
    ) != (center, 3, 3):
        return blocked("start_boundary")
    if any(value is None for value in (
        raw.party_species_ids, raw.party_hp, raw.party_max_hp, raw.party_status,
        raw.bag_items, raw.player_money, raw.party_moves, raw.party_pp,
    )):
        return blocked("missing_resource_observation")
    party = tuple(raw.party_species_ids)
    if not party or any(len(value) != len(party) for value in (
        raw.party_hp, raw.party_max_hp, raw.party_status, raw.party_moves, raw.party_pp,
    )) or raw.party_count != len(party):
        return blocked("incomplete_party")
    if raw.party_hp != raw.party_max_hp or any(raw.party_status) or min(raw.party_hp) <= 0:
        return blocked("party_needs_recovery")
    bag = dict(raw.bag_items)
    cost = 0
    support = ("navigation", "scripted_battles", "automatic_healing")
    if objective_id == "liberate_silph":
        from .red_story_funding import silph_supply_plan
        from .silph import SILPH_ICE_BEAM_LINEAGES, _silph_capacity_ready

        if silph_gift_received is not False:
            return blocked("silph_gift_not_verified_unclaimed")
        if not party_core_intact(party) or not 3 <= len(party) <= 6 or (
            tuple(raw.first_party_moves or ()), tuple(raw.first_party_pp or ()),
        ) not in SILPH_ICE_BEAM_LINEAGES.values():
            return blocked("unsupported_silph_party_or_moves")
        # This frontier admits only the already-earned Ice Beam variant.
        events = (EventFlag.BEAT_SILPH_CO_5F_TRAINER_0,
                  EventFlag.BEAT_SILPH_CO_3F_TRAINER_0,
                  EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2,
                  EventFlag.BEAT_SILPH_CO_RIVAL, EventFlag.BEAT_SILPH_CO_11F_TRAINER_0,
                  EventFlag.SILPH_CO_11_UNLOCKED_DOOR, EventFlag.BEAT_SILPH_CO_GIOVANNI,
                  EventFlag.GOT_MASTER_BALL, 0x18D, 0x18E)
        if raw.event_flags is None or len(raw.event_flags) <= max(map(int, events)) // 8:
            return blocked("missing_silph_event_boundary")
        if not event_flag_is_set(raw.event_flags, EventFlag.GOT_TM13) or any(
            event_flag_is_set(raw.event_flags, int(event)) for event in events
        ) or any(bag.get(item) for item in (
            ItemId.CARD_KEY, ItemId.MASTER_BALL, ItemId.FRESH_WATER, ItemId.TM13_ICE_BEAM,
        )):
            return blocked("silph_preparation_already_changed")
        if raw.status_flags_1 is None or not raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK:
            return blocked("saffron_guard_access")
        if not _silph_capacity_ready(bag):
            return blocked("bag_capacity")
        cost = silph_supply_plan(raw).purchase_cost
        support += ("no_sale_stock_top_up", "owned_item_storage_if_needed")
    elif objective_id == "rescue_fuji":
        moves, pp = raw.first_party_moves, raw.first_party_pp
        if not tower_party_supported(party) or moves is None or pp is None or (
            len(moves) < 3 or len(pp) < 3 or moves[2] not in QUALIFIED_TOWER_SPECIAL_MOVES
            or not pp[2] & 0x3F
        ):
            return blocked("unsupported_tower_party_or_move")
        if not bag.get(ItemId.SILPH_SCOPE) or (
            bag.get(ItemId.SUPER_POTION, 0) < HIDEOUT_SUPER_POTION_RESERVE
        ):
            return blocked("missing_scope_or_potions")
        # Leave room for chapter pickups; do not invent a cleanup route.
        if len(bag) > 16:
            return blocked("bag_capacity")
    elif objective_id == "defeat_erika":
        if not early_erika_party_supported(party) or (
            tuple(raw.first_party_moves or ()), tuple(raw.first_party_pp or ()),
        ) not in EARLY_ERIKA_ICE_BEAM_LINEAGES:
            return blocked("unsupported_erika_party_or_moves")
        if raw.badge_bits not in {0x07, 0x17} or raw.event_flags is None or (
            len(raw.event_flags) <= max(int(event) for event in (
                EventFlag.BEAT_ERIKA, EventFlag.GOT_TM21, EventFlag.GOT_TM13,
            )) // 8
        ):
            return blocked("missing_erika_event_boundary")
        if any(event_flag_is_set(raw.event_flags, int(event)) for event in (
            EventFlag.BEAT_ERIKA, EventFlag.GOT_TM21, EventFlag.GOT_TM13,
        )) or any(bag.get(item) for item in (
            ItemId.TM21_MEGA_DRAIN, ItemId.TM13_ICE_BEAM, ItemId.FRESH_WATER,
        )):
            return blocked("erika_preparation_already_changed")
        special = bag.get(ItemId.X_SPECIAL, 0)
        accuracy = bag.get(ItemId.X_ACCURACY, 0)
        if not 0 <= special <= X_SPECIAL_PURCHASE_QUANTITY or not 0 <= accuracy <= 1:
            return blocked("unsupported_battle_item_stock")
        # Preserve headroom for both new stacks and the roof exchange. Existing
        # chapter cleanup remains available but is not assumed by this frontier.
        if len(bag) + int(special == 0) + int(accuracy == 0) + 1 > 20:
            return blocked("bag_capacity")
        cost = (FRESH_WATER_PRICE + (X_SPECIAL_PURCHASE_QUANTITY - special) * X_SPECIAL_PRICE
                + (1 - accuracy) * X_ACCURACY_REPLACEMENT_PRICE)
        support += ("ice_beam_lesson", "battle_item_purchase")
    else:
        if raw.status_flags_1 is None:
            return blocked("missing_guard_access_observation")
        support = ("navigation",)
        if not raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK:
            if any(bag.get(item) for item in (
                ItemId.FRESH_WATER, ItemId.SODA_POP, ItemId.LEMONADE,
            )):
                return blocked("unsupported_carried_drink")
            cost = FRESH_WATER_PRICE
            if len(party) in {3, 4} and not {EEVEE, JOLTEON}.intersection(party):
                # The legacy preparation's terminal verifier is stricter than
                # its entry checks. Respect that contract before any purchase;
                # do not broaden it or force an evolution to satisfy it here.
                if not party_core_intact((*party, JOLTEON)):
                    return blocked("unsupported_jolteon_terminal_core")
                if bag.get(ItemId.THUNDER_STONE) or (
                    "pokemon:national:133" in observation.collection_observation.owned_species
                ):
                    return blocked("unsupported_eevee_preparation_history")
                cost += THUNDER_STONE_PRICE
                support += ("eevee_gift", "jolteon_evolution")
            if len(bag) >= 20:
                return blocked("bag_capacity")
            support += ("guard_drink_purchase",)
    if raw.player_money < cost:
        return blocked("insufficient_cash")
    return StoryResourceAdmission(True, "entry_resources_verified", cost, support)


@dataclass(frozen=True)
class RedStoryFrontier:
    supplements: tuple[RedLiveSupplementalOption, ...]
    admissions: tuple[tuple[str, StoryResourceAdmission], ...]

    @property
    def required_cash(self) -> int:
        """Useful budget for the largest admitted single goal, never their sum."""
        return max((row.planned_spend for _, row in self.admissions if row.executable), default=0)


def build_red_story_frontier(
    *, observation: RedGoalObservation, provider: RedStoryGoalBindingProvider,
    ordinary_bindings: GoalBindingSet, observe: Callable[[], RedGoalObservation],
    model_feature_version: int = 4,
    observe_silph_gift: Callable[[], bool] | None = None,
) -> RedStoryFrontier:
    """Join private chapter executors to existing identity-free policy features.

    Cost-aware story projection requires v4. Ordinary recovery/storage bindings
    remain with the caller's mixed menu and its unchanged safety controller.
    """
    if type(model_feature_version) is not int or model_feature_version != 4:
        raise ValueError("resource-aware story frontier requires feature version 4")
    if any(binding.kind is GoalKind.ADVANCE_STORY for binding in ordinary_bindings.bindings):
        raise ValueError("remove legacy single-target story binding before plural composition")
    if not callable(observe):
        raise TypeError("story frontier requires a live re-observation")
    skills, admissions = [], []
    for objective in provider.graph.available_objectives(observation.game_state):
        skill = provider.skills.get(objective.id)
        if skill is None:
            admissions.append((objective.id, StoryResourceAdmission(False, "missing_skill")))
            continue
        provider.skills.require_for(objective)
        admission = admit_red_story_resources(observation, objective.id,
            silph_gift_received=(observe_silph_gift() if objective.id == "liberate_silph"
                                 and observe_silph_gift is not None else None))
        if not skill.availability(observation.game_state).executable:
            admission = StoryResourceAdmission(False, "skill_unavailable")
        admissions.append((objective.id, admission))
        if admission.executable:
            skills.append(skill)
    admitted = replace(provider, skills=ObjectiveSkillRegistry(skills))
    supplements = []
    plans = dict(admissions)
    for offer in admitted.offers(observation):
        binding = offer.binding
        objective_id = binding.binding_ref.removeprefix("pokemon.red:story:")
        plan = plans[objective_id]
        question = GoalBindingSet((binding.opportunity, *(row for row in
            ordinary_bindings.opportunities if row.kind is not GoalKind.ADVANCE_STORY)),
            (binding, *ordinary_bindings.bindings)).question(observation.situation)
        candidate = project_living_dex_goal_candidate(
            question, 0, feature_version=4, binding_ref=binding.binding_ref,
        )
        candidate = replace(candidate, economy_offer=replace(
            candidate.economy_offer, planned_spend=plan.planned_spend,
        ))

        def execute(binding=binding, plan=plan, objective_id=objective_id) -> GoalExecutionReport:
            live = observe()
            if live.raw != observation.raw or live.game_state != observation.game_state or (
                not live.input_ready
            ):
                raise ValueError("story frontier changed before execution; rebuild without acting")
            if objective_id == "liberate_silph" and (
                observe_silph_gift is None or observe_silph_gift() is not False
            ):
                raise ValueError("Silph gift boundary changed before execution")
            report = binding.execute()
            return replace(report, evidence={**report.evidence, "story_resources": {
                "planned_spend": plan.planned_spend,
                "scripted_support": list(plan.scripted_support),
            }})

        supplements.append(supplemental_live_option(replace(binding, execute=execute), candidate))
    return RedStoryFrontier(tuple(supplements), tuple(admissions))
