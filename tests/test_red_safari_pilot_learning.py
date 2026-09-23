import hashlib
import json
import shutil
from dataclasses import asdict

import pytest
from test_goal_resource_quote import _supply_model

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_safari_acquisition import RedSafariZoneOffer, select_red_safari_area
from pokemon_red_completion.red_safari_pilot_learning import (
    SCHEMA,
    SCHEMA_V2,
    pilot_menu,
    pilot_outcome,
    read_episode,
    reward_contract,
)


def snapshots():
    before = dict(registered=["starter"], target_registered=["starter"],
                  specimens=[["starter", 1]], money=3000, battle=0, ready=True,
                  party_species=[177], party_hp=[20], free_party_slots=5, balls=0, steps=0)
    after = dict(before, registered=["capture", "starter"],
                 target_registered=["capture", "starter"],
                 specimens=[["capture", 1], ["starter", 1]],
                 party_species=[177, 18], party_hp=[20, 70], free_party_slots=4,
                 money=2500, balls=29, steps=450)
    return before, after


def test_outcome_reconstructs_novelty_and_cost_without_economy_label():
    before, after = snapshots()
    row = pilot_outcome(before, after, actions=20, frames=200, captures=1)
    assert row.verified_success and row.completion_gain == 1 / 124
    assert row.resource_cost == 1 / 30
    assert row.economy is None


def test_v2_units_match_registered_training_without_loosening_runtime_ceiling():
    before, after = snapshots()
    old = pilot_outcome(before, after, actions=300, frames=30000, captures=1)
    new = pilot_outcome(before, after, actions=300, frames=30000, captures=1, schema=SCHEMA_V2)
    assert old.action_cost == old.frame_cost == 0.1
    assert new.action_cost == new.frame_cost == 0.01
    assert old.resource_cost == new.resource_cost
    assert new.economy is None
    with pytest.raises(ValueError):
        pilot_outcome(before, after, actions=3001, frames=30000, captures=1, schema=SCHEMA_V2)


def test_unknown_reward_schema_rejected():
    with pytest.raises(ValueError, match="schema"):
        reward_contract("invented")


@pytest.mark.parametrize("changes", [
    {"money": 3000}, {"battle": 1}, {"ready": False}, {"balls": 31},
    {"steps": 501}, {"specimens": [["capture", 1]]}, {"registered": ["capture"]},
    {"party_hp": [19, 70]}, {"party_species": [18, 177]},
])
def test_outcome_rejects_unverified_or_changed_evidence(changes):
    before, after = snapshots()
    with pytest.raises(ValueError):
        pilot_outcome(before, dict(after, **changes), actions=20, frames=200, captures=1)


def fixture(tmp_path, partition="train", schema=SCHEMA):
    model = _supply_model()
    offers = (RedSafariZoneOffer("wild:SafariZoneCenter:grass", 220, ((25, 111),) * 10, (111,)),
              RedSafariZoneOffer("wild:SafariZoneNorth:grass", 218, ((25, 30),) * 10, (30,)))
    before, after = snapshots()
    menu = pilot_menu(before, offers, (10, 20))
    choice = select_red_safari_area(model, menu, offers, seed=12)
    after["map"] = choice.selected_offer.map_id
    plan = dict(schema=schema, partition=partition, source_state_sha256="b" * 64,
                behavior_model_sha256=model.model_sha256, seed=12,
                teacher_assistance="isolated_native_gate_source_only", promotion_eligible=False)
    if schema == SCHEMA_V2:
        plan.update(teacher_assistance="isolated_native_gate_context_only",
                    reward_contract=reward_contract(schema), maximum_actions=3000,
                    maximum_frames=300000)
    selection = dict(choice=choice.public_dict(), menu=menu.policy_dict(),
                     offers=[asdict(o) for o in offers], route_steps=[10, 20],
                     controller_actions_before_commit=0)
    result = dict(schema=schema, status="settled", plan_sha256=canonical_sha256(plan),
                  selection_sha256=canonical_sha256(selection),
                  terminal_state_sha256=hashlib.sha256(b"terminal").hexdigest(),
                  economy_label_eligible=False, actions=1, frames=50,
                  execution=dict(captures=1, admission=dict(status="ok", single_admission=True)))
    for name, value in [("plan", plan), ("selection", selection), ("before", before),
                        ("after", after), ("result", result)]:
        (tmp_path / (name + ".json")).write_text(json.dumps(value))
    (tmp_path / "terminal.state").write_bytes(b"terminal")
    trace = dict(ordinal=1, before_frame=0, after_frame=50, error=None,
                 selection_sha256=result["selection_sha256"])
    (tmp_path / "actions.jsonl").write_text(json.dumps(trace) + "\n")
    return model


def seal(tmp_path):
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()
             if p.name != "manifest.json"}
    schema = json.loads((tmp_path / "plan.json").read_text())["schema"]
    payload = json.dumps(dict(schema=schema, files=files)).encode()
    (tmp_path / "manifest.json").write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def read(tmp_path, model, digest, **changes):
    args = dict(expected_manifest_sha256=digest, behavior_model=model,
                expected_partition="train", expected_source_sha256="b" * 64)
    args.update(changes)
    return read_episode(tmp_path, **args)


