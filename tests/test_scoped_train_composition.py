"""Explicit source custody and unchanged existing pool boundaries, ROM-free."""

import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_scoped_train_composition as module
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_story_battle import StoryTrainerContract


def case(tmp_path):
    payload = b"state"
    context = json.dumps(dict(state_sha256=sha256(payload).hexdigest())).encode()
    work = b"{}"
    contract = StoryTrainerContract(
        "defeat_erika", "observed-story-obstruction", 134, (219, 19, 1), 86, 330
    )
    spec = module.ScopedTrainComposition(
        sha256(payload).hexdigest(),
        "b" * 64,
        "c" * 40,
        sha256(context).hexdigest(),
        sha256(work).hexdigest(),
        tmp_path / "native-plan.json",
        (contract,),
    )
    source = dict(
        partition="train",
        state_sha256=spec.source_state_sha256,
        origin_sha256=spec.source_origin_sha256,
        source_commit=spec.source_commit,
        experiment_sha256=spec.work_order_sha256,
    )
    return spec, source, payload, context, work


@pytest.mark.parametrize("fault", ["state", "context", "work", "origin", "root"])
def test_source_context_and_work_order_must_match_before_construction(tmp_path, fault):
    spec, source, payload, context, work = case(tmp_path)
    args = dict(origin_sha=source["origin_sha256"], origin_id=spec.root_lineage_id)
    spec.require_source(payload, context, work, **args)
    if fault == "state":
        payload += b"changed"
    if fault == "context":
        context += b" "
    if fault == "work":
        work += b"changed"
    if fault == "origin":
        args["origin_sha"] = "e" * 64
    if fault == "root":
        args["origin_id"] = "development"
    with pytest.raises(ValueError):
        spec.require_source(payload, context, work, **args)


@pytest.mark.parametrize(
    "key,value",
    [
        ("partition", "development"),
        ("state_sha256", "e" * 64),
        ("origin_sha256", "e" * 64),
        ("source_commit", "e" * 40),
        ("experiment_sha256", "e" * 64),
    ],
)
def test_assembly_cannot_relabel_or_replace_source_before_native_io(tmp_path, key, value):
    spec, source, *_ = case(tmp_path)
    source[key] = value
    with pytest.raises(ValueError, match="assembly source differs"):
        spec.bind(None, source=source, output=tmp_path / "unused", initial=None)
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("native", [False, True])
def test_existing_pools_bind_all_objectives_without_menu_filtering(tmp_path, monkeypatch, native):
    spec, source, *_ = case(tmp_path)
    contract = replace(spec.contracts[0], objective_id="rescue_fuji")
    spec = replace(spec, contracts=spec.contracts + (contract,))
    calls = []

    class Readonly:
        pass

    monkeypatch.setattr(module, "ReadOnlyController", Readonly)
    monkeypatch.setattr(
        module.ScopedTrainingBattlers,
        "for_native_source",
        lambda prototype, **kw: calls.append(kw) or NS(declaration_sha256="d" * 64),
    )
    session = NS(frames_executed=0) if native else Readonly()
    if native:
        spec.native_plan_path.write_text(
            json.dumps(dict(source={**source, "configuration_sha256": "f" * 64}))
        )
    result = spec.bind(
        NS(session=session), source=source, output=tmp_path / "fresh-group", initial=None
    )
    assert {key[0] for key in result.pools} == {"defeat_erika", "rescue_fuji"}
    assert tuple(c["contracts"][0] for c in calls) == spec.contracts
    expected = canonical_sha256(json.loads(spec.native_plan_path.read_bytes())) if native else None
    assert all(c["native_plan_sha256"] == expected for c in calls)
    assert all(c["source"] == source for c in calls)


@pytest.mark.parametrize("fault", ["wrong_native_source", "late_bind"])
def test_executing_scope_binds_exact_native_plan_before_any_input(tmp_path, fault):
    spec, source, *_ = case(tmp_path)
    bad = {**source, "partition": "development"} if fault == "wrong_native_source" else source
    spec.native_plan_path.write_text(json.dumps(dict(source=bad)))
    actor = NS(session=NS(frames_executed=1 if fault == "late_bind" else 0))
    with pytest.raises(ValueError, match="before input"):
        spec.bind(actor, source=source, output=tmp_path / "unused", initial=None)
    assert not (tmp_path / "unused").exists()


