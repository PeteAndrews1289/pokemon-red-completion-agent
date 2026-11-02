import copy
import hashlib
import json

import pytest

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.red_post_battle_strategy import red_battle_aftermath


def episode():
    state = {
        "party_hp": [100],
        "party_max_hp": [100],
        "party_levels": [40],
        "party_pp": [[2, 0, 0, 0]],
        "opponent_party_position": 0,
        "opponent_hp": 2,
    }
    after = {**state, "party_hp": [0], "party_pp": [[1, 0, 0, 0]]}
    return {
        "schema": "pokemon.red.trainer-practice-model-episode.v4",
        "decision_count": 1,
        "battle_won": False,
        "stop_reason": "party_defeated",
        "action_counts": {"attack": 1},
        "metrics": {"party_pp_spent": 1, "opponent_faints": 0, "move_suppressed_or_failed": 0},
        "decisions": [
            {
                "decision_index": 1,
                "kind": "attack",
                "state_before": state,
                "state_after": after,
                "observation": {
                    "features": {
                        "battle": {
                            "active": True,
                            "kind": "trainer",
                            "opponent_party_count": 2,
                            "opponent_remaining_count": 2,
                            "opponent_level": 50,
                            "opponent_max_hp": 200,
                            "opponent_species_ref": "private-enemy",
                        },
                        "party": {"count": 1, "active_index": 0},
                        "world": {"area_ref": "private-map"},
                    }
                },
                "outcome": {"move_executed": True, "opponent_fainted": False},
            }
        ],
    }


def project(ep):
    payload = json.dumps(ep).encode()
    return red_battle_aftermath(payload, expected_sha256=hashlib.sha256(payload).hexdigest())


def test_loss_projects_only_observed_opponent_and_terminal():
    r = project(episode())
    assert r.result is BattleResult.LOST and r.opponent_levels == (50,)
    assert r.opponent_count == 2 and r.opponents_defeated == 0
    assert r.pp_spent_fraction == 0.5 and r.last_opponent_hp_fraction == 0.01
    assert "private" not in str(r)


def initial_unobserved_trainer_switch():
    ep = episode()
    row = ep["decisions"][0]
    for name in ("state_before", "state_after"):
        row[name].update(
            party_hp=[0, 100],
            party_max_hp=[100, 100],
            party_levels=[40, 30],
            party_pp=[[2, 0, 0, 0], [2, 0, 0, 0]],
        )
    row["state_before"]["opponent_party_position"] = 255
    row["state_after"]["opponent_party_position"] = 0
    row["observation"]["features"]["party"]["count"] = 2
    row.update(
        kind="forced_switch",
        outcome=None,
        referee_opponent_roster_hp_before=[200, 200],
        referee_opponent_roster_hp_after=[200, 200],
        opponent_faints=0,
    )
    ep.update(action_counts={"forced_switch": 1}, stop_reason="decision_cap")
    ep["metrics"]["party_pp_spent"] = 0
    return ep


def test_initial_forced_switch_does_not_invent_stale_opponent_level():
    ep = initial_unobserved_trainer_switch()
    # No actual foe has been observed yet: keep the history coverage guard.
    with pytest.raises(ValueError, match="observed level coverage required"):
        project(ep)
    next_row = copy.deepcopy(ep["decisions"][0])
    next_row.update(
        decision_index=2, kind="attack", outcome={"move_executed": True, "opponent_fainted": False}
    )
    next_row["state_before"]["opponent_party_position"] = 0
    next_row["observation"]["features"]["party"]["active_index"] = 1
    next_row["observation"]["features"]["battle"]["opponent_level"] = 14
    ep["decisions"].append(next_row)
    ep.update(decision_count=2, action_counts={"forced_switch": 1, "attack": 1})
    assert project(ep).opponent_levels == (14,)


