import json
from dataclasses import dataclass, replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.party_development_outcome_learning import (
    canonical_party_development_outcome_model_sha256,
    upgrade_party_development_model_for_workload,
)
from test_party_development_outcome_learning import _initialized_model
from test_red_player_configuration import config


@pytest.fixture
def model_record(tmp_path):
    model = upgrade_party_development_model_for_workload(_initialized_model())
    canonical = canonical_party_development_outcome_model_sha256(model)
    path = tmp_path / "venue-model.json"
    path.write_text(json.dumps(model.to_dict(), sort_keys=True))
    configured = replace(config(), evolution_venue_model_sha256=canonical,
                         evolution_venue_scope=("route11", "mansion"))
    plan = dict(partition="development", configuration=configured.to_dict(),
                native_evolution_venue_model=dict(path=str(path),
                    content_sha256=sha256(path.read_bytes()).hexdigest(),
                    reason="Unit-only existing scorer; no native execution or fitting."))
    return N(model=model, canonical=canonical, path=path, configuration=configured, plan=plan)


@pytest.mark.parametrize("route_work", [False, True])
def test_legacy_configuration_documents_remain_exact(route_work):
    old = replace(config(), quote_capture_route_work=route_work)
    expected = dict(schema=configuration.ROUTE_WORK_SCHEMA if route_work else configuration.SCHEMA,
                    origin_sha256=old.origin_sha256, origin_id=old.origin_id,
                    goal_model_sha256=old.goal_model_sha256, assembly_flags=old.assembly_flags,
                    excluded_profiles=old.excluded_profiles, loanable_specimen_refs=old.loanable_specimen_refs)
    if route_work:
        expected["quote_capture_route_work"] = True
    assert old.to_dict() == expected
    from pokemon_red_completion.provenance import canonical_sha256
    assert old.sha256 == canonical_sha256(expected)
    assert configuration.RedPlayerConfiguration.from_dict(json.loads(json.dumps(expected))).to_dict() == expected


@pytest.mark.parametrize("route_work", [False, True])
def test_venue_identity_and_scope_survive_durable_roundtrip(model_record, route_work):
    current = replace(model_record.configuration, quote_capture_route_work=route_work)
    document = current.to_dict()
    assert document["schema"] == configuration.VENUE_SCHEMA
    restored = configuration.RedPlayerConfiguration.from_dict(json.loads(json.dumps(document)))
    assert restored == current and restored.sha256 == current.sha256
    assert current.sha256 != replace(current, evolution_venue_model_sha256=None, evolution_venue_scope=()).sha256
    assert current.sha256 != replace(current, evolution_venue_scope=current.evolution_venue_scope[::-1]).sha256


@pytest.mark.parametrize("scope", [(), ("route11",), ("route11", "route11"),
    ("route11", "unknown"), ("route11", True), ["route11", "mansion"], None])
def test_configured_scope_is_explicit_and_not_coerced(model_record, scope):
    with pytest.raises(ValueError, match="model identity and distinct scope"):
        replace(model_record.configuration, evolution_venue_scope=scope)


def test_unversioned_or_unpaired_venue_identity_is_refused(model_record):
    for schema in [configuration.SCHEMA, configuration.ROUTE_WORK_SCHEMA]:
        document = dict(model_record.configuration.to_dict(), schema=schema)
        with pytest.raises(ValueError, match="schema"):
            configuration.RedPlayerConfiguration.from_dict(document)
    with pytest.raises(ValueError):
        replace(config(), evolution_venue_scope=("route11", "mansion"))
    with pytest.raises(ValueError):
        replace(config(), evolution_venue_model_sha256="a" * 64)


def test_declared_model_authenticates_file_and_canonical_identity(model_record):
    model = configuration.declared_native_evolution_venue_model(model_record.plan)
    assert canonical_party_development_outcome_model_sha256(model) == model_record.canonical
    assert model.outcome_training_examples == model_record.model.outcome_training_examples
    assert configuration.declared_native_evolution_venue_model({}) is None


@pytest.mark.parametrize("fault", ["missing_config", "missing_spec", "partition", "reason", "relative",
    "malformed_sha", "extra", "file_changed", "canonical_changed", "symlink"])
