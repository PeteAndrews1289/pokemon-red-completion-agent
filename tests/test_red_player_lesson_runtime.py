"""ROM-free boundary tests; these are not native cartridge qualification."""

import copy
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_post_battle_strategy import aftermath
from test_private_artifacts import _make_store
from test_red_player_lesson import player_records

import pokemon_red_completion.red_player_lesson_runtime as module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind, GoalManagerQuestion
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_native_curriculum import (
    NativeCurriculumInput,
    load_native_curriculum,
)


class Emulator:
    frame_count = 0
    pressed_buttons = frozenset()
    partial = False

    def save_state_bytes(self):
        return str(self.frame_count).encode()

    def press(self, button):
        self.pressed_buttons |= {button}

    def release(self, button):
        self.pressed_buttons -= {button}

    def tick(self, frames):
        self.frame_count += min(frames, 2) if self.partial else frames
        if self.partial:
            raise RuntimeError("simulated interrupted tick")


@pytest.mark.parametrize('ups',[0,1,2,3])
def test_live_pp_readiness_uses_native_capacity_without_changing_legacy_snapshot(
    tmp_path,monkeypatch,ups,
):
    _,emulator,args=fixture(tmp_path,monkeypatch)
    capture=module.capture_player_lesson_snapshot
    def current(runtime):
        observation,snapshot=capture(runtime)
        raw=observation.raw
        raw.party_count=len(snapshot['party'])
        raw.party_moves=tuple(tuple(m[0] for m in p['moves']) for p in snapshot['party'])
        raw.party_pp=tuple((5|(ups<<6),3,0,0) for _ in snapshot['party'])
        return observation,snapshot
    monkeypatch.setattr(module,'capture_player_lesson_snapshot',current)
    runtime=args['runtime_factory'](emulator)
    settings=dict(battle=None,combat_specimen_refs=args['combat_specimen_refs'],
                  remaining_budget=(1.,)*5)
    legacy=module.observe_native_player_boundary(runtime,**settings)
    live=module.observe_native_player_boundary(runtime,include_live_pp_readiness=True,**settings)
    old=dict(zip(legacy.readiness.public_dict()['names'],legacy.readiness.values,strict=True))
    new=dict(zip(live.readiness.public_dict()['names'],live.readiness.values,strict=True))
    assert old['current.pp_known']==0 and old['current.pp_fraction']==0
    assert new['current.pp_known']==1
    assert new['current.pp_fraction']==pytest.approx(8/(60+7*ups))
    assert live.lesson_snapshot==legacy.lesson_snapshot and live.state==legacy.state==b'0'
    assert emulator.frame_count==0 and not emulator.pressed_buttons


@pytest.mark.parametrize('permission',[None,0,1,'yes'])
def test_live_pp_permission_is_strict_before_any_observation(permission):
    with pytest.raises(TypeError,match='explicit boolean'):
        module.observe_native_player_boundary(None,battle=None,combat_specimen_refs=(),
            remaining_budget=(),include_live_pp_readiness=permission)


@pytest.mark.parametrize("permission", [None, 0, 1, "yes"])
def test_atomic_teacher_pp_permission_is_strict_before_input(tmp_path, monkeypatch, permission):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError, match="explicit boolean"):
        module.record_native_player_lesson(store, **kwargs, include_live_pp_readiness=permission)
    assert emulator.frame_count == 0 and not emulator.pressed_buttons


def test_atomic_teacher_forwards_explicit_live_pp_readiness(tmp_path, monkeypatch):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    boundary = module.observe_native_player_boundary
    flags = []
    def observed(*args, **settings):
        flags.append(settings["include_live_pp_readiness"])
        # The fixture has no native PP reader; test forwarding, not PP arithmetic.
        return boundary(*args, **{**settings, "include_live_pp_readiness": False})
    monkeypatch.setattr(module, "observe_native_player_boundary", observed)
    result = module.record_native_player_lesson(store, **kwargs, include_live_pp_readiness=True)
    assert result["admitted"] and flags == [True]