@pytest.mark.parametrize(
    "mutation", ["attack", "voluntary", "healthy", "missing_proof", "invalid_after", "not_initial"]
)
def test_stale_position_exception_requires_initial_fainted_forced_switch_proof(mutation):
    ep = initial_unobserved_trainer_switch()
    row = ep["decisions"][0]
    if mutation == "attack":
        row.update(kind="attack", outcome={"move_executed": True, "opponent_fainted": False})
    elif mutation == "voluntary":
        row["kind"] = "voluntary_switch"
    elif mutation == "healthy":
        row["state_before"]["party_hp"][0] = 1
    elif mutation == "missing_proof":
        for name in (
            "referee_opponent_roster_hp_before",
            "referee_opponent_roster_hp_after",
            "opponent_faints",
        ):
            del row[name]
    elif mutation == "invalid_after":
        row["state_after"]["opponent_party_position"] = 255
    else:
        first = copy.deepcopy(row)
        first["state_before"]["opponent_party_position"] = 0
        first["state_before"]["party_hp"][0] = 1
        row["decision_index"] = 2
        ep["decisions"].insert(0, first)
        ep["decision_count"] = 2
    with pytest.raises(ValueError, match="invalid active opponent position"):
        project(ep)


def test_trainer_ai_switch_uses_authenticated_roster_faint_not_stale_active_foe():
    ep = episode()
    row = ep["decisions"][0]
    row.update(
        referee_opponent_roster_hp_before=[100, 150],
        referee_opponent_roster_hp_after=[100, 0],
        opponent_faints=1,
    )
    # The attacked foe differs from the pre-turn active one. Keep the original
    # selected-turn outcome rather than rewriting it to agree with the metric.
    assert row["outcome"]["opponent_fainted"] is False
    ep["metrics"]["opponent_faints"] = 1
    result = project(ep)
    assert result.opponents_defeated == 1 and result.opponent_count == 2
    assert "150" not in str(result)  # no referee roster HP in actor features


@pytest.mark.parametrize(
    "change",
    [
        {"opponent_faints": True},
        {"opponent_faints": 0},
        {"referee_opponent_roster_hp_after": [100]},
        {"referee_opponent_roster_hp_after": [100, -1]},
        {"referee_opponent_roster_hp_before": [100, 0]},
        {"referee_opponent_roster_hp_before": [True, 150]},
    ],
)
def test_invalid_referee_roster_faint_proof_is_not_metric_fallback(change):
    ep = episode()
    row = ep["decisions"][0]
    row.update(
        referee_opponent_roster_hp_before=[100, 150],
        referee_opponent_roster_hp_after=[100, 0],
        opponent_faints=1,
    )
    row.update(change)
    ep["metrics"]["opponent_faints"] = 1
    with pytest.raises(ValueError):
        project(ep)


def test_partial_roster_proof_cannot_be_used_as_unverified_faint_count():
    ep = episode()
    ep["decisions"][0]["opponent_faints"] = 1
    with pytest.raises(ValueError, match="incomplete opponent roster"):
        project(ep)


def test_verified_roster_knockouts_do_not_invent_unobserved_opponent_levels():
    ep = episode()
    ep.update(battle_won=True, stop_reason="battle_won")
    row = ep["decisions"][0]
    row["state_after"]["party_hp"] = [100]
    row.update(
        referee_opponent_roster_hp_before=[100, 150],
        referee_opponent_roster_hp_after=[0, 0],
        opponent_faints=2,
    )
    ep["metrics"]["opponent_faints"] = 2
    result = project(ep)
    assert result.result is BattleResult.WON and result.opponents_defeated == 2
    assert result.opponent_levels == (50,) and result.opponent_count == 2


def test_native_explicit_zero_action_counts_match_older_sparse_counts():
    ep = episode()
    before = project(ep)
    ep["action_counts"].update(voluntary_switch=0, forced_switch=0, switch_prompt=0)
    assert project(ep) == before


