"""Read-only, hash-bound continuation of original intent and observed history.

The caller authenticates this document and the terminal before loading. This
adapter grants no new budget, input, source partition or learning admission.
Preparation retains its ORIGINAL observations: an achieved target must not be
rebuilt as a new target above the current level. New specimens stay undecided.
"""

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import isfinite

from .goal_search_memory import SEARCH_MEMORY_SCHEMA, GoalSearchMemory
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
from .red_player_configuration import checkpoint_quiescent, player_lifecycle_fields
from .red_player_lesson import capture_player_lesson_snapshot

SCHEMA = "pokemon.red.native-player-continuation.v1"


def step_search_memory_dict(document, *, state_sha256=None):
    """Extract a validated private search-memory mapping from a step or checkpoint.

    Step-boundary ``search-memory-before.json`` and ``movement-memory-before.json``
    wrap the private ``GoalSearchMemory`` mapping in an outer observation envelope,
    whereas ``CONTEXT.json["search_memory"]`` stores the inner private mapping
    directly. Validate either form and optionally merge movement observations
    recorded alongside the same ``state_sha256``.
    """
    if document is None:
        return None
    if not isinstance(document, dict):
        raise ValueError("step search memory document must be a mapping")
    if document.get("schema") == SEARCH_MEMORY_SCHEMA:
        return GoalSearchMemory.from_private_dict(document).private_dict()
    inner = document.get("memory")
    if not isinstance(inner, dict):
        raise ValueError("step search memory envelope lacks inner memory mapping")
    if state_sha256 is not None and document.get("state_sha256") != state_sha256:
        raise ValueError("step search memory state_sha256 differs from boundary")
    return GoalSearchMemory.from_private_dict(inner).private_dict()


def build_step_diagnostic_checkpoint(
    parent_context,
    *,
    state_bytes,
    before_snapshot,
    spent,
    step_search_memory=None,
    step_movement_memory=None,
    guest_backend_closed=True,
):
    """Build a quiescent diagnostic parent checkpoint from a saved step boundary.

    Preserves the parent segment's original ``preparation`` observations and
    ``field_carrier`` custody while unwrapping step-boundary search/movement
    memory envelopes and emitting the top-level ``released=True`` +
    ``driver_terminal`` lifecycle fields required by ``authenticate_parent``
    and ``restore_player_continuation``.
    """
    if not isinstance(parent_context, dict) or parent_context.get("schema") != SCHEMA:
        raise ValueError("step diagnostic checkpoint requires a valid parent context")
    if not isinstance(state_bytes, (bytes, bytearray)):
        raise TypeError("step diagnostic checkpoint requires raw state bytes")
    state_sha = sha256(state_bytes).hexdigest()
    if not isinstance(before_snapshot, dict) or before_snapshot.get("state_sha256") != state_sha:
        raise ValueError("step diagnostic before_snapshot state_sha256 differs")
    facts = before_snapshot.get("facts")
    if not isinstance(facts, dict) or not isinstance(facts.get("player_lesson"), dict):
        raise ValueError("step diagnostic before_snapshot lacks player_lesson facts")
    diagnostics = facts.get("diagnostics")
    bag = (
        diagnostics["bag_items"]
        if isinstance(diagnostics, dict) and "bag_items" in diagnostics
        else parent_context.get("bag")
    )
    if not isinstance(bag, list) or type(facts.get("cash")) is not int:
        raise ValueError("step diagnostic before_snapshot lacks cash or bag_items")
    memory_doc = (
        step_search_memory_dict(step_search_memory, state_sha256=state_sha)
        if step_search_memory is not None
        else step_search_memory_dict(parent_context.get("search_memory"))
    )
    if step_movement_memory is not None:
        move_doc = step_search_memory_dict(step_movement_memory, state_sha256=state_sha)
        if memory_doc is None:
            memory_doc = move_doc
        else:
            merged = dict(memory_doc)
            if "movement_visits" in move_doc:
                merged["movement_visits"] = move_doc["movement_visits"]
            if "movement_returns" in move_doc:
                merged["movement_returns"] = move_doc["movement_returns"]
            memory_doc = GoalSearchMemory.from_private_dict(merged).private_dict()
    preparation = _plan(parent_context.get("preparation"))
    context_doc = dict(
        schema=SCHEMA,
        state_sha256=state_sha,
        lesson=dict(facts["player_lesson"]),
        cash=facts["cash"],
        bag=list(bag),
        preparation=None if preparation is None else asdict(preparation),
        battle=None,
        spent=_costs(spent),
        grants_new_budget=False,
        fit_allowed=False,
        **({"search_memory": memory_doc} if memory_doc is not None else {}),
        **(
            {"field_carrier": dict(parent_context["field_carrier"])}
            if "field_carrier" in parent_context
            else {}
        ),
    )
    result_doc = dict(
        state_sha256=state_sha,
        context_sha256=canonical_sha256(context_doc),
        spent=dict(context_doc["spent"]),
        field_ready=bool(facts.get("input_ready")) and facts.get("battle_state") == 0,
        released=True,
        **player_lifecycle_fields(
            scope="driver_terminal",
            released=True,
            guest_backend_closed=guest_backend_closed,
        ),
    )
    if not checkpoint_quiescent(result_doc):
        raise ValueError("step diagnostic checkpoint result is not quiescent")
    return context_doc, result_doc


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


