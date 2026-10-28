import json
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import run_fresh_red_player as fresh
from run_fresh_red_player import (
    SCHEMA,
    model_handoff_verified,
    realized_configuration,
    retained_power_on,
    validate_fresh_plan,
)

from pokemon_red_completion.red_player_configuration import ASSEMBLY_FLAGS


def plan():
    return dict(
        schema=SCHEMA,
        partition="development",
        fit_allowed=False,
        copy_back=False,
        resume_allowed=False,
        startup="declared_squirtle_mechanics_no_teacher_combat",
        loan_identity_binding="observed_initial_starter",
        extra_boot_frames=997,
        seed=2026100901,
        limits=dict(
            decisions=6, actions=6000, frames=450000, seconds=600, heals=64, cash_debits=None
        ),
        chunk=dict(decisions=2, actions=6000, frames=450000, seconds=300),
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("parent", "/old/save"),
        ("fit_allowed", True),
        ("resume_allowed", True),
        ("copy_back", True),
        ("partition", "train"),
        ("extra_boot_frames", True),
        ("seed", -1),
        ("startup", "teacher_rival"),
        ("launch_authorized", False),
        ("readiness_only", True),
    ],
)
def test_fresh_entry_rejects_restore_teacher_and_scope_changes(key, value):
    spec = plan()
    assert validate_fresh_plan(spec) is spec
    spec[key] = value
    with pytest.raises(ValueError):
        validate_fresh_plan(spec)


def test_import_only_checks_blocked_plan_without_granting_gameplay_authority():
    spec = plan()
    spec.update(launch_authorized=False, readiness_only=True)
    original = deepcopy(spec)
    assert validate_fresh_plan(spec, import_only=True) is spec
    assert spec == original
    with pytest.raises(ValueError):
        validate_fresh_plan(spec)
    for key, value in (("parent", "/old/save"), ("fit_allowed", True),
                       ("startup", "teacher_rival"), ("extra_boot_frames", True)):
        faulty = dict(spec, **{key: value})
        with pytest.raises(ValueError):
            validate_fresh_plan(faulty, import_only=True)
    with pytest.raises(TypeError):
        validate_fresh_plan(spec, import_only=1)


@pytest.mark.parametrize("legacy_toggle", [True, False])
def test_fresh_entry_rejects_undeclared_owned_move_toggle(legacy_toggle):
    spec = plan()
    spec["owned_machine_options"] = legacy_toggle
    with pytest.raises(ValueError, match="owned machine options"):
        validate_fresh_plan(spec)


def test_fresh_entry_preserves_declared_owned_move_policy():
    spec = plan()
    spec["owned_machine_options"] = dict(
        mode="direct_attack_capacity_v1",
        reason="The model chooses compatible owned moves, not supplied recipients.",
    )
    before = deepcopy(spec)
    assert validate_fresh_plan(spec) is spec
    assert spec == before


def test_fresh_entry_preserves_valid_spectator_settings_without_changing_plan():
    spec = dict(plan(), spectator=dict(port=8769, maximum_fps=4))
    before = deepcopy(spec)
    assert validate_fresh_plan(spec) is spec
    assert spec == before


@pytest.mark.parametrize("spectator", [True, {}, {"port": 8769, "maximum_fps": 0},
    {"port": 8769, "maximum_fps": 4, "host": "0.0.0.0"}])
def test_fresh_entry_rejects_bad_spectator_settings_even_in_import_mode(spectator):
    spec = dict(plan(), spectator=spectator)
    with pytest.raises(ValueError, match="spectator"):
        validate_fresh_plan(spec, import_only=True)


def test_observed_starter_binding_keeps_template_and_blocks_only_declared_teacher():
    template = dict(
        goal_model_sha256="b" * 64,
        assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        excluded_profiles=(),
        quote_capture_route_work=True,
    )
    before = deepcopy(template)
    config = realized_configuration(
        template,
        origin_sha256="a" * 64,
        origin_id="fresh",
        starter_ref="observed-starter",
        teacher_profiles=(("advance_story", "c" * 64),),
    )
    assert template == before and config.loanable_specimen_refs == ("observed-starter",)
    assert not config.admits(N(kind=N(value="advance_story"), binding_ref="native:" + "c" * 64))
    assert config.admits(N(kind=N(value="advance_story"), binding_ref="native:" + "d" * 64))