@pytest.mark.parametrize("ordinal", [9999, 10000, 100000, 200000])
def test_action_record_ids_keep_safe_length_and_identity(ordinal):
    ids = set()
    for kind in ("action", "trace"):
        for declaration in ("a" * 64, "b" * 64):
            name = module.native_action_record_id(kind, declaration, ordinal)
            assert len(name) <= 80
            legacy = f"rnl-{kind}-{declaration}-{ordinal}"
            assert name == (legacy if len(legacy) <= 80 else
                            f"rnl-{kind}-{sha256(legacy.encode('ascii')).hexdigest()}")
            ids.add(name)
    assert len(ids) == 4


def test_recorded_action_limit_is_typed_before_any_new_input(tmp_path):
    _, _, store = _make_store(tmp_path)
    emulator = Emulator()
    controller = module.NativeLessonController(emulator, maximum_frames=1000)
    actions = module._RecordedActions(controller, store, "a" * 64, 1)
    actions.enabled = True
    actions.trace = [None]
    with pytest.raises(module.ControllerActionBudgetExhausted) as caught:
        actions.execute(MacroAction(MacroActionKind.WAIT))
    assert caught.value.maximum_actions == caught.value.attempted_actions == 1
    assert emulator.frame_count == 0 and len(actions.trace) == 1


@pytest.mark.parametrize("partial", [False, True])
def test_recorded_actions_cross_ten_thousand_boundary(tmp_path, partial):
    _, _, store = _make_store(tmp_path)
    emulator = Emulator()
    controller = module.NativeLessonController(emulator, maximum_frames=1000)
    actions = module._RecordedActions(controller, store, "a" * 64, 10002)
    actions.enabled = True
    actions.trace = [None] * 9999  # Skip historical input, exercise the actual writer.
    actions.execute(MacroAction(MacroActionKind.WAIT))
    emulator.partial = partial
    if partial:
        with pytest.raises(RuntimeError, match="simulated interrupted tick"):
            actions.execute(MacroAction(MacroActionKind.WAIT))
    else:
        actions.execute(MacroAction(MacroActionKind.WAIT))
    for ordinal in (9999, 10000):
        intent = store.find_sealed_record(
            module.native_action_record_id("action", "a" * 64, ordinal)
        ).read()
        trace = store.find_sealed_record(
            module.native_action_record_id("trace", "a" * 64, ordinal)
        ).read()
        assert intent["ordinal"] == trace["ordinal"] == ordinal
        assert trace["succeeded"] is (ordinal == 9999 or not partial)
    assert not controller.input_enabled


@pytest.mark.parametrize("kind,declaration,ordinal", [
    ("other", "a" * 64, 0), ("action", "A" * 64, 0),
    ("trace", "a" * 63, 0), ("action", "a" * 64, -1),
    ("trace", "a" * 64, True),
])
def test_action_record_ids_reject_invalid_identity(kind, declaration, ordinal):
    with pytest.raises(ValueError, match="identity"):
        module.native_action_record_id(kind, declaration, ordinal)


