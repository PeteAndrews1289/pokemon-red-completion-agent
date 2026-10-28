"""Authenticated native teacher outcomes in the registered player's coordinates.

These are unit-weight demonstrations, never sampled arms. The trusted recorder
must publish the declaration before input and audit the native terminal. Digests
authenticate that record; they do not turn arbitrary external JSON into truth.
No emulator, intervention action, economy target or promotion lives here.
"""

import re
from dataclasses import dataclass, replace

from .goal_manager import GoalKind, GoalManagerQuestion, GoalNeed
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    living_dex_option_context_from_goal_situation,
)
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_player_economy import restore_snapshot, semantic_facts
from .red_player_training_plan import COMPLETION_ACTIONS, COMPLETION_FRAMES
from .red_registered_outcome import red_registered_outcome_from_observations
from .registered_checkpoint import RegisteredCollectionCheckpoint
from .registered_collection import REGISTERED_OBJECTIVE

CONTRACT = "registered-native-teacher-unit-outcome-v1"
PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v1"
OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v1"
EXCHANGE_CONTRACT = "registered-native-npc-exchange-unit-outcome-v1"
EXCHANGE_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v2"
EXCHANGE_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v2"
PLAYER_CONTRACT = "registered-native-player-unit-outcome-v1"
PLAYER_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v3"
PLAYER_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v3"
READINESS_CONTRACT = "registered-native-player-readiness-unit-outcome-v1"
READINESS_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v4"
READINESS_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v4"
RESOURCE_CONTRACT = "registered-native-player-resource-unit-outcome-v1"
RESOURCE_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v5"
RESOURCE_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v5"
CONTINUOUS_RESOURCE_CONTRACT = "registered-native-continuous-resource-unit-outcome-v1"
CONTINUOUS_RESOURCE_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v6"
CONTINUOUS_RESOURCE_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v6"
CHALLENGE_CONTRACT = "registered-native-player-challenge-unit-outcome-v1"
CHALLENGE_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v7"
CHALLENGE_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v7"
STORY_UNIT_CONTRACT = "registered-native-player-story-unit-outcome-v1"
STORY_UNIT_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v8"
STORY_UNIT_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v8"
PREPARATION_CONTRACT = "registered-native-player-preparation-unit-outcome-v1"
PREPARATION_PLAN_SCHEMA = "pokemon.red.native-curriculum-declaration.v9"
PREPARATION_OUTCOME_SCHEMA = "pokemon.red.native-curriculum-outcome.v9"


def _continuous_situation(plan):
    """Reconstruct the opt-in stock pressure; no new inference feature schema."""
    from .observation import ItemId
    from .red_capture_readiness import ORDINARY_BALLS, CapturePreparationBudget

    situation = dict(semantic_facts(plan["before"])["situation"])
    pressures = dict(situation["need_pressures"])
    situation["need_pressures"] = pressures
    budget = plan["capture_reserve"]
    if budget is not None:
        budget = CapturePreparationBudget(**{**budget, "ball": ItemId(budget["ball"])})
        economy = restore_snapshot(plan["economy_before"])
        if economy is None:
            raise ValueError("continuous resource projection requires economy")
        inventory = dict(economy.inventory)
        stock = sum(inventory.get(f"red-item-{int(b):03d}", 0) for b in ORDINARY_BALLS)
        pressures[GoalNeed.RESOURCES.value] = 1 - min(1, stock / budget.reserve)
        pressures[GoalNeed.STORAGE_CAPACITY.value] = max(
            pressures[GoalNeed.STORAGE_CAPACITY.value],
            float(semantic_facts(plan["before"])["immediate_capture_slots"] <= 0),
        )
    return situation


