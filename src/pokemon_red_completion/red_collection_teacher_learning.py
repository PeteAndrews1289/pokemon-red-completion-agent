"""Actual collection lessons for the existing local option-value learner.

Teachers choose only in TRAIN. The sealed question precedes input; admission
reconstructs the selected vector and native outcome, never alternative labels.
This is a bridge to existing recording/registration/fit machinery, not a policy.
"""

import re
from dataclasses import asdict, dataclass

from .goal_manager import GoalKind
from .living_dex_option_value import LivingDexCurriculumOutcomeExample
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .provenance import canonical_sha256
from .red_player_lesson_runtime import observe_native_player_boundary, player_diagnostic_state
from .red_player_training_plan import COMPLETION_ACTIONS, COMPLETION_FRAMES
from .red_registered_outcome import red_registered_outcome_from_observations

COLLECTION_TEACHER_SCHEMA = "pokemon.red.native-collection-teacher-lesson.v1"
_KINDS = {
    GoalKind.ACQUIRE_SPECIES: "acquire",
    GoalKind.EVOLVE_SPECIES: "evolve",
    GoalKind.RESTORE_TEAM: "restore",
}


@dataclass(frozen=True, slots=True)
class CollectionTeacherLessonInput:
    declaration_sha256: str
    outcome_sha256: str
    native_execution_claim_id: str

    def __post_init__(self):
        if (
            any(
                not isinstance(s, str) or re.fullmatch(r"[0-9a-f]{64}", s) is None
                for s in (self.declaration_sha256, self.outcome_sha256)
            )
            or not isinstance(self.native_execution_claim_id, str)
            or re.fullmatch(r"rnp-execution-[0-9a-f]{64}", self.native_execution_claim_id) is None
        ):
            raise ValueError("collection teacher input identity differs")

    def public_dict(self):
        return asdict(self)


def publish_collection_teacher_outcome(store, plan, result, *, native_execution_claim_id):
    """Seal the actual result; the loader independently checks metered inputs."""
    collection_teacher_example(plan, result, result["trace"])
    sha = canonical_sha256(result)
    store.publish_sealed_record(
        "rct-outcome-" + sha, kind="red_collection_teacher_outcome", record=result
    )
    item = CollectionTeacherLessonInput(canonical_sha256(plan), sha, native_execution_claim_id)
    load_collection_teacher_lesson(store, item)
    return item


def load_collection_teacher_lesson(store, item):
    """Reauthenticate the native claim and every trace/action before any fit."""
    from .red_native_player import NativeExecutionIdentity
    from .red_player_lesson_runtime import native_action_record_id

    if not isinstance(item, CollectionTeacherLessonInput):
        raise TypeError("collection teacher lesson needs a typed input")

    def read(identifier, kind):
        record = store.find_sealed_record(identifier, expected_kind=kind)
        if record is None:
            raise ValueError("collection teacher sealed evidence is missing")
        return record.read()

    plan = read("rct-plan-" + item.declaration_sha256, "red_collection_teacher_declaration")
    result = read("rct-outcome-" + item.outcome_sha256, "red_collection_teacher_outcome")
    native = read(item.native_execution_claim_id, "red_native_player_execution")
    if (
        native.get("schema") != "pokemon.red.native-continuous-player.v2"
        or NativeExecutionIdentity(**native["execution"]).claim_id != item.native_execution_claim_id
        or canonical_sha256(plan) != item.declaration_sha256
        or canonical_sha256(result) != item.outcome_sha256
        or native["source"] != plan["source"]
        or any(native["execution"][key] != plan["execution"][key] for key in ("run_id", "arm_id"))
        or native["limits"]["actions"] != plan["maximum_actions"]
        or native["limits"]["frames"] != plan["maximum_frames"]
    ):
        raise ValueError("collection teacher evidence differs from native execution")
    declaration = canonical_sha256(native)
    batch_reader = getattr(store, "read_native_record_batch", None)
    # A native action or trace is at most one MiB. Sixteen records therefore
    # fit the snapshot byte bound even at their individual maximum size.
    for start in range(0, len(result["trace"]), 16):
        rows = result["trace"][start:start + 16]
        records = []
        for phase in ("trace", "action"):
            kind = "red_native_lesson_" + phase
            identifiers = tuple(
                native_action_record_id(phase, declaration, index)
                for index in range(start, start + len(rows))
            )
            if batch_reader is None:
                records.append(tuple(read(identifier, kind) for identifier in identifiers))
            else:
                batch = batch_reader(identifiers, expected_kind=kind)
                if len(batch) != len(identifiers):
                    raise ValueError("collection teacher native batch length differs")
                if any(record.summary.record_id != identifier or record.summary.kind != kind
                       for record, identifier in zip(batch, identifiers, strict=True)):
                    raise ValueError("collection teacher native batch identity differs")
                records.append(tuple(record.read() for record in batch))
        for offset, (row, actual, action) in enumerate(zip(rows, *records, strict=True)):
            if (
                actual != row
                or action.get("ordinal") != start + offset
                or action.get("before_frame") != row["before_frame"]
            ):
                raise ValueError("collection teacher trace differs from native journal")
    return collection_teacher_example(plan, result, result["trace"])