def resumed_struggle_episode():
    ep = episode()
    ep.update(battle_won=True, stop_reason="battle_won", action_counts={"forced_struggle": 1})
    ep["metrics"].update(party_pp_spent=0, opponent_faints=1)
    row = ep["decisions"][0]
    row.update(
        kind="forced_struggle",
        authority="forced_mechanic",
        policy_elapsed_ns=0,
        model_diagnostics={},
        legal_party_slots=[],
        referee_opponent_roster_hp_before=[0, 0, 2],
        referee_opponent_roster_hp_after=[0, 0, 0],
        opponent_faints=1,
        outcome=dict(
            schema="pokemon.red.forced-struggle-turn.v1", authority="forced_mechanic", pp_spent=0
        ),
    )
    row["observation"]["features"]["battle"].update(
        opponent_party_count=3, opponent_remaining_count=1
    )
    row["state_before"].update(party_pp=[[0, 0, 0, 0]], opponent_party_position=2)
    row["state_after"].update(
        party_hp=[50], party_pp=[[0, 0, 0, 0]], opponent_party_position=2, opponent_hp=0
    )
    return ep


def model_struggle_episode():
    ep = resumed_struggle_episode()
    ep["action_counts"] = {"model_struggle": 1}
    row = ep["decisions"][0]
    row.update(
        kind="model_struggle", authority="learner", policy_elapsed_ns=100,
        legal_party_slots=[2], semantic_action=BattleAction.struggle().public_dict(),
        model_diagnostics={
            "control_choice": "struggle",
            "struggle_proposal": {
                "schema": "pokemon.red.model-struggle-proposal.v1",
                "semantic_action": "pokemon.core:battle:struggle",
                "public_move_ref": "pokemon.red.gb.us.rev0:move:165",
                "source_visible_pp": [0, 0, 0, 0], "projection_pp": [0.0],
                "ordinary_move_legal_mask": [False], "observation_modified": False,
                "supplied_action": False,
            },
        },
    )
    row["outcome"].update(
        schema="pokemon.red.model-struggle-turn.v1", authority="learner",
        move_slot=None, departed_main_menu=True, cartridge_selection_observed=True,
        selected_move_ref="pokemon.red.gb.us.rev0:move:165", suppression=None,
        execution_claim="attempt_only",
    )
    row["observation"]["features"]["party"]["count"] = 2
    for name in ("state_before", "state_after"):
        row[name]["party_hp"] = row[name]["party_hp"] + [100]
        row[name]["party_max_hp"] = row[name]["party_max_hp"] + [100]
        row[name]["party_levels"] = row[name]["party_levels"] + [40]
        row[name]["party_pp"] = row[name]["party_pp"] + [[0, 0, 0, 0]]
    return ep


def test_model_struggle_projects_learned_execution_without_forced_attribution():
    result = project(model_struggle_episode())
    assert result.result is BattleResult.WON
    assert result.opponents_defeated == 3 and result.pp_spent_fraction == 0
    assert result.voluntary_switch_fraction == 0


@pytest.mark.parametrize("mutation", [
    "authority", "semantic", "positive_pp", "no_reserve", "reserve_list", "supplied",
    "projection_pp", "ordinary_mask", "selection", "roster", "latency",
])
def test_model_struggle_history_refuses_unproven_or_relabelled_execution(mutation):
    ep = model_struggle_episode()
    row = ep["decisions"][0]
    proposal = row["model_diagnostics"]["struggle_proposal"]
    if mutation == "authority":
        row["authority"] = "forced_mechanic"
    elif mutation == "semantic":
        row["semantic_action"] = BattleAction.move(1).public_dict()
    elif mutation == "positive_pp":
        row["state_before"]["party_pp"][0][0] = 1
    elif mutation == "no_reserve":
        row["state_before"]["party_hp"][1] = 0
    elif mutation == "reserve_list":
        row["legal_party_slots"] = []
    elif mutation == "supplied":
        proposal["supplied_action"] = True
    elif mutation == "projection_pp":
        proposal["projection_pp"] = [1.0]
    elif mutation == "ordinary_mask":
        proposal["ordinary_move_legal_mask"] = [True]
    elif mutation == "selection":
        row["outcome"]["cartridge_selection_observed"] = False
    elif mutation == "roster":
        for key in (
            "referee_opponent_roster_hp_before",
            "referee_opponent_roster_hp_after",
            "opponent_faints",
        ):
            del row[key]
    else:
        row["policy_elapsed_ns"] = True
    with pytest.raises(ValueError):
        project(ep)


