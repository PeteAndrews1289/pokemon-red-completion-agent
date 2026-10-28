"""Prospective consequence evidence on the existing continuous player's port.

Trusted native observers verify snapshots and event endpoints. Sealed documents
authenticate their evidence, not arbitrary caller assertions. This recorder never
selects a goal, edits a save, supplies a battle action or fits a model.
"""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .goal_manager import GoalDecisionOutcome, GoalKind, GoalManagerQuestion
from .living_dex_goal_policy import living_dex_option_kind_for_goal
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_challenge_consequence import (
    ChallengeConsequence,
    ConsequenceExample,
    consequence_contract,
    require_digest,
    require_preparation_workload,
)
from .provenance import canonical_sha256
from .red_autonomous_player import _record
from .red_consequence_choice import recovery_purchase_quote, condition_consequence_candidate
from .red_integrated_play import measured_cost
from .red_player_lesson import (
    capture_player_lesson_snapshot,
    validate_player_lesson,
    validate_preparation_lesson,
    verify_player_lesson,
)
from .red_player_lesson_runtime import native_action_record_id
from .red_player_resource_lesson import validate_resource_lesson, verify_resource_lesson
from .red_player_story_unit import _reached, _validate_snapshot, capture_story_unit


@dataclass(frozen=True)
class ChallengeConsequenceSpec:
    initial_kind: GoalKind
    challenge_target: dict
    preparation_target: dict | None = None
    maximum_phases: int = 4
    evolution_contract: dict | None = None
    feedback_version: int = 1
    include_recovery_purchases: bool = False
    include_challenge_arrival: bool = False
    machine_lesson: dict | None = None

    def __post_init__(self):
        from .red_player_story_unit import validate_story_unit_target

        validate_story_unit_target(self.challenge_target)
        consequence_contract(self.feedback_version)
        if type(self.include_recovery_purchases) is not bool or (
            self.include_recovery_purchases and self.feedback_version != 2
        ):
            raise ValueError("recovery purchases require an explicit progress lesson")
        if type(self.include_challenge_arrival) is not bool:
            raise ValueError("challenge arrival requires an explicit boolean opt-in")
        kinds = {GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM}
        if self.include_recovery_purchases:
            kinds.add(GoalKind.RESUPPLY)
        if (
            self.initial_kind not in kinds
            or self.challenge_target["kind"] != "events"
            or type(self.maximum_phases) is not int
            or not 1 <= self.maximum_phases <= 4
            or (self.initial_kind is GoalKind.DEVELOP_TEAM) != (
                (self.preparation_target is not None) or (self.machine_lesson is not None))
            or self.preparation_target is not None and self.machine_lesson is not None
        ):
            raise ValueError("consequence requires one event challenge and optional initial dose")
        if self.preparation_target is not None and (
            set(self.preparation_target) != {"specimen_ref", "level"}
            or type(self.preparation_target["specimen_ref"]) is not str
            or type(self.preparation_target["level"]) is not int
            or not 1 <= self.preparation_target["level"] <= 100
        ):
            raise ValueError("consequence preparation target differs")
        if self.machine_lesson is not None:
            _validate_machine_target(self.machine_lesson)
            object.__setattr__(self, "machine_lesson", deepcopy(self.machine_lesson))
        object.__setattr__(self, "challenge_target", deepcopy(self.challenge_target))
        object.__setattr__(self, "preparation_target", deepcopy(self.preparation_target))
        if self.evolution_contract is not None:
            from .red_player_evolution_lesson import validate_evolution_lesson_contract

            validate_evolution_lesson_contract(self.evolution_contract)
            object.__setattr__(self, "evolution_contract", deepcopy(self.evolution_contract))

    @property
    def schema_version(self):
        return (6 if self.machine_lesson is not None else 5 if self.include_challenge_arrival else 4 if self.include_recovery_purchases else 3 if self.feedback_version == 2
                else 2 if self.evolution_contract is not None else 1)

    def document(self):
        values = asdict(self)
        if self.machine_lesson is None:
            values.pop("machine_lesson")
        version = self.schema_version
        if not self.include_challenge_arrival:
            values.pop("include_challenge_arrival")
        if not self.include_recovery_purchases:
            values.pop("include_recovery_purchases")
        if self.feedback_version == 1:
            values.pop("feedback_version")
        if version == 1:
            values.pop("evolution_contract")
        return dict(schema=f"pokemon.red.challenge-consequence-spec.v{version}", **values)

    @classmethod
    def from_document(cls, doc):
        spec = cls(
            GoalKind(doc["initial_kind"]),
            doc["challenge_target"],
            doc["preparation_target"],
            doc["maximum_phases"],
            doc.get("evolution_contract"),
            doc.get("feedback_version", 1),
            doc.get("include_recovery_purchases", False),
            doc.get("include_challenge_arrival", False),
            doc.get("machine_lesson"),
        )
        if canonical_sha256(spec.document()) != canonical_sha256(doc):
            raise ValueError("consequence specification changed")
        return spec



def _private_binding_document(binding):
    return dict(binding_ref=binding.binding_ref, kind=binding.kind.value,
                story_objective_ref=binding.story_objective_ref,
                story_approach_only=binding.story_approach_only)