def fixture(tmp_path, monkeypatch, *, kind=GoalKind.ADVANCE_STORY, fault=None,
            record_factory=player_records):
    plan, result = record_factory(tmp_path / "documents", kind)
    _, _, store = _make_store(tmp_path)
    emulator = Emulator()
    emulator.partial = fault == "partial"
    question = GoalManagerQuestion.from_policy_input(plan["question"])
    current = dict(done=False)
    runtime = None

    def capture(rt):
        # Exercise recorder's snapshot seam with validated existing lesson fixtures.
        doc = result["after"] if current["done"] else plan["before"]
        snapshot = result["player_lesson"] if current["done"] else plan["player_lesson"]["before"]
        economy = result.get("economy_after") if current["done"] else plan.get("economy_before")
        observation = NS(
            situation=question.situation,
            public_dict=lambda: copy.deepcopy(doc),
            raw=NS(player_money=economy["cash"] if economy else 3000,
                   bag_items=tuple((int(ref.rsplit("-", 1)[1]), count)
                                   for ref, count in economy["inventory"]) if economy else ()),
        )
        if fault == "audit_input" and current["done"]:
            rt.emulator.tick(1)
        if fault == "capture_failure" and emulator.frame_count:
            raise ValueError("unreadable terminal")
        return observation, copy.deepcopy(snapshot)

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(module, "project_registered_observation", lambda o, _: o)

    def factory(controller):
        nonlocal runtime

        def enumerator(actions):
            if fault == "enumerate_input":
                actions.execute(MacroAction(MacroActionKind.WAIT))
            def execute():
                # Published declaration is required before the first action.
                assert actions.delegate.declaration != "unarmed"
                if fault == "bypass":
                    controller.tick(1)
                actions.execute(MacroAction(MacroActionKind.WAIT))
                if fault == "execution_failure":
                    raise RuntimeError("goal stopped after a real action")
                if fault == "budget":
                    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=100000))
                current["done"] = fault != "false_success"
                return GoalExecutionReport(actions.actions_executed, controller.frames_executed, {})

            def verify(_report):
                if fault == "verify_action":
                    actions.execute(MacroAction(MacroActionKind.WAIT))
                if fault == "invalid_verdict":
                    return NS(status="succeeded")
                if fault == "verify_input":
                    controller.press("a")
                if fault == "reset":
                    controller.load_state_bytes(b"bad")
                return GoalVerification.succeeded()

            old = question.opportunities[0]
            binding = ExecutableGoalBinding(
                old.binding_ref, kind, old.estimated_effort, old.estimated_risk, execute, verify,
                resource_quote=old.resource_quote,
            )
            return NS(enumerate=lambda _: GoalBindingSet(question.opportunities, (binding,)))

        runtime = NS(emulator=controller, registration_policy=object(), enumerator=enumerator)
        return runtime

    source = dict(plan["source"], state_sha256=sha256(emulator.save_state_bytes()).hexdigest())
    kwargs = dict(
        emulator=emulator,
        runtime_factory=factory,
        source=source,
        selected_index=0,
        target=plan["player_lesson"]["target"],
        battle=aftermath(),
        combat_specimen_refs=(plan["player_lesson"]["before"]["party"][0]["specimen_ref"],),
        remaining_budget=(1.0,) * 5,
        target_cash=3000,
        maximum_actions=5,
        maximum_frames=1000,
    )
    return store, emulator, kwargs


@pytest.mark.parametrize("kind", [GoalKind.RESUPPLY, GoalKind.ACQUIRE_SPECIES])
def test_live_resource_binding_retains_readiness_and_measured_economy(tmp_path, monkeypatch, kind):
    from test_red_player_resource_lesson import records

    store, emulator, kwargs = fixture(tmp_path, monkeypatch, kind=kind, record_factory=records)
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["admitted"] and result["succeeded"], result
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    assert row.feature_version == 5
    assert row.outcome.economy.cash_delta == (-1000 if kind is GoalKind.RESUPPLY else 0)
    assert result["frames"] == emulator.frame_count > 0


@pytest.mark.parametrize("mutate", [False, True])
def test_custom_binding_enumerator_shares_guarded_native_port(tmp_path, monkeypatch, mutate):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    calls = []

    def enumerate_bindings(rt, actions, observation):
        calls.append((rt, actions, observation))
        if mutate:
            rt.emulator.tick(1)
        return rt.enumerator(actions).enumerate(observation)

    kwargs["enumerate_bindings"] = enumerate_bindings
    if mutate:
        with pytest.raises(RuntimeError):
            module.record_native_player_lesson(store, **kwargs)
        assert emulator.frame_count == 0
    else:
        result = module.record_native_player_lesson(store, **kwargs)
        assert result["admitted"] and len(calls) == 1


def test_preflight_validates_exact_lesson_without_consuming_it(tmp_path, monkeypatch):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    before = emulator.save_state_bytes()
    preflight = module.record_native_player_lesson(store, **kwargs, preflight_only=True)
    assert not preflight["attempted"] and not preflight["admitted"]
    assert preflight["input_frames"] == 0 and emulator.save_state_bytes() == before
    assert store.find_sealed_record("rnc-plan-" + preflight["declaration_sha256"],
                                    expected_kind="red_native_curriculum_plan") is None
    actual = module.record_native_player_lesson(store, **kwargs)
    assert actual["admitted"] and actual["declaration_sha256"] == preflight["declaration_sha256"]


def test_preflight_rejects_invalid_target_without_input(tmp_path, monkeypatch):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    kwargs["target"] = {"objective": "invented"}
    with pytest.raises(ValueError):
        module.record_native_player_lesson(store, **kwargs, preflight_only=True)
    assert emulator.frame_count == 0


