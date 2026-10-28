"""Optional member intents on the existing bounded preparation executor.

Nothing here chooses a member, changes a persistent role, or sends game input.
The outer goal policy selects one returned executor and retains its real costs.
"""

from collections.abc import Mapping
from dataclasses import replace

from .gen1_cartridge import EvolutionMethod, evolution_graph, internal_to_dex
from .party_preparation import (
    PreparationMember,
    PreparationPlan,
    PreparationPurpose,
    build_optional_preview_preparation_plan,
)
from .player_option_preparation import OptionPreparation
from .post_battle_strategy import BattleAftermath, BattleResult
from .provenance import canonical_sha256
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_party_preparation import observe_preparation_members
from .red_player_field_goals import routed_preparation_binding
from .scenario_lab import ScenarioPartition


def preparation_venue_rank(encounter_levels, travel_cost):
    """Disclosed level-band support; not a learned venue choice or XP promise.

    Prefer productive reachable bands to choosing low-level grass solely for
    its short approach. The caller must still prove reachability, nurse access
    and actual training results. Equal bands prefer cheaper travel. This reads
    decoded encounter levels, not species identities or previous outcomes.
    """
    if (not isinstance(encounter_levels, tuple) or not encounter_levels
            or any(type(level) is not int or not 1 <= level <= 100
                   for level in encounter_levels)
            or type(travel_cost) not in (int, float) or not 0 <= travel_cost < float("inf")):
        raise ValueError("preparation venue requires actual levels and finite travel cost")
    return -sum(encounter_levels) / len(encounter_levels), travel_cost


def preparation_venue_within_party_band(encounter_levels, party_levels):
    """Optional decoded-band screen for a weak fresh party, not a win promise.

    Keep the existing productivity ranking, but exclude average wild bands
    above the actual strongest member. This does not select a trainee, goal or
    route, require grinding, or predict type matchups and critical hits.
    """
    preparation_venue_rank(encounter_levels, 0)
    if (not isinstance(party_levels, tuple) or not party_levels
            or any(type(level) is not int or not 1 <= level <= 100 for level in party_levels)):
        raise ValueError("venue screening requires actual party levels")
    return sum(encounter_levels)/len(encounter_levels) <= max(party_levels)


def member_preparation_plans(
    plan: PreparationPlan,
    members: tuple[PreparationMember, ...],
    *,
    opponent_levels: tuple[int, ...],
    forecast_ref: str,
    cartridge: RedPracticeCartridge,
    evolutions: Mapping[int, int | None],
    maximum_level_gain: int = 3,
    reference_mode: str = "median",
    allow_above_reference: bool = False,
    observed_defeat: BattleAftermath | None = None,
) -> tuple[tuple[PreparationPlan, OptionPreparation], ...]:
    """One temporary target per eligible observed member; no lowest-slot priority.

    Existing field/collection roles stay excluded. Undecided catches are optional
    candidates, not automatically assigned permanent combat duty. The dose retains
    the existing three-level ceiling. By default it cannot exceed the selected
    opposition reference. A typed observed loss permits explicit short contrasts
    above it; the native port admits only typed TRAIN or DEVELOPMENT scope.
    The caller authenticates the loss and source ancestry. Roles and the actual
    opposition quote are never edited to manufacture a target.
    """
    if type(allow_above_reference) is not bool or (allow_above_reference and (
        not isinstance(observed_defeat, BattleAftermath)
        or observed_defeat.result is not BattleResult.LOST
    )):
        raise ValueError("above-reference option requires an observed defeat")
    if (len(members) != len(plan.roster)
            or {m.specimen_ref for m in members} != {m.specimen_ref for m in plan.roster}):
        raise ValueError("member inventory changed; reassess the retained roster")
    choices = []
    for member in members:
        if member.purpose not in (PreparationPurpose.COMBAT, PreparationPurpose.UNDECIDED):
            continue
        mon = member.observation
        if mon.experience is None:
            continue
        temporary = replace(
            member,
            purpose=PreparationPurpose.COMBAT,
            purpose_reason="optional temporary member preparation",
            milestone_level=None,
        )
        roster = tuple(temporary if m.specimen_ref == member.specimen_ref else m for m in members)
        quoted = build_optional_preview_preparation_plan(
            roster,
            opponent_levels,
            forecast_ref=forecast_ref,
            maximum_level_gain=maximum_level_gain,
            budget=plan.budget,
            reference_mode=reference_mode,
            allow_above_reference=allow_above_reference,
        )
        target = dict(quoted.targets).get(member.specimen_ref)
        if target is None:
            continue
        single = replace(quoted, targets=((member.specimen_ref, target),))
        xp = cartridge.species(mon.species_id).experience_at_level(target) - mon.experience
        known_moves = tuple(m for m in mon.moves if m.is_known)
        maxima = tuple(m.max_pp for m in known_moves if m.max_pp is not None)
        pp = (sum(m.current_pp for m in known_moves) / max(1, sum(maxima))
              if known_moves and len(maxima) == len(known_moves) else None)
        descriptor = OptionPreparation(
            mon.level,
            target,
            xp,
            mon.hp_ratio,
            pp,
            member.purpose is PreparationPurpose.COMBAT,
            member.purpose is PreparationPurpose.UNDECIDED,
            evolutions.get(mon.species_id),
        )
        choices.append((single, descriptor))
    return tuple(choices)


def member_preparation_options(
    runtime,
    actions,
    *,
    plan,
    opponent_levels,
    forecast_ref,
    home_map,
    route,
    maximum_level_gain=3,
    reference_mode="median",
    allow_above_reference=False,
    observed_defeat=None,
    **kwargs,
):
    """Produce fresh routed executors with distinct private member/target identity."""
    partition = getattr(kwargs.get("battler"), "source_partition", None)
    if (allow_above_reference and partition is not ScenarioPartition.TRAIN
            and partition is not ScenarioPartition.DEVELOPMENT):
        raise ValueError("above-reference native preparation requires typed TRAIN or DEVELOPMENT scope")
    members = observe_preparation_members(runtime.emulator, plan)
    dex = internal_to_dex(route.rom)
    codes = {number: code for code, number in dex.items()}
    levels = {
        codes[e.from_species]: e.requirement
        for edges in evolution_graph(route.rom).values()
        for e in edges
        if e.method is EvolutionMethod.LEVEL
    }
    choices = member_preparation_plans(
        plan,
        members,
        opponent_levels=opponent_levels,
        forecast_ref=forecast_ref,
        cartridge=RedPracticeCartridge(route.rom),
        evolutions=levels,
        maximum_level_gain=maximum_level_gain,
        reference_mode=reference_mode,
        allow_above_reference=allow_above_reference,
        observed_defeat=observed_defeat,
    )
    result = []
    for intent, descriptor in choices:
        binding = routed_preparation_binding(
            runtime,
            actions,
            home_map=home_map,
            route=route,
            plan=intent,
            **kwargs,
        )
        if binding is None:
            continue
        # The existing field route ref only identifies the origin/home. Bind
        # member intent as well so sibling executors cannot share an identity.
        binding = replace(
            binding,
            binding_ref="pokemon.red:member-preparation:"
            + canonical_sha256(
                dict(
                    executor=binding.binding_ref,
                    targets=intent.targets,
                    facts=descriptor.public_dict(),
                )
            ),
        )
        result.append((binding, descriptor))
    return tuple(result)