def _conditioned_consequence_menu(plan, menu, selected):
    """Authenticate a teacher's same-boundary parent; retain the raw menu."""
    witness = plan.get("preparation_parent_witness")
    if witness is None:
        if plan.get("schema") == "pokemon.red.challenge-consequence-plan.v9":
            raise ValueError("consequence preparation parent witness is missing")
        return menu
    fields = {"schema", "source_state_sha256", "menu_sha256", "bindings",
              "parent_index", "parent_binding_ref", "selected_dose_index",
              "selected_dose_ref", "preparation_target", "authority", "model_queries"}
    spec = ChallengeConsequenceSpec.from_document(plan["spec"])
    machine = spec.machine_lesson is not None
    if machine:
        fields = fields | {"machine_lesson"}
    schema = ("pokemon.red.consequence-preparation-parent.v2" if machine
              else "pokemon.red.consequence-preparation-parent.v1")
    if (type(witness) is not dict or set(witness) != fields
            or witness["schema"] != schema
            or plan.get("feature_version") != 15 or spec.feedback_version != 2
            or spec.initial_kind is not GoalKind.DEVELOP_TEAM
            or (spec.preparation_target is None) != machine
            or machine and witness["machine_lesson"] != spec.machine_lesson
            or plan["source"]["partition"] != "train"
            or witness["source_state_sha256"] != plan["source"]["state_sha256"]
            or witness["source_state_sha256"] != plan["before"]["state_sha256"]
            or witness["menu_sha256"] != canonical_sha256(plan["menu"])
            or type(witness["selected_dose_index"]) is not int
            or witness["selected_dose_index"] != selected
            or witness["selected_dose_ref"] != plan["binding_ref"]
            or witness["preparation_target"] != spec.preparation_target
            or witness["authority"] != "teacher_supplied_observed_parent"
            or type(witness["model_queries"]) is not int or witness["model_queries"] != 0):
        raise ValueError("consequence preparation parent witness differs")
    bindings, parent = witness["bindings"], witness["parent_index"]
    if (type(bindings) is not list or len(bindings) != len(menu.candidates)
            or type(parent) is not int or parent not in menu.available_indices
            or parent == selected or selected not in menu.available_indices):
        raise ValueError("consequence preparation parent inventory differs")
    for i, binding in enumerate(bindings):
        if (type(binding) is not dict
                or set(binding) != {"binding_ref", "kind", "story_objective_ref", "story_approach_only"}
                or type(binding["binding_ref"]) is not str or not binding["binding_ref"]
                or type(binding["story_approach_only"]) is not bool
                or menu.candidates[i].features.kind is not living_dex_option_kind_for_goal(
                    GoalKind(binding["kind"]), feature_version=15)):
            raise ValueError("consequence preparation binding inventory differs")
    if (len({b["binding_ref"] for b in bindings}) != len(bindings)
            or bindings[selected]["binding_ref"] != plan["binding_ref"]
            or bindings[parent]["binding_ref"] != witness["parent_binding_ref"]
            or bindings[parent]["kind"] != GoalKind.ADVANCE_STORY.value
            or bindings[parent]["story_approach_only"] is not False
            or type(bindings[parent]["story_objective_ref"]) is not str
            or not bindings[parent]["story_objective_ref"]
            or (not machine and (menu.candidates[selected].preparation is None
                                 or menu.candidates[selected].move_change is not None))):
        raise ValueError("consequence preparation parent binding differs")
    if machine:
        # Reuse the owned-TM/source/custody verifier before deriving policy facts.
        # project_consequence also checks this before projecting paid outcomes.
        _validate_machine_start(plan["before"], menu.candidates[selected],
                                plan["binding_ref"], spec.machine_lesson)
    candidate = condition_consequence_candidate(menu.candidates[selected], menu.candidates[parent])
    return replace(menu, candidates=tuple(candidate if i == selected else c
                                         for i, c in enumerate(menu.candidates)))


def _has_challenge_or_member_preparation_target(spec, candidate, *, feature_version):
    """Keep raw missing previews for a separately declared member-dose lesson.

    This is collector admission only. The existing workload and preparation
    validators still authenticate the exact specimen/level against the source;
    no challenge facts, policy features or inference eligibility are invented.
    Other action families and legacy feature contracts keep their preview gate.
    """
    return candidate.challenge is not None or (
        spec.initial_kind is GoalKind.DEVELOP_TEAM
        and spec.preparation_target is not None
        and spec.machine_lesson is None
        and feature_version in (9, 10, 15)
        and candidate.features.kind is living_dex_option_kind_for_goal(
            GoalKind.DEVELOP_TEAM, feature_version=feature_version)
        and candidate.move_change is None
        and candidate.preparation is not None
        and candidate.level_workload is not None
    )


def _validate_machine_target(target):
    from .player_option_move_change import OptionMoveChange

    if type(target) is not dict or set(target) != {"lesson", "move_change"}:
        raise ValueError("machine consequence target scope differs")
    lesson = target["lesson"]
    if (type(lesson) is not dict
            or set(lesson) != {"item_id", "party_slot", "replace_slot", "species_id", "before_moves", "move_id"}
            or any(type(lesson[k]) is not int for k in ("item_id", "party_slot", "replace_slot", "species_id", "move_id"))
            or not 201 <= lesson["item_id"] <= 250
            or not 1 <= lesson["party_slot"] <= 6
            or not 1 <= lesson["replace_slot"] <= 4
            or not 1 <= lesson["species_id"] <= 255
            or not 1 <= lesson["move_id"] <= 165
            or type(lesson["before_moves"]) is not list or len(lesson["before_moves"]) != 4
            or any(type(m) is not int or not 0 <= m <= 165 for m in lesson["before_moves"])
            or lesson["move_id"] in lesson["before_moves"]
            or lesson["before_moves"][lesson["replace_slot"]-1] in {15, 19, 57, 70, 148}):
        raise ValueError("machine consequence lesson differs")
    from .red_battle_practice_cartridge import _TMHM_MOVES
    moves = lesson["before_moves"]
    if (lesson["move_id"] != _TMHM_MOVES[lesson["item_id"] - 201]
            or (0 in moves and lesson["replace_slot"] != moves.index(0) + 1)
            or (0 in moves and any(moves[moves.index(0):]))):
        raise ValueError("machine consequence cartridge lesson differs")
    facts = OptionMoveChange.from_public(target["move_change"])
    from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref

    old = lesson["before_moves"][lesson["replace_slot"] - 1]
    proposed = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(lesson["move_id"]))
    removed = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(old)) if old else None
    types = RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(lesson["species_id"])).types
    if (facts.proposed != proposed or facts.removed != removed
            or facts.proposed_current_pp != proposed.max_pp or facts.proposed_maximum_pp != proposed.max_pp
            or facts.proposed_stab != (proposed.type_name in types)
            or facts.removed_stab != (removed is not None and removed.type_name in types)
            or facts.removed_effectiveness is not None or facts.proposed_effectiveness is not None):
        raise ValueError("machine consequence mechanics differ from observed lesson")
    return facts


def _capture_machine_boundary(runtime):
    from dataclasses import is_dataclass

    def native_value(value):
        if is_dataclass(value):
            return native_value(asdict(value))
        if isinstance(value, dict):
            return {str(k): native_value(v) for k, v in value.items()}
        if isinstance(value, (set, frozenset)):
            return [native_value(v) for v in sorted(value)]
        if isinstance(value, (tuple, list)):
            return [native_value(v) for v in value]
        if isinstance(value, bytes):
            return value.hex()
        return value

    reader = runtime.reader
    raw = reader.read()
    return dict(location=[raw.map_id, raw.player_y, raw.player_x],
        badges=raw.badge_bits, events=raw.event_flags.hex(),
        party_stats=native_value(raw.party_stats),
        party_pp=native_value(raw.party_pp),
        protected_collection_sha256=canonical_sha256(native_value(dict(
            boxes=reader.read_all_box_states(), dex=reader.read_pokedex_state(), pc=reader.read_pc_items()))))


