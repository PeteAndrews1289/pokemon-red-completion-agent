"""Authenticated native teacher outcomes in the registered player's coordinates.

These are unit-weight demonstrations, never sampled arms. The trusted recorder
must publish the declaration before input and audit the native terminal. Digests
authenticate that record; they do not turn arbitrary external JSON into truth.
No emulator, intervention action, economy target or promotion lives here.
"""

import re
from dataclasses import dataclass

from .goal_manager import GoalKind, GoalManagerQuestion
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
    exchange = plan.get("schema") == EXCHANGE_PLAN_SCHEMA
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
        } | ({"npc_exchange"} if exchange else set())
        or plan["schema"] != (EXCHANGE_PLAN_SCHEMA if exchange else PLAN_SCHEMA)
        or plan["contract"] != (EXCHANGE_CONTRACT if exchange else CONTRACT)
        or plan["partition"] != "train"
        or plan["objective"] != REGISTERED_OBJECTIVE
        or plan["teacher_selected"] is not True
        or plan["comparative_choice"] is not False
    ):
        raise ValueError("native curriculum declaration scope differs")
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
        or q.opportunities[index].kind is not GoalKind.ACQUIRE_SPECIES
        or q.situation.policy_dict() != semantic_facts(plan["before"])["situation"]
    ):
        raise ValueError("native curriculum question differs from before observation")
    # Validate the declared registration contract even before an outcome exists.
    checkpoint = RegisteredCollectionCheckpoint.from_public(plan["before"]["registration"])
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
    candidate = project_living_dex_goal_candidate(
        q, index, feature_version=4, binding_ref="native-teacher-execution"
    )
    if candidate is None:
        raise ValueError("native curriculum has no portable candidate")
    return context, candidate


def publish_declaration(store: PrivateArtifactRoot, plan):
    curriculum_projection(plan)
    sha = canonical_sha256(plan)
    store.publish_sealed_record("rnc-plan-" + sha, kind="red_native_curriculum_plan", record=plan)
    return sha


def reconstruct_native_curriculum(plan, result):
    context, candidate = curriculum_projection(plan)
    exchange = plan["schema"] == EXCHANGE_PLAN_SCHEMA
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
        } | ({"npc_exchange"} if exchange else set())
        or result["schema"] != (EXCHANGE_OUTCOME_SCHEMA if exchange else OUTCOME_SCHEMA)
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
    outcome = red_registered_outcome_from_observations(
        plan["before"],
        result["after"],
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        succeeded=result["succeeded"],
        actions=len(trace),
        frames=frame,
        maximum_actions=COMPLETION_ACTIONS,
        maximum_frames=COMPLETION_FRAMES,
        npc_exchange=(plan["npc_exchange"], result["npc_exchange"]) if exchange else None,
    )
    return LivingDexCurriculumOutcomeExample(
        canonical_sha256(plan),
        "train",
        4,
        candidate.vector(context, feature_version=4),
        outcome,
    )


def _read(store, sha, *, plan):
    record = store.find_sealed_record(
        ("rnc-plan-" if plan else "rnc-outcome-") + sha,
        expected_kind="red_native_curriculum_plan" if plan else "red_native_curriculum_outcome",
    )
    if record is None or canonical_sha256(record.read()) != sha:
        raise ValueError("native curriculum authenticated record missing or changed")
    return record.read()


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