def test_resumed_native_struggle_keeps_existing_faints_without_inventing_levels():
    result = project(resumed_struggle_episode())
    assert result.result is BattleResult.WON and result.opponents_defeated == 3
    assert result.opponent_count == 3 and result.opponent_levels == (50,)
    assert result.pp_spent_fraction == result.suppressed_attack_fraction == 0


@pytest.mark.parametrize(
    "change",
    [
        dict(authority="model"),
        dict(policy_elapsed_ns=1),
        dict(model_diagnostics={"learned": True}),
        dict(legal_party_slots=[1]),
        dict(outcome=dict(schema="invented", authority="forced_mechanic", pp_spent=0)),
    ],
)
def test_struggle_does_not_accept_model_authority_or_unknown_mechanics(change):
    ep = resumed_struggle_episode()
    ep["decisions"][0].update(change)
    with pytest.raises(ValueError, match="mechanical evidence"):
        project(ep)


def test_struggle_requires_zero_pp_last_survivor_and_roster_proof():
    for mutation in ("pp", "reserve", "roster"):
        ep = resumed_struggle_episode()
        row = ep["decisions"][0]
        if mutation == "pp":
            row["state_before"]["party_pp"][0][0] = 1
        elif mutation == "reserve":
            row["observation"]["features"]["party"]["count"] = 2
            row["state_after"] = copy.deepcopy(row["state_after"])
            for state in (row["state_before"], row["state_after"]):
                for key in ("party_hp", "party_max_hp", "party_levels", "party_pp"):
                    state[key].append(copy.deepcopy(state[key][0]))
        else:
            for key in (
                "referee_opponent_roster_hp_before",
                "referee_opponent_roster_hp_after",
                "opponent_faints",
            ):
                del row[key]
        with pytest.raises(ValueError, match="mechanical evidence"):
            project(ep)


@pytest.mark.parametrize(
    "counts",
    [
        {"attack": True},
        {"attack": 1, "invented": 0},
        {"attack": 1, "forced_switch": -1},
        {"attack": 1, "forced_switch": 1},
    ],
)
def test_invalid_explicit_action_counts_still_reject(counts):
    ep = episode()
    ep["action_counts"] = counts
    with pytest.raises(ValueError, match="action counts"):
        project(ep)


def test_unresolved_not_relabelled_loss_or_success():
    ep = episode()
    ep["stop_reason"] = "decision_cap"
    assert project(ep).result is BattleResult.UNRESOLVED


def test_repeated_turns_do_not_multiply_opposition():
    ep = episode()
    row = copy.deepcopy(ep["decisions"][0])
    row["decision_index"] = 2
    ep["decisions"].append(row)
    ep["decision_count"] = 2
    ep["action_counts"]["attack"] = 2
    ep["metrics"]["party_pp_spent"] = 2
    assert project(ep).opponent_levels == (50,)


def test_different_next_opponent_max_hp_is_not_guessed():
    ep = episode()
    ep["decisions"][0]["state_after"]["opponent_party_position"] = 1
    assert project(ep).last_opponent_hp_fraction is None


def test_switching_opponent_deduplicates_actual_seen_slots_only():
    ep = episode()
    first = ep["decisions"][0]
    first["observation"]["features"]["battle"].update(
        opponent_party_count=3, opponent_remaining_count=3
    )
    second = copy.deepcopy(first)
    second["decision_index"] = 2
    second["state_before"]["opponent_party_position"] = 2
    second["state_after"]["opponent_party_position"] = 2
    second["observation"]["features"]["battle"]["opponent_level"] = 55
    ep["decisions"].append(second)
    ep["decision_count"] = ep["action_counts"]["attack"] = 2
    ep["metrics"]["party_pp_spent"] = 2
    result = project(ep)
    assert result.opponent_levels == (50, 55) and result.opponent_count == 3
    assert result.last_opponent_hp_fraction == 0.01
    assert "position" not in str(result)