def _validate_machine_start(before, candidate, binding_ref, target):
    from .red_player_lesson import validate_snapshot
    from .red_party_pp import decode_red_party_pp

    validate_snapshot(before["lesson"], before["observation"])
    facts = _validate_machine_target(target)
    lesson = target["lesson"]
    if (candidate.move_change != facts or candidate.preparation is not None
            or candidate.level_workload is not None):
        raise ValueError("machine consequence candidate differs from declared observed facts")
    expected = "pokemon.red:owned-machine:" + before["state_sha256"] + ":" + canonical_sha256(lesson)
    if binding_ref != expected:
        raise ValueError("machine consequence binding differs from exact source/lesson")
    index, slot = lesson["party_slot"] - 1, lesson["replace_slot"] - 1
    party = before["lesson"]["party"]
    if index >= len(party):
        raise ValueError("machine consequence recipient is absent")
    member = party[index]
    boundary = before["machine_boundary"]
    stats = boundary["party_stats"][index] if boundary["party_stats"] is not None else None
    charges = decode_red_party_pp(tuple(lesson["before_moves"]), tuple(boundary["party_pp"][index])).moves[slot]
    if (member["species_id"] != lesson["species_id"]
            or [m[0] for m in member["moves"]] != lesson["before_moves"]
            or member["hp"] <= 0
            or facts.removed_current_pp != (member["moves"][slot][1] if facts.removed else None)
            or facts.removed_maximum_pp != (charges.maximum_pp if facts.removed else None)
            or facts.recipient_attack != (stats[0] if stats is not None else None)
            or facts.recipient_special_attack != (stats[3] if stats is not None else None)):
        raise ValueError("machine consequence facts differ from native party")
    from .red_player_economy import restore_snapshot
    economy = restore_snapshot(before["economy"])
    if economy is None or economy.cash != before["cash"]:
        raise ValueError("machine consequence native economy differs")
    items = dict(economy.inventory)
    if items.get(f"red-item-{lesson['item_id']:03d}", 0) <= 0:
        raise ValueError("machine consequence requires an owned TM")
    if not before["settled"]:
        raise ValueError("machine consequence requires field control")


def _verify_machine_end(before, after, target, succeeded):
    """The existing executor verifies native legality; retain exact custody here."""
    from .red_player_lesson import validate_snapshot

    validate_snapshot(after["lesson"], after["observation"])
    if type(succeeded) is not bool:
        raise ValueError("machine consequence lacks a boolean verdict")
    if not succeeded:
        if (before["lesson"] != after["lesson"] or before["economy"] != after["economy"]
                or before["machine_boundary"] != after["machine_boundary"]
                or before["endpoint"] != after["endpoint"]):
            raise ValueError("failed machine lesson changed protected state")
        return
    lesson = target["lesson"]
    facts = _validate_machine_target(target)
    expected = deepcopy(before["lesson"])
    expected["party"][lesson["party_slot"] - 1]["moves"][lesson["replace_slot"] - 1] = [lesson["move_id"], facts.proposed_current_pp]
    economy = deepcopy(before["economy"])
    inventory = dict(economy["inventory"])
    key = f"red-item-{lesson['item_id']:03d}"
    inventory[key] -= 1
    economy["inventory"] = [[key, value] for key, value in sorted(inventory.items()) if value]
    boundary = deepcopy(before["machine_boundary"])
    boundary["party_pp"][lesson["party_slot"] - 1][lesson["replace_slot"] - 1] = facts.proposed_current_pp
    if (after["lesson"] != expected or after["economy"] != economy
            or after["machine_boundary"] != boundary
            or after["cash"] != before["cash"] or after["heals"] != before["heals"]
            or after["endpoint"] != before["endpoint"]):
        raise ValueError("machine consequence changed protected custody or expected move/PP")


def challenge_progress_from_episode(episode, *, battle):
    """Observed lower-bound roster progress, not XP or a counterfactual win.

    Reuse the battler's semantic aftermath verifier. Previously damaged switched
    foes are not filled in; only verified knockouts and the last living foe's
    observed HP contribute. This conservative fraction is not a win probability.
    """
    from .red_post_battle_strategy import red_battle_aftermath

    payload = json.dumps(episode, sort_keys=True, allow_nan=False).encode()
    aftermath = red_battle_aftermath(payload, expected_sha256=sha256(payload).hexdigest())
    if aftermath.result.value != battle or battle not in {"won", "lost"}:
        raise ValueError("progress episode and native challenge result differ")
    if battle == "won":
        return 1.0
    partial = (1 - aftermath.last_opponent_hp_fraction
               if aftermath.last_opponent_hp_fraction is not None
               and aftermath.last_opponent_hp_fraction > 0 else 0.0)
    return min(1.0, (aftermath.opponents_defeated + partial) / aftermath.opponent_count)


def _pure_challenge_arrival(phase, target):
    """Accept only the existing travel binding reaching this uncompleted challenge."""
    before, after = phase["before"], phase["after"]
    return (
        phase["kind"] == GoalKind.ADVANCE_STORY.value
        and isinstance(phase["binding_ref"], str)
        and phase["binding_ref"].startswith("pokemon.red:story-travel:")
        and phase["verified"] is True
        and phase["error"] is None
        and phase["cost_verified"] is True
        and phase["battle"] is None
        and phase.get("challenge_episode") is None
        and before["endpoint"]["map_id"] != target["map_id"]
        and after["endpoint"]["map_id"] == target["map_id"]
        and before["endpoint"]["events"] == after["endpoint"]["events"]
        and not all(after["endpoint"]["events"])
        and before["lesson"] == after["lesson"]
        and before["cash"] == after["cash"]
        and after["settled"] is True
        and after["actions"] > before["actions"]
        and after["frames"] > before["frames"]
    )