@pytest.mark.parametrize("mode", ["valid", "input", "invalid"])
def test_challenge_measurement_is_preinput_and_durably_reconstructable(tmp_path, monkeypatch, mode):
    from pokemon_red_completion.player_option_challenge import OptionChallenge

    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    challenge = OptionChallenge.from_levels(combat_levels=(40,), opponent_levels=(38, 42))
    calls = []

    def observe(rt, binding, boundary):
        calls.append(binding.binding_ref)
        assert emulator.frame_count == 0
        if mode == "input":
            rt.emulator.tick(1)
        return challenge if mode != "invalid" else challenge.public_dict()

    kwargs["observe_challenge"] = observe
    if mode != "valid":
        with pytest.raises((ValueError, RuntimeError, TypeError)):
            module.record_native_player_lesson(store, **kwargs)
        assert emulator.frame_count == 0
        return
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["admitted"] and result["succeeded"] and len(calls) == 1
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    assert row.feature_version == 6 and row.outcome.verified_success
    assert any(row.features[-54:])


@pytest.mark.parametrize(
    "kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM]
)
def test_live_binding_to_durable_native_import(tmp_path, monkeypatch, kind):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, kind=kind)
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["admitted"] and result["succeeded"]
    assert result["actions_attempted"] == result["actions_completed"] == 1
    assert result["frames"] == emulator.frame_count > 0
    assert result["elapsed_seconds"] >= 0
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    assert row.feature_version == 5 and row.outcome.verified_success
    assert row.outcome.action_cost > 0 and row.outcome.frame_cost > 0
    assert not row.public_dict()["comparative_choice"]
    assert (
        store.find_sealed_record(
            "rnl-attempt-" + result["declaration_sha256"], expected_kind="red_native_lesson_attempt"
        ).read()
        == result
    )


@pytest.mark.parametrize(
    "fault",
    [
        "partial",
        "budget",
        "bypass",
        "false_success",
        "capture_failure",
        "verify_input",
        "audit_input",
        "reset",
        "invalid_verdict",
        "verify_action",
    ],
)
def test_bad_attempt_retains_diagnostics_without_success(tmp_path, monkeypatch, fault):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, fault=fault)
    result = module.record_native_player_lesson(store, **kwargs)
    assert not result["succeeded"]
    assert result["error_type"]
    assert result["frames"] == emulator.frame_count <= 1000
    assert not emulator.pressed_buttons
    if fault in {
        "partial",
        "budget",
        "bypass",
        "false_success",
        "capture_failure",
        "audit_input",
        "invalid_verdict",
    }:
        assert not result["admitted"]
    if fault == "partial":
        assert result["frames"] == 1 and result["trace"][0]["succeeded"] is False


def test_actor_and_teacher_share_fresh_readiness_projection(tmp_path, monkeypatch):
    from test_red_live_option_menu import _ordinary_bindings, _situation

    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    original_capture = module.capture_player_lesson_snapshot

    def capture(rt):
        observation, snapshot = original_capture(rt)
        observation.situation = _situation(resources=0.1)
        return observation, snapshot

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    calls = []
    runtime.enumerator = lambda actions: NS(enumerate=lambda before: _ordinary_bindings(calls))
    args = {
        name: kwargs[name]
        for name in (
            "battle",
            "combat_specimen_refs",
            "remaining_budget",
        )
    }
    boundary = module.observe_native_player_boundary(runtime, **args)
    options = module.observe_native_player_options(
        runtime,
        object(),
        **args,
        target_cash=3000,
        ordering_seed_sha256="a" * 64,
    )
    assert options.menu.feature_version == 5
    assert all(c.readiness == boundary.readiness for c in options.menu.candidates)
    assert options.menu.context.economy_snapshot == boundary.economy
    # Re-observation after consumed budget is not cached.
    args["remaining_budget"] = (0.5,) * 5
    changed = module.observe_native_player_options(
        runtime,
        object(),
        **args,
        target_cash=3000,
        ordering_seed_sha256="a" * 64,
    )
    assert changed.menu.candidate_vector(0) != options.menu.candidate_vector(0)
    assert changed.menu.candidates[0].readiness.values[-5:] == (0.5,) * 5
    assert emulator.frame_count == 0 and not calls
    assert not emulator.pressed_buttons