def _stored_undecided_preparation(plan, current, guard, edges):
    """Reconcile active preparation with exact,unreserved native storage.

    Undecided captures have no retained task to erase. Missing protected roles,
    targets and named custody still fail;original active observations survive.
    """
    from .red_player_party_guard import RedPlayerPartyGuard

    live = {member.specimen_ref for member in current}
    missing = {member.specimen_ref for member in plan.roster} - live
    if not missing or guard is None:
        return plan
    if (not isinstance(guard, RedPlayerPartyGuard) or guard.loanable_refs
            or guard.field_carrier is not None or guard.storage_reader is None
            or missing & set(guard.refs)
            or guard.reader.preparation_specimen_refs()
            != tuple(member.specimen_ref for member in current)):
        raise ValueError("stored preparation refresh lacks restored retained custody")
    guard.verify_active_roster_restored()
    if guard.reader.read().members != tuple(member.observation for member in current):
        raise ValueError("stored preparation refresh has incoherent active observations")
    targeted = {ref for ref, _ in plan.targets}
    boxed = guard.storage_reader.read_box_specimen_identities()
    for old in plan.roster:
        if old.specimen_ref not in missing:
            continue
        if (old.purpose is not PreparationPurpose.UNDECIDED or old.purpose_reason
                or old.milestone_level is not None or old.specimen_ref in targeted):
            raise ValueError("stored preparation refresh cannot discard an assigned purpose")
        matches = [member for member in boxed
                   if member.preparation_ref == old.specimen_ref
                   and (member.species_id == old.observation.species_id
                        or _earned_evolution(old.observation, member, edges))]
        if (len(matches) != 1 or old.observation.experience is None
                or matches[0].experience < old.observation.experience
                or matches[0].level < old.observation.level):
            raise ValueError("stored undecided specimen is missing,ambiguous or regressed")
    roster = tuple(replace(member, observation=replace(member.observation, slot=i))
                   for i, member in enumerate(
                       (member for member in plan.roster if member.specimen_ref not in missing), 1))
    return replace(plan, roster=roster)


def refresh_preparation_roster(emulator, plan, *, evolution_rom=None, party_guard=None):
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
    if evolution_rom is None and party_guard is not None:
        from .red_player_party_guard import RedPlayerPartyGuard

        if isinstance(party_guard, RedPlayerPartyGuard):
            edges = party_guard.edges
    plan = _stored_undecided_preparation(plan, current, party_guard, edges)
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
    field_carrier: object = None
    story_kind_commitment: object = None