def project_consequence(plan, phases, *, interrupted=False):
    """Separate completed/unattempted/censored outcomes; no atomic reward rewriting."""
    spec = ChallengeConsequenceSpec.from_document(plan["spec"])
    workload = plan.get("schema") in {
        "pokemon.red.challenge-consequence-plan.v5",
        "pokemon.red.challenge-consequence-plan.v6",
        "pokemon.red.challenge-consequence-plan.v7",
        "pokemon.red.challenge-consequence-plan.v8",
        "pokemon.red.challenge-consequence-plan.v9",
    }
    feature_version = plan.get("feature_version") if workload else 7
    if (
        set(plan)
        != {
            "schema",
            "consequence_schema",
            "prospective",
            "partition",
            "source",
            "execution",
            "spec",
            "before",
            "menu",
            "selected_index",
            "binding_ref",
        }
        | ({"recovery_purchase_question"} if spec.include_recovery_purchases else set())
        | ({"feature_version"} if workload else set())
        | ({"preparation_parent_witness"} if plan.get("schema") == "pokemon.red.challenge-consequence-plan.v9" else set())
        or plan.get("schema")
        not in {
            "pokemon.red.challenge-consequence-plan.v1",
            "pokemon.red.challenge-consequence-plan.v2",
            "pokemon.red.challenge-consequence-plan.v3",
            "pokemon.red.challenge-consequence-plan.v4",
            "pokemon.red.challenge-consequence-plan.v5",
            "pokemon.red.challenge-consequence-plan.v6",
        "pokemon.red.challenge-consequence-plan.v7",
        "pokemon.red.challenge-consequence-plan.v8",
        "pokemon.red.challenge-consequence-plan.v9",
        }
        or plan.get("consequence_schema") not in {
            consequence_contract(1)[0], consequence_contract(2)[0]}
        or plan.get("prospective") is not True
        or plan.get("partition") != "train"
        or type(interrupted) is not bool
        or plan.get("source", {}).get("partition") != "train"
    ):
        raise ValueError("consequence requires prospective TRAIN declaration")
    if workload and (type(feature_version) is not int or feature_version not in (9, 10, 15)):
        raise ValueError("workload consequence requires declared V9 features")
    if spec.include_challenge_arrival and not workload:
        raise ValueError("challenge arrival requires explicit V9 workload features")
    version = (9 if "preparation_parent_witness" in plan else
               (8 if feature_version == 15 else 7 if feature_version == 10 else 6 if spec.include_challenge_arrival else 5) if workload else spec.schema_version)
    if plan["schema"] != f"pokemon.red.challenge-consequence-plan.v{version}":
        raise ValueError("consequence evolution version differs")
    if plan["consequence_schema"] != consequence_contract(spec.feedback_version)[0]:
        raise ValueError("consequence prospective feedback version differs")
    menu = restore_living_dex_policy_menu(plan["menu"])
    selected = plan["selected_index"]
    if (
        menu.feature_version not in (6, 7, 9, 10, 15)
        or menu.feature_version > feature_version
        or type(selected) is not int
        or selected not in menu.available_indices
    ):
        raise ValueError("consequence requires exact selected declared features")
    feature_menu = _conditioned_consequence_menu(plan, menu, selected)
    candidate = menu.candidates[selected]
    if (
        candidate.features.kind
        is not living_dex_option_kind_for_goal(spec.initial_kind, feature_version=feature_version)
        or not _has_challenge_or_member_preparation_target(
            spec, candidate, feature_version=feature_version)
    ):
        raise ValueError("consequence prospective option differs")
    require_preparation_workload(candidate, feature_version)
    target = spec.challenge_target
    require_digest(plan["source"]["state_sha256"])
    if plan["before"]["state_sha256"] != plan["source"]["state_sha256"]:
        raise ValueError("consequence source and initial state differ")
    if any(plan["before"][k] != 0 for k in ("actions", "completed_actions", "frames", "heals")):
        raise ValueError("consequence cannot omit leading preparation or restoration costs")
    _validate_snapshot(target, plan["before"]["endpoint"])
    if all(plan["before"]["endpoint"]["events"]):
        raise ValueError("consequence challenge was already completed")
    if spec.machine_lesson is not None:
        if feature_version not in (10, 15):
            raise ValueError("machine consequence requires explicit V10 facts")
        _validate_machine_start(plan["before"], candidate, plan["binding_ref"], spec.machine_lesson)
    elif spec.initial_kind is GoalKind.DEVELOP_TEAM:
        validate_preparation_lesson(
            dict(
                before=plan["before"]["observation"],
                player_lesson=dict(before=plan["before"]["lesson"], target=spec.preparation_target),
                preparation=None
                if candidate.preparation is None
                else candidate.preparation.public_dict(),
            ),
            spec.initial_kind,
            pp_evidence=plan["before"].get("preparation_pp"),
            source_state_sha256=plan["before"]["state_sha256"],
        )
    elif candidate.preparation is not None:
        raise ValueError("nontraining consequence borrowed member preparation")
    purchase_question = None
    if spec.include_recovery_purchases:
        recorded_question = plan["recovery_purchase_question"]
        if spec.initial_kind is GoalKind.RESUPPLY:
            purchase_question = GoalManagerQuestion.from_policy_input(recorded_question)
            quote = purchase_question.opportunities[0].resource_quote
            if (
                purchase_question.opportunities[0].kind is not GoalKind.RESUPPLY
                or not recovery_purchase_quote(quote)
                or candidate.economy_offer is None
                or candidate.economy_offer.planned_spend != quote.purchase_cost
            ):
                raise ValueError("consequence purchase differs from the prospective quote")
            validate_resource_lesson(_purchase_lesson_plan(plan["before"]), purchase_question)
        elif recorded_question is not None:
            raise ValueError("nonpurchase consequence borrowed a recovery quote")
    if not 1 <= len(phases) <= spec.maximum_phases:
        raise ValueError("consequence phase census differs")
    previous = plan["before"]
    actions = frames = debits = credits = heals = 0
    attempted = completed = False
    error = "interrupted" if interrupted else None
    failed = False
    challenge_progress = 0.0
    for ordinal, phase in enumerate(phases):
        if spec.machine_lesson is not None and ordinal == 0 and phase["binding_ref"] != plan["binding_ref"]:
            raise ValueError("machine consequence phase differs from selected binding")
        kind = GoalKind(phase["kind"])
        if (
            type(phase["ordinal"]) is not int
            or phase["ordinal"] != ordinal
            or phase["before"] != previous
            or completed
            or attempted
            or failed
            or kind is not spec.initial_kind
            and ordinal == 0
            or ordinal > 0
            and kind not in {GoalKind.RESTORE_TEAM, GoalKind.ADVANCE_STORY}
            or phase["interventions"] != []
        ):
            raise ValueError("consequence phase linkage, continuation or intervention differs")
        after = phase["after"]
        require_digest(after["state_sha256"])
        for snapshot in (previous, after):
            if any(
                type(snapshot[k]) is not int or snapshot[k] < 0
                for k in ("actions", "frames", "cash", "heals", "completed_actions")
            ):
                raise ValueError("consequence counters are not measured integers")
        _validate_snapshot(target, after["endpoint"])
        edges = ()
        if spec.evolution_contract is not None:
            from .red_player_evolution_lesson import verify_evolution_lesson_boundary

            edges = verify_evolution_lesson_boundary(
                previous["lesson"],
                after["lesson"],
                previous["observation"],
                after["observation"],
                kind,
                spec.evolution_contract,
            )
        if any(
            old and not new
            for old, new in zip(
                previous["endpoint"]["events"], after["endpoint"]["events"], strict=True
            )
        ):
            raise ValueError("consequence lost challenge prerequisites")
        a = after["actions"] - previous["actions"]
        f = after["frames"] - previous["frames"]
        dh = after["heals"] - previous["heals"]
        if any(type(v) is not int or v < 0 for v in (a, f, dh)):
            raise ValueError("consequence counters reset")
        debit = previous["cash"] - after["cash"]
        actions += a
        frames += f
        heals += dh
        debits += max(0, debit)
        credits += max(0, -debit)
        if (
            phase["error"] is not None
            or phase["verified"] is None
            or not after["settled"]
            or phase["cost_verified"] is not True
            or after["completed_actions"] - previous["completed_actions"] != a
        ):
            error = "execution_or_verification_incomplete"
        else:
            if type(phase["verified"]) is not bool:
                raise ValueError("consequence verification is not boolean")
            if kind is GoalKind.ADVANCE_STORY:
                battle = phase["battle"]
                if spec.include_challenge_arrival and _pure_challenge_arrival(phase, target):
                    pass
                elif battle not in {"won", "lost"}:
                    error = "challenge_not_observed"
                else:
                    attempted = True
                    completed = _reached(target, after["endpoint"])
                    if completed != (battle == "won") or completed != phase["verified"]:
                        raise ValueError("challenge result lacks actual endpoint proof")
                    if spec.feedback_version == 2:
                        challenge_progress = challenge_progress_from_episode(
                            phase["challenge_episode"], battle=battle)
            elif kind is GoalKind.RESUPPLY:
                verify_resource_lesson(
                    _purchase_lesson_plan(previous),
                    dict(after=after["observation"], player_lesson=after["lesson"],
                         economy_after=after["economy"], succeeded=phase["verified"]),
                    purchase_question,
                )
                failed = not phase["verified"]
                if all(after["endpoint"]["events"]):
                    raise ValueError("purchase unexpectedly completed the declared challenge")
            elif kind is GoalKind.DEVELOP_TEAM and spec.machine_lesson is not None:
                _verify_machine_end(previous, after, spec.machine_lesson, phase["verified"])
                failed = not phase["verified"]
                if all(after["endpoint"]["events"]):
                    raise ValueError("machine lesson unexpectedly completed challenge")
            else:
                lesson_target = (
                    spec.preparation_target
                    if kind is GoalKind.DEVELOP_TEAM
                    else {"restoration": "improve_without_regression"}
                )
                verify_player_lesson(
                    dict(before=previous["lesson"], target=lesson_target),
                    after["lesson"],
                    previous["observation"],
                    after["observation"],
                    kind,
                    phase["verified"],
                    level_evolutions=edges,
                )
                failed = not phase["verified"]
                if all(after["endpoint"]["events"]):
                    raise ValueError("preparation unexpectedly completed the declared challenge")
        previous = after
    if not attempted and not failed and error is None:
        error = "challenge_not_reached_before_stop"
    outcome = (
        None
        if error
        else ChallengeConsequence(
            attempted, completed, actions, frames, debits, credits, heals,
            feedback_version=spec.feedback_version,
            initial_goal_failed=(failed if spec.feedback_version == 2 else None),
            challenge_progress=(challenge_progress if spec.feedback_version == 2 else None),
        )
    )
    return ConsequenceExample(
        canonical_sha256(plan),
        plan["source"]["origin_sha256"],
        feature_menu.candidate_vector(selected, feature_version=feature_version),
        outcome,
        error,
        provenance="native_train",
        feedback_version=spec.feedback_version,
        feature_version=feature_version,
    )