def test_duplicate_species_levels_in_distinct_seen_slots_count_separately():
    ep = episode()
    second = copy.deepcopy(ep["decisions"][0])
    second["decision_index"] = 2
    second["state_before"]["opponent_party_position"] = 1
    second["state_after"]["opponent_party_position"] = 1
    ep["decisions"].append(second)
    ep["decision_count"] = ep["action_counts"]["attack"] = 2
    ep["metrics"]["party_pp_spent"] = 2
    assert project(ep).opponent_levels == (50, 50)


def test_identity_changes_do_not_change_features():
    ep = episode()
    other = copy.deepcopy(ep)
    other["decisions"][0]["observation"]["features"]["world"] = {"map": "different"}
    other["decisions"][0]["observation"]["features"]["battle"]["opponent_species_ref"] = (
        "other-title"
    )
    assert project(ep) == project(other)


def test_win_requires_all_opponents_defeated():
    ep = episode()
    ep["battle_won"] = True
    ep["stop_reason"] = "battle_exited"
    with pytest.raises(ValueError, match="victory"):
        project(ep)
    ep["decisions"][0]["observation"]["features"]["battle"]["opponent_party_count"] = 1
    ep["decisions"][0]["observation"]["features"]["battle"]["opponent_remaining_count"] = 1
    ep["decisions"][0]["outcome"]["opponent_fainted"] = True
    ep["metrics"]["opponent_faints"] = 1
    ep["decisions"][0]["state_after"]["party_hp"] = [50]
    ep["decisions"][0]["state_after"]["opponent_hp"] = 0
    assert project(ep).result is BattleResult.WON


def settled_final_trainer_knockout():
    ep = episode()
    ep.update(
        battle_won=True,
        stop_reason="battle_won",
        final_battle_state=0,
        final_enemy_roster_hp=[0, 0],
    )
    row = ep["decisions"][0]
    row["observation"]["features"]["battle"]["opponent_remaining_count"] = 1
    row["state_before"]["opponent_party_position"] = 1
    row["state_after"].update(opponent_party_position=1, opponent_hp=0, party_hp=[50])
    row.update(
        referee_opponent_roster_hp_before=[0, 2],
        referee_opponent_roster_hp_after=[0, 2],
        opponent_faints=0,
    )
    return ep


def test_final_native_settlement_adds_only_proven_last_trainer_knockout():
    ep = settled_final_trainer_knockout()
    result = project(ep)
    assert result.result is BattleResult.WON and result.opponents_defeated == 2
    assert result.opponent_levels == (50,)
    assert ep["metrics"]["opponent_faints"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "active",
        "boolean_exit",
        "living_enemy",
        "missing_roster",
        "short_roster",
        "boolean_hp",
        "wrong_member",
        "no_survivor",
    ],
)
def test_final_trainer_settlement_needs_concurrent_native_evidence(fault):
    ep = settled_final_trainer_knockout()
    row = ep["decisions"][0]
    if fault == "active":
        ep["final_battle_state"] = 2
    elif fault == "boolean_exit":
        ep["final_battle_state"] = False
    elif fault == "living_enemy":
        ep["final_enemy_roster_hp"] = [0, 1]
    elif fault == "missing_roster":
        del ep["final_enemy_roster_hp"]
    elif fault == "short_roster":
        ep["final_enemy_roster_hp"] = [0]
    elif fault == "boolean_hp":
        ep["final_enemy_roster_hp"] = [0, False]
    elif fault == "wrong_member":
        row["referee_opponent_roster_hp_before"] = [2, 0]
        row["referee_opponent_roster_hp_after"] = [2, 0]
    else:
        row["state_after"]["party_hp"] = [0]
    with pytest.raises(ValueError):
        project(ep)


