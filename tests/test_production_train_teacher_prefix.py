"""Exact registered TRAIN source custody; no guest, ROM, inference or fitting."""

import ast
import json
import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_production_train_admission import scope_and_actor

from pokemon_red_completion.red_production_train_admission import ProductionTrainAdmission
from pokemon_red_completion.red_production_train_source import (
    SOURCE049_ARTIFACT_PINS,
    SOURCE049_GROUP,
    VerifiedTeacherPrefixTrainSource,
    authenticate_teacher_prefix_train_source,
)


@pytest.fixture(scope="module")
def artifacts():
    path = os.environ.get("POKEMON_SOURCE049_ARTIFACT_PATHS")
    if path is None:
        pytest.skip("private immutable teacher-prefix artifacts not supplied; zero guest required")
    return {k: Path(v).read_bytes() for k, v in json.loads(Path(path).read_bytes()).items()}


@pytest.fixture
def admitted_source(artifacts):
    proof = authenticate_teacher_prefix_train_source(artifacts=artifacts, source_commit="a" * 40)
    admission = ProductionTrainAdmission(
        proof.source_state_sha256,
        proof.source_origin_sha256,
        proof.source_commit,
        "b" * 64,
        sha256(artifacts["prefix_envelope"]).hexdigest(),
        sha256(proof.progress_bytes()).hexdigest(),
        derived_source_proof=proof,
    )
    plan = json.dumps(
        dict(partition="train", production_train_components=admission.declaration()), sort_keys=True
    ).encode()
    admission = ProductionTrainAdmission.authenticate(
        source_state=artifacts["prefix_state"],
        envelope_bytes=artifacts["prefix_envelope"],
        progress_bytes=proof.progress_bytes(),
        plan_bytes=plan,
        source_commit=proof.source_commit,
        derived_source_proof=proof,
        context_bytes=artifacts["prefix_context"],
    )
    return admission, proof, plan


def test_seven_phase_source_retains_correlated_origin_and_costs(admitted_source, artifacts):
    a, proof, plan = admitted_source
    d = proof.document()
    assert d["prefix_phase_count"] == 7 and d["source_group_sha256"] == SOURCE049_GROUP
    assert d["cumulative_spent"] == json.loads(artifacts["prefix_context"])["spent"]
    assert d["cumulative_spent"]["actions"] == 272 and d["cumulative_spent"]["frames"] == 19692
    assert d["failed_v1_costs_remain_additional"] is True
    assert d["independent_origin"] is d["fit_admission"] is d["grants_new_budget"] is False
    assert a.objective_id == "defeat_blaine" and a.story_map_id == 166 and a.wild_map_id == 15
    a.require_work_order(plan)
    assert ProductionTrainAdmission.from_document(a.document(), derived_source_proof=proof) == a


@pytest.mark.parametrize("name", sorted(SOURCE049_ARTIFACT_PINS))
def test_any_changed_artifact_rejects_before_native_use(artifacts, name):
    changed = dict(artifacts)
    changed[name] += b" "
    with pytest.raises(ValueError, match="artifact changed"):
        authenticate_teacher_prefix_train_source(artifacts=changed, source_commit="a" * 40)


def test_missing_prefix_and_unverified_constructor_reject(artifacts):
    changed = dict(artifacts)
    changed.pop("phase_6")
    with pytest.raises(ValueError, match="census"):
        authenticate_teacher_prefix_train_source(artifacts=changed, source_commit="a" * 40)
    with pytest.raises(ValueError, match="authenticated"):
        VerifiedTeacherPrefixTrainSource({})


@pytest.mark.parametrize(
    "field",
    [
        "source_state_sha256",
        "source_origin_sha256",
        "source_commit",
        "envelope_sha256",
        "progress_sha256",
    ],
)
def test_constructor_cannot_spoof_source_or_fresh_metadata(admitted_source, field):
    a, _, _ = admitted_source
    with pytest.raises(ValueError):
        replace(a, **{field: "f" * (40 if field == "source_commit" else 64)})


@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "origin",
        "group",
        "independence",
        "omitted_failed_costs",
        "proof",
        "context",
        "state",
        "target",
        "work_order",
    ],
)
def test_authenticate_rejects_context_metadata_and_plan_substitution(
    admitted_source, artifacts, fault
):
    a, proof, plan = admitted_source
    progress = json.loads(proof.progress_bytes())
    work = json.loads(plan)
    kwargs = dict(
        source_state=artifacts["prefix_state"],
        envelope_bytes=artifacts["prefix_envelope"],
        source_commit=proof.source_commit,
        derived_source_proof=proof,
        context_bytes=artifacts["prefix_context"],
    )
    if fault == "partition":
        progress["partition"] = "development"
    elif fault == "origin":
        progress["source_origin_sha256"] = "f" * 64
    elif fault == "group":
        progress["source_group_sha256"] = "f" * 64
    elif fault == "independence":
        progress["independent_origin"] = True
    elif fault == "omitted_failed_costs":
        progress["failed_prefix_costs_retained"] = False
    elif fault == "proof":
        kwargs["derived_source_proof"] = None
    elif fault == "context":
        kwargs["context_bytes"] += b" "
    elif fault == "state":
        kwargs["source_state"] += b" "
    elif fault == "target":
        work["production_train_components"]["objective_id"] = "defeat_misty"
    else:
        work["partition"] = "development"
    with pytest.raises(ValueError):
        ProductionTrainAdmission.authenticate(
            **kwargs,
            progress_bytes=json.dumps(progress, sort_keys=True, separators=(",", ":")).encode(),
            plan_bytes=json.dumps(work).encode(),
        )


