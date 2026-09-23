"""Completed recovery must preserve choices, censored costs and earned resources."""

import hashlib
import json

import pytest

from pokemon_red_completion.red_safari_lineage import (
    EXACT_PLAN,
    load_safari_lineage,
    verify_completed_safari,
    verify_safari_terminal_facts,
)


def encoded(doc):
    return json.dumps(doc).encode()


def digest(doc):
    return hashlib.sha256(encoded(doc)).hexdigest()


def fixture():
    reserve, model = "a" * 64, "b" * 64
    facts = dict(
        cash=1000,
        owned_species=["pokemon:national:007"],
        registered_species=1,
        specimen_counts={"pokemon:national:007": 1},
        specimens=1,
        bag_items=[[1, 2]],
        party_hp=[12],
        party_pp=[[10, 2]],
        session=dict(
            in_safari_zone=True, safari_game_over=False, safari_balls=28, safari_steps=100
        ),
        map_id=217,
        position_yx=[3, 4],
        battle_state=1,
        input_ready=False,
        actions=16,
        frames=384,
    )
    docs = {}
    for prefix, source, terminal, binding in (
        ("origin", "c" * 64, "d" * 64, "pokemon.red:fishing-live:first"),
        ("choice", "g" * 64, "h" * 64, "pokemon.red:safari-fishing-live:second"),
    ):
        outcome = dict(
            ordinal=0,
            before_state_sha256=source,
            terminal_state_sha256=terminal,
            safe_terminal=False,
            selected_kind="acquire_species",
            error_type="SafariFishingError",
            after=dict(facts),
            choice=dict(
                mode="model_exploration", teacher_labels=0, model_sha256=model, menu_sha256="menu"
            ),
        )
        docs[prefix + "_outcome"] = outcome
        docs[prefix + "_plan"] = dict(
            schema="pokemon.red.autonomous-option-run.v1",
            model_sha256=model,
            teacher_actions_allowed=False,
            provenance=dict(
                parent_state_sha256=source,
                reserve_origin_state_sha256=reserve,
                maximum_actions=4000,
                maximum_frames=400000,
            ),
        )
        docs[prefix + "_result"] = dict(
            schema="pokemon.red.autonomous-option-result.v1",
            model_sha256=model,
            teacher_actions=0,
            outcomes=[outcome],
        )
        docs[prefix + "_started"] = dict(
            state_sha256=source,
            menu_sha256="menu",
            selected_kind="acquire_species",
            selected_binding_ref=binding,
        )
    docs["settlement"] = dict(
        schema="pokemon.red.defensive-safari-settlement-result.v1",
        parent_outcome_sha256=digest(docs["origin_outcome"]),
        before_state_sha256="d" * 64,
        terminal_state_sha256="e" * 64,
        safe_terminal=True,
        preserved_resources=True,
        error=None,
        model_queries=0,
        extra_payment=0,
    )
    docs["censored_plan"] = dict(
        schema="pokemon.red.safari-fishing-goal-continuation.v1",
        parent_outcome_sha256=digest(docs["origin_outcome"]),
        settlement_result_sha256=digest(docs["settlement"]),
        before_state_sha256="e" * 64,
        selected_binding_ref=docs["origin_started"]["selected_binding_ref"],
        reserve_origin={"sha256": reserve},
        model_queries=0,
    )
    docs["censored_audit"] = dict(
        schema="pokemon.red.fishing-report-serialization-audit.v1",
        plan_sha256=digest(docs["censored_plan"]),
        before_state_sha256="e" * 64,
        terminal_sha256="g" * 64,
        status="terminal_verified_telemetry_censored",
        safe=True,
        resource_preservation=True,
        replayed=False,
        model_queries=0,
        actions=None,
        frames=None,
    )
    docs["choice_plan"]["provenance"]["parent_terminal_audit_sha256"] = digest(
        docs["censored_audit"]
    )
    parent = dict(
        schema=EXACT_PLAN,
        parent_outcome_sha256=digest(docs["choice_outcome"]),
        parent_result_sha256=digest(docs["choice_result"]),
        before_state_sha256="h" * 64,
        reserve_origin={"sha256": reserve},
        model_queries=0,
        learning_eligible=False,
        selected_binding_ref=docs["choice_started"]["selected_binding_ref"],
        maximum_actions=3984,
        maximum_frames=399616,
    )
    after = {
        **facts,
        "cash": 1000,
        "owned_species": ["pokemon:national:007", "pokemon:national:147"],
        "registered_species": 2,
        "specimens": 2,
        "specimen_counts": {"pokemon:national:007": 1, "pokemon:national:147": 1},
        "battle_state": 0,
        "input_ready": True,
        "safe": True,
        "session": {**facts["session"], "safari_balls": 21, "safari_steps": 56},
    }
    final = dict(
        schema="pokemon.red.safari-fishing-exact-continuation-result.v1",
        before_state_sha256="h" * 64,
        terminal_state_sha256="i" * 64,
        safe_terminal=True,
        verification="succeeded",
        error=None,
        model_queries=0,
        learning_eligible=False,
        before=facts,
        after=after,
        actions=386,
        frames=32244,
        evidence={"new_registrations": 1},
    )
    plan = dict(reserve_origin={"sha256": reserve}, state={"sha256": "i" * 64}, model_sha256=model)
    return plan, parent, final, docs