def test_typed_episode_roundtrip(tmp_path):
    model = fixture(tmp_path)
    row = read(tmp_path, model, seal(tmp_path))
    assert row.partition == "train" and row.outcome.verified_success
    assert row.outcome.economy is None


def test_v2_typed_episode_roundtrip(tmp_path):
    model = fixture(tmp_path, schema=SCHEMA_V2)
    row = read(tmp_path, model, seal(tmp_path))
    assert row.outcome.action_cost == 1 / 30000
    assert row.outcome.frame_cost == 50 / 3000000


@pytest.mark.parametrize("field,value", [
    ("reward_contract", "registered-novelty-with-safari-consumables-v1"),
    ("maximum_actions", 30000), ("maximum_frames", 3000000),
])
def test_v2_rejects_resealed_unit_or_execution_drift(tmp_path, field, value):
    model = fixture(tmp_path, schema=SCHEMA_V2)
    plan = json.loads((tmp_path / "plan.json").read_text())
    plan[field] = value
    result = json.loads((tmp_path / "result.json").read_text())
    result["plan_sha256"] = canonical_sha256(plan)
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="reward units"):
        read(tmp_path, model, seal(tmp_path))


def test_development_cannot_be_relabelled_train(tmp_path):
    model = fixture(tmp_path, "development")
    with pytest.raises(ValueError, match="scope"):
        read(tmp_path, model, seal(tmp_path))


@pytest.mark.parametrize("file,key,value", [
    ("after", "map", 999), ("after", "money", 3000),
    ("selection", "controller_actions_before_commit", 1),
    ("result", "frames", 51), ("result", "economy_label_eligible", True),
    ("plan", "promotion_eligible", True), ("plan", "source_state_sha256", "c" * 64),
])
def test_rejects_inconsistent_resealed_artifacts(tmp_path, file, key, value):
    model = fixture(tmp_path)
    path = tmp_path / (file + ".json")
    doc = json.loads(path.read_text())
    doc[key] = value
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        read(tmp_path, model, seal(tmp_path))


def test_rejects_artifact_mutation(tmp_path):
    model = fixture(tmp_path)
    digest = seal(tmp_path)
    (tmp_path / "terminal.state").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest"):
        read(tmp_path, model, digest)


def test_retains_censored_failure_without_target(tmp_path):
    model = fixture(tmp_path)
    path = tmp_path / "result.json"
    doc = json.loads(path.read_text())
    doc.update(status="censored", error="interrupted")
    path.write_text(json.dumps(doc))
    assert read(tmp_path, model, seal(tmp_path)) is None


def recovery_fixture(tmp_path):
    parent, recovered = tmp_path / "original", tmp_path / "recovered"
    parent.mkdir()
    model = fixture(parent)
    result = json.loads((parent / "result.json").read_text())
    result.update(status="censored", error="search cap")
    (parent / "result.json").write_text(json.dumps(result))
    parent_digest = seal(parent)
    shutil.copytree(parent, recovered)
    trace = (parent / "actions.jsonl").read_bytes()
    row = json.loads(trace)
    row.update(ordinal=2, before_frame=50, after_frame=100)
    (recovered / "actions.jsonl").write_bytes(trace + json.dumps(row).encode() + b"\n")
    result.update(status="settled", actions=2, frames=100)
    (recovered / "result.json").write_text(json.dumps(result))
    recovery = dict(kind="exact_selected_goal_continuation", model_queries=0,
                    additional_admissions=0, selection_sha256=result["selection_sha256"],
                    original_plan_sha256=result["plan_sha256"], original_actions=1,
                    original_frames=50, original_episode_id="original",
                    original_manifest_sha256=parent_digest,
                    original_terminal_sha256=result["terminal_state_sha256"],
                    original_trace_sha256=hashlib.sha256(trace).hexdigest())
    (recovered / "recovery.json").write_text(json.dumps(recovery))
    return model, parent, recovered


def test_exact_goal_recovery_retains_parent_and_all_costs(tmp_path):
    model, parent, recovered = recovery_fixture(tmp_path)
    row = read(recovered, model, seal(recovered))
    assert row.outcome.action_cost == 2 / 3000
    assert row.outcome.frame_cost == 100 / 300000
    assert read(parent, model, seal(parent)) is None


@pytest.mark.parametrize("key,value", [
    ("model_queries", 1), ("additional_admissions", 1),
    ("original_episode_id", "../original"), ("original_episode_id", "recovered"),
    ("original_terminal_sha256", "a" * 64), ("original_trace_sha256", "a" * 64),
    ("original_frames", 49), ("original_manifest_sha256", "a" * 64),
])
def test_recovery_rejects_changed_origin_or_unaccounted_choice(tmp_path, key, value):
    model, _, recovered = recovery_fixture(tmp_path)
    path = recovered / "recovery.json"
    recovery = json.loads(path.read_text())
    recovery[key] = value
    path.write_text(json.dumps(recovery))
    with pytest.raises(ValueError):
        read(recovered, model, seal(recovered))


def test_recovery_rejects_rewritten_trace_prefix(tmp_path):
    model, _, recovered = recovery_fixture(tmp_path)
    path = recovered / "actions.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[0]["before_frame"] = 0.0  # same numeric chain, different retained bytes
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    with pytest.raises(ValueError, match="prefix"):
        read(recovered, model, seal(recovered))