def blaine_scope(admission):
    _, scope, actor = scope_and_actor("story")
    scope.source_state_sha256 = actor.source_state_sha256 = admission.source_state_sha256
    scope.root_lineage_id = actor.root_lineage_id = admission.root_lineage_id
    scope.work_order_sha256 = admission.work_order_sha256
    scope.contract = N(
        objective_id="defeat_blaine",
        battle_plan_id="defeat_blaine",
        map_id=166,
        trainer_identity=(239, 39, 1),
        defeated_event=665,
        victory_money=4653,
        victory_items=((238, 1),),
        victory_badge_bits=64,
    )
    scope.gym_reward = admission.story_reward
    return scope, actor


def test_exact_blaine_contract_accepted_and_funding_is_not(admitted_source):
    a, _, _ = admitted_source
    scope, actor = blaine_scope(a)
    a.require_actor(actor, scope, "story")
    with pytest.raises(ValueError):
        a.require_actor(actor, scope, "funding")


@pytest.mark.parametrize(
    "field,value",
    [
        ("objective_id", "defeat_misty"),
        ("battle_plan_id", "ordinary-trainer-funding"),
        ("map_id", 65),
        ("trainer_identity", (239, 39, 2)),
        ("defeated_event", 664),
        ("victory_money", 4654),
        ("victory_items", ((211, 1),)),
        ("victory_badge_bits", 2),
    ],
)
def test_wrong_story_target_or_reward_fails(admitted_source, field, value):
    a, _, _ = admitted_source
    scope, actor = blaine_scope(a)
    setattr(scope.contract, field, value)
    with pytest.raises(ValueError):
        a.require_actor(actor, scope, "story")


def helper_hook(name):
    path = (
        Path(__file__).resolve().parents[1]
        / "runtime_helpers/red_whole_player_inventory_20261006.py"
    )
    tree = ast.parse(path.read_text())
    assembly = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "assembly")
    return path, next(n for n in assembly.body if isinstance(n, ast.FunctionDef) and n.name == name)


def test_existing_pool_hook_uses_exact_blaine_reward_and_same_runtime(
    admitted_source, monkeypatch, tmp_path
):
    from pokemon_red_completion.executor import NativeLessonController
    from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers

    a, _, _ = admitted_source
    port = NativeLessonController(N(frame_count=0), maximum_frames=1000)
    reader = N(read=lambda: None)
    runtime = N(reader=reader, emulator=port, adapter=object())
    contract = object()
    wild = N(session=port)
    story = N(session=port, development_story_scope=N(contract=contract))
    calls = []
    pool = N(wild=wild, story=lambda c: story if c is contract else None)
    monkeypatch.setattr(
        ScopedTrainingBattlers,
        "for_production_source",
        lambda *args, **kwargs: calls.append(kwargs) or pool,
    )
    holder = dict(
        actor=wild, runtime=runtime, training_reader=reader, initial_battle=None, scoped_actors={}
    )

    def preparation(map_id, **kwargs):
        assert map_id == 15
        return wild

    def leader(reward, rt, **kwargs):
        assert reward is a.story_reward and reward.objective_id == "defeat_blaine" and rt is runtime
        return story

    path, hook = helper_hook("ensure_training_pool")
    ns = dict(
        training_admission=a,
        holder=holder,
        source={},
        output=tmp_path,
        preparation_actor=preparation,
        leader_actor=leader,
        NativeBattlerHistory=lambda *args, **kwargs: None,
    )
    exec(compile(ast.Module(body=[hook], type_ignores=[]), str(path), "exec"), ns)
    assert ns["ensure_training_pool"](runtime) is pool
    assert ns["ensure_training_pool"](runtime) is pool and len(calls) == 1
    assert holder["scoped_actors"]["defeat_blaine"][0] is story
    assert calls[0]["reader"] is reader and port.frames_executed == 0


def test_admission_selects_supported_alternative_and_discloses_raw_venues(admitted_source):
    a, _, _ = admitted_source
    path, hook = helper_hook("preparation")
    node = next(
        n
        for n in hook.body
        if isinstance(n, ast.If)
        and any(
            isinstance(x, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "ordinary_venues" for t in x.targets)
            for x in n.body
        )
    )
    ns = dict(training_admission=a, holder={}, venues=[(0, 22), (1, 15), (2, 165)])
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    assert ns["venues"] == [(1, 15)]
    d = ns["holder"]["preparation_admission"]
    assert d["ordinary_reachable_venue_maps"] == [22, 15, 165]
    assert d["admitted_venue_maps"] == [15] and [v["map_id"] for v in d["unavailable"]] == [22, 165]
    assert d["unrestricted_preparation_coverage"] is False
