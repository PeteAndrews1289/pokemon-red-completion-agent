"""Read-only, hash-bound continuation of original intent and observed history.

The caller authenticates this document and the terminal before loading. This
adapter grants no new budget, input, source partition or learning admission.
Preparation retains its ORIGINAL observations: an achieved target must not be
rebuilt as a new target above the current level. New specimens stay undecided.
"""

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import isfinite

from .goal_search_memory import GoalSearchMemory
from .party import MoveObservation, PartyMemberObservation, StatusCondition
from .party_preparation import (
    PreparationBudget,
    PreparationMember,
    PreparationPlan,
    PreparationPurpose,
)
from .post_battle_strategy import BattleAftermath, BattleResult
from .provenance import canonical_sha256
from .red_party import PokemonRedPartyReader
from .red_player_lesson import capture_player_lesson_snapshot

SCHEMA = "pokemon.red.native-player-continuation.v1"


def extend_preparation_roster(plan, current, *, evolution_edges=frozenset()):
    """Preserve original evidence/roles; adopt additional specimens as undecided."""
    if not isinstance(plan, PreparationPlan) or not isinstance(current, tuple):
        raise TypeError("typed preparation and current roster required")
    previous = {m.specimen_ref: m for m in plan.roster}
    live = {m.specimen_ref: m for m in current}
    if len(live) != len(current) or not previous.keys() <= live.keys():
        raise ValueError("continuation lost or duplicated a preparation specimen")
    roster = []
    for member in current:
        old = previous.get(member.specimen_ref)
        if old is None:
            roster.append(PreparationMember(member.specimen_ref, member.observation))
            continue
        if (
            (
                member.observation.species_id != old.observation.species_id
                and not _earned_evolution(old.observation, member.observation, evolution_edges)
            )
            or member.observation.level < old.observation.level
            or (
                old.observation.experience is not None
                and (
                    member.observation.experience is None
                    or member.observation.experience < old.observation.experience
                )
            )
        ):
            raise ValueError("continuation preparation identity or progress regressed")
        # Reordering is physical, not a change to the original level/XP evidence.
        roster.append(
            replace(old, observation=replace(old.observation, slot=member.observation.slot))
        )
    return replace(plan, roster=tuple(roster))


def _earned_evolution(old, new, edges):
    """Match a level-only lineage against the preserved original observation.

    A continuation may span both starter evolutions. Do not refresh its original
    level/XP evidence merely to make the latest species a direct-edge match.
    The per-battle evolution guard remains strictly one observed evolution.
    """
    if (
        new.level <= old.level
        or old.experience is None
        or new.experience is None
        or new.experience <= old.experience
    ):
        return False
    pending, visited = [old.species_id], {old.species_id}
    while pending:
        species = pending.pop()
        for source, target, level in edges:
            if source != species or new.level < level or target in visited:
                continue
            if target == new.species_id:
                return True
            visited.add(target)
            pending.append(target)
    return False


def refresh_preparation_roster(emulator, plan, *, evolution_rom=None):
    """Explicit immutable menu-boundary refresh; never alter targets or costs.

    Use between goals, not inside a closed preparation excursion. Collision,
    removal and regression checks remain in the existing reader/extension.
    The caller retains the returned plan and records a changed plan separately.
    """
    state = emulator.save_state_bytes()
    reader = PokemonRedPartyReader(emulator)
    current = tuple(
        PreparationMember(ref, member)
        for ref, member in zip(
            reader.preparation_specimen_refs(),
            reader.read().members,
            strict=True,
        )
    )
    edges = frozenset()
    if evolution_rom is not None:
        from .red_trainer_evolution import level_evolution_edges
        from .rom import verify_rom_bytes

        verify_rom_bytes(evolution_rom)
        edges = level_evolution_edges(evolution_rom)
    result = extend_preparation_roster(plan, current, evolution_edges=edges)
    if emulator.save_state_bytes() != state:
        raise ValueError("preparation roster refresh changed native state")
    return result