def _purchase_lesson_plan(before):
    """Reuse the existing independently verified native purchase contract."""
    return dict(
        selected_index=0, before=before["observation"], economy_before=before["economy"],
        player_lesson=dict(before=before["lesson"], target={"resource": "purchase_stock"}),
        target_cash=0,
    )


def capture_consequence_snapshot(s, target, *, include_resources=False, include_machine=False, include_preparation_pp=False):
    """Read-only common observer; no recorder, partition conversion or admission."""
    snapshot = s.snapshot()
    observation, lesson = capture_player_lesson_snapshot(s.runtime)
    endpoint = capture_story_unit(s.runtime, target)
    if s.controller.save_state_bytes() != snapshot.state:
        raise ValueError("consequence observation changed state")
    result = dict(
        state_sha256=snapshot.sha256,
        actions=len(s.recorder.trace),
        completed_actions=s.actions.actions_executed,
        frames=s.controller.frames_executed,
        heals=s.heals,
        cash=observation.raw.player_money,
        lesson=lesson,
        observation=observation.public_dict(),
        endpoint=endpoint,
        settled=bool(snapshot.safe and snapshot.facts["input_ready"]),
    )
    if include_preparation_pp:
        from .red_player_lesson import capture_preparation_pp_evidence
        result["preparation_pp"] = capture_preparation_pp_evidence(
            observation.raw, lesson, result["state_sha256"])
    if include_machine:
        result["machine_boundary"] = _capture_machine_boundary(s.runtime)
    if include_resources:
        from .red_player_economy import snapshot_document
        from .resource_economy_observation import EconomySnapshot

        raw = observation.raw
        result["economy"] = snapshot_document(EconomySnapshot(
            raw.player_money, tuple(sorted((f"red-item-{i:03d}", n) for i, n in raw.bag_items))))
    return result