def test_live_menu_rejects_enumeration_that_changes_state(tmp_path, monkeypatch):
    from test_red_live_option_menu import _ordinary_bindings, _situation

    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    original_capture = module.capture_player_lesson_snapshot

    def capture(rt):
        observation, snapshot = original_capture(rt)
        observation.situation = _situation(resources=0.1)
        return observation, snapshot

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)

    def enumerate_options(before):
        emulator.tick(1)
        return _ordinary_bindings([])

    runtime.enumerator = lambda _: NS(enumerate=enumerate_options)
    with pytest.raises(ValueError, match="menu changed state"):
        module.observe_native_player_options(
            runtime,
            object(),
            **{
                name: kwargs[name]
                for name in (
                    "battle",
                    "combat_specimen_refs",
                    "remaining_budget",
                    "target_cash",
                )
            },
            ordering_seed_sha256="a" * 64,
        )


@pytest.mark.parametrize("support", [False, True])
@pytest.mark.parametrize("alternatives", ["none", "ordinary", "supplemental"])
@pytest.mark.parametrize("goal_kind", [
    GoalKind.EVOLVE_SPECIES, GoalKind.RESUPPLY, GoalKind.ACQUIRE_SPECIES,
    GoalKind.DEVELOP_TEAM, GoalKind.MANAGE_STORAGE,
])
def test_sole_supplemental_qualified_goal_reuses_support_only_without_choice(
    tmp_path, monkeypatch, support, alternatives, goal_kind,
):
    from dataclasses import replace

    from test_red_live_option_menu import (
        _binding,
        _fishing_candidate,
        _no_ordinary_bindings,
        _ordinary_bindings,
        _situation,
    )

    from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
    from pokemon_red_completion.red_live_option_menu import (
        RedLiveOptionMenuError,
        RedLiveOptionSet,
        supplemental_live_option,
    )
    from pokemon_red_completion.red_player_support import RedPlayerSupport

    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    original_capture = module.capture_player_lesson_snapshot

    def capture(rt):
        observed, snapshot = original_capture(rt)
        observed.situation = _situation(resources=0.1)
        return observed, snapshot

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    calls = []
    original = _ordinary_bindings(calls) if alternatives == "ordinary" else _no_ordinary_bindings()
    runtime.enumerator = lambda _: NS(enumerate=lambda _: original)
    supplements = []
    for index in range(2 if alternatives == "supplemental" else 1):
        binding = _binding(goal_kind, binding_ref=f"singleton-{index}", calls=calls)
        candidate = _fishing_candidate(f"row-{index}", travel=0.2)
        kind = {GoalKind.EVOLVE_SPECIES: LivingDexOptionKind.EVOLVE,
                GoalKind.RESUPPLY: LivingDexOptionKind.RESUPPLY,
                GoalKind.DEVELOP_TEAM: LivingDexOptionKind.DEVELOP,
                GoalKind.MANAGE_STORAGE: LivingDexOptionKind.MANAGE_STORAGE,
                GoalKind.ACQUIRE_SPECIES: LivingDexOptionKind.ACQUIRE}[goal_kind]
        candidate = replace(candidate, features=replace(candidate.features, kind=kind))
        supplements.append(supplemental_live_option(binding, candidate))
    args = {name: kwargs[name] for name in
            ("battle", "combat_specimen_refs", "remaining_budget", "target_cash")}
    args.update(allow_support=support, supplements=tuple(supplements),
                ordering_seed_sha256="a" * 64)
    if not support and alternatives == "none":
        with pytest.raises(RedLiveOptionMenuError, match="distinct executable"):
            module.observe_native_player_options(runtime, object(), **args)
    else:
        options = module.observe_native_player_options(runtime, object(), **args)
        if alternatives == "none":
            assert isinstance(options, RedPlayerSupport)
            assert options.binding is supplements[0].binding
            public = options.public_dict()
            assert public["model_queries"] == 0 and public["comparative_choice"] is False
            assert public["support_role"] == "forced_singleton"
            assert public["selected_kind"] == goal_kind.value
            untouched = tuple(o for o in original.opportunities if o.kind is not goal_kind)
            assert tuple(o for o in options.bindings.opportunities
                         if o.kind is not goal_kind) == untouched
        else:
            assert isinstance(options, RedLiveOptionSet)
            assert len(options.menu.available_indices) >= 2
    assert emulator.frame_count == 0 and not emulator.pressed_buttons and not calls


