import json
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _situation

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_live_option_menu import supplemental_live_option
from pokemon_red_completion.red_player_configuration import (
    ASSEMBLY_FLAGS,
    ROUTE_WORK_SCHEMA,
    SCHEMA,
    RedPlayerConfiguration,
    assemble_configured_player,
)
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


def config():
    return RedPlayerConfiguration(
        "a" * 64,
        "earned-origin",
        "b" * 64,
        tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        (("evolve_species", "c" * 64),),
        ("reserve-individual",),
    )


def test_configuration_roundtrip_keeps_exact_exclusion_and_identity():
    before = config()
    after = RedPlayerConfiguration.from_dict(json.loads(json.dumps(before.to_dict())))
    assert after == before and after.sha256 == before.sha256
    broken = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="native:evolution:" + "c" * 64, calls=[])
    assert not after.admits(broken)
    assert after.admits(replace(broken, binding_ref="native:evolution:" + "d" * 64))
    assert after.admits(replace(broken, kind=GoalKind.ADVANCE_STORY))
    assert not after.admits(replace(broken,
        binding_ref="native:evolution:profile-"+"d"*64+":config-"+"c"*64))
    assert after.admits(replace(broken,
        binding_ref="native:evolution:profile-"+"c"*64+":config-"+"d"*64))


def test_route_work_configuration_versions_only_the_explicit_opt_in():
    before = config()
    legacy = before.to_dict()
    assert legacy["schema"] == SCHEMA and "quote_capture_route_work" not in legacy
    assert RedPlayerConfiguration.from_dict(legacy).to_dict() == legacy
    opted = replace(before, quote_capture_route_work=True)
    payload = json.loads(json.dumps(opted.to_dict()))
    assert payload["schema"] == ROUTE_WORK_SCHEMA and payload["quote_capture_route_work"] is True
    assert RedPlayerConfiguration.from_dict(payload) == opted
    assert opted.sha256 != before.sha256
    assert replace(opted, quote_capture_route_work=False).sha256 == before.sha256


@pytest.mark.parametrize("value", [None, 1, "yes", False])
def test_route_work_v2_rejects_coercion_or_unversioned_flags(value):
    document = json.loads(json.dumps(replace(config(), quote_capture_route_work=True).to_dict()))
    document["quote_capture_route_work"] = value
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(document)
    document["schema"] = SCHEMA
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(document)


@pytest.mark.parametrize("value", [None, 1, "yes"])
def test_route_work_constructor_rejects_coercion(value):
    with pytest.raises(ValueError, match="explicit boolean"):
        replace(config(), quote_capture_route_work=value)


@pytest.mark.parametrize("enabled", [False, True])
def test_route_work_reaches_backend_only_from_versioned_configuration(tmp_path, enabled):
    calls = []

    def assemble(*args, **kwargs):
        calls.append(kwargs)
        menu = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
        return b"unchanged", None, menu, {}, {"partition": "development"}

    original = config()
    configuration = replace(original, quote_capture_route_work=enabled)
    reloaded = RedPlayerConfiguration.from_dict(json.loads(json.dumps(configuration.to_dict())))
    payload, _, _, _, source = assemble_configured_player(
        N(assembly=assemble), reloaded, tmp_path, tmp_path, plan_path=tmp_path / "plan.json")
    assert payload == b"unchanged" and source["configuration_sha256"] == configuration.sha256
    if enabled:
        assert calls[0]["quote_capture_route_work"] is True
    else:
        assert "quote_capture_route_work" not in calls[0]
    assert original.to_dict()["schema"] == SCHEMA


def test_pending_reward_precedes_routing_without_inventing_a_model_choice(tmp_path, monkeypatch):
    from pokemon_red_completion import red_player_configuration as module

    pending = _binding(GoalKind.RECOVER_CONTROL, binding_ref="pending", calls=[])
    monkeypatch.setattr(module, "pending_gym_reward_binding", lambda *a, **kw: pending)
    menu = NativeStoryBranchInventory(
        lambda *_: pytest.fail("ordinary routing must not read the open reward dialogue"),
        lambda *_: pytest.fail("compulsory settlement must not ask for another story branch"),
    )
    backend = N(
        assembly=lambda *a, **kw: (
            b"state",
            None,
            menu,
            {"configured_route": N(route_world=object())},
            {"partition": "development"},
        )
    )
    _, _, configured, _, _ = assemble_configured_player(
        backend,
        config(),
        tmp_path,
        tmp_path,
        plan_path=tmp_path / "plan.json",
    )
    runtime = N(emulator=N(save_state_bytes=lambda: b"state"))
    inventory = configured.enumerate(runtime, None, N(situation=_situation()))
    assert inventory.bindings == (pending,)
    assert len(inventory.opportunities) == 2
    assert configured.supplements(runtime, None, None, inventory) == ()


