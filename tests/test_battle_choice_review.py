import copy
import hashlib
import json

import pytest
from test_battle_matchups import _member

from pokemon_red_completion.battle_choice_review import review_battle_choices
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_species_ref


def episode(kind="voluntary_switch"):
    members = [
        _member(28, level=60, hp=80, moves=((57, 10),)),
        _member(132, level=55, hp=90, moves=((29, 15), (156, 5))),
        _member(104, level=55, hp=20, moves=((84, 20),)),
    ]
    for i, member in enumerate(members):
        member["party_index"] = i
    party = dict(
        count=3,
        active_index=0,
        members=members,
        lead={k: v for k, v in members[0].items() if k != "party_index"},
    )
    decision = dict(
        decision_index=1,
        kind=kind,
        party_slot=2,
        legal_party_slots=[2, 3],
        move_slot=1,
        legal_move_slots=[1],
        model_diagnostics={"control_probabilities": [0.49, 0.51]},
        observation={
            "features": {
                "party": party,
                "battle": {
                    "opponent_species_ref": pokemon_red_species_ref(14),
                    "opponent_level": 56,
                    "opponent_hp": 2,
                    "opponent_max_hp": 142,
                },
            }
        },
    )
    return dict(
        schema="pokemon.red.trainer-practice-model-episode.v4",
        decision_count=1,
        decisions=[decision],
    )


def review(ep):
    data = json.dumps(ep).encode()
    return review_battle_choices(
        data, expected_sha256=hashlib.sha256(data).hexdigest(), catalog=RED_BATTLE_CATALOG
    )


def test_cli_never_overwrites_episode_or_prior_report(tmp_path, monkeypatch, capsys):
    from review_battle_choices import main

    source = tmp_path / "episode.json"
    source.write_text(json.dumps(episode()))
    original = source.read_bytes()
    output = tmp_path / "review.json"
    args = [
        "review",
        str(source),
        "--sha256",
        hashlib.sha256(original).hexdigest(),
        "--output",
        str(output),
    ]
    monkeypatch.setattr("sys.argv", args)
    main()
    assert json.loads(capsys.readouterr().out)["decision_count"] == 1
    recorded = output.read_bytes()
    with pytest.raises(FileExistsError):
        main()
    assert output.read_bytes() == recorded and source.read_bytes() == original
    monkeypatch.setattr("sys.argv", args[:-1] + [str(source)])
    with pytest.raises(FileExistsError):
        main()
    assert source.read_bytes() == original


def test_flags_observable_switch_risk_without_claiming_counterfactual_or_changing_input():
    ep = episode()
    original = copy.deepcopy(ep)
    report = review(ep)
    assert ep == original
    row = report["decisions"][0]
    assert row["zero_power_choice_with_covered_alternative"]
    assert row["other_coverage_slots"] == [1, 3]
    assert row["opponent_hp"] == 2
    assert report["counts"]["control_margins_within_0_05"] == 1
    assert not report["policy_changed"] and not report["training_labels"]
    assert not report["counterfactual_tested"]
    assert "species" not in json.dumps(report) and "move_ref" not in json.dumps(report)


@pytest.mark.parametrize("kind", ["forced_switch", "switch_prompt", "voluntary_switch"])
def test_denominator_and_alternatives_follow_legal_action_kind(kind):
    ep = episode(kind)
    ep["decisions"][0]["legal_party_slots"] = [2]
    row = review(ep)["decisions"][0]
    assert row["zero_power_choice_with_covered_alternative"] == (kind != "forced_switch")


def test_declined_prompt_is_staying_not_a_missing_switch_target():
    ep = episode("switch_prompt")
    ep["decisions"][0]["party_slot"] = None
    row = review(ep)["decisions"][0]
    assert row["stayed"] and row["selected_party_slot"] == 1
    ep["decisions"][0]["kind"] = "forced_switch"
    with pytest.raises(ValueError):
        review(ep)