def retained_collection_teacher_lessons(store, corpus, incoming=()):
    prior = tuple(
        CollectionTeacherLessonInput(**row) for row in corpus.get("collection_teacher_lessons", [])
    )
    items = (*prior, *incoming)
    if len({x.declaration_sha256 for x in items}) != len(items):
        raise ValueError("collection teacher repeats or replaces an execution")
    return items, tuple(load_collection_teacher_lesson(store, item) for item in items)


def declare_collection_teacher_lesson(session, options, selected_index, *, setup_receipt_sha256):
    """Seal one teacher choice from the same native menu used at inference."""
    if session.source.get("partition") != "train":
        raise ValueError("collection teachers require TRAIN provenance")
    if (
        type(selected_index) is not int
        or selected_index not in options.menu.available_indices
        or len(setup_receipt_sha256) != 64
        or any(c not in "0123456789abcdef" for c in setup_receipt_sha256)
    ):
        raise ValueError("collection teacher selection or setup receipt differs")
    binding = options.binding(selected_index)
    if binding.kind not in _KINDS:
        raise ValueError("collection teacher supports acquisition, evolution and recovery only")
    boundary = observe_native_player_boundary(
        session.runtime,
        battle=None,
        combat_specimen_refs=session.roles,
        remaining_budget=(1.0,) * 5,
    )
    if canonical_sha256(options.menu.policy_dict()) != options.menu.policy_sha256:
        raise ValueError("collection teacher question changed")
    before = session.snapshot()
    if before.sha256 != session.source["state_sha256"] or before.facts["actions"] != 0:
        raise ValueError("collection teacher declaration must precede all inputs")
    plan = dict(
        schema=COLLECTION_TEACHER_SCHEMA,
        source=dict(session.source),
        execution=dict(run_id=session.execution.run_id, arm_id=session.execution.arm_id),
        setup_receipt_sha256=setup_receipt_sha256,
        before=boundary.registered.public_dict(),
        before_sha256=before.sha256,
        menu=options.menu.policy_dict(),
        selected_index=selected_index,
        selected_kind=binding.kind.value,
        feature_version=session.model_feature_version,
        maximum_actions=session.limits.actions,
        maximum_frames=session.limits.frames,
        outcome_normalization_actions=COMPLETION_ACTIONS,
        outcome_normalization_frames=COMPLETION_FRAMES,
        comparative_choice=False,
        unexecuted_alternative_labels=0,
    )
    if binding.kind is GoalKind.RESTORE_TEAM:
        # Recovery has no registration delta; authenticate its actual HP/status/PP
        # change instead of admitting a success from the executor's boolean alone.
        plan["before_diagnostics"] = player_diagnostic_state(boundary.observation)
    plan_sha = canonical_sha256(plan)
    session.store.publish_sealed_record(
        "rct-plan-" + plan_sha, kind="red_collection_teacher_declaration", record=plan
    )
    return plan


def collection_teacher_example(plan, result, trace):
    """Admit only a readable, actually executed TRAIN outcome, including failures."""
    if (
        plan.get("schema") != COLLECTION_TEACHER_SCHEMA
        or plan.get("source", {}).get("partition") != "train"
        or result.get("declaration_sha256") != canonical_sha256(plan)
        or result.get("source_sha256") != plan.get("before_sha256")
        or plan.get("before_sha256") != plan.get("source", {}).get("state_sha256")
        or result.get("field_ready") is not True
        or result.get("buttons_released") is not True
        or result.get("error_type") is not None
        or type(result.get("succeeded")) is not bool
    ):
        raise ValueError("collection lesson requires matching settled TRAIN execution")
    menu = restore_living_dex_policy_menu(plan["menu"])
    index, kind = plan["selected_index"], GoalKind(plan["selected_kind"])
    if (
        kind not in _KINDS
        or index not in menu.available_indices
        or menu.candidates[index].features.kind.value != _KINDS[kind]
    ):
        raise ValueError("collection lesson selected question differs")
    if kind is GoalKind.RESTORE_TEAM:
        _require_restoration_diagnostics(plan, result)
    actions, frames = result["actions"], result["frames"]
    if (
        type(actions) is not int
        or actions <= 0
        or type(frames) is not int
        or frames <= 0
        or actions != len(trace)
        or actions > plan["maximum_actions"]
        or frames > plan["maximum_frames"]
    ):
        raise ValueError("collection lesson costs differ from input trace")
    previous = 0
    for ordinal, row in enumerate(trace):
        if (
            row.get("ordinal") != ordinal
            or row.get("before_frame") != previous
            or row.get("succeeded") is not True
            or type(row.get("after_frame")) is not int
            or row["after_frame"] <= previous
        ):
            raise ValueError("collection lesson input trace is incomplete")
        previous = row["after_frame"]
    if previous != frames:
        raise ValueError("collection lesson frame cost differs from actual inputs")
    outcome = red_registered_outcome_from_observations(
        plan["before"],
        result["after"],
        selected_kind=kind,
        succeeded=result["succeeded"],
        actions=actions,
        frames=frames,
        maximum_actions=COMPLETION_ACTIONS,
        maximum_frames=COMPLETION_FRAMES,
    )
    return LivingDexCurriculumOutcomeExample(
        canonical_sha256(plan),
        "train",
        plan["feature_version"],
        menu.candidate_vector(index, feature_version=plan["feature_version"]),
        outcome,
    )