@pytest.mark.parametrize(
    "fault", ["missing_flag", "coerced_flag", "bad_profile", "two_loans", "unknown"]
)
def test_configuration_rejects_silent_scope_changes(fault):
    d = json.loads(json.dumps(config().to_dict()))
    if fault == "missing_flag":
        d["assembly_flags"].pop()
    elif fault == "coerced_flag":
        d["assembly_flags"][0][1] = 1
    elif fault == "bad_profile":
        d["excluded_profiles"][0][1] = "wrong"
    elif fault == "two_loans":
        d["loanable_specimen_refs"].append("another")
    else:
        d["force_story"] = True
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(d)


def test_fresh_assemblies_filter_only_the_exact_offer_without_breaking_menu_identity(tmp_path):
    calls = []
    advance = _binding(GoalKind.ADVANCE_STORY, binding_ref="native:story", calls=calls)
    broken = _binding(
        GoalKind.EVOLVE_SPECIES, binding_ref="native:evolution:" + "c" * 64, calls=calls
    )
    other = replace(broken, binding_ref="native:evolution:" + "d" * 64)
    situation = _situation()
    question = GoalBindingSet(
        (advance.opportunity, broken.opportunity), (advance, broken)
    ).question(situation)
    supplemental = tuple(
        supplemental_live_option(
            b,
            project_living_dex_goal_candidate(
                question, 1, feature_version=7, binding_ref=b.binding_ref
            ),
        )
        for b in (broken, other)
    )
    built = []

    def backend_assembly(*args, **kwargs):
        menu = NativeStoryBranchInventory(
            lambda *args: GoalBindingSet(
                (advance.opportunity, broken.opportunity), (advance, broken)
            ),
            lambda *args: ((advance, OptionChallenge(False, False, 0.0, 0.0, 0.0)),),
            enumerate_collection=lambda *args: supplemental,
        )
        built.append(menu)
        return b"state", None, menu, {}, {"partition": "development"}

    backend = N(assembly=backend_assembly)
    runtime = N(emulator=N(save_state_bytes=lambda: b"state"))
    observation = N(situation=situation)
    for configuration in (
        config(),
        RedPlayerConfiguration.from_dict(json.loads(json.dumps(config().to_dict()))),
    ):
        _, _, menu, _, source = assemble_configured_player(
            backend, configuration, tmp_path, tmp_path, plan_path=tmp_path / "plan.json"
        )
        inventory = menu.enumerate(runtime, None, observation)
        additions = menu.supplements(runtime, None, observation, inventory)
        assert tuple(b.binding_ref for b in inventory.bindings) == (advance.binding_ref,)
        assert tuple(row.binding.binding_ref for row in additions) == (other.binding_ref,)
        assert source["configuration_sha256"] == config().sha256
    assert len(built) == 2 and built[0] is not built[1] and not calls


@pytest.mark.parametrize("fault", [None, "context_hash", "state_hash", "running", "foreign",
                                  "duplicate", "missing", "changed_config"])
def test_pending_loan_authenticates_only_the_immediate_original_roster(tmp_path, fault):
    from hashlib import sha256

    from pokemon_red_completion.red_player_configuration import authenticated_preloan_roster

    parent, prior = tmp_path / "new", tmp_path / "old"
    parent.mkdir()
    prior.mkdir()
    refs = [*(f"retained-{i}" for i in range(5)), "reserve-individual"]
    context = dict(state_sha256=sha256(b"source").hexdigest(), spent={}, lesson=dict(party=[
        dict(specimen_ref=ref, species_id=i+1, level=17, experience=5000, hp=40, max_hp=40,
             status="healthy", moves=[[33, 35]]) for i, ref in enumerate(refs)]))
    if fault == "duplicate":
        context["lesson"]["party"][-1]["specimen_ref"] = refs[0]
    encoded = json.dumps(context).encode()
    (prior / "CONTEXT.json").write_bytes(encoded)
    (prior / "terminal.state").write_bytes(b"source")
    result = dict(worker_stopped=fault != "running", released=True, spent={},
        state_sha256=context["state_sha256"], context_sha256=sha256(encoded).hexdigest(),
        configuration_sha256=config().sha256)
    (prior / "RESULT.json").write_text(json.dumps(result))
    record = dict(actual_parent=str(prior), context_sha256=result["context_sha256"],
                  source_sha256=result["state_sha256"], configuration_sha256=config().sha256)
    if fault == "context_hash":
        record["context_sha256"] = "0" * 64
    if fault == "state_hash":
        record["source_sha256"] = "0" * 64
    if fault == "changed_config":
        record["configuration_sha256"] = "0" * 64
    if fault == "foreign":
        record["actual_parent"] = str(tmp_path.parent / "foreign")
    current = dict(preparation=dict(roster=[dict(specimen_ref=r) for r in refs]),
                   lesson=dict(party=[dict(specimen_ref=r) for r in refs[:5]] +
                                     [dict(specimen_ref="guest")]))
    if fault == "missing":
        current["preparation"]["roster"].pop()
    (parent / "CONTEXT.json").write_text(json.dumps(current))
    (parent / "PLAN.json").write_text(json.dumps(record))
    if fault:
        with pytest.raises(ValueError):
            authenticated_preloan_roster(parent, config())
    else:
        party, restored_refs = authenticated_preloan_roster(parent, config())
        assert restored_refs == tuple(refs) and party.size == 6
        assert party.members[-1].level == 17
        assert (prior / "terminal.state").read_bytes() == b"source"