@pytest.mark.parametrize(
    "field,value",
    [
        ("decision_count", True),
        ("decision_count", 2),
        ("schema", "unknown"),
        ("battle_won", 1),
        ("decisions", []),
        ("action_counts", {}),
    ],
)
def test_bad_episode_rejected(field, value):
    ep = episode()
    ep[field] = value
    with pytest.raises(ValueError):
        project(ep)


@pytest.mark.parametrize(
    "metric", ["party_pp_spent", "opponent_faints", "move_suppressed_or_failed"]
)
def test_metrics_must_match_decisions(metric):
    ep = episode()
    ep["metrics"][metric] += 1
    with pytest.raises(ValueError, match="metrics"):
        project(ep)


@pytest.mark.parametrize(
    "field,value",
    [
        ("opponent_remaining_count", 0),
        ("opponent_party_count", True),
        ("opponent_level", 101),
        ("active", False),
        ("kind", "invented"),
        ("opponent_max_hp", 0),
    ],
)
def test_malformed_enemy_evidence_rejected(field, value):
    ep = episode()
    ep["decisions"][0]["observation"]["features"]["battle"][field] = value
    with pytest.raises(ValueError):
        project(ep)


def test_conflicting_repeated_level_rejected():
    ep = episode()
    row = copy.deepcopy(ep["decisions"][0])
    row["decision_index"] = 2
    row["observation"]["features"]["battle"]["opponent_level"] = 51
    ep["decisions"].append(row)
    ep["decision_count"] = 2
    with pytest.raises(ValueError, match="conflicting"):
        project(ep)


def test_wild_history_uses_observed_single_opponent_not_stale_roster_ram():
    ep = episode()
    row = ep["decisions"][0]
    battle = row["observation"]["features"]["battle"]
    battle["kind"] = "wild"
    del battle["opponent_party_count"], battle["opponent_remaining_count"]
    row["state_before"]["opponent_party_position"] = 5
    row["state_after"]["opponent_party_position"] = None
    result = project(ep)
    assert result.opponent_count == 1 and result.opponent_levels == (50,)
    assert result.result is BattleResult.LOST
    assert result.last_opponent_hp_fraction == 0.01


def wild_switch_knockout():
    ep = episode()
    ep.update(
        battle_won=True,
        stop_reason="battle_won",
        final_battle_state=0,
        action_counts={"voluntary_switch": 1},
    )
    ep["metrics"]["party_pp_spent"] = 0
    row = ep["decisions"][0]
    row.update(kind="voluntary_switch", outcome=None)
    row["observation"]["features"]["battle"]["kind"] = "wild"
    row["state_after"].update(party_hp=[50], party_pp=[[2, 0, 0, 0]], opponent_hp=0)
    return ep


def trainer_switch_knockout(count=1):
    ep = wild_switch_knockout()
    battle = ep["decisions"][0]["observation"]["features"]["battle"]
    battle.update(kind="trainer", opponent_party_count=count, opponent_remaining_count=1)
    ep["final_enemy_roster_hp"] = [0] * count
    return ep


@pytest.mark.parametrize("count", [1, 3])
@pytest.mark.parametrize("position", [0, None])
def test_legacy_trainer_switch_knockout_uses_complete_native_terminal(count, position):
    ep = trainer_switch_knockout(count)
    ep["decisions"][0]["state_after"]["opponent_party_position"] = position
    result = project(ep)
    assert result.result is BattleResult.WON
    assert result.opponents_defeated == result.opponent_count == count
    assert result.opponent_levels == (50,)  # No unseen roster levels are invented.
    assert result.last_opponent_hp_fraction == 0
    assert ep["metrics"]["opponent_faints"] == 0