class NativeConsequenceRecorder:
    """Optional passive recorder sharing the exact guarded native session."""

    def __init__(self, session, spec):
        if (
            type(spec) is not ChallengeConsequenceSpec
            or session.source["partition"] != "train"
            or session.model_feature_version not in (7, 9, 10, 15)
        ):
            raise ValueError("consequence recording needs a prospective TRAIN V7, V9, V10 or V15 session")
        self.session = session
        self.spec_document = spec.document()
        self.plan = None
        self.phases = []
        self.active = None
        self.done = False
        self.preparation_parent_witness = None

    @property
    def spec(self):
        return ChallengeConsequenceSpec.from_document(self.spec_document)

    def capture(self, *, include_preparation_pp=False):
        return capture_consequence_snapshot(self.session, self.spec.challenge_target,
            include_resources=(self.spec.include_recovery_purchases or self.spec.machine_lesson is not None),
            include_machine=self.spec.machine_lesson is not None,
            include_preparation_pp=include_preparation_pp)

    def declare_preparation_parent(self, options, binding, parent):
        """Prospectively disclose an explicit teacher parent, with zero queries."""
        if (self.plan is not None or self.phases or self.active is not None or self.done
                or self.preparation_parent_witness is not None):
            raise ValueError("consequence parent must be declared once before input")
        index = next((i for i, b in enumerate(options.bindings) if b is binding), None)
        parent_index = next((i for i, b in enumerate(options.bindings) if b is parent), None)
        if index is None or parent_index is None:
            raise ValueError("consequence parent requires exact observed binding objects")
        before = self.capture()
        if any(before[k] != 0 for k in ("actions", "completed_actions", "frames", "heals")):
            raise ValueError("consequence parent declaration cannot omit leading costs")
        witness = dict(schema=("pokemon.red.consequence-preparation-parent.v2"
                              if self.spec.machine_lesson is not None
                              else "pokemon.red.consequence-preparation-parent.v1"),
            source_state_sha256=before["state_sha256"], menu_sha256=canonical_sha256(options.menu.policy_dict()),
            bindings=[_private_binding_document(b) for b in options.bindings],
            parent_index=parent_index, parent_binding_ref=parent.binding_ref,
            selected_dose_index=index, selected_dose_ref=binding.binding_ref,
            preparation_target=deepcopy(self.spec.preparation_target),
            authority="teacher_supplied_observed_parent", model_queries=0)
        if self.spec.machine_lesson is not None:
            witness["machine_lesson"] = deepcopy(self.spec.machine_lesson)
        plan = dict(spec=self.spec_document, source=self.session.source, before=before,
            menu=options.menu.policy_dict(), selected_index=index, binding_ref=binding.binding_ref,
            feature_version=self.session.model_feature_version, preparation_parent_witness=witness)
        _conditioned_consequence_menu(plan, options.menu, index)
        self.preparation_parent_witness = deepcopy(witness)
        return deepcopy(witness)

    def begin(self, options, binding, *, preflight_only=False):
        if type(preflight_only) is not bool or preflight_only and self.plan is not None:
            raise ValueError("consequence preflight must be an unused boolean mode")
        if self.active is not None or self.done or len(self.phases) >= self.spec.maximum_phases:
            raise ValueError("consequence cannot start another phase")
        include_preparation_pp = False
        if not self.phases and binding.kind is GoalKind.DEVELOP_TEAM and hasattr(options, "menu"):
            selected = next((i for i, b in enumerate(options.bindings)
                             if b.binding_ref == binding.binding_ref), None)
            if selected is not None:
                preparation = options.menu.candidates[selected].preparation
                include_preparation_pp = preparation is not None and preparation.pp_fraction is not None
        before = self.capture(include_preparation_pp=include_preparation_pp)
        if self.spec.include_challenge_arrival and self.session.model_feature_version not in (9, 10, 15):
            raise ValueError("challenge arrival requires explicit V9 workload features")
        if not self.phases:
            if (
                binding.kind is not self.spec.initial_kind
                or not hasattr(options, "menu")
                or before["actions"]
                or before["frames"]
            ):
                raise ValueError(
                    "consequence must declare its selected initial option before input"
                )
            index = next(
                i for i, b in enumerate(options.bindings) if b.binding_ref == binding.binding_ref
            )
            plan = dict(
                schema=f"pokemon.red.challenge-consequence-plan.v{8 if self.session.model_feature_version == 15 else 7 if self.session.model_feature_version == 10 else 6 if self.spec.include_challenge_arrival else 5 if self.session.model_feature_version == 9 else self.spec.schema_version}",
                consequence_schema=consequence_contract(self.spec.feedback_version)[0],
                prospective=True,
                partition="train",
                source=deepcopy(self.session.source),
                execution=asdict(self.session.execution),
                spec=self.spec_document,
                before=before,
                menu=options.menu.policy_dict(),
                selected_index=index,
                binding_ref=binding.binding_ref,
                **({"feature_version": self.session.model_feature_version} if self.session.model_feature_version in (9, 10, 15) else {}),
            )
            if self.preparation_parent_witness is not None:
                plan["schema"] = "pokemon.red.challenge-consequence-plan.v9"
                plan["preparation_parent_witness"] = deepcopy(self.preparation_parent_witness)
                if plan["preparation_parent_witness"]["bindings"] != [
                        _private_binding_document(b) for b in options.bindings]:
                    raise ValueError("consequence observed binding inventory changed before input")
                _conditioned_consequence_menu(plan, options.menu, index)
            if self.spec.include_recovery_purchases:
                plan["recovery_purchase_question"] = None
                if binding.kind is GoalKind.RESUPPLY:
                    if not recovery_purchase_quote(binding.resource_quote):
                        raise ValueError("consequence requires an actual medicine purchase")
                    other = next(b for b in options.bindings if b.kind is not binding.kind)
                    question = GoalManagerQuestion(
                        options.situation, (binding.opportunity, other.opportunity))
                    plan["recovery_purchase_question"] = dict(
                        schema=question.policy_input["schema"],
                        situation=question.situation.policy_dict(),
                        candidates=[o.policy_dict() for o in question.opportunities],
                    )
                    validate_resource_lesson(_purchase_lesson_plan(before), question)
            candidate = options.menu.candidates[index]
            if (options.menu.feature_version not in (6, 7, 9, 10, 15)
                    or options.menu.feature_version > self.session.model_feature_version
                    or not _has_challenge_or_member_preparation_target(
                        self.spec, candidate, feature_version=self.session.model_feature_version)):
                raise ValueError("consequence requires prospective declared challenge facts or exact member-dose target")
            if candidate.features.kind is not living_dex_option_kind_for_goal(
                binding.kind, feature_version=self.session.model_feature_version
            ):
                raise ValueError("consequence candidate and executable goal differ")
            require_preparation_workload(candidate, self.session.model_feature_version)
            if all(before["endpoint"]["events"]):
                raise ValueError("consequence challenge is already complete")
            if self.spec.machine_lesson is not None:
                if self.session.model_feature_version not in (10, 15):
                    raise ValueError("machine consequence requires explicit V10 facts")
                _validate_machine_start(before, candidate, binding.binding_ref, self.spec.machine_lesson)
            elif binding.kind is GoalKind.DEVELOP_TEAM:
                validate_preparation_lesson(
                    dict(
                        before=before["observation"],
                        player_lesson=dict(
                            before=before["lesson"], target=self.spec.preparation_target
                        ),
                        preparation=None
                        if candidate.preparation is None
                        else candidate.preparation.public_dict(),
                    ),
                    binding.kind,
                    pp_evidence=before.get("preparation_pp"),
                    source_state_sha256=before["state_sha256"],
                )
            elif binding.kind is GoalKind.RESTORE_TEAM:
                validate_player_lesson(
                    dict(
                        before=before["lesson"],
                        target={"restoration": "improve_without_regression"},
                    ),
                    before["observation"],
                    binding.kind,
                )
            if preflight_only:
                return plan
            self.plan = plan
            self.session.store.publish_sealed_record(
                "rcc-plan-" + canonical_sha256(plan),
                kind="red_challenge_consequence_plan",
                record=plan,
            )
            _record(self.session.output / "consequence-plan.json", plan)
        elif before != self.phases[-1]["after"] or binding.kind not in {
            GoalKind.RESTORE_TEAM,
            GoalKind.ADVANCE_STORY,
        }:
            raise ValueError("consequence continuation is not restoration then challenge")
        self.active = dict(
            ordinal=len(self.phases),
            kind=binding.kind.value,
            binding_ref=binding.binding_ref,
            before=before,
        )
        _record(
            self.session.output / f"consequence-intent-{len(self.phases):03d}.json", self.active
        )

    def end(self, report, verdict, error=None):
        if self.active is None:
            return
        after = self.capture()
        s = self.session
        before = self.active["before"]

        # Use the same cost verifier as the continuous runner, not claimed totals.
        def counters(value):
            return dict(
                actions=value["actions"],
                completed_actions=value["completed_actions"],
                frames=value["frames"],
                cash=value["cash"],
            )

        cost_ok = measured_cost(counters(before), counters(after), report) is not None
        cost_ok = cost_ok and all(r["succeeded"] for r in s.recorder.trace[before["actions"] :])
        phase = dict(
            self.active,
            after=after,
            interventions=[],
            error=None if error is None else type(error).__name__,
            verified=None if verdict is None else verdict.status is GoalDecisionOutcome.SUCCEEDED,
            battle=None if report is None else report.evidence.get("battle", {}).get("outcome"),
            cost_verified=cost_ok,
        )
        if self.spec.feedback_version == 2:
            phase["challenge_episode"] = (
                None if report is None
                else deepcopy(report.evidence.get("battle", {}).get("episode")))
        self.phases.append(phase)
        _record(s.output / f"consequence-phase-{phase['ordinal']:03d}.json", phase)
        self.active = None
        self.done = (
            (phase["kind"] == GoalKind.ADVANCE_STORY.value
             and not (self.spec.include_challenge_arrival
                      and _pure_challenge_arrival(phase, self.spec.challenge_target)))
            or phase["verified"] is not True
            or len(self.phases) == self.spec.maximum_phases
        )

    def finish(self):
        if self.plan is None:
            return None
        document = dict(
            schema="pokemon.red.challenge-consequence-result.v1",
            declaration_sha256=canonical_sha256(self.plan),
            phases=self.phases,
            interrupted=self.active is not None,
            row=None,
            error=None,
        )
        try:
            row = project_consequence(self.plan, self.phases, interrupted=document["interrupted"])
            document["row"] = row.document()
        except (ValueError, KeyError, TypeError) as error:
            document["error"] = type(error).__name__ + ": " + str(error)
        digest = canonical_sha256(document)
        self.session.store.publish_sealed_record(
            "rcc-result-" + digest, kind="red_challenge_consequence_result", record=document
        )
        _record(self.session.output / "consequence-result.json", document)
        return document


