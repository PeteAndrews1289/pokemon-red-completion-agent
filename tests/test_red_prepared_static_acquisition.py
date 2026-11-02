from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_routed_static_capture as module
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget


@pytest.fixture
def setup(monkeypatch):
    target = RedStaticCaptureTarget(144, 74, 50, 162, 3, 67, (2, 5), 2522)
    em = SimpleNamespace(save_state_bytes=lambda: bytes([state["version"]]),
                         frame_count=0, pressed_buttons=())
    state = dict(version=0, owned=frozenset(), consumed=False, returned=True)
    observation = SimpleNamespace(raw=SimpleNamespace(battle_state=0), input_ready=True)
    runtime = SimpleNamespace(emulator=em, adapter=SimpleNamespace(observe=lambda: observation),
                              reader=SimpleNamespace(read_pokedex_state=lambda: SimpleNamespace(
                                  owned_species=state["owned"])))
    actions = SimpleNamespace(actions_executed=0)
    monkeypatch.setattr(module, "red_static_capture_targets", lambda rom: (target,))
    monkeypatch.setattr(module, "observe_static_capture", lambda reader, bound: SimpleNamespace(
        registered=bound.species_number in state["owned"], consumed=state["consumed"]))
    calls = []

    def execute(bound):
        calls.append(bound)
        actions.actions_executed += 5
        em.frame_count += 60
        state.update(version=1, owned=frozenset({target.species_number}), consumed=True)
        return GoalExecutionReport(2, 20, {"captured": True})

    def binding(**changes):
        return module.prepared_static_acquisition_binding(
            runtime, actions, rom=b"", target=target, execute_prepared=execute,
            verify_return=lambda: state["returned"], estimated_effort=.4,
            estimated_risk=.25, **changes)

    return binding, state, em, actions, calls


def test_discovery_has_no_execution_and_complete_costs_include_preparation(setup):
    make, state, em, actions, calls = setup
    binding = make()
    assert calls == [] and actions.actions_executed == em.frame_count == 0
    report = binding.execute()
    assert report.actions_executed == 5 and report.frames_executed == 60
    assert report.evidence["learned_preparation"] is False
    assert binding.verify(report).status.value == "succeeded"
    with pytest.raises(RuntimeError, match="already attempted"):
        binding.execute()


@pytest.mark.parametrize("missing", ["registration", "event", "return", "terminal", "report"])
def test_labels_cannot_replace_native_registration_consumption_and_return(setup, missing):
    make, state, em, actions, calls = setup
    binding = make()
    report = binding.execute()
    if missing == "registration":
        state["owned"] = frozenset()
    elif missing == "event":
        state["consumed"] = False
    elif missing == "return":
        state["returned"] = False
    elif missing == "terminal":
        state["version"] = 2
    else:
        report = GoalExecutionReport(5, 60, dict(report.evidence))
    assert binding.verify(report).status.value == "failed"


def test_consumed_source_not_offered_and_stale_source_never_runs(setup):
    make, state, em, actions, calls = setup
    binding = make()
    state["version"] = 2
    with pytest.raises(RuntimeError, match="source changed"):
        binding.execute()
    assert not calls
    state["consumed"] = True
    assert make() is None


@pytest.mark.parametrize("permission", ["true", 1, None])
def test_second_snorlax_permission_is_not_truthy_generic_source_admission(setup, permission):
    make, _, _, _, _ = setup
    with pytest.raises(ValueError, match="Boolean"):
        make(allow_route16_snorlax=permission)


def test_route16_opt_in_still_rejects_a_target_with_fabricated_consumption(monkeypatch, setup):
    from dataclasses import replace

    from pokemon_red_completion import red_snorlax_capture as snorlax

    make, _, _, _, _ = setup
    exact = RedStaticCaptureTarget(143, 132, 30, 27, 1, 67, (10, 26), 1225)
    monkeypatch.setattr(snorlax, "route16_snorlax_target", lambda _: exact)
    # Existing cartridge members stay valid under the opt-in; it does not
    # authorize arbitrary other static targets.
    assert make(allow_route16_snorlax=True) is not None
    runtime = type("Runtime", (), {})()
    with pytest.raises(ValueError, match="differs from cartridge"):
        module.prepared_static_acquisition_binding(runtime, None, rom=b"",
            target=replace(exact, event_flag=1224), execute_prepared=lambda _: None,
            verify_return=lambda: True, estimated_effort=.4, estimated_risk=.25,
            allow_route16_snorlax=True)