def test_real_fresh_teacher_overlap_preserves_exact_exclusions_and_order():
    teacher = ("advance_story", "006ebf832ae16c10f36622368ed7458183ac88de5ef325ece31e227b6bb3c2e9")
    other = ("evolve_species", "c" * 64)
    additional = ("advance_story", "d" * 64)
    template = dict(
        goal_model_sha256="b" * 64,
        assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        excluded_profiles=[list(other), list(teacher)],
        quote_capture_route_work=True,
    )
    before = deepcopy(template)
    profiles = (teacher, additional)
    config = realized_configuration(
        template, origin_sha256="a" * 64, origin_id="fresh",
        starter_ref="observed-starter", teacher_profiles=profiles,
    )
    assert template == before and profiles == (teacher, additional)
    assert config.excluded_profiles == (other, teacher, additional)
    for kind, profile in config.excluded_profiles:
        assert not config.admits(N(kind=N(value=kind), binding_ref="native:" + profile))
    assert config.admits(N(kind=N(value="advance_story"), binding_ref="native:" + "e" * 64))
    repeated = realized_configuration(
        dict(template, excluded_profiles=config.excluded_profiles),
        origin_sha256="a" * 64, origin_id="fresh", starter_ref="observed-starter",
        teacher_profiles=profiles,
    )
    assert repeated == config and repeated.sha256 == config.sha256


def test_realization_collapses_only_an_identical_kind_and_profile_pair():
    template = dict(
        goal_model_sha256="b" * 64,
        assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        excluded_profiles=(("evolve_species", "c" * 64),),
        quote_capture_route_work=True,
    )
    config = realized_configuration(
        template, origin_sha256="a" * 64, origin_id="fresh", starter_ref="observed-starter",
        teacher_profiles=(("advance_story", "c" * 64),),
    )
    assert config.excluded_profiles == (
        ("evolve_species", "c" * 64), ("advance_story", "c" * 64)
    )


@pytest.mark.parametrize("faulty_list", ["base", "teacher"])
@pytest.mark.parametrize(
    "fault", ["duplicate", "unknown_kind", "short_hash", "upper_hash", "short_pair"]
)
def test_realization_does_not_normalize_invalid_or_duplicate_input_lists(faulty_list, fault):
    pair = ("advance_story", "c" * 64)
    invalid = {
        "duplicate": (pair, pair),
        "unknown_kind": (("teacher_override", "c" * 64),),
        "short_hash": (("advance_story", "c" * 63),),
        "upper_hash": (("advance_story", "C" * 64),),
        "short_pair": (("advance_story",),),
    }[fault]
    template = dict(
        goal_model_sha256="b" * 64,
        assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        excluded_profiles=invalid if faulty_list == "base" else (pair,),
        quote_capture_route_work=True,
    )
    before = deepcopy(template)
    with pytest.raises(ValueError, match="exclusions must name exact kind/profile pairs"):
        realized_configuration(
            template, origin_sha256="a" * 64, origin_id="fresh", starter_ref="observed-starter",
            teacher_profiles=invalid if faulty_list == "teacher" else (pair,),
        )
    assert template == before


def test_realization_keeps_teacher_pair_type_validation_when_it_overlaps():
    template = dict(
        goal_model_sha256="b" * 64,
        assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
        excluded_profiles=(("advance_story", "c" * 64),),
        quote_capture_route_work=True,
    )
    with pytest.raises(ValueError, match="exclusions must name exact kind/profile pairs"):
        realized_configuration(
            template, origin_sha256="a" * 64, origin_id="fresh", starter_ref="observed-starter",
            teacher_profiles=(["advance_story", "c" * 64],),
        )


def test_error_retains_terminal_before_emulator_stops(tmp_path):
    class Emulator:
        _backend = None
        frame_count = 123
        pressed_buttons = frozenset()

        def __enter__(self):
            self._backend = object()
            return self

        def save_state_bytes(self):
            assert self._backend is not None
            return b"earned-current-terminal"

        def __exit__(self, *args):
            self._backend = None

    result = {}
    with pytest.raises(RuntimeError), retained_power_on(Emulator(), tmp_path, result):
        raise RuntimeError("native failure")
    assert (tmp_path / "terminal.state").read_bytes() == b"earned-current-terminal"
    assert result["worker_stopped"] and result["released"] and result["frames"] == 123