def _costs(spent):
    keys = {"decisions", "actions", "frames", "seconds", "heals", "cash_debits"}
    if not isinstance(spent, dict) or set(spent) != keys:
        raise ValueError("complete cumulative cost ledger required")
    for key, value in spent.items():
        if (
            type(value) not in ((int, float) if key == "seconds" else (int,))
            or not isfinite(value)
            or value < 0
        ):
            raise ValueError("invalid cumulative continuation cost")
    return dict(spent)


def _plan(document):
    if document is None:
        return None
    d = dict(document)
    roster = []
    for entry in d.pop("roster"):
        member = dict(entry)
        observation = dict(member.pop("observation"))
        observation["status"] = StatusCondition(observation["status"])
        observation["moves"] = tuple(MoveObservation(**m) for m in observation["moves"])
        roster.append(
            PreparationMember(
                **{**member, "purpose": PreparationPurpose(member["purpose"])},
                observation=PartyMemberObservation(**observation),
            )
        )
    return PreparationPlan(
        **{
            **d,
            "roster": tuple(roster),
            "targets": tuple(tuple(row) for row in d["targets"]),
            "budget": PreparationBudget(**d["budget"]),
        }
    )


def accumulate_player_costs(previous, *, decisions, actions, frames, seconds, heals, cash_deltas):
    """Carry actual spending without using later income to refund earlier costs.

    Each signed delta is cash before minus cash after ONE retained goal.
    Positive values are debits; negative values are income, never negative cost.
    """
    previous = _costs(previous)
    if not isinstance(cash_deltas, tuple) or any(type(n) is not int for n in cash_deltas):
        raise ValueError("per-goal integral cash deltas required")
    delta = _costs(
        dict(
            decisions=decisions,
            actions=actions,
            frames=frames,
            seconds=seconds,
            heals=heals,
            cash_debits=sum(max(0, n) for n in cash_deltas),
        )
    )
    return {key: previous[key] + delta[key] for key in previous}


def _battle(document):
    if document is None:
        return None
    return BattleAftermath(
        **{
            **document,
            "result": BattleResult(document["result"]),
            "opponent_levels": tuple(document["opponent_levels"]),
            "engaged_levels": tuple(document["engaged_levels"]),
        }
    )


@dataclass(frozen=True)
class ResumedPlayerContext:
    preparation: PreparationPlan | None
    battle: BattleAftermath | None
    spent: dict
    search_memory: GoalSearchMemory | None = None


def capture_player_continuation(runtime, *, preparation, battle, spent, search_memory=None):
    if preparation is not None and not isinstance(preparation, PreparationPlan):
        raise TypeError("typed original preparation plan required")
    if battle is not None and not isinstance(battle, BattleAftermath):
        raise TypeError("observed battle history required")
    if search_memory is not None and not isinstance(search_memory, GoalSearchMemory):
        raise TypeError("typed measured search memory required")
    state = runtime.emulator.save_state_bytes()
    observation, lesson = capture_player_lesson_snapshot(runtime)
    result = dict(
        schema=SCHEMA,
        state_sha256=sha256(state).hexdigest(),
        lesson=lesson,
        cash=observation.raw.player_money,
        bag=observation.raw.bag_items,
        preparation=None if preparation is None else asdict(preparation),
        battle=None if battle is None else asdict(battle),
        spent=_costs(spent),
        grants_new_budget=False,
        fit_allowed=False,
        **({"search_memory": search_memory.private_dict()} if search_memory is not None else {}),
    )
    if runtime.emulator.save_state_bytes() != state:
        raise ValueError("continuation capture changed native state")
    return result