@pytest.mark.parametrize("support", [False, True])
@pytest.mark.parametrize("storage", [0.75, 0.875])
@pytest.mark.parametrize("storage_peer", [False, True])
def test_storage_masked_acquisitions_do_not_hide_a_sole_ordinary_support(
    tmp_path, monkeypatch, support, storage, storage_peer,
):
    from dataclasses import replace

    from test_red_live_option_menu import (
        _binding,
        _fishing_candidate,
        _no_ordinary_bindings,
        _situation,
    )

    from pokemon_red_completion.red_live_option_menu import (
        RedLiveOptionMenuError,
        RedLiveOptionSet,
        supplemental_live_option,
    )
    from pokemon_red_completion.red_player_support import RedPlayerSupport

    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    original_capture = module.capture_player_lesson_snapshot

    def capture(rt):
        observed, snapshot = original_capture(rt)
        observed.situation = _situation(resources=0.1, storage=storage)
        return observed, snapshot

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    calls = []
    supply = _binding(GoalKind.RESUPPLY, binding_ref="sole-ordinary", calls=calls)
    rows = (supply,)
    if storage_peer:
        rows += (_binding(GoalKind.MANAGE_STORAGE, binding_ref="storage-peer", calls=calls),)
    by_kind = {b.kind: b for b in rows}
    original = _no_ordinary_bindings()
    bindings = replace(original, bindings=rows, opportunities=tuple(
        by_kind[o.kind].opportunity if o.kind in by_kind else o
        for o in original.opportunities
    ))
    runtime.enumerator = lambda _: NS(enumerate=lambda _: bindings)
    supplements = tuple(supplemental_live_option(
        _binding(GoalKind.ACQUIRE_SPECIES, binding_ref=f"capture-{i}", calls=calls),
        _fishing_candidate(f"capture-row-{i}", travel=0.2),
    ) for i in range(2))
    args = {name: kwargs[name] for name in
            ("battle", "combat_specimen_refs", "remaining_budget", "target_cash")}
    args.update(allow_support=support, supplements=supplements,
                ordering_seed_sha256="a" * 64)
    masked = storage > 0.75 and not storage_peer
    if masked and not support:
        with pytest.raises(RedLiveOptionMenuError, match="count=1"):
            module.observe_native_player_options(runtime, object(), **args)
    else:
        options = module.observe_native_player_options(runtime, object(), **args)
        if masked:
            assert isinstance(options, RedPlayerSupport)
            assert options.binding is supply and options.bindings is bindings
            public = options.public_dict()
            assert public["model_queries"] == 0 and public["comparative_choice"] is False
            assert public["support_role"] == "forced_singleton"
            assert public["selected_kind"] == "resupply"
        else:
            assert isinstance(options, RedLiveOptionSet)
            assert {b.binding_ref for b in options.bindings} == (
                {b.binding_ref for b in rows} | {s.binding.binding_ref for s in supplements}
            )
    assert emulator.frame_count == 0 and not emulator.pressed_buttons and not calls


def test_sole_ordinary_capture_cannot_bypass_storage_guard(tmp_path, monkeypatch):
    from dataclasses import replace

    from test_red_live_option_menu import _binding, _no_ordinary_bindings, _situation

    from pokemon_red_completion.red_live_option_menu import RedLiveOptionMenuError

    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    original_capture = module.capture_player_lesson_snapshot

    def capture(rt):
        observed, snapshot = original_capture(rt)
        observed.situation = _situation(storage=0.875)
        return observed, snapshot

    monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    calls = []
    capture_binding = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="blocked", calls=calls)
    original = _no_ordinary_bindings()
    bindings = replace(original, bindings=(capture_binding,), opportunities=tuple(
        capture_binding.opportunity if o.kind is GoalKind.ACQUIRE_SPECIES else o
        for o in original.opportunities
    ))
    runtime.enumerator = lambda _: NS(enumerate=lambda _: bindings)
    args = {name: kwargs[name] for name in
            ("battle", "combat_specimen_refs", "remaining_budget", "target_cash")}
    with pytest.raises(RedLiveOptionMenuError, match="count=0"):
        module.observe_native_player_options(runtime, object(), allow_support=True,
                                            ordering_seed_sha256="a" * 64, **args)
    assert emulator.frame_count == 0 and not emulator.pressed_buttons and not calls