@pytest.mark.parametrize(
    "fault",
    ["missing_roster", "living_roster", "boolean_roster", "wrong_shape",
     "active", "boolean_exit", "living_enemy", "fainted_before", "changed_foe",
     "more_than_one_missing", "attack", "no_survivor", "metric",
     "boolean_hp", "missing_maximum", "boolean_maximum", "excess_before_hp"],
)
def test_legacy_trainer_switch_knockout_keeps_strict_victory_proof(fault):
    ep = trainer_switch_knockout()
    row = ep["decisions"][0]
    if fault == "missing_roster":
        del ep["final_enemy_roster_hp"]
    elif fault == "living_roster":
        ep["final_enemy_roster_hp"] = [1]
    elif fault == "boolean_roster":
        ep["final_enemy_roster_hp"] = [False]
    elif fault == "wrong_shape":
        ep["final_enemy_roster_hp"] = [0, 0]
    elif fault == "active":
        ep["final_battle_state"] = 2
    elif fault == "boolean_exit":
        ep["final_battle_state"] = False
    elif fault == "living_enemy":
        row["state_after"]["opponent_hp"] = 1
    elif fault == "fainted_before":
        row["state_before"]["opponent_hp"] = 0
    elif fault == "changed_foe":
        row["state_after"]["opponent_party_position"] = 1
    elif fault == "more_than_one_missing":
        row["observation"]["features"]["battle"].update(
            opponent_party_count=2, opponent_remaining_count=2
        )
        ep["final_enemy_roster_hp"] = [0, 0]
    elif fault == "attack":
        row["kind"] = "attack"
        ep["action_counts"] = {"attack": 1}
    elif fault == "no_survivor":
        row["state_after"]["party_hp"] = [0]
    elif fault == "metric":
        ep["metrics"]["opponent_faints"] = 1
    elif fault == "boolean_hp":
        row["state_after"]["opponent_hp"] = False
    elif fault in {"missing_maximum", "boolean_maximum", "excess_before_hp"}:
        row["state_after"]["opponent_party_position"] = None
        if fault == "excess_before_hp":
            row["state_before"]["opponent_hp"] = 201
        else:
            row["observation"]["features"]["battle"]["opponent_max_hp"] = (
                False if fault == "boolean_maximum" else 0
            )
    with pytest.raises(ValueError):
        project(ep)


def test_wild_switch_knockout_uses_native_exit_without_rewriting_attack_metrics():
    ep = wild_switch_knockout()
    result = project(ep)
    assert result.result is BattleResult.WON and result.opponents_defeated == 1
    assert ep["metrics"]["opponent_faints"] == 0
    assert result.last_opponent_hp_fraction == 0


@pytest.mark.parametrize(
    "fault",
    [
        "active",
        "boolean_exit",
        "living_enemy",
        "trainer",
        "fainted_before",
        "attack",
        "no_survivor",
    ],
)
def test_wild_switch_knockout_rejects_incomplete_or_contradictory_evidence(fault):
    ep = wild_switch_knockout()
    row = ep["decisions"][0]
    if fault == "active":
        ep["final_battle_state"] = 1
    elif fault == "boolean_exit":
        ep["final_battle_state"] = False
    elif fault == "living_enemy":
        row["state_after"]["opponent_hp"] = 1
    elif fault == "trainer":
        row["observation"]["features"]["battle"]["kind"] = "trainer"
    elif fault == "fainted_before":
        row["state_before"]["opponent_hp"] = 0
    elif fault == "attack":
        row["kind"] = "attack"
        ep["action_counts"] = {"attack": 1}
    else:
        row["state_after"]["party_hp"] = [0]
    with pytest.raises(ValueError):
        project(ep)


def test_wild_trainer_transition_inside_one_episode_rejected():
    ep = episode()
    row = copy.deepcopy(ep["decisions"][0])
    row["decision_index"] = 2
    row["observation"]["features"]["battle"]["kind"] = "wild"
    ep["decisions"].append(row)
    ep["decision_count"] = 2
    with pytest.raises(ValueError, match="battle kind changed"):
        project(ep)


def test_corrupted_or_unpinned_bytes_rejected():
    for digest in ("0" * 64, "bad", None):
        with pytest.raises(ValueError, match="authentication"):
            red_battle_aftermath(b"{}", expected_sha256=digest)


def test_missing_fields_fail_closed():
    ep = episode()
    del ep["decisions"][0]["state_after"]["party_pp"]
    with pytest.raises(ValueError, match="incomplete"):
        project(ep)