def load_challenge_consequence(store, *, declaration_sha256, result_sha256):
    """Reauthenticate prospective native evidence; never import arbitrary diagnostics."""

    def read(prefix, digest, kind):
        require_digest(digest)
        record = store.find_sealed_record(prefix + digest, expected_kind=kind)
        if record is None or canonical_sha256(record.read()) != digest:
            raise ValueError("consequence authenticated evidence unavailable")
        return record.read()

    plan = read("rcc-plan-", declaration_sha256, "red_challenge_consequence_plan")
    result = read("rcc-result-", result_sha256, "red_challenge_consequence_result")
    if (
        set(result) != {"schema", "declaration_sha256", "phases", "interrupted", "row", "error"}
        or result["schema"] != "pokemon.red.challenge-consequence-result.v1"
    ):
        raise ValueError("consequence result scope differs")
    from .red_native_player import NativeExecutionIdentity

    execution = NativeExecutionIdentity(**plan["execution"])
    record = store.find_sealed_record(
        execution.claim_id, expected_kind="red_native_player_execution"
    )
    if (
        record is None
        or record.read().get("consequence_spec") != plan["spec"]
        or record.read()["source"] != plan["source"]
        or record.read().get("consequence_feature_version", 7) != plan.get("feature_version", 7)
        or result["declaration_sha256"] != declaration_sha256
        or result["error"] is not None
    ):
        raise ValueError("consequence lacks its prospective native execution claim")
    row = project_consequence(plan, result["phases"], interrupted=result["interrupted"])
    _verify_native_counters(store, record.read(), result["phases"])
    if canonical_sha256(row.document()) != canonical_sha256(result["row"]):
        raise ValueError("consequence projection changed")
    return row


def _verify_native_counters(store, native, phases):
    """Reopen the existing write-ahead action log, including failed macro costs."""
    count = phases[-1]["after"]["actions"]
    if count > native["limits"]["actions"]:
        raise ValueError("consequence exceeded native action bound")
    declaration = canonical_sha256(native)
    if store.find_sealed_record(native_action_record_id("action", declaration, count)) is not None:
        raise ValueError("consequence omits a later native action")
    counters = [(0, 0)]
    frame = completed = 0
    for ordinal in range(count):
        intent = store.find_sealed_record(
            native_action_record_id("action", declaration, ordinal),
            expected_kind="red_native_lesson_action",
        )
        trace = store.find_sealed_record(
            native_action_record_id("trace", declaration, ordinal),
            expected_kind="red_native_lesson_trace",
        )
        if intent is None or trace is None:
            raise ValueError("consequence native action evidence is missing")
        action, outcome = intent.read(), trace.read()
        if (
            action["ordinal"] != ordinal
            or outcome["ordinal"] != ordinal
            or action["before_frame"] != frame
            or outcome["before_frame"] != frame
            or type(outcome["after_frame"]) is not int
            or outcome["after_frame"] < frame
            or type(outcome["succeeded"]) is not bool
        ):
            raise ValueError("consequence native action evidence differs")
        frame = outcome["after_frame"]
        completed += int(outcome["succeeded"])
        counters.append((frame, completed))
    if frame > native["limits"]["frames"]:
        raise ValueError("consequence exceeded native frame bound")
    for phase in phases:
        for snapshot in (phase["before"], phase["after"]):
            if counters[snapshot["actions"]] != (snapshot["frames"], snapshot["completed_actions"]):
                raise ValueError("consequence counters differ from sealed native actions")
    if phases[-1]["after"]["heals"] > native["limits"]["heals"]:
        raise ValueError("consequence exceeded native restoration bound")


@dataclass(frozen=True)
class ScopedTrainConsequenceReadback:
    """Qualified native evidence only; no execution status or launch authority."""
    row: ConsequenceExample
    scoped_declaration_sha256: str
    episode_sha256: str
    capture_manifest_sha256: str
    actor_index: int
    invocation_ordinal: int