def verify(plan, parent, final, docs):
    verify_completed_safari(
        plan,
        {"prior_plan": encoded(parent), "prior_outcome": encoded(final)},
        {k: encoded(v) for k, v in docs.items()},
    )


def test_completed_chain_preserves_unknown_costs_and_no_new_query():
    items = fixture()
    verify(*items)
    assert items[-1]["censored_audit"]["actions"] is None
    verify_safari_terminal_facts(items[2], items[2]["after"])


@pytest.mark.parametrize(
    "change",
    [
        "reserve",
        "terminal",
        "missing",
        "ancestor_hash",
        "ancestor_gap",
        "wrong_goal",
        "failed",
        "unsafe",
        "refit",
        "requery",
        "budget",
        "before_cash",
        "cash",
        "bag",
        "hp",
        "pp",
        "flags",
        "specimens",
        "session",
        "censored_cost",
        "assistance",
    ],
)
def test_refuses_broken_or_substituted_chain(change):
    plan, parent, final, docs = fixture()
    if change == "reserve":
        plan["reserve_origin"]["sha256"] = "z" * 64
    elif change == "terminal":
        plan["state"]["sha256"] = "z" * 64
    elif change == "missing":
        del docs["censored_audit"]
    elif change == "ancestor_hash":
        parent["parent_result_sha256"] = "z" * 64
    elif change == "ancestor_gap":
        docs["origin_plan"]["provenance"]["parent_state_sha256"] = "z" * 64
    elif change == "wrong_goal":
        parent["selected_binding_ref"] += "other"
    elif change == "failed":
        final["verification"] = "failed"
    elif change == "unsafe":
        final["safe_terminal"] = False
    elif change == "refit":
        final["learning_eligible"] = True
    elif change == "requery":
        final["model_queries"] = 1
    elif change == "budget":
        parent["maximum_frames"] += 1
    elif change == "before_cash":
        final["before"] = {**final["before"], "cash": 2000}
    elif change in {"cash", "bag", "hp", "pp"}:
        key = {"cash": "cash", "bag": "bag_items", "hp": "party_hp", "pp": "party_pp"}[change]
        final["after"][key] = 0
    elif change == "flags":
        final["after"]["owned_species"] = ["pokemon:national:147"]
    elif change == "specimens":
        final["after"]["specimen_counts"] = {"pokemon:national:147": 2}
    elif change == "session":
        final["after"]["session"]["safari_balls"] = 30
    elif change == "censored_cost":
        docs["censored_audit"]["actions"] = 0
    else:
        plan["assisted_training_money"] = 500
    with pytest.raises(ValueError, match="Safari lineage"):
        verify(plan, parent, final, docs)


@pytest.mark.parametrize("key", ["cash", "owned_species", "specimen_counts", "session", "party_hp"])
def test_live_observation_must_match_receipt(key):
    _, _, receipt, _ = fixture()
    observed = dict(receipt["after"])
    observed[key] = None
    with pytest.raises(ValueError, match="live terminal"):
        verify_safari_terminal_facts(receipt, observed)


def test_manifest_authenticates_every_original_file(tmp_path):
    _, _, _, docs = fixture()
    refs = {}
    for name, doc in docs.items():
        path = tmp_path / name
        path.write_bytes(encoded(doc))
        refs[name] = {"path": str(path), "sha256": digest(doc)}
    payload = encoded({"schema": "pokemon.red.completed-safari-lineage.v1", "records": refs})
    assert load_safari_lineage(payload) == {k: encoded(v) for k, v in docs.items()}
    (tmp_path / "origin_plan").write_bytes(b"{}")
    with pytest.raises(ValueError, match="authentication"):
        load_safari_lineage(payload)


def test_runner_dispatches_only_completed_safari_with_manifest(monkeypatch):
    import run_red_autonomous_collection as runner

    plan, parent, final, docs = fixture()
    records = {k: encoded(v) for k, v in docs.items()}
    monkeypatch.setattr(runner, "load_safari_lineage", lambda _: records)
    payloads = {"prior_plan": encoded(parent), "prior_outcome": encoded(final)}
    with pytest.raises(ValueError, match="authenticated lineage"):
        runner._verify_reserve_lineage(plan, payloads)
    payloads["safari_lineage"] = b"manifest"
    runner._verify_reserve_lineage(plan, payloads)
    with pytest.raises(ValueError, match="authenticated lineage"):
        runner._verify_reserve_lineage(plan, payloads, field_settlement=True)