def test_native_no_history_lesson_admits_without_borrowing_an_old_battle(tmp_path, monkeypatch):
    store, _, kwargs = fixture(tmp_path, monkeypatch)
    kwargs["battle"] = None
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["admitted"] and result["succeeded"]
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    assert row.outcome.verified_success


def test_readable_failed_goal_retains_negative_label_and_real_cost(tmp_path, monkeypatch):
    store, _, kwargs = fixture(tmp_path, monkeypatch, fault="execution_failure")
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["admitted"] and not result["succeeded"]
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    assert row.outcome.verified_success is False and row.outcome.action_cost > 0


@pytest.mark.parametrize(
    "fault", ["partition", "state", "target", "index", "combat", "enumerate_input"],
)
def test_preflight_refuses_before_any_input(tmp_path, monkeypatch, fault):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, fault=fault)
    if fault == "partition":
        kwargs["source"]["partition"] = "test"
    if fault == "state":
        kwargs["source"]["state_sha256"] = "0" * 64
    if fault == "target":
        kwargs["target"] = {"objective": "not-a-live-objective"}
    if fault == "index":
        kwargs["selected_index"] = True
    if fault == "combat":
        kwargs["combat_specimen_refs"] = ("missing",)
    with pytest.raises((ValueError, RuntimeError)):
        module.record_native_player_lesson(store, **kwargs)
    assert emulator.frame_count == 0


def test_same_declaration_cannot_run_twice_even_after_failure(tmp_path, monkeypatch):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, fault="bypass")
    result = module.record_native_player_lesson(store, **kwargs)
    assert result["frames"] == 0
    with pytest.raises(ValueError, match="already attempted"):
        module.record_native_player_lesson(store, **kwargs)
    assert emulator.frame_count == 0


@pytest.mark.parametrize("preparation", [False, True])
def test_recorded_live_lesson_fits_and_reloads_existing_registered_player(
    tmp_path, monkeypatch, preparation,
):
    from test_red_player_training_fit import _fit

    import pokemon_red_completion.red_player_training_fit as fitting
    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    folder = tmp_path / "fit"
    folder.mkdir()
    store, rows, prior, request, _ = _fit(folder, monkeypatch)
    monkeypatch.setattr(
        fitting,
        "load_red_player_training_episode",
        lambda *a, **k: NS(objective=REGISTERED_OBJECTIVE, examples=rows, curriculum_examples=()),
    )
    arguments = dict(
        episodes=(request,),
        source_commit="e" * 40,
        source_bundle_sha256="f" * 64,
        registered_objective=True,
    )

    def fit(prior, **extra):
        report = fitting.fit_red_player_update(store, prior=prior, **arguments, **extra)
        digest = report["model"]["model_sha256"]
        record = store.find_sealed_record("rpr-model-" + digest, expected_kind="red_player_model")
        return report, load_player_goal_model_record_bytes(
            record.read_bytes(), expected_model_sha256=digest
        )

    _, registered = fit(prior)
    harness = tmp_path / "harness"
    harness.mkdir()
    _, _, kwargs = fixture(harness, monkeypatch)
    if preparation:
        # Nondevelopment V7 lessons have no selected-member descriptor, but
        # still require the comparison baseline to bridge to the V7 coordinates.
        kwargs["observe_preparation"] = lambda *_: None
    attempt = module.record_native_player_lesson(store, **kwargs)
    assert attempt["admitted"]
    item = NativeCurriculumInput(**attempt["outcome"])
    report, learned = fit(registered, native_curriculum=(item,))
    assert learned.model.feature_version == (7 if preparation else 5)
    assert report["new_settled_examples"] == 1
    assert set(registered.retained_example_sha256) <= set(learned.retained_example_sha256)
    original = load_native_curriculum(store, item)
    assert original.features == load_native_curriculum(store, item).features