def load_scoped_train_challenge_consequence(
    store, *, declaration_sha256, result_sha256, scoped_output,
    expected_scoped_declaration_sha256, expected_native_plan_sha256,
    expected_story_contract,
):
    """Read one completed K/TRAIN story consequence and its exact scoped witness.

    Caller supplies authenticated prospective digests/contract and separately
    authenticates native exit, controls, package, source custody and costs.
    This pure reader never converts a failed worker into a successful worker,
    grants continuation, or admits training. Ordinary native losses are valid.
    Risk/evaluation overrides and repeated target battles remain outside scope.
    """
    from pathlib import Path
    from .battle_scenario_capture import open_battle_scenario_capture
    from .red_learned_trainer import (
        FROZEN_K_SHA256, K_QUALIFICATION_SHA256, story_battle_authority,
    )
    from .red_story_battle import StoryTrainerContract
    from .red_trainer_practice_log import verify_trainer_practice_event_log
    from .red_scoped_training_battlers import scoped_train_root_lineage_id
    from .scenario_lab import ScenarioPartition

    def require(condition, reason):
        if not condition:
            raise ValueError("scoped TRAIN consequence " + reason)

    def read(path):
        return json.loads(path.read_bytes())

    require(type(expected_story_contract) is StoryTrainerContract, "needs a typed contract")
    require_digest(expected_scoped_declaration_sha256)
    require_digest(expected_native_plan_sha256)
    row = load_challenge_consequence(
        store, declaration_sha256=declaration_sha256, result_sha256=result_sha256,
    )
    plan = store.find_sealed_record(
        "rcc-plan-" + declaration_sha256, expected_kind="red_challenge_consequence_plan",
    ).read()
    result = store.find_sealed_record(
        "rcc-result-" + result_sha256, expected_kind="red_challenge_consequence_result",
    ).read()
    source, target = plan["source"], plan["spec"]["challenge_target"]
    require(plan["partition"] == source["partition"] == "train"
            and source["experiment_sha256"] == expected_native_plan_sha256,
            "source or native plan differs")
    require(row.outcome is not None and row.outcome.attempted
            and result["interrupted"] is False, "is incomplete")
    contract = asdict(expected_story_contract)
    require(target == dict(kind="events", map_id=expected_story_contract.map_id,
                           events=[expected_story_contract.defeated_event]),
            "target differs from the declared story contract")
    root = Path(scoped_output)
    declaration = read(root / "declaration.json")
    require(canonical_sha256(declaration) == expected_scoped_declaration_sha256,
            "declaration digest differs")
    require(declaration["schema"] == "pokemon.red.scoped-train-battlers.v1"
            and declaration["source_partition"] == "train"
            and declaration["source_state_sha256"] == source["state_sha256"]
            and declaration["source_commit"] == source["source_commit"]
            and declaration["root_lineage_id"] == scoped_train_root_lineage_id(source["origin_sha256"])
            and declaration["native_plan_sha256"] == expected_native_plan_sha256
            and declaration["experiment_sha256"] == expected_native_plan_sha256
            and declaration["fit_allowed"] is False
            and declaration["authority_promotion"] is False
            and declaration["model_sha256"] == FROZEN_K_SHA256
            and declaration["qualification_sha256"] == K_QUALIFICATION_SHA256,
            "declaration authority differs")
    actors = declaration["actors"]
    require(all(a["index"] == i for i, a in enumerate(actors)), "actor indices differ")
    matches = [a for a in actors if a["scope"] == "story"
               and canonical_sha256(a["contract"]) == canonical_sha256(contract)]
    require(len(matches) == 1, "does not identify one exact story actor")
    actor = matches[0]
    require(actor["model_sha256"] == FROZEN_K_SHA256
            and actor["qualification_sha256"] == K_QUALIFICATION_SHA256
            and actor["train_risk_story_scope"] is None, "actor override is unsupported")

    # Global invocation ordinals include wild battles; actor-local battle numbers do not.
    starts = sorted(root.glob("battle-*-start.json"))
    require(starts and set(root.glob("battle-*.json")) == {
        root / f"battle-{i:03d}-{phase}.json"
        for i in range(len(starts)) for phase in ("start", "end")
    }, "invocation census differs")
    calls = [0] * len(actors)
    previous_frame = declaration["frame_origin"]
    target_calls = []
    for ordinal, path in enumerate(starts):
        start, end = read(path), read(root / f"battle-{ordinal:03d}-end.json")
        index = start["actor"]
        require(type(index) is int and 0 <= index < len(actors), "invocation actor differs")
        require(start["schema"] == "pokemon.red.scoped-train-battle-start.v1"
                and start["ordinal"] == ordinal
                and start["declaration_sha256"] == expected_scoped_declaration_sha256
                and start["calls_before"] == calls[index]
                and type(start["before_frame"]) is int
                and start["before_frame"] >= previous_frame, "invocation start differs")
        expected = dict(start, schema="pokemon.red.scoped-train-battle-end.v1",
                        calls_after=calls[index] + 1,
                        after_frame=end["after_frame"], error=None)
        require(end == expected and type(end["after_frame"]) is int
                and end["after_frame"] > start["before_frame"], "invocation end differs")
        calls[index] += 1
        previous_frame = end["after_frame"]
        if index == actor["index"]:
            target_calls.append(end)
    require(len(target_calls) == 1 and calls[actor["index"]] == 1,
            "requires exactly one completed target call")
    invocation = target_calls[0]
    directory = root / f"actor-{actor['index']:03d}" / "battle-0001"
    require(set((root / f"actor-{actor['index']:03d}").glob("battle-*")) == {directory},
            "target battle census differs")
    capture = open_battle_scenario_capture(
        directory / "initial.state", directory / "initial.state.json",
    )
    manifest = capture.manifest
    require((manifest.capture_id, manifest.root_lineage_id, manifest.source_commit,
             manifest.source_state_sha256, manifest.partition,
             manifest.expected_battle_state, manifest.expected_map) ==
            ("player-trainer-0001", declaration["root_lineage_id"],
             source["source_commit"], source["state_sha256"], ScenarioPartition.TRAIN,
             2, expected_story_contract.map_id), "native capture identity differs")
    episode, endpoint = read(directory / "outcome.json"), read(directory / "endpoint.json")
    require(episode["capture_id"] == manifest.capture_id
            and episode["manifest_sha256"] == capture.manifest_sha256
            and endpoint["model_sha256"] == actor["model_sha256"]
            and endpoint["qualification_sha256"] == actor["qualification_sha256"]
            and endpoint["outcome_sha256"] == canonical_sha256(episode)
            and endpoint["final_state_sha256"] == sha256((directory / "final.state").read_bytes()).hexdigest()
            and endpoint["actor_returned_win"] is episode["battle_won"]
            and endpoint["outer_goal_verification_required"] is True,
            "native endpoint differs")
    log = verify_trainer_practice_event_log(directory / "events")
    first = read(directory / "events/event-00001.json")["payload"]
    identity = first.get("identity", {})
    expected = dict(
        model_sha256=actor["model_sha256"], qualification_sha256=actor["qualification_sha256"],
        source_commit=source["source_commit"], root_lineage_id=declaration["root_lineage_id"],
        parent_state_sha256=source["state_sha256"], source_partition="train", fit_allowed=False,
        authority=story_battle_authority(actor["model_sha256"], actor["qualification_sha256"]),
    )
    require(first.get("event") == "run_identity"
            and all(identity.get(k) == v for k, v in expected.items())
            and canonical_sha256(identity.get("train_story_contract")) == canonical_sha256(contract)
            and identity.get("train_funding_diagnostic", False) is False
            and identity.get("wild_training", False) is False, "native event identity differs")
    require(log["complete"] and log["terminal_event"] == "run_finished"
            and not log.get("failed_decisions")
            and log["started_decisions"] == log["completed_decisions"],
            "native event chain is incomplete")
    last = read(directory / "events" / f"event-{log['event_count']:05d}.json")["payload"]
    require(last.get("outcome") == endpoint, "native terminal event differs")
    phase = result["phases"][-1]
    require(phase["battle"] == ("won" if episode["battle_won"] else "lost")
            and canonical_sha256(phase["challenge_episode"]) == canonical_sha256(episode)
            and phase["before"]["frames"] <= invocation["before_frame"] - declaration["frame_origin"]
            and invocation["after_frame"] - declaration["frame_origin"] <= phase["after"]["frames"]
            and row.outcome.completed is episode["battle_won"],
            "final consequence is not the exact native story outcome")
    return ScopedTrainConsequenceReadback(
        row, expected_scoped_declaration_sha256, canonical_sha256(episode),
        capture.manifest_sha256, actor["index"], invocation["ordinal"],
    )