def capture_player_continuation(
    runtime, *, preparation, battle, spent, search_memory=None, story_kind_commitment_carrier=None, preparation_story_history=None,
):
    if preparation is not None and not isinstance(preparation, PreparationPlan):
        raise TypeError("typed original preparation plan required")
    if battle is not None and not isinstance(battle, BattleAftermath):
        raise TypeError("observed battle history required")
    if search_memory is not None and not isinstance(search_memory, GoalSearchMemory):
        raise TypeError("typed measured search memory required")
    if story_kind_commitment_carrier is not None:
        from .red_story_kind_commitment import StoryKindCommitmentCarrier

        if type(story_kind_commitment_carrier) is not StoryKindCommitmentCarrier:
            raise TypeError("typed story kind commitment carrier required")
    if preparation_story_history is not None:
        from .red_player_preparation_history import StoryPreparationHistory
        if type(preparation_story_history) is not StoryPreparationHistory:
            raise TypeError("typed story preparation history required")
    state = runtime.emulator.save_state_bytes()
    guard = getattr(runtime.adapter, "party_guard", None)
    if preparation is not None:
        from .red_player_party_guard import RedPlayerPartyGuard

        if (isinstance(guard, RedPlayerPartyGuard) and not guard.loanable_refs
                and guard.field_carrier is None):
            live = set(guard.reader.preparation_specimen_refs())
            missing = tuple(member for member in preparation.roster
                            if member.specimen_ref not in live)
            if (missing and not {member.specimen_ref for member in missing} & set(guard.refs)
                    and all(member.purpose is PreparationPurpose.UNDECIDED
                            and not member.purpose_reason and member.milestone_level is None
                            and member.specimen_ref not in dict(preparation.targets)
                            for member in missing)):
                preparation = refresh_preparation_roster(
                    runtime.emulator, preparation, party_guard=guard)
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
    if preparation_story_history is not None and preparation_story_history.retained is not None:
        result["preparation_story_loss"] = preparation_story_history.private_dict()
    if story_kind_commitment_carrier is not None and story_kind_commitment_carrier.current is not None:
        result["story_kind_commitment"] = story_kind_commitment_carrier.document()
    guard = getattr(runtime.adapter, "party_guard", None)
    custody = getattr(guard, "field_carrier", None)
    if custody is not None:
        guard.verify()
        result["field_carrier"] = custody.private_dict()
    if runtime.emulator.save_state_bytes() != state:
        raise ValueError("continuation capture changed native state")
    return result


def restore_player_continuation(
    runtime, document, *, expected_sha256, evolution_rom=None, loanable_refs=frozenset(),
):
    """Authenticate original facts and reobserve native state before any action."""
    if (
        not isinstance(document, dict)
        or set(document) - {"search_memory", "field_carrier", "story_kind_commitment", "preparation_story_loss"}
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
    if "preparation_story_loss" in document:
        from .red_player_preparation_history import StoryPreparationHistory
        StoryPreparationHistory.from_document(document["preparation_story_loss"])
    memory = (
        GoalSearchMemory.from_private_dict(document["search_memory"])
        if "search_memory" in document else None
    )
    custody = None
    if "field_carrier" in document:
        from .red_field_carrier_custody import FieldCarrierCustody, restore_custody_guard
        custody = FieldCarrierCustody.from_private_dict(document["field_carrier"])
        if evolution_rom is None or custody.original_loanable_refs != loanable_refs:
            raise ValueError("field-carrier continuation lacks its original declared guard")
    state = runtime.emulator.save_state_bytes()
    if sha256(state).hexdigest() != document["state_sha256"]:
        raise ValueError("continuation terminal differs")
    if custody is not None:
        restored_guard = restore_custody_guard(runtime, custody, rom=evolution_rom)
        # The legacy inner factory has a plain slotted adapter. Its outer
        # configured factory installs the returned custody before execution.
        if hasattr(runtime.adapter, "party_guard"):
            runtime.adapter.party_guard = restored_guard
    preparation, battle, spent = (
        _plan(document["preparation"]),
        _battle(document["battle"]),
        _costs(document["spent"]),
    )
    commitment = None
    if "story_kind_commitment" in document:
        from .red_story_kind_commitment import StoryKindCommitmentCarrier

        carrier = StoryKindCommitmentCarrier.from_document(
            document["story_kind_commitment"],
            completed_objectives=document["lesson"]["completed_objectives"],
        )
        commitment = carrier.current
        if commitment is not None:
            runtime.adapter.graph.objective(commitment.objective_ref)
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
            permitted_missing = (
                frozenset({custody.displaced_ref, custody.carrier_ref})
                if custody is not None and custody.phase == "pending" else loanable_refs
            )
            if (
                not isinstance(loanable_refs, frozenset)
                or (missing != loanable_refs if custody is None
                    else not missing <= permitted_missing)
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
    return ResumedPlayerContext(preparation, battle, spent, memory, custody, commitment)
