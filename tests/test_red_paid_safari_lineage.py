"""Fail-closed legacy paid-search admission; no private inputs or cartridge."""

import hashlib
import json

import pytest

from pokemon_red_completion.red_paid_safari_lineage import (
    PAID_RECORDS,
    verify_paid_safari_lineage,
    verify_paid_safari_live_facts,
)


def fixture():
    session = dict(in_safari_zone=True, safari_game_over=False, safari_balls=24, safari_steps=129)
    facts = dict(
        cash=1500,
        owned_species=["a"],
        registered_species=1,
        specimen_counts={"a": 1},
        specimens=1,
        bag_items=[[1, 3]],
        party_hp=[50],
        party_pp=[[10]],
        session=session,
        map_id=218,
        position_yx=[31, 28],
        party=[dict(slot=1, species_id=66, xp=1000)],
    )
    outcome = dict(
        before_state_sha256="b" * 64,
        terminal_state_sha256="c" * 64,
        safe_terminal=True,
        selected_kind="acquire_species",
        error_type="RedAreaExecutionError",
        error_chain=[dict(reason_code="semantic_action_limit_exceeded")],
        choice=dict(
            model_sha256="m" * 64, menu_sha256="menu", mode="model_exploration", teacher_labels=0
        ),
        before=dict(cash=2000),
        after=dict(
            facts,
            actions=100,
            frames=1000,
            session=dict(session, safari_balls=30, safari_steps=305),
        ),
    )
    docs = dict(
        prior_plan=dict(
            schema="pokemon.red.autonomous-option-run.v1",
            model_sha256="m" * 64,
            provenance=dict(maximum_actions=5000, maximum_frames=50000),
        ),
        prior_outcome=outcome,
        prior_result=dict(outcomes=[outcome]),
        prior_execution_started=dict(
            state_sha256="b" * 64,
            selected_kind="acquire_species",
            menu_sha256="menu",
            selected_binding_ref="pokemon.red:safari-live:original",
        ),
        paid_safari_input=dict(
            rom=dict(sha256="r" * 64),
            state=dict(sha256="c" * 64),
            before=dict(sha256="b" * 64),
            source_commit="source",
        ),
        paid_safari_plan=dict(
            schema="pokemon.red.paid-safari-continuation.v1",
            source_commit="source",
            original_selected_binding="pokemon.red:safari-live:original",
            before_state_sha256="c" * 64,
            model_queries=0,
            maximum_macros=1000,
            maximum_frames=10000,
            remaining_original_actions=4900,
            remaining_original_frames=49000,
        ),
        paid_safari_result=dict(
            schema="pokemon.red.paid-safari-continuation-result.v1",
            before_state_sha256="c" * 64,
            terminal_state_sha256="d" * 64,
            model_queries=0,
            extra_payment=0,
            safe_terminal=True,
            preserved_resources=True,
            report=None,
            registered_gains=[],
            specimens_before=1,
            specimens_after=1,
            error=dict(type="RedAreaExecutionError", reason_code="semantic_action_limit_exceeded"),
            after=dict(
                cash=1500,
                registrations=1,
                position=[218, 31, 28],
                session=session,
                macros=100,
                frames=2000,
            ),
        ),
        paid_safari_audit=dict(
            schema="pokemon.red.paid-safari-native-audit.v1",
            status="verified_native_zero_input",
            terminal_sha256="d" * 64,
            safe=True,
            original_inputs_unchanged=True,
            frames=0,
            facts=facts,
        ),
    )
    plan = dict(model_sha256="m" * 64, rom=dict(sha256="r" * 64), state=dict(sha256="d" * 64))
    return plan, docs


def encode(docs):
    # Rehash mutations too: tests reject semantically wrong but authenticated receipts.
    def digest(key):
        return hashlib.sha256(json.dumps(docs[key]).encode()).hexdigest()

    for source, target in (
        ("parent_plan", "prior_plan"),
        ("parent_result", "prior_result"),
        ("outcome", "prior_outcome"),
        ("execution", "prior_execution_started"),
    ):
        docs["paid_safari_input"][source] = dict(sha256=digest(target))
    docs["paid_safari_plan"]["input_plan_sha256"] = digest("paid_safari_input")
    docs["paid_safari_plan"]["original_goal_outcome_sha256"] = digest("prior_outcome")
    docs["paid_safari_audit"]["result_sha256"] = digest("paid_safari_result")
    return {key: json.dumps(value).encode() for key, value in docs.items()}