def test_aliases_cannot_change_rewards_or_duplicate_contracts(tmp_path):
    spec, *_ = case(tmp_path)
    c = spec.contracts[0]
    with pytest.raises(ValueError, match="unique contracts"):
        replace(spec, contracts=(c, c))
    with pytest.raises(ValueError, match="disagree on native reward"):
        replace(spec, contracts=(c, replace(c, objective_id="rescue_fuji", victory_money=331)))


def test_finite_pool_limits_are_retained(tmp_path):
    spec, *_ = case(tmp_path)
    c = spec.contracts[0]
    with pytest.raises(ValueError, match="finite pool scope"):
        replace(spec, contracts=tuple(replace(c, defeated_event=i) for i in range(33)))


def test_group_roles_remain_exact_and_declarations_cannot_be_changed(tmp_path):
    spec, source, *_ = case(tmp_path)
    c = spec.contracts[0]
    observed = []
    child = NS(declaration_sha256="d" * 64, story=lambda x: observed.append(x) or "actor")
    group = module.ScopedTrainBattlerGroup(
        {(c.objective_id, c.battle_plan_id, c.map_id): child},
        source=source,
        output=tmp_path,
        initial=None,
    )
    assert group.story(c) == "actor" and observed == [c]
    with pytest.raises(ValueError, match="outside prospective scope"):
        group.story(replace(c, battle_plan_id="another-role"))
    with pytest.raises(TypeError):
        group.pools[(c.objective_id, c.battle_plan_id, c.map_id)] = child
    child.declaration_sha256 = "e" * 64
    with pytest.raises(ValueError, match="declaration changed"):
        group.story(c)


@pytest.mark.parametrize("overlap", [False, True])
def test_group_preserves_every_child_result_and_checks_frame_order(tmp_path, overlap):
    spec, source, *_ = case(tmp_path)
    # Mechanical merge only; the real child verifies native state/battle receipts.
    import inspect

    from pokemon_red_completion.post_battle_strategy import BattleResult
    from pokemon_red_completion.red_scoped_training_battlers import ScopedBattleOutcome

    fields = inspect.signature(ScopedBattleOutcome).parameters
    assert "before_frame" in fields and "after_frame" in fields
    # Use the existing immutable battle record shape, retaining its result/hash.
    rows = [
        ScopedBattleOutcome(0, 10, 20, BattleResult.WON, "a" * 64),
        ScopedBattleOutcome(0, 19 if overlap else 21, 30, BattleResult.LOST, "b" * 64),
    ]
    calls = []

    def child(row):
        return NS(
            declaration_sha256="d" * 64, verified_outcomes=lambda **kw: calls.append(kw) or (row,)
        )

    group = module.ScopedTrainBattlerGroup(
        {("a", "x", 1): child(rows[1]), ("b", "x", 2): child(rows[0])},
        source=source,
        output=tmp_path,
        initial=None,
    )
    args = dict(
        expected_native_plan_sha256="f" * 64,
        expected_declaration_sha256=group.declaration_sha256,
        source_sha256=source["state_sha256"],
    )
    if overlap:
        with pytest.raises(ValueError, match="overlapping native battles"):
            group.verified_outcomes(**args)
    else:
        merged = group.verified_outcomes(**args)
        assert [(x.ordinal, x.result) for x in merged] == [
            (0, BattleResult.WON),
            (1, BattleResult.LOST),
        ]
        assert len(calls) == 2 and all(x["expected_native_plan_sha256"] == "f" * 64 for x in calls)


def test_configured_player_forwards_only_valid_explicit_train_composition(tmp_path):
    from test_red_player_configuration import config

    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory

    spec, source, payload, context, work = case(tmp_path)
    (tmp_path / "terminal.state").write_bytes(payload)
    (tmp_path / "CONTEXT.json").write_bytes(context)
    plan = tmp_path / "PLAN.json"
    plan.write_bytes(work)
    configuration = replace(
        config(), origin_sha256=spec.source_origin_sha256, origin_id=spec.root_lineage_id
    )
    calls = []

    def assembly(*a, **kw):
        calls.append(kw)
        menu = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
        return payload, None, menu, {}, source

    assemble_configured_player(
        NS(assembly=assembly),
        configuration,
        tmp_path,
        tmp_path,
        plan_path=plan,
        scoped_train_composition=spec,
    )
    assert calls[0]["scoped_train_composition"] is spec
    assert "training_admission" not in calls[0]
    with pytest.raises(ValueError, match="source/context/work order"):
        assemble_configured_player(
            NS(assembly=assembly),
            config(),
            tmp_path,
            tmp_path,
            plan_path=plan,
            scoped_train_composition=spec,
        )
    assert len(calls) == 1