def restore_player_continuation(
    runtime, document, *, expected_sha256, evolution_rom=None, loanable_refs=frozenset(),
):
    """Authenticate original facts and reobserve native state before any action."""
    if (
        not isinstance(document, dict)
        or set(document) - {"search_memory"}
        != {
            "schema",
            "state_sha256",
            "lesson",
            "cash",
            "bag",
            "preparation",
            "battle",
            "spent",
            "grants_new_budget",
            "fit_allowed",
        }
        or document["schema"] != SCHEMA
        or canonical_sha256(document) != expected_sha256
        or document["grants_new_budget"] is not False
        or document["fit_allowed"] is not False
    ):
        raise ValueError("continuation identity or scope differs")
    memory = (
        GoalSearchMemory.from_private_dict(document["search_memory"])
        if "search_memory" in document else None
    )
    state = runtime.emulator.save_state_bytes()
    if sha256(state).hexdigest() != document["state_sha256"]:
        raise ValueError("continuation terminal differs")
    preparation, battle, spent = (
        _plan(document["preparation"]),
        _battle(document["battle"]),
        _costs(document["spent"]),
    )
    graph = runtime.adapter.graph
    facts = frozenset(
        f
        for name in document["lesson"]["completed_objectives"]
        for f in graph.objective(name).completion_facts
    )
    runtime.observer.latch_verified_facts(facts)
    observation, lesson = capture_player_lesson_snapshot(runtime)
    if (
        canonical_sha256(lesson) != canonical_sha256(document["lesson"])
        or observation.raw.player_money != document["cash"]
        or canonical_sha256(observation.raw.bag_items) != canonical_sha256(document["bag"])
    ):
        raise ValueError("restored continuation observation differs")
    if preparation is not None:
        reader = PokemonRedPartyReader(runtime.emulator)
        current = tuple(
            PreparationMember(ref, member)
            for ref, member in zip(
                reader.preparation_specimen_refs(), reader.read().members, strict=True
            )
        )
        edges = frozenset()
        if evolution_rom is not None:
            from .red_trainer_evolution import level_evolution_edges
            from .rom import verify_rom_bytes

            verify_rom_bytes(evolution_rom)
            edges = level_evolution_edges(evolution_rom)
        missing = {m.specimen_ref for m in preparation.roster} - {
            m.specimen_ref for m in current
        }
        if missing:
            if (
                not isinstance(loanable_refs, frozenset)
                or missing != loanable_refs
                or len(missing) != 1
            ):
                raise ValueError("continuation lost an undeclared preparation specimen")
            original = next(m for m in preparation.roster if m.specimen_ref in missing)
            boxed = [m for m in runtime.reader.read_box_specimen_identities()
                     if m.preparation_ref == original.specimen_ref]
            if (
                len(boxed) != 1
                or boxed[0].level < original.observation.level
                or (original.observation.experience is not None
                    and boxed[0].experience < original.observation.experience)
                or (boxed[0].species_id != original.observation.species_id
                    and not _earned_evolution(original.observation, boxed[0], edges))
            ):
                raise ValueError("continuation named loan is missing, ambiguous or regressed")
            # Validate retained active members against ORIGINAL observations.
            # The boxed observation remains historical, never a fabricated HP
            # claim; its actual fingerprint/XP/species were checked separately.
            original_refs = {m.specimen_ref for m in preparation.roster}
            current = tuple(m for m in current if m.specimen_ref in original_refs) + (original,)
            # The boxed original's historical slot can now belong to an active
            # retained member. These are logical preparation slots, not a claim
            # that the boxed individual is physically in the party. Keep all
            # original observations/roles and exclude the temporary guest.
            current = tuple(
                replace(member, observation=replace(member.observation, slot=index))
                for index, member in enumerate(current, 1)
            )
        preparation = extend_preparation_roster(preparation, current, evolution_edges=edges)
    if runtime.emulator.save_state_bytes() != state:
        raise ValueError("continuation restoration changed native state")
    return ResumedPlayerContext(preparation, battle, spent, memory)