@pytest.mark.parametrize("fault", [None, "context_hash", "state_hash", "running", "unreleased",
    "changed_config", "spent", "duplicate", "wrong_loan", "changed_roster", "cycle",
    "foreign", "limit", "no_original"])
def test_pending_loan_follows_only_verified_consecutive_recovery_sources(
    tmp_path, monkeypatch, fault
):
    from hashlib import sha256

    from pokemon_red_completion import red_player_configuration as module

    refs = [*(f"retained-{i}" for i in range(5)), "reserve-individual"]
    guest_refs = refs[:5] + ["guest"]
    paths = [tmp_path / name for name in ("original", "recovery-one", "recovery-two")]
    contexts, results = [], []
    for i, path in enumerate(paths):
        path.mkdir()
        active = refs if i == 0 else guest_refs
        if i == 0 and fault == "no_original":
            active = guest_refs
        if i == 1 and fault == "duplicate":
            active = guest_refs[:-1] + [guest_refs[0]]
        if i == 1 and fault == "wrong_loan":
            active = refs[1:] + ["guest"]
        retained = refs[:5] + ["substituted"] if i == 1 and fault == "changed_roster" else refs
        state = f"state-{i}".encode()
        document = dict(state_sha256=sha256(state).hexdigest(), spent={"actions": i},
            preparation=dict(roster=[dict(specimen_ref=r) for r in retained]),
            lesson=dict(party=[dict(specimen_ref=ref, species_id=j+1, level=17,
                experience=5000, hp=40, max_hp=40, status="healthy", moves=[[33, 35]])
                for j, ref in enumerate(active)]))
        encoded = json.dumps(document).encode()
        (path / "terminal.state").write_bytes(state)
        (path / "CONTEXT.json").write_bytes(encoded)
        result = dict(worker_stopped=not (i == 0 and fault == "running"),
            released=not (i == 0 and fault == "unreleased"), spent=document["spent"],
            state_sha256=document["state_sha256"], context_sha256=sha256(encoded).hexdigest(),
            configuration_sha256=config().sha256)
        if i == 0 and fault == "spent":
            result["spent"] = {"actions": 999}
        (path / "RESULT.json").write_text(json.dumps(result))
        contexts.append(document)
        results.append(result)
    for i in (1, 2):
        result = results[i-1]
        record = dict(actual_parent=str(paths[i-1]), context_sha256=result["context_sha256"],
            source_sha256=result["state_sha256"], configuration_sha256=config().sha256)
        if i == 1:
            if fault == "context_hash":
                record["context_sha256"] = "0" * 64
            if fault == "state_hash":
                record["source_sha256"] = "0" * 64
            if fault == "changed_config":
                record["configuration_sha256"] = "0" * 64
            if fault == "cycle":
                record["actual_parent"] = str(paths[2])
            if fault == "foreign":
                record["actual_parent"] = str(tmp_path.parent / "foreign")
        (paths[i] / "PLAN.json").write_text(json.dumps(record))
    if fault == "no_original":
        (paths[0] / "PLAN.json").write_text(json.dumps(dict(actual_parent=str(paths[0]))))
    if fault == "limit":
        monkeypatch.setattr(module, "MAX_PRELOAN_HISTORY_LINKS", 1)
    before = {str(p): p.read_bytes() for root in paths for p in root.iterdir()}
    if fault:
        with pytest.raises(ValueError):
            module.authenticated_preloan_roster(paths[2], config())
    else:
        party, original_refs = module.authenticated_preloan_roster(paths[2], config())
        assert party.size == 6 and original_refs == tuple(refs)
        assert "guest" not in original_refs
    assert {str(p): p.read_bytes() for root in paths for p in root.iterdir()} == before



@pytest.mark.parametrize("version", [5, 6, 7, 8, 9])
def test_model_schema_enables_workload_observation_without_changing_legacy_kwargs(tmp_path, version):
    calls = []
    def assembly(*args, **kwargs):
        calls.append(kwargs)
        menu = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
        return b"unchanged", None, menu, {}, {"partition": "development"}
    configuration = config()
    before = configuration.to_dict()
    payload, _, _, _, _ = assemble_configured_player(
        N(assembly=assembly), configuration, tmp_path, tmp_path,
        plan_path=tmp_path/"plan.json", model_feature_version=version)
    assert payload == b"unchanged" and configuration.to_dict() == before
    if version == 9:
        assert calls[0]["include_level_workload"] is True
    else:
        assert "include_level_workload" not in calls[0]


@pytest.mark.parametrize("version", [None, True, 4, 12, "9", 9.0])
def test_bad_model_schema_fails_before_backend_assembly(tmp_path, version):
    backend = N(assembly=lambda *a, **k: pytest.fail("invalid schema reached backend"))
    with pytest.raises(ValueError, match="supported model feature version"):
        assemble_configured_player(backend, config(), tmp_path, tmp_path,
                                  plan_path=tmp_path/"plan.json", model_feature_version=version)