def test_bad_artifact_or_declaration_is_refused(model_record, tmp_path, fault):
    plan = json.loads(json.dumps(model_record.plan))
    spec = plan["native_evolution_venue_model"]
    if fault == "missing_config":
        plan.pop("configuration")
    elif fault == "missing_spec":
        plan.pop("native_evolution_venue_model")
    elif fault == "partition":
        plan["partition"] = "train"
    elif fault == "reason":
        spec["reason"] = " "
    elif fault == "relative":
        spec["path"] = "venue-model.json"
    elif fault == "malformed_sha":
        spec["content_sha256"] = "invalid"
    elif fault == "extra":
        spec["fallback_venue"] = "route11"
    elif fault == "file_changed":
        model_record.path.write_text(model_record.path.read_text() + " ")
    elif fault == "canonical_changed":
        plan["configuration"]["evolution_venue_model_sha256"] = "e" * 64
    else:
        link = tmp_path / "linked-model.json"
        link.symlink_to(model_record.path)
        spec["path"] = str(link)
    with pytest.raises(ValueError):
        configuration.declared_native_evolution_venue_model(plan)


def test_missing_configured_identity_is_rejected_before_artifact_read(monkeypatch, model_record):
    import pokemon_red_completion.party_development_outcome_learning as learning
    monkeypatch.setattr(learning, "load_party_development_outcome_model",
                        lambda *a, **k: pytest.fail("missing identity reached artifact reader"))
    plan = dict(model_record.plan, configuration={})
    with pytest.raises(ValueError, match="explicit configured identity"):
        configuration.declared_native_evolution_venue_model(plan)


def test_legacy_model_schema_cannot_be_activated(model_record):
    legacy = _initialized_model()
    model_record.path.write_text(json.dumps(legacy.to_dict()))
    plan = json.loads(json.dumps(model_record.plan))
    plan["native_evolution_venue_model"]["content_sha256"] = sha256(model_record.path.read_bytes()).hexdigest()
    plan["configuration"]["evolution_venue_model_sha256"] = canonical_party_development_outcome_model_sha256(legacy)
    with pytest.raises(ValueError, match="declared workload scorer"):
        configuration.declared_native_evolution_venue_model(plan)


def test_collection_port_forwards_explicit_model_without_changing_scope(monkeypatch, model_record):
    import pokemon_red_completion.red_player_collection_options as options
    from test_red_player_collection_options import fixture
    runtime, actions, observation = fixture(monkeypatch)
    calls = []
    monkeypatch.setattr(options, "enumerate_red_level_evolutions", lambda *a, **k: calls.append(k) or ())
    venues = (context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE)
    assert options.player_collection_supplements(runtime, actions, observation, world=N(),
        evolution_venue_model=model_record.model, evolution_venue_model_sha256=model_record.canonical,
        evolution_training_venues=venues) == ()
    assert calls[0]["venue_model"] is model_record.model
    assert calls[0]["venue_model_sha256"] == model_record.canonical
    assert calls[0]["training_venues"] == venues
    assert "prefer_highest_supported_venue" not in calls[0]
    assert actions.actions_executed == runtime.emulator.frame_count == 0


def test_collection_rejects_bad_or_prefiltered_model_before_observation(monkeypatch, model_record):
    import pokemon_red_completion.red_player_collection_options as options
    monkeypatch.setattr(options, "_field_ready", lambda *a: pytest.fail("invalid model reached observer"))
    for arguments in [dict(evolution_venue_model=model_record.model),
        dict(evolution_venue_model=model_record.model, evolution_venue_model_sha256="0" * 64),
        dict(evolution_venue_model=model_record.model, evolution_venue_model_sha256=model_record.canonical,
             prefer_highest_evolution_venue=True)]:
        with pytest.raises(ValueError):
            options.player_collection_supplements(None, None, None, world=None, **arguments)