def test_model_handoff_cannot_pass_from_initialization_or_failed_admission():
    assert not model_handoff_verified([])
    assert not model_handoff_verified([dict(model_decisions=0, stop_reason="menu_unavailable")])
    assert model_handoff_verified([dict(model_decisions=1, outcomes=[])])
    assert not model_handoff_verified(
        [dict(model_decisions=1, outcomes=[dict(error_type="ValueError")])]
    )


@pytest.mark.parametrize("fault", [
    None, "unknown_error", "wrong_state", "no_digest", "wrong_binding", "substitution",
    "input", "false_zero", "unqualified", "erased_failure", "wrong_schema",
])
def test_readiness_adjudicates_only_matching_confirmed_control_receipt(fault):
    state = "b" * 64
    outcome = dict(
        error_type="RouteExecutionError",
        error="field dialogue is not an admitted native faint",
        terminal_state_sha256=state,
    )
    receipt = dict(
        schema="pokemon.red.qualified-native-control-handoff.v1",
        state_sha256=state, binding_ref="pokemon.red:retained-engagement:" + state,
        qualified=True, failed_transport_preserved=True, strategic_substitution=False,
        inputs=0, frames=0, model_queries=0,
    )
    if fault == "unknown_error":
        outcome["error"] = "unexplained transport fault"
    elif fault == "wrong_state":
        receipt["state_sha256"] = "c" * 64
    elif fault == "no_digest":
        receipt["state_sha256"] = None
    elif fault == "wrong_binding":
        receipt["binding_ref"] = "ordinary-strategy"
    elif fault == "substitution":
        receipt["strategic_substitution"] = True
    elif fault == "input":
        receipt["inputs"] = 1
    elif fault == "false_zero":
        receipt["inputs"] = False
    elif fault == "unqualified":
        receipt["qualified"] = False
    elif fault == "erased_failure":
        receipt["failed_transport_preserved"] = False
    elif fault == "wrong_schema":
        receipt["schema"] = "arbitrary-success"
    episodes = [dict(model_decisions=1, outcomes=[outcome])]
    original = deepcopy(episodes)
    assert not model_handoff_verified(episodes)
    assert model_handoff_verified(
        episodes, recovered_control_handoffs=(receipt,)
    ) is (fault is None)
    assert episodes == original


@pytest.mark.parametrize("machine_mode", [None, "direct_attack_capacity_v1",
    "boxed_frontier_attack_capacity_v2", "boxed_frontier_evolution_bundles_v3"])