def test_permutation_follows_member_not_slot():
    ep = episode()
    decision = ep["decisions"][0]
    party = decision["observation"]["features"]["party"]
    party["members"][1], party["members"][2] = party["members"][2], party["members"][1]
    for i, member in enumerate(party["members"]):
        member["party_index"] = i
    decision["party_slot"] = 3
    row = review(ep)["decisions"][0]
    assert row["zero_power_choice_with_covered_alternative"] and row["selected_party_slot"] == 3


def test_other_species_with_same_moves_and_immunity_has_same_risk():
    ep = episode()
    ep["decisions"][0]["observation"]["features"]["party"]["members"][1]["species_ref"] = (
        pokemon_red_species_ref(177)
    )
    assert review(ep)["decisions"][0]["zero_power_choice_with_covered_alternative"]


def test_low_hp_switch_is_descriptive_not_rejected():
    ep = episode()
    ep["decisions"][0]["party_slot"] = 3
    report = review(ep)
    assert report["counts"]["switch_choices_below_quarter_hp"] == 1
    assert not report["decisions"][0]["zero_power_choice_with_covered_alternative"]


@pytest.mark.parametrize(
    "move,status,immune", [(29, None, True), (156, None, False), (57, "sleep", False)]
)
def test_move_slot_is_one_based_and_status_or_sleep_is_not_called_immunity(move, status, immune):
    ep = episode("attack")
    party = ep["decisions"][0]["observation"]["features"]["party"]
    member = _member(132, level=55, hp=90, moves=((move, 5),))
    member["status"] = status
    party["members"][0] = dict(member, party_index=0)
    party["lead"] = member
    row = review(ep)["decisions"][0]
    assert row["type_immune_attack"] == immune
    assert row["selected_while_asleep"] == (status == "sleep")
    assert row["selected_status_move"] == (move == 156)


@pytest.mark.parametrize(
    "fault",
    [
        "count",
        "order",
        "kind",
        "digest",
        "fainted",
        "illegal",
        "duplicate",
        "lead",
        "probability",
        "nan",
        "zero_pp",
        "bad_slot",
        "active_candidate",
        "boolean_move_mask",
        "duplicate_move_mask",
        "malformed_switch_mask",
    ],
)
def test_malformed_or_unbound_observations_refuse(fault):
    ep = episode(
        "attack"
        if fault in {"zero_pp", "bad_slot", "boolean_move_mask", "duplicate_move_mask"}
        else "voluntary_switch"
    )
    d = ep["decisions"][0]
    party = d["observation"]["features"]["party"]
    if fault == "count":
        ep["decision_count"] = 2
    elif fault == "order":
        d["decision_index"] = 2
    elif fault == "kind":
        d["kind"] = "teacher"
    elif fault == "fainted":
        party["members"][1]["hp"] = 0
    elif fault == "illegal":
        d["party_slot"] = 1
    elif fault == "duplicate":
        d["legal_party_slots"] = [2, 2]
    elif fault == "lead":
        party["lead"] = {}
    elif fault == "probability":
        d["model_diagnostics"]["control_probabilities"] = [0.8, 0.8]
    elif fault == "nan":
        d["model_diagnostics"]["control_probabilities"] = [float("nan"), 0.5]
    elif fault == "zero_pp":
        party["lead"]["moves"][0]["pp"] = 0
    elif fault == "bad_slot":
        d["move_slot"] = True
    elif fault == "active_candidate":
        d["legal_party_slots"] = [1, 2, 3]
        d["party_slot"] = 1
    elif fault == "boolean_move_mask":
        d["legal_move_slots"] = [True]
    elif fault == "duplicate_move_mask":
        d["legal_move_slots"] = [1, 1]
    elif fault == "malformed_switch_mask":
        d["legal_party_slots"] = [[], 2]
    with pytest.raises(ValueError):
        if fault == "digest":
            review_battle_choices(
                json.dumps(ep).encode(), expected_sha256="0" * 64, catalog=RED_BATTLE_CATALOG
            )
        else:
            review(ep)
