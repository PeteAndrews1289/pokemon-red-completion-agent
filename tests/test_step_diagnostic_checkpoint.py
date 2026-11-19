"""ROM-free checks for step-boundary diagnostic checkpoint reconstruction."""

import json
from dataclasses import asdict
from hashlib import sha256

import pytest
import run_configured_red_player as driver
from test_party_preparation import enemies, team

from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.party_preparation import build_preparation_plan
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_configuration import checkpoint_quiescent
from pokemon_red_completion.red_player_continuation import (
    SCHEMA,
    build_step_diagnostic_checkpoint,
    step_search_memory_dict,
)


def _sample_parent_context():
    member = team(5)[0]
    plan = build_preparation_plan((member,), enemies(10))
    mem = GoalSearchMemory()
    mem.record("wild:route1", "a" * 64, exhausted=True, actions=12, frames=360)
    return dict(
        schema=SCHEMA,
        state_sha256=sha256(b"parent-state").hexdigest(),
        lesson=dict(
            schema="pokemon.red.player-lesson-snapshot.v1",
            completed_objectives=["begin_adventure"],
            objective_catalog=["begin_adventure", "defeat_brock"],
            in_battle=False,
            party=[
                dict(
                    specimen_ref=member.specimen_ref,
                    species_id=member.observation.species_id,
                    level=member.observation.level,
                    experience=member.observation.experience,
                    hp=member.observation.hp,
                    max_hp=member.observation.max_hp,
                    status="healthy",
                    moves=[[33, 35]],
                )
            ],
        ),
        cash=3000,
        bag=[[4, 5]],
        preparation=asdict(plan),
        battle=None,
        spent=dict(decisions=10, actions=500, frames=40000, seconds=12.5, heals=1, cash_debits=200),
        grants_new_budget=False,
        fit_allowed=False,
        search_memory=mem.private_dict(),
    )


def test_step_search_memory_dict_unwraps_step_envelopes_and_validates():
    mem = GoalSearchMemory()
    mem.record("wild:route22", "b" * 64, exhausted=False, actions=8, frames=240)
    mem.observe_movement_endpoint("c" * 64, "d" * 64)
    private = mem.private_dict()
    state_sha = sha256(b"step-before").hexdigest()

    assert step_search_memory_dict(None) is None
    assert step_search_memory_dict(private) == private

    step_envelope = dict(
        state_sha256=state_sha,
        objective_sha256="b" * 64,
        objectives_by_binding={"b1": "b" * 64},
        memory=private,
    )
    assert step_search_memory_dict(step_envelope, state_sha256=state_sha) == private

    with pytest.raises(ValueError, match="state_sha256 differs"):
        step_search_memory_dict(step_envelope, state_sha256="e" * 64)

    with pytest.raises(ValueError, match="inner memory mapping"):
        step_search_memory_dict({"state_sha256": state_sha})


def test_build_step_diagnostic_checkpoint_passes_authenticate_parent_and_merges_movement(tmp_path):
    parent_ctx = _sample_parent_context()
    state_bytes = b"dojo-step-012-before-state"
    state_sha = sha256(state_bytes).hexdigest()

    mem_search = GoalSearchMemory()
    mem_search.record("wild:route22", "b" * 64, exhausted=True, actions=25, frames=800)

    mem_move = GoalSearchMemory()
    mem_move.record("wild:route22", "b" * 64, exhausted=True, actions=25, frames=800)
    mem_move.observe_movement_endpoint("c" * 64, "d" * 64)
    mem_move.record_movement_return(state_sha, "c" * 64, "d" * 64)

    before_snapshot = dict(
        state_sha256=state_sha,
        facts=dict(
            cash=22912,
            battle_state=0,
            input_ready=True,
            diagnostics=dict(bag_items=[[1, 1], [3, 8]]),
            player_lesson=dict(
                schema="pokemon.red.player-lesson-snapshot.v1",
                completed_objectives=["begin_adventure", "defeat_brock"],
                objective_catalog=["begin_adventure", "defeat_brock"],
                in_battle=False,
                party=parent_ctx["lesson"]["party"],
            ),
        ),
    )
    spent = dict(
        decisions=1920,
        actions=903196,
        frames=71628435,
        seconds=21752.25,
        heals=1138,
        cash_debits=77188,
    )

    context_doc, result_doc = build_step_diagnostic_checkpoint(
        parent_ctx,
        state_bytes=state_bytes,
        before_snapshot=before_snapshot,
        spent=spent,
        step_search_memory=dict(
            state_sha256=state_sha,
            objective_sha256="b" * 64,
            objectives_by_binding={},
            memory=mem_search.private_dict(),
        ),
        step_movement_memory=dict(
            schema="pokemon.red.movement-recurrence-observation.v1",
            state_sha256=state_sha,
            memory=mem_move.private_dict(),
        ),
    )

    assert result_doc["released"] is True
    assert checkpoint_quiescent(result_doc)
    assert result_doc["context_sha256"] == canonical_sha256(context_doc)
    assert context_doc["search_memory"]["schema"] == "pokemon.core.private-search-memory.v1"
    restored_mem = GoalSearchMemory.from_private_dict(context_doc["search_memory"])
    assert restored_mem.movement_endpoint_seen("c" * 64, "d" * 64)
    assert context_doc["search_memory"]["movement_returns"] == mem_move.private_dict()["movement_returns"]

    fixture = tmp_path / "saved-preaction-fixture"
    fixture.mkdir()
    (fixture / "terminal.state").write_bytes(state_bytes)
    (fixture / "CONTEXT.json").write_text(json.dumps(context_doc, indent=2) + "\n")
    result_doc["context_sha256"] = sha256((fixture / "CONTEXT.json").read_bytes()).hexdigest()
    (fixture / "RESULT.json").write_text(json.dumps(result_doc, indent=2) + "\n")

    authenticated = driver.authenticate_parent(
        fixture, lambda p: sha256(p.read_bytes()).hexdigest()
    )
    assert authenticated == json.loads(json.dumps(context_doc))