@pytest.mark.parametrize("control_handoff", [None, "accepted", "rejected"])
@pytest.mark.parametrize("model_version", [7, 9])
def test_fresh_driver_renews_same_emulator_and_forwards_policy_without_loading(
    tmp_path, monkeypatch, control_handoff, machine_mode, model_version
):
    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()
        _backend = None
        state = b"power-on"
        loads = 0

        def __enter__(self):
            self._backend = object()
            return self

        def __exit__(self, *args):
            self._backend = None

        def save_state_bytes(self):
            return self.state

        def load_state_bytes(self, state):
            self.loads += 1
            pytest.fail("fresh renewals must not restore a state")

    emulator = Emulator()
    import run_configured_red_player as configured
    import pokemon_red_completion.red_boxed_machine_options as boxed
    import pokemon_red_completion.red_prepared_evolution_options as prepared

    recipe_calls = []
    monkeypatch.setattr(configured, "owned_machine_options", lambda *a, **k: ("party-machine",))
    monkeypatch.setattr(boxed, "boxed_frontier_machine_options", lambda *a, **k: ("boxed-machine",))

    def quotes(*args, rom, world):
        assert rom == b"fixture-ROM" and world.startswith("fresh-route-")
        return ("typed-machine-choice",)

    def recipes(*args, **kwargs):
        assert kwargs["machine_choices"] == ("typed-machine-choice",)
        assert kwargs["evolution_options"] == ("ordinary-evolution",)
        assert kwargs["enumerate_collection"](*args) == ("ordinary-evolution",)
        recipe_calls.append(kwargs)
        return ("prepared-evolution",)

    monkeypatch.setattr(boxed, "quoted_boxed_frontier_machine_options", quotes)
    monkeypatch.setattr(prepared, "prepared_evolution_options", recipes)

    def digest(path):
        return sha256(path.read_bytes()).hexdigest()

    model = N(model_sha256="b" * 64, feature_version=model_version)
    initial_holder = dict(refs=("starter",), plan=object())
    teacher = N(
        kind=N(value="advance_story"),
        configuration_sha256="c" * 64,
        mechanic=fresh.RedGoalMechanic.OAKS_ERRAND,
    )

    def initial_factory(controller):
        runtime = N(emulator=controller, profile=N(providers=(teacher,)))
        # The real bootstrap assembly returns the runtime, but does not retain
        # it in this holder. Only configured continuation assembly does that.
        return runtime

    c = N(
        ROM=tmp_path / "rom",
        REPO=tmp_path,
        PyBoyAdapter=lambda *a, **k: emulator,
        digest=digest,
        source_code_identity=lambda repo: "d" * 64,
    )
    c.ROM.write_bytes(b"fixture-ROM")
    backend = N(
        c=c, shared=N(assembly=lambda *a, **k: (initial_factory, None, initial_holder, None))
    )
    monkeypatch.setattr(fresh.importlib, "import_module", lambda name: backend)
    monkeypatch.setattr(fresh, "bind_player_package", lambda *a, **k: dict(source_commit="e" * 40))
    monkeypatch.setattr(
        fresh, "load_player_goal_model_record_bytes", lambda *a, **k: N(model=model)
    )
    monkeypatch.setattr(fresh, "initialize_private_root", lambda *a, **k: object())
    monkeypatch.setattr(fresh, "_OpeningActions", lambda *a: N(delegate=N(attempted_actions=1)))
    monkeypatch.setattr(fresh, "requires_compulsory_settlement", lambda runtime: False)

    def opening(*args, **kwargs):
        emulator.state, emulator.frame_count = b"starter", 997
        return N(passed=True, verified_objectives=("choose_starter",), public_dict=lambda: {})

    monkeypatch.setattr(fresh, "run_opening_chapter", opening)
    monkeypatch.setattr(
        fresh,
        "capture_player_continuation",
        lambda runtime, **kwargs: dict(
            state_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
            spent=kwargs["spent"],
        ),
    )
    assembled, calls = [], []

    def assembly(backend, config, parent, output, *, plan_path, model_feature_version):
        assert model_feature_version == model_version
        declared = json.loads(plan_path.read_bytes())
        assert declared["goal_selection"]["mode"] == "exploration"
        context = json.loads((parent / "CONTEXT.json").read_bytes())
        assert declared.get("owned_machine_options") == spec.get("owned_machine_options")
        holder = dict(prior_spent=context["spent"],
            configured_route=N(route_world=f"fresh-route-{len(assembled)}"))
        assembled.append(context["state_sha256"])

        def factory(controller):
            holder["runtime"] = N(emulator=controller, reader=N(read=lambda:N(badge_bits=255)))
            return holder["runtime"]

        menu = N(enumerate_owned_machines=lambda *a:("existing-machine",),
            enumerate_collection=lambda *a:("ordinary-evolution",))
        return (parent / "terminal.state").read_bytes(), factory, menu, holder, object()

    def chunk(**kwargs):
        menu, runtime = kwargs["menu"], kwargs["holder"]["runtime"]
        expected_machines = ("existing-machine",)
        if machine_mode:
            expected_machines += ("party-machine",)
        if machine_mode in ("boxed_frontier_attack_capacity_v2", "boxed_frontier_evolution_bundles_v3"):
            expected_machines += ("boxed-machine",)
        assert menu.enumerate_owned_machines(runtime, object(), object()) == expected_machines
        expected_evolutions = ("ordinary-evolution",)
        if machine_mode == "boxed_frontier_evolution_bundles_v3":
            expected_evolutions += ("prepared-evolution",)
        assert menu.enumerate_collection(runtime, object(), object()) == expected_evolutions
        if machine_mode == "boxed_frontier_evolution_bundles_v3":
            assert recipe_calls[-1]["admits"] == kwargs["configuration"].admits
            assert not recipe_calls[-1]["admits"](N(kind=N(value="advance_story"), binding_ref="native:"+"c"*64))
        calls.append(kwargs)
        ordinal = kwargs["ordinal"]
        emulator.state, emulator.frame_count = f"earned-{ordinal}".encode(), 997 + ordinal * 20
        spent = dict(kwargs["holder"]["prior_spent"])
        for key, delta in dict(decisions=2, actions=3, frames=20, seconds=1).items():
            spent[key] += delta
        context = dict(state_sha256=sha256(emulator.state).hexdigest(), spent=spent)
        output = kwargs["output"]
        (output / "terminal.state").write_bytes(emulator.state)
        (output / "CONTEXT.json").write_text(json.dumps(context))
        error_type = (
            "RouteExecutionError" if control_handoff else "ControllerFrameBudgetExhausted"
        ) if ordinal == 1 else None
        outcome = dict(error_type=error_type)
        if control_handoff and ordinal == 1:
            outcome.update(
                error="field dialogue is not an admitted native faint",
                terminal_state_sha256=context["state_sha256"],
            )
        result = dict(
            released=True,
            field_ready=ordinal > 1,
            error=None,
            state_sha256=context["state_sha256"],
            native_facts={},
            chunk_costs=dict(actions_attempted=3, frames=20),
            episode=dict(
                model_decisions=1,
                stop_reason="execution_failed" if ordinal == 1 else "decision_budget",
                outcomes=[outcome],
            ),
        )
        return result, context

    monkeypatch.setattr(fresh, "assemble_configured_player", assembly)
    monkeypatch.setattr(fresh, "execute_player_chunk", chunk)
    handoff_calls = []

    def qualify(row, *, runtime, menu):
        handoff_calls.append(row["state_sha256"])
        if control_handoff == "rejected":
            return None
        return dict(
            schema="pokemon.red.qualified-native-control-handoff.v1",
            qualified=True, state_sha256=row["state_sha256"],
            binding_ref="pokemon.red:retained-engagement:" + row["state_sha256"],
            failed_transport_preserved=True, strategic_substitution=False,
            inputs=0, frames=0, model_queries=0,
        )

    monkeypatch.setattr(fresh, "qualified_menu_control_handoff", qualify)
    spec = plan()
    actor = tmp_path / "actor.json"
    actor.write_bytes(b"actor")
    spec.update(
        runtime_package=dict(path="manifest", sha256="a" * 64),
        backend_module="backend",
        goal_model_record=dict(path=str(actor), content_sha256=digest(actor)),
        goal_selection=dict(mode="exploration", reason="Same frozen policy."),
        configuration_template=dict(
            goal_model_sha256=model.model_sha256,
            assembly_flags=tuple((k, k != "protect_party_species") for k in sorted(ASSEMBLY_FLAGS)),
            excluded_profiles=(),
            quote_capture_route_work=True,
        ),
    )
    if machine_mode:
        spec["owned_machine_options"] = dict(mode=machine_mode,
            reason="Reuse the same declared preparation capability in fresh renewals.")
    if control_handoff:
        spec["automatic_runtime_renewal"] = dict(mode="live_chunks_v1", reason="Declared renewal.")
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(spec))
    before = path.read_bytes()
    fresh.run(path)
    assert path.read_bytes() == before
    result = json.loads((tmp_path / "RESULT.json").read_bytes())
    rejected = control_handoff == "rejected"
    assert len(calls) == (1 if rejected else 3)
    assert emulator.loads == 0 and emulator._backend is None
    assert result["state_loads"] == 0 and result["worker_stopped"]
    assert result["ready"] is not rejected
    assert result["spent"]["decisions"] == (2 if rejected else 6)
    assert result["spent"]["actions"] == (4 if rejected else 10)
    assert len(set(assembled)) == (1 if rejected else 3)
    assert len(handoff_calls) == (1 if control_handoff else 0)
    if control_handoff == "accepted":
        first = json.loads((tmp_path / "runs/segment-001/RESULT.json").read_bytes())
        assert first["continuation_reason"] == "automatic_control_recovery"
        assert first["episode"]["outcomes"][0]["error_type"] == "RouteExecutionError"
        assert len(result["verified_automatic_control_recoveries"]) == 1
        assert not result["pending_automatic_control_recoveries"]
    assert all(call["plan"]["goal_selection"] == spec["goal_selection"] for call in calls)
    assert len(recipe_calls) == (len(calls) if machine_mode == "boxed_frontier_evolution_bundles_v3" else 0)