@dataclass(frozen=True)
class NativeCurriculumInput:
    declaration_sha256: str
    outcome_sha256: str

    def __post_init__(self):
        for value in (self.declaration_sha256, self.outcome_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("native curriculum digest differs")

    def public_dict(self):
        return dict(declaration_sha256=self.declaration_sha256, outcome_sha256=self.outcome_sha256)


def curriculum_projection(plan):
    """Rebuild the ordinary inference vector; no acquisition-only approximations."""
    preparation = plan.get("schema") == PREPARATION_PLAN_SCHEMA
    exchange = plan.get("schema") == EXCHANGE_PLAN_SCHEMA
    story_unit = plan.get("schema") == STORY_UNIT_PLAN_SCHEMA
    challenge = story_unit or plan.get("schema") == CHALLENGE_PLAN_SCHEMA
    continuous = plan.get("schema") == CONTINUOUS_RESOURCE_PLAN_SCHEMA
    resource = continuous or plan.get("schema") == RESOURCE_PLAN_SCHEMA
    readiness = preparation or challenge or resource or plan.get("schema") == READINESS_PLAN_SCHEMA
    player = readiness or plan.get("schema") == PLAYER_PLAN_SCHEMA
    plan_schema = (
        PREPARATION_PLAN_SCHEMA if preparation else
        STORY_UNIT_PLAN_SCHEMA if story_unit else CHALLENGE_PLAN_SCHEMA if challenge else
        CONTINUOUS_RESOURCE_PLAN_SCHEMA if continuous else
        RESOURCE_PLAN_SCHEMA if resource else READINESS_PLAN_SCHEMA if readiness else
        PLAYER_PLAN_SCHEMA if player else EXCHANGE_PLAN_SCHEMA if exchange else PLAN_SCHEMA
    )
    contract = (PREPARATION_CONTRACT if preparation else
                STORY_UNIT_CONTRACT if story_unit else CHALLENGE_CONTRACT if challenge else
                CONTINUOUS_RESOURCE_CONTRACT if continuous else
                RESOURCE_CONTRACT if resource else READINESS_CONTRACT if readiness
                else PLAYER_CONTRACT if player else EXCHANGE_CONTRACT if exchange else CONTRACT)
    if (
        set(plan)
        != {
            "schema",
            "contract",
            "partition",
            "objective",
            "question",
            "selected_index",
            "before",
            "economy_before",
            "target_cash",
            "source",
            "maximum_actions",
            "maximum_frames",
            "teacher_selected",
            "comparative_choice",
        } | ({"npc_exchange"} if exchange else {"player_lesson"} if player else set())
        | ({"readiness"} if readiness else set())
        | ({"challenge"} if challenge else set())
        | ({"story_unit"} if story_unit else set())
        | ({"preparation", "challenge"} if preparation else set())
        | ({"capture_reserve", "execution_identity"} if continuous else set())
        or plan["schema"] != plan_schema
        or plan["contract"] != contract
        or plan["partition"] != "train"
        or plan["objective"] != REGISTERED_OBJECTIVE
        or plan["teacher_selected"] is not (not continuous)
        or plan["comparative_choice"] is not False
    ):
        raise ValueError("native curriculum declaration scope differs")
    if continuous:
        from .red_native_player import NativeExecutionIdentity

        NativeExecutionIdentity(**plan["execution_identity"])
    source = plan["source"]
    if (
        set(source)
        != {
            "origin_sha256",
            "state_sha256",
            "setup_receipt_sha256",
            "source_commit",
            "source_bundle_sha256",
            "partition",
        }
        or source["partition"] != "train"
        or any(
            not isinstance(source[k], str) or not re.fullmatch(r"[0-9a-f]{64}", source[k])
            for k in (
                "origin_sha256",
                "state_sha256",
                "setup_receipt_sha256",
                "source_bundle_sha256",
            )
        )
        or not re.fullmatch(r"[0-9a-f]{40}", source["source_commit"])
    ):
        raise ValueError("native curriculum TRAIN source differs")
    for key, limit in (
        ("maximum_actions", COMPLETION_ACTIONS),
        ("maximum_frames", COMPLETION_FRAMES),
    ):
        if type(plan[key]) is not int or not 0 < plan[key] <= limit:
            raise ValueError("native curriculum execution bound differs")
    q = GoalManagerQuestion.from_policy_input(plan["question"])
    index = plan["selected_index"]
    if (
        type(index) is not int
        or index not in q.available_indices
        or (not player and q.opportunities[index].kind is not GoalKind.ACQUIRE_SPECIES)
        or q.situation.policy_dict() != (
            _continuous_situation(plan) if continuous
            else semantic_facts(plan["before"])["situation"]
        )
    ):
        raise ValueError("native curriculum question differs from before observation")
    # Validate the declared registration contract even before an outcome exists.
    checkpoint = RegisteredCollectionCheckpoint.from_public(plan["before"]["registration"])
    if story_unit:
        from .red_player_story_unit import validate_story_unit_lesson

        validate_story_unit_lesson(plan, q.opportunities[index].kind)
    elif resource:
        from .red_player_resource_lesson import validate_resource_lesson

        validate_resource_lesson(plan, q)
    elif player:
        from .red_player_lesson import validate_player_lesson

        validate_player_lesson(plan["player_lesson"], plan["before"], q.opportunities[index].kind)
    if exchange:
        from .red_npc_exchange_learning import validate_exchange_declaration

        validate_exchange_declaration(checkpoint, plan["npc_exchange"])
    economy = restore_snapshot(plan["economy_before"])
    if economy is None:
        raise ValueError("native curriculum requires observed economy context")
    if exchange:
        native = plan["npc_exchange"]["before"]
        inventory = {f"red-item-{item:03d}": n for item, n in native["bag"]}
        if economy.cash != native["cash"] or dict(economy.inventory) != inventory:
            raise ValueError("native exchange economy differs from native snapshot")
    context = living_dex_option_context_from_goal_situation(
        q.situation,
        economy_snapshot=economy,
        target_cash=plan["target_cash"],
    )
    from .player_readiness import PlayerReadiness

    candidate = project_living_dex_goal_candidate(
        q, index, feature_version=5 if readiness else 4, binding_ref="native-teacher-execution",
        readiness=PlayerReadiness.from_public(plan["readiness"]) if readiness else None,
    )
    if candidate is None:
        raise ValueError("native curriculum has no portable candidate")
    if challenge:
        from .player_option_challenge import OptionChallenge

        candidate = replace(candidate, challenge=OptionChallenge.from_public(plan["challenge"]))
    if preparation:
        from .player_option_challenge import OptionChallenge
        from .red_player_lesson import validate_preparation_lesson

        facts = validate_preparation_lesson(plan, q.opportunities[index].kind)
        candidate = replace(candidate, preparation=facts, challenge=(
            None if plan["challenge"] is None else OptionChallenge.from_public(plan["challenge"])
        ))
    return context, candidate


def publish_declaration(store: PrivateArtifactRoot, plan):
    curriculum_projection(plan)
    _require_continuous_execution(store, plan)
    sha = canonical_sha256(plan)
    store.publish_sealed_record("rnc-plan-" + sha, kind="red_native_curriculum_plan", record=plan)
    return sha


def reconstruct_native_curriculum(plan, result):
    context, candidate = curriculum_projection(plan)
    preparation = plan["schema"] == PREPARATION_PLAN_SCHEMA
    exchange = plan["schema"] == EXCHANGE_PLAN_SCHEMA
    story_unit = plan["schema"] == STORY_UNIT_PLAN_SCHEMA
    challenge = story_unit or plan["schema"] == CHALLENGE_PLAN_SCHEMA
    continuous = plan["schema"] == CONTINUOUS_RESOURCE_PLAN_SCHEMA
    resource = continuous or plan["schema"] == RESOURCE_PLAN_SCHEMA
    readiness = preparation or challenge or resource or plan["schema"] == READINESS_PLAN_SCHEMA
    player = readiness or plan["schema"] == PLAYER_PLAN_SCHEMA
    outcome_schema = (
        PREPARATION_OUTCOME_SCHEMA if preparation else
        STORY_UNIT_OUTCOME_SCHEMA if story_unit else CHALLENGE_OUTCOME_SCHEMA if challenge else
        CONTINUOUS_RESOURCE_OUTCOME_SCHEMA if continuous else
        RESOURCE_OUTCOME_SCHEMA if resource else READINESS_OUTCOME_SCHEMA if readiness
        else PLAYER_OUTCOME_SCHEMA if player
        else EXCHANGE_OUTCOME_SCHEMA if exchange else OUTCOME_SCHEMA
    )
    if (
        set(result)
        != {
            "schema",
            "declaration_sha256",
            "after",
            "succeeded",
            "trace",
            "terminal_state_sha256",
            "native_audit",
            "interventions_during_execution",
        } | ({"npc_exchange"} if exchange else {"player_lesson"} if player else set())
        | ({"economy_after"} if resource else set())
        | ({"story_unit"} if story_unit else set())
        or result["schema"] != outcome_schema
        or result["declaration_sha256"] != canonical_sha256(plan)
        or type(result["succeeded"]) is not bool
        or result["interventions_during_execution"] != []
        or not re.fullmatch(r"[0-9a-f]{64}", result["terminal_state_sha256"])
    ):
        raise ValueError("native curriculum outcome scope differs")
    audit = result["native_audit"]
    if (
        not isinstance(audit, dict)
        or type(audit.get("input_frames")) is not int
        or audit.get("passed") is not True
        or audit
        != dict(
            before_sha256=plan["source"]["state_sha256"],
            terminal_sha256=result["terminal_state_sha256"],
            input_frames=0,
            passed=True,
        )
    ):
        raise ValueError("native curriculum audit binding differs")
    trace = result["trace"]
    if not isinstance(trace, list) or not 0 < len(trace) <= plan["maximum_actions"]:
        raise ValueError("native curriculum trace census differs")
    frame = 0
    for ordinal, row in enumerate(trace):
        if (
            set(row) != {"ordinal", "before_frame", "after_frame", "succeeded"}
            or type(row["ordinal"]) is not int
            or row["ordinal"] != ordinal
            or type(row["before_frame"]) is not int
            or row["before_frame"] != frame
            or type(row["after_frame"]) is not int
            or row["after_frame"] <= frame
            or row["succeeded"] is not True
        ):
            raise ValueError("native curriculum trace continuity differs")
        frame = row["after_frame"]
    if frame > plan["maximum_frames"]:
        raise ValueError("native curriculum frame budget exceeded")
    selected_kind = GoalKind.ACQUIRE_SPECIES
    measured_economy = None
    if player:
        from .red_player_lesson import verify_player_lesson

        question = GoalManagerQuestion.from_policy_input(plan["question"])
        selected_kind = question.opportunities[plan["selected_index"]].kind
        if story_unit:
            from .red_player_story_unit import verify_story_unit_lesson

            verify_story_unit_lesson(plan, result, selected_kind)
        elif resource:
            from .red_player_resource_lesson import verify_resource_lesson

            measured_economy = verify_resource_lesson(plan, result, question)
        else:
            verify_player_lesson(
                plan["player_lesson"], result["player_lesson"], plan["before"], result["after"],
                selected_kind, result["succeeded"],
            )
    outcome = red_registered_outcome_from_observations(
        plan["before"],
        result["after"],
        selected_kind=selected_kind,
        succeeded=result["succeeded"],
        actions=len(trace),
        frames=frame,
        maximum_actions=COMPLETION_ACTIONS,
        maximum_frames=COMPLETION_FRAMES,
        npc_exchange=(plan["npc_exchange"], result["npc_exchange"]) if exchange else None,
    )
    feature_version = 7 if preparation else 6 if challenge else 5 if readiness else 4
    return LivingDexCurriculumOutcomeExample(
        canonical_sha256(plan),
        "train",
        feature_version,
        candidate.vector(context, feature_version=feature_version),
        replace(outcome, economy=measured_economy) if resource else outcome,
    )


def _read(store, sha, *, plan):
    record = store.find_sealed_record(
        ("rnc-plan-" if plan else "rnc-outcome-") + sha,
        expected_kind="red_native_curriculum_plan" if plan else "red_native_curriculum_outcome",
    )
    if record is None or canonical_sha256(record.read()) != sha:
        raise ValueError("native curriculum authenticated record missing or changed")
    document = record.read()
    if plan:
        _require_continuous_execution(store, document)
    return document


def _require_continuous_execution(store, plan):
    if plan.get("schema") != CONTINUOUS_RESOURCE_PLAN_SCHEMA:
        return
    from .red_native_player import NativeExecutionIdentity

    identity = NativeExecutionIdentity(**plan["execution_identity"])
    sealed = store.find_sealed_record(
        identity.claim_id, expected_kind="red_native_player_execution"
    )
    if sealed is None:
        raise ValueError("continuous lesson lacks its prospective execution claim")
    execution = sealed.read()
    if (
        execution.get("execution") != plan["execution_identity"]
        or execution.get("resource_setup_receipt") != plan["source"]["setup_receipt_sha256"]
        or execution.get("capture_reserve") != plan["capture_reserve"]
        or any(execution["source"][key] != plan["source"][key] for key in (
            "origin_sha256", "partition", "source_commit", "source_bundle_sha256",
        ))
        or plan["maximum_actions"] > execution["limits"]["actions"]
        or plan["maximum_frames"] > execution["limits"]["frames"]
    ):
        raise ValueError("continuous resource lesson differs from its authorized execution")


def publish_outcome(store, declaration_sha256, result):
    plan = _read(store, declaration_sha256, plan=True)
    reconstruct_native_curriculum(plan, result)
    sha = canonical_sha256(result)
    store.publish_sealed_record(
        "rnc-outcome-" + sha, kind="red_native_curriculum_outcome", record=result
    )
    return NativeCurriculumInput(declaration_sha256, sha)


def load_native_curriculum(store, item: NativeCurriculumInput):
    return reconstruct_native_curriculum(
        _read(store, item.declaration_sha256, plan=True),
        _read(store, item.outcome_sha256, plan=False),
    )


def retained_native_curriculum(store, corpus, incoming=()):
    """Future fits reauthenticate old lessons rather than trusting cached vectors."""
    prior = tuple(NativeCurriculumInput(**row) for row in corpus.get("native_curriculum", []))
    if len({x.declaration_sha256 for x in (*prior, *incoming)}) != len(prior) + len(incoming):
        raise ValueError("native curriculum repeats or replaces an execution")
    items = (*prior, *incoming)
    return items, tuple(load_native_curriculum(store, item) for item in items)
