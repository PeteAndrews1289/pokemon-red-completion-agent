"""New workloads retain historical TRAIN custody and strict native scope."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from pokemon_red_completion import captured_progress as capture_module
from pokemon_red_completion import goal_manager_protocol as protocol
from pokemon_red_completion import party_development_outcome_learning as learning
from pokemon_red_completion import red_teacher_venue as teacher


def setup_case(tmp_path, monkeypatch):
    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def write(name, value):
        p = tmp_path / name
        p.write_text(json.dumps(value))
        return p

    state = tmp_path / "source.state"
    state.write_bytes(b"original authenticated TRAIN state")
    envelope = write("source.json", {})
    registry = write("registry.json", {})
    prior = write("prior.json", {})
    pre = write(
        "pre.json",
        dict(passed=True, actions_executed=0, assignment_id="assignment", state_sha256=sha(state)),
    )
    proof = write(
        "auth.json",
        dict(
            schema="pokemon.authenticated-historical-goal-TRAIN-source.v1",
            passed=True,
            partition="train",
            checkpoint_id="train-source",
            root_lineage_id="train-root",
            registry_sha256=sha(registry),
            **{
                key: dict(path=str(p), sha256=sha(p))
                for key, p in [
                    ("source", state),
                    ("envelope", envelope),
                    ("registry", registry),
                    ("historical_preflight", pre),
                    ("prior_authentication", prior),
                ]
            },
        ),
    )
    assignment = SimpleNamespace(
        partition="train", root_lineage_id="train-root", assignment_id="assignment"
    )
    monkeypatch.setattr(
        protocol,
        "parse_goal_manager_registry",
        lambda _: SimpleNamespace(registry_sha256=sha(registry), assignment=lambda _: assignment),
    )
    capture = SimpleNamespace(checkpoint_id="train-source", state_sha256=sha(state))
    monkeypatch.setattr(capture_module, "load_captured_progress", lambda *a, **k: capture)
    model = SimpleNamespace(outcome_training_root_lineage_ids=(), outcome_training_state_sha256=())
    monkeypatch.setattr(learning, "load_party_development_outcome_model", lambda *a, **k: model)
    monkeypatch.setattr(
        learning, "canonical_party_development_outcome_model_sha256", lambda _: "a" * 64
    )
    plan = dict(
        schema=teacher.HIGH_LEVEL_SCHEMA,
        cutoff_utc=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        source_authentication=str(proof),
        source=str(state),
        source_envelope=str(envelope),
        source_sha256=sha(state),
        pins={str(p): sha(p) for p in [state, envelope, registry, prior, pre, proof]},
        venue_model_path="model",
        venue_model_file_sha256="b" * 64,
        venue_model_sha256="a" * 64,
        sources=[
            dict(
                declared_partition="train",
                execution_partition="train",
                assigned_lineage="train-root",
                state_sha256=sha(state),
                venue_mode="teacher",
                assigned_venue_index=1,
                fixture_level=49,
            )
        ],
        allow_direct_evolution=True,
        venue_symbols=[
            "ROUTE_11_TRAINING_VENUE",
            "DIGLETTS_CAVE_TRAINING_VENUE",
            "MANSION_TRAINING_VENUE",
        ],
        copy_back=False,
        campaign_writes=False,
        caps=dict(new_fits=0, emulators=1, state_loads=1, outer_seconds=540),
        native_limits=dict(seconds=360),
    )
    return plan, model, capture


def test_new_workload_authenticates_original_train_root_without_relabel(tmp_path, monkeypatch):
    plan, model, capture = setup_case(tmp_path, monkeypatch)
    observed, payload, proof = teacher.authenticate_venue_source(plan)
    assert observed is capture and payload == b"original authenticated TRAIN state"
    assert proof["partition"] == "train" and proof["independent_origin"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "consumed_root",
        "consumed_state",
        "level",
        "index",
        "mode",
        "source_sha",
        "unbound_proof",
        "load_cap",
        "copy_back",
    ],
)
def test_workload_rejects_unsafe_or_ineligible_declarations_before_emulator(
    tmp_path, monkeypatch, fault
):
    plan, model, capture = setup_case(tmp_path, monkeypatch)
    item = plan["sources"][0]
    if fault == "partition":
        item["execution_partition"] = "development"
    if fault == "consumed_root":
        model.outcome_training_root_lineage_ids = ("train-root",)
    if fault == "consumed_state":
        model.outcome_training_state_sha256 = (capture.state_sha256,)
    if fault == "level":
        item["fixture_level"] = 22
    if fault == "index":
        item["assigned_venue_index"] = True
    if fault == "mode":
        plan["allow_direct_evolution"] = False
    if fault == "source_sha":
        plan["source_sha256"] = "f" * 64
    if fault == "unbound_proof":
        plan["pins"].pop(plan["source_authentication"])
    if fault == "load_cap":
        plan["caps"]["state_loads"] = 2
    if fault == "copy_back":
        plan["copy_back"] = True
    with pytest.raises(ValueError):
        teacher.authenticate_venue_source(plan)


@pytest.mark.parametrize("fault", [None, "role", "pin", "candidate", "admission", "unaccepted"])
def test_related_validation_is_explicit_pinned_and_cannot_admit(tmp_path, monkeypatch, fault):
    plan, model, capture = setup_case(tmp_path, monkeypatch)
    model.outcome_training_root_lineage_ids = ("train-root",)
    plan["validation_role"] = "exposed-TRAIN-component-no-admission"
    plan["party_venue_fit_eligible"] = False
    plan["sources"][0]["venue_mode"] = "model"
    fit = tmp_path / "fit.json"
    fit.write_text(
        json.dumps(
            dict(
                passed=True,
                accepted=fault != "unaccepted",
                model_sha256="a" * 64,
                model=dict(sha256="b" * 64),
            )
        )
    )
    plan["validation_fit_result"] = str(fit)
    plan["pins"][str(fit)] = hashlib.sha256(fit.read_bytes()).hexdigest()
    if fault == "role":
        plan["validation_role"] = "independent-dev"
    if fault == "pin":
        plan["pins"].pop(str(fit))
    if fault == "candidate":
        plan["venue_model_file_sha256"] = "c" * 64
    if fault == "admission":
        plan["party_venue_fit_eligible"] = True
    if fault is None:
        assert teacher.authenticate_venue_source(plan)[0] is capture
    else:
        with pytest.raises(ValueError):
            teacher.authenticate_venue_source(plan)


@pytest.mark.parametrize("fault", [None, "not_validation", "level", "unknown"])
def test_second_trainee_is_validation_only(tmp_path, monkeypatch, fault):
    plan, model, capture = setup_case(tmp_path, monkeypatch)
    item = plan["sources"][0]
    item.update(trainee_profile="dragonair54_to55", fixture_level=54)
    fit = tmp_path / "fit.json"
    fit.write_text(
        json.dumps(
            dict(passed=True, accepted=True, model_sha256="a" * 64, model=dict(sha256="b" * 64))
        )
    )
    plan.update(
        validation_role="exposed-TRAIN-component-no-admission",
        validation_fit_result=str(fit),
        party_venue_fit_eligible=False,
    )
    plan["pins"][str(fit)] = hashlib.sha256(fit.read_bytes()).hexdigest()
    if fault == "not_validation":
        plan.pop("validation_role")
    if fault == "level":
        item["fixture_level"] = 49
    if fault == "unknown":
        item["trainee_profile"] = "unreviewed"
    if fault is None:
        assert teacher.authenticate_venue_source(plan)[0] is capture
    else:
        with pytest.raises(ValueError):
            teacher.authenticate_venue_source(plan)