def _require_restoration_diagnostics(plan, result):
    """A successful nursing target needs genuine, stock-preserving restoration."""
    before, after = plan.get("before_diagnostics"), result.get("after_diagnostics")
    if any(
        not isinstance(state, dict)
        or state.get("schema") != "pokemon.red.player-diagnostic-state.v1"
        or state.get("diagnostic_only") is not True
        for state in (before, after)
    ):
        raise ValueError("recovery lesson needs observed native diagnostics")
    identity = ("party_species_ids", "party_levels", "party_max_hp", "party_moves")
    mutable = ("party_hp", "party_status", "party_pp_current", "party_pp_maximum")
    for key in (*identity, *mutable):
        if (
            not isinstance(before.get(key), list)
            or not before[key]
            or not isinstance(after.get(key), list)
            or len(after[key]) != len(before[key])
        ):
            raise ValueError("recovery lesson native party observation differs")
    size = len(before["party_species_ids"])
    if any(len(state[key]) != size for state in (before, after) for key in (*identity, *mutable)):
        raise ValueError("recovery lesson native party size differs")
    if any(before[key] != after[key] for key in identity):
        raise ValueError("recovery lesson changed the retained party")
    for state in (before, after):
        if not all(
            type(hp) is int and type(maximum) is int and 0 <= hp <= maximum and maximum > 0
            for hp, maximum in zip(state["party_hp"], state["party_max_hp"], strict=True)
        ) or not all(
            type(status) is int and 0 <= status <= 255 for status in state["party_status"]
        ):
            raise ValueError("recovery lesson HP/status observation differs")
        for quantities, maxima in zip(
            state["party_pp_current"], state["party_pp_maximum"], strict=True
        ):
            if (
                not isinstance(quantities, list)
                or not isinstance(maxima, list)
                or len(quantities) != len(maxima)
                or len(quantities) != 4
                or not all(
                    type(q) is int and type(m) is int and 0 <= q <= m <= 63
                    for q, m in zip(quantities, maxima, strict=True)
                )
            ):
                raise ValueError("recovery lesson PP observation differs")
    if before["party_pp_maximum"] != after["party_pp_maximum"]:
        raise ValueError("recovery lesson changed native PP capacity")

    def restored(state):
        return (
            state["party_hp"] == state["party_max_hp"]
            and not any(state["party_status"])
            and state["party_pp_current"] == state["party_pp_maximum"]
        )

    if result["succeeded"] and (restored(before) or not restored(after)):
        raise ValueError("recovery success requires actual complete native restoration")


def set_isolated_training_experience(
    memory, *, partition, isolated_training_setup, party_index, experience, cartridge
):
    """Disclosed teacher-only XP conditioning; not reachable as a player action."""
    from .red_party import EXPERIENCE_OFFSET, PokemonRedPartyReader, member_field_address

    if partition != "train" or isolated_training_setup is not True:
        raise ValueError("experience conditioning requires isolated TRAIN authority")
    party = PokemonRedPartyReader(memory).read()
    if type(party_index) is not int or not 0 <= party_index < party.size:
        raise ValueError("training experience member differs")
    member = party.members[party_index]
    species = cartridge.species(member.species_id)
    if (
        type(experience) is not int
        or member.level >= 100
        or not species.experience_at_level(member.level)
        <= experience
        < species.experience_at_level(member.level + 1)
    ):
        raise ValueError("training experience must retain the declared native level")
    writes = []
    for byte in range(3):
        address = member_field_address(party_index, EXPERIENCE_OFFSET + byte)
        value = (experience >> (16 - byte * 8)) & 255
        old = memory.read_u8(address)
        memory.write_u8(address, value)
        writes.append(dict(address=address, before=old, after=value))
    if PokemonRedPartyReader(memory).read().members[party_index].experience != experience:
        raise ValueError("training experience write did not verify")
    return tuple(writes)


def set_isolated_training_emulator_experience(
    emulator, *, partition, isolated_training_setup, party_index, experience, cartridge
):
    """Teacher-only bridge; the actor emulator interface remains read-only.

    Reuse the same-level XP conditioner and its exact write receipt. The private
    backend mapping stays inside this setup adapter, never in a player action.
    """
    if (
        partition != "train"
        or isolated_training_setup is not True
        or getattr(emulator, "pressed_buttons", None) != frozenset()
    ):
        raise ValueError("emulator XP setup requires released isolated TRAIN authority")
    memory = emulator._require_backend().memory

    class ExperienceMemory:
        def read_u8(self, address):
            return int(memory[address])

        def write_u8(self, address, value):
            memory[address] = value

    return set_isolated_training_experience(
        ExperienceMemory(), partition=partition,
        isolated_training_setup=isolated_training_setup, party_index=party_index,
        experience=experience, cartridge=cartridge,
    )