def test_admits_failed_receipt_without_turning_it_into_success():
    plan, docs = fixture()
    assert verify_paid_safari_lineage(plan, encode(docs)) == docs["paid_safari_audit"]["facts"]
    assert docs["paid_safari_result"]["report"] is None


@pytest.mark.parametrize(
    "record,key,value",
    [
        ("prior_plan", "model_sha256", "other"),
        ("prior_plan", "schema", "unknown"),
        ("prior_execution_started", "selected_binding_ref", "teacher:target"),
        ("prior_execution_started", "menu_sha256", "other"),
        ("prior_outcome", "error_type", "OtherError"),
        ("prior_outcome", "safe_terminal", False),
        ("paid_safari_input", "source_commit", "other"),
        ("paid_safari_plan", "original_selected_binding", "other"),
        ("paid_safari_plan", "remaining_original_actions", 5000),
        ("paid_safari_plan", "maximum_macros", 6000),
        ("paid_safari_plan", "model_queries", False),
        ("paid_safari_result", "model_queries", 1),
        ("paid_safari_result", "extra_payment", 500),
        ("paid_safari_result", "terminal_state_sha256", "other"),
        ("paid_safari_result", "safe_terminal", False),
        ("paid_safari_result", "preserved_resources", False),
        ("paid_safari_result", "registered_gains", ["unverified"]),
        ("paid_safari_result", "error", None),
        ("paid_safari_result", "report", {}),
        ("paid_safari_result", "specimens_after", 2),
        ("paid_safari_audit", "frames", True),
        ("paid_safari_audit", "frames", 1),
        ("paid_safari_audit", "safe", False),
        ("paid_safari_audit", "original_inputs_unchanged", False),
    ],
)
def test_rehashed_semantic_mutations_rejected(record, key, value):
    plan, docs = fixture()
    docs[record][key] = value
    with pytest.raises(ValueError, match="paid Safari"):
        verify_paid_safari_lineage(plan, encode(docs))


@pytest.mark.parametrize("key", PAID_RECORDS)
def test_partial_receipts_rejected(key):
    plan, docs = fixture()
    payloads = encode(docs)
    del payloads[key]
    with pytest.raises(ValueError):
        verify_paid_safari_lineage(plan, payloads)


def test_assistance_rejected_even_if_zero():
    plan, docs = fixture()
    plan["assisted_training_money"] = 0
    with pytest.raises(ValueError):
        verify_paid_safari_lineage(plan, encode(docs))


@pytest.mark.parametrize(
    "cost,value", [("macros", 1001), ("frames", 10001), ("macros", True), ("frames", -1)]
)
def test_bounded_costs(cost, value):
    plan, docs = fixture()
    docs["paid_safari_result"]["after"][cost] = value
    with pytest.raises(ValueError):
        verify_paid_safari_lineage(plan, encode(docs))


@pytest.mark.parametrize(
    "key,value",
    [
        ("safari_balls", 31),
        ("safari_steps", 306),
        ("safari_steps", 0),
        ("safari_balls", True),
        ("in_safari_zone", False),
        ("safari_game_over", True),
    ],
)
def test_paid_resources_cannot_reset_or_expire(key, value):
    plan, docs = fixture()
    docs["paid_safari_result"]["after"]["session"][key] = value
    with pytest.raises(ValueError):
        verify_paid_safari_lineage(plan, encode(docs))


def test_native_facts_checked_not_just_audit_flag():
    _, docs = fixture()
    expected = docs["paid_safari_audit"]["facts"]
    actual = dict(expected, battle_state=0, input_ready=True, party_training=[[1, 66, 1000]])
    verify_paid_safari_live_facts(expected, actual)
    for key, value in (
        ("cash", 2000),
        ("battle_state", 1),
        ("input_ready", False),
        ("owned_species", []),
        ("party_training", [[1, 66, 2000]]),
    ):
        with pytest.raises(ValueError):
            verify_paid_safari_live_facts(expected, dict(actual, **{key: value}))