def test_fresh_template_and_chunk_wiring_retain_optional_identity(model_record):
    import run_configured_red_player as configured
    import run_fresh_red_player as fresh
    from test_run_fresh_red_player import plan as fresh_plan
    from copy import deepcopy
    old = configured.player_wiring_declaration({})
    assert "native_evolution_venue_model" not in old
    spec = fresh_plan()
    spec.update(configuration_template=dict(model_record.configuration.to_dict(), quote_capture_route_work=False),
                native_evolution_venue_model=model_record.plan["native_evolution_venue_model"])
    before = deepcopy(spec)
    assert fresh.validate_fresh_plan(spec) is spec and spec == before
    wiring = configured.player_wiring_declaration(spec)
    assert wiring["native_evolution_venue_model"] == spec["native_evolution_venue_model"]
    realized = fresh.realized_configuration(spec["configuration_template"], origin_sha256="d" * 64,
        origin_id="unit-opening", starter_ref="unit-starter", teacher_profiles=())
    assert realized.evolution_venue_model_sha256 == model_record.canonical
    assert realized.evolution_venue_scope == ("route11", "mansion")
    renewed = configuration.RedPlayerConfiguration.from_dict(json.loads(json.dumps(realized.to_dict())))
    assert renewed == realized
    spec["native_evolution_venue_model"]["content_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        fresh.validate_fresh_plan(spec, import_only=True)


@dataclass
class _ConfiguredRoute:
    full_event_offsets: bool = False
    observe_terrain: bool = False
    allow_wild_faints: bool = False
    allow_field_faint_dialogue: bool = False
    route_world: object = None


@pytest.mark.parametrize("cached", [False, True])
def test_configured_factory_preserves_policy_across_runtime_renewal(monkeypatch, model_record, tmp_path, cached):
    import pokemon_red_completion.red_party as party
    from test_red_native_boxed_evolution import runtime_fixture
    runtime, reader, unused_collection = runtime_fixture(tmp_path, count=1)
    configured = replace(model_record.configuration,
        assembly_flags=tuple((name, False) for name in sorted(configuration.ASSEMBLY_FLAGS)))
    plan = dict(model_record.plan, configuration=configured.to_dict())
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    controller = N(frame_count=0, pressed_buttons=frozenset(), save_state_bytes=lambda: b"retained")
    guards, calls = [], []
    guard = N(verify_active_roster_restored=lambda: guards.append(True))
    monkeypatch.setattr(configuration.RedPlayerPartyGuard, "from_rom", lambda *a, **k: guard)
    monkeypatch.setattr(party, "PokemonRedPartyReader", lambda port: N(
        preparation_specimen_refs=lambda: configured.loanable_specimen_refs))
    rom = tmp_path / "unit-cartridge"
    rom.write_bytes(b"unit-only;not-a-ROM")
    def assembly(*args, **kwargs):
        from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
        calls.append(kwargs)
        menu = NativeStoryBranchInventory(lambda *a: None, lambda *a: ())
        return b"retained", lambda port: replace(runtime, emulator=port), menu, {}, {"partition": "development"}
    backend = N(assembly=assembly, c=N(ROM=rom), shared=N(
        RedVermilionGroundTransition=N(from_rom=lambda payload: _ConfiguredRoute())))
    for renewal in range(2):
        kwargs = {"evolution_venue_model": model_record.model} if cached else {}
        payload, factory, menu, holder, source = configuration.assemble_configured_player(
            backend, configured, tmp_path, tmp_path, plan_path=path, model_feature_version=9, **kwargs)
        current = factory(controller)
        policy = current.native_evolution_venue_policy
        assert isinstance(policy, native.NativeEvolutionVenuePolicy)
        assert policy.model_sha256 == model_record.canonical
        assert policy.training_venues == (context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE)
        assert holder["runtime"] is current and holder["configuration_sha256"] == configured.sha256
        assert source["configuration_sha256"] == configured.sha256 and payload == b"retained"
    assert len(guards) == len(calls) == 2
    assert all("evolution_venue_model" not in arguments for arguments in calls)
    assert all("native_evolution_venue_policy" not in arguments for arguments in calls)
    assert controller.frame_count == 0 and not controller.pressed_buttons


def test_enabled_configuration_cannot_silently_use_a_missing_or_foreign_model(model_record, tmp_path):
    backend = N(assembly=lambda *a, **k: pytest.fail("unbound model reached legacy assembly"))
    path = tmp_path / "missing-node.json"
    path.write_text(json.dumps(dict(partition="development", configuration=model_record.configuration.to_dict())))
    with pytest.raises(ValueError):
        configuration.assemble_configured_player(backend, model_record.configuration, tmp_path, tmp_path, plan_path=path)
    with pytest.raises(ValueError):
        configuration.assemble_configured_player(backend, config(), tmp_path, tmp_path,
            plan_path=path, evolution_venue_model=model_record.model)


@pytest.mark.parametrize("enabled", [False, True])
def test_runtime_mode_reaches_native_selection_without_legacy_prefilter(monkeypatch, model_record, tmp_path, enabled):
    from test_red_native_boxed_evolution import runtime_fixture
    from test_red_goal_context import _ActionDelegate
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.red_collection import red_internal_species_id
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused
    from pokemon_red_completion.observation import MapId
    runtime, reader, unused_collection = runtime_fixture(tmp_path, count=1)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(reader.raw, map_id=MapId.CINNABAR_POKECENTER,
        party_species_ids=(*reader.raw.party_species_ids[:5], source), party_levels=(54, 55, 55, 55, 55, 32))
    scope = (context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE)
    if enabled:
        runtime = replace(runtime, native_evolution_venue_policy=native.NativeEvolutionVenuePolicy(
            model_record.model, model_record.canonical, scope))
    candidates = (*scope, context.DIGLETTS_CAVE_TRAINING_VENUE)
    monkeypatch.setattr(native, "wild_tables", lambda rom: {venue.map_id: ((10, 0x21),) for venue in candidates})
    # This test isolates configured scorer propagation, not Mansion route planning.
    # Its world is deliberately a ROM-only sentinel; provide the capability at this seam.
    transport_checks = []
    def transport_ready(rt, world, party):
        assert rt.reader is reader and world.rom == b"unit-only" and party.members
        transport_checks.append(True)
        return True
    monkeypatch.setattr(native, "_mansion_transport_ready", transport_ready)
    order = []
    monkeypatch.setattr(native, "prepare_native_training_center", lambda *a: order.append("center"))
    monkeypatch.setattr(native, "restore_native_center_party", lambda *a: order.append("nurse") or 0)
    rich = runtime.adapter.observe().party
    rich = replace(rich, members=tuple(replace(member, experience=member.level ** 3 + 100) for member in rich.members))
    monkeypatch.setattr(native, "PokemonRedPartyReader", lambda port: N(read=lambda: rich))
    def select(observation, **arguments):
        assert enabled
        order.append("model")
        assert arguments["model"] is model_record.model and arguments["model_sha256"] == model_record.canonical
        assert tuple(venue.map_id for venue in arguments["venues"]) == tuple(venue.map_id for venue in scope)
        return arguments["venues"][0]
    monkeypatch.setattr(native, "select_native_evolution_model_venue", select)
    def train(*args, **kwargs):
        order.append("train")
        expected = scope[0] if enabled else scope[1]
        assert tuple(venue.map_id for venue in kwargs["venues"]) == (expected.map_id,)
        raise EvolutionTrainingPaused(0, 0)
    monkeypatch.setattr(context, "run_red_team_balancing", train)
    bound = native.bind_native_boxed_evolution(runtime, N(rom=b"unit-only"),
        prefer_highest_supported_venue=True)
    actions = CountingExecutor(_ActionDelegate())
    bound.party_level_evolution_executor(source, target, actions)
    assert order == ["center", "nurse"] + (["model"] if enabled else []) + ["train"]
    assert bool(transport_checks) is enabled
    assert actions.actions_executed == runtime.emulator.frame_count == 0


@pytest.mark.parametrize("fault", ["foreign_model", "forced_scope", "unknown_policy"])
def test_runtime_policy_rejects_conflicting_explicit_authority(model_record, tmp_path, fault):
    from test_red_native_boxed_evolution import runtime_fixture
    runtime, reader, unused_collection = runtime_fixture(tmp_path, count=1)
    policy = native.NativeEvolutionVenuePolicy(model_record.model, model_record.canonical,
        (context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE))
    arguments = {}
    if fault == "foreign_model":
        arguments.update(venue_model=model_record.model, venue_model_sha256="e" * 64)
    elif fault == "forced_scope":
        arguments["training_venues"] = (context.DIGLETTS_CAVE_TRAINING_VENUE,)
    else:
        policy = N(model=model_record.model)
    runtime = replace(runtime, native_evolution_venue_policy=policy)
    with pytest.raises(ValueError, match="conflict|configured native venue policy"):
        native.bind_native_boxed_evolution(runtime, N(rom=b"unit-only"), **arguments)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("early", [False, True])
def test_ordinary_backend_legacy_venue_arguments_respect_configured_mode(monkeypatch, model_record, enabled, early):
    import pokemon_red_completion.red_player_collection_options as options
    from test_red_player_collection_options import fixture
    runtime, actions, observation = fixture(monkeypatch)
    scope = (context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE)
    if enabled:
        runtime.native_evolution_venue_policy = native.NativeEvolutionVenuePolicy(
            model_record.model, model_record.canonical, scope)
    # Exact legacy shape from the ordinary backend: Cave only after eight badges,
    # Cave plus Route11 earlier, with the highest-band preference enabled.
    legacy = (context.DIGLETTS_CAVE_TRAINING_VENUE,)
    if early:
        legacy += (context.ROUTE_11_TRAINING_VENUE,)
    calls = []
    monkeypatch.setattr(options, "enumerate_red_level_evolutions", lambda *a, **k: calls.append(k) or ())
    assert options.player_collection_supplements(runtime, actions, observation, world=N(),
        prefer_highest_evolution_venue=True, evolution_training_venues=legacy) == ()
    assert calls[0]["training_venues"] == (scope if enabled else legacy)
    assert calls[0].get("prefer_highest_supported_venue", False) is (not enabled)
    assert "venue_model" not in calls[0]  # The exact runtime policy remains inherited.
    assert actions.actions_executed == runtime.emulator.frame_count == 0


def test_collection_refuses_unknown_runtime_policy_before_observation(monkeypatch):
    import pokemon_red_completion.red_player_collection_options as options
    monkeypatch.setattr(options, "_field_ready", lambda *a: pytest.fail("unknown policy reached observer"))
    with pytest.raises(ValueError, match="configured native venue policy"):
        options.player_collection_supplements(N(native_evolution_venue_policy=N()), None, None, world=None)