@pytest.mark.parametrize("route,quantum", [(False, None), (True, None), (True, 4)])
def test_no_loan_configuration_is_explicit_and_does_not_reinterpret_old_schema(route, quantum):
    from test_red_player_configuration import config

    from pokemon_red_completion.red_player_configuration import (
        NO_LOAN_SCHEMA,
        RedPlayerConfiguration,
    )

    old = config()
    configuration = replace(
        old,
        loanable_specimen_refs=(),
        quote_capture_route_work=route,
        preparation_encounter_quantum=quantum,
    )
    document = json.loads(json.dumps(configuration.to_dict()))
    assert document["schema"] == NO_LOAN_SCHEMA
    assert RedPlayerConfiguration.from_dict(document) == configuration
    forged = {**document, "schema": old.to_dict()["schema"]}
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(forged)
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(
            {**document, "loanable_specimen_refs": ["invented-permission"]}
        )
    assert RedPlayerConfiguration.from_dict(old.to_dict()) == old


def test_real_pools_bind_fresh_nested_output_without_inputs_or_invented_receipts(
    tmp_path, monkeypatch
):
    from test_red_scoped_training_battlers import prototype

    spec, source, *_ = case(tmp_path)

    class Readonly:
        frame_count = 0

    monkeypatch.setattr(module, "ReadOnlyController", Readonly)
    p = replace(
        prototype(tmp_path),
        session=Readonly(),
        source_commit=spec.source_commit,
        source_state_sha256=spec.source_state_sha256,
        root_lineage_id=spec.root_lineage_id,
    )
    contract = spec.contracts[0]
    alternate = replace(contract, battle_plan_id="required-tower-rocket")
    spec = replace(spec, contracts=(contract, alternate))
    output = tmp_path / "fresh-parent/scoped-actors"
    group = spec.bind(p, source=source, output=output, initial=None)
    assert group.story(contract).train_story_contract == contract
    assert group.story(alternate).train_story_contract == alternate
    assert group.history() is None and group.receipts == ()
    assert p.calls == 0 and p.session.frame_count == 0
    with pytest.raises(FileExistsError):
        spec.bind(p, source=source, output=output, initial=None)


def test_same_role_on_different_maps_has_distinct_finite_pools(tmp_path, monkeypatch):
    from test_red_scoped_training_battlers import prototype

    spec, source, *_ = case(tmp_path)

    class Readonly:
        frame_count = 0

    monkeypatch.setattr(module, "ReadOnlyController", Readonly)
    c = spec.contracts[0]
    other = replace(c, map_id=14, defeated_event=100)
    spec = replace(spec, contracts=(c, other))
    p = replace(
        prototype(tmp_path),
        session=Readonly(),
        source_commit=spec.source_commit,
        source_state_sha256=spec.source_state_sha256,
        root_lineage_id=spec.root_lineage_id,
    )
    group = spec.bind(p, source=source, output=tmp_path / "route-group", initial=None)
    assert len(group.pools) == 2
    assert group.story(c).train_story_contract == c
    assert group.story(other).train_story_contract == other
    assert group.story(c) is not group.story(other)
    assert p.session.frame_count == 0 and not group.receipts


def test_readonly_then_native_factory_keep_distinct_declarations_and_no_reexecution(tmp_path, monkeypatch):
    spec, source, *_ = case(tmp_path)
    class Readonly: pass
    monkeypatch.setattr(module,"ReadOnlyController",Readonly)
    monkeypatch.setattr(module.ScopedTrainingBattlers,"for_native_source",lambda prototype,**kw:NS(declaration_sha256="d"*64))
    root=tmp_path/"scoped-native-train"
    pre=spec.bind(NS(session=Readonly()),source=source,output=root,initial=None)
    spec.native_plan_path.write_text(json.dumps(dict(source=source)))
    native=spec.bind(NS(session=NS(frames_executed=0)),source=source,output=root,initial=None)
    assert pre.output != native.output and pre.output.is_dir() and native.output==root
    assert (pre.output/"declaration.json").exists() and (native.output/"declaration.json").exists()
    with pytest.raises(FileExistsError):
        spec.bind(NS(session=NS(frames_executed=0)),source=source,output=root,initial=None)
