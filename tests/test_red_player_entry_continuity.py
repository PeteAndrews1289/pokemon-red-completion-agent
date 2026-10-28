"""Entry parity and recovery without a ROM or a replacement gameplay policy."""

import json
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as configured
import run_fresh_red_player as fresh


def declaration():
    return dict(
        partition="development",
        objectives=["defeat_brock"],
        seed=31,
        goal_selection=dict(mode="exploration", reason="Retain one declared policy."),
    )


def test_exhausted_copies_can_be_inspected_but_never_renewed_or_refunded():
    baseline = dict(decisions=10, actions=20)
    current = dict(decisions=12, actions=30)
    allowance = dict(decisions=2, actions=5)
    assert configured.remaining_allowance(current, baseline, allowance, inspection=True) == {
        "decisions": 0,
        "actions": -5,
    }
    with pytest.raises(ValueError):
        configured.remaining_allowance(current, baseline, allowance)
    with pytest.raises(ValueError):
        configured.remaining_allowance(
            dict(decisions=9, actions=30), baseline, allowance, inspection=True
        )


@pytest.mark.parametrize("executed", [False, True])
def test_failed_prelaunch_identity_is_preserved_and_cannot_erase_real_inputs(tmp_path, executed):
    node = tmp_path / "runs/segment-001"
    node.mkdir(parents=True)
    (node / "PLAN.json").write_text("{}")
    (node / "PRELAUNCH-ERROR.json").write_text(
        json.dumps(
            dict(
                phase="before_emulator",
                worker_stopped=True,
                state_loads=0,
                inputs=0,
                frames=0,
                passed=False,
            )
        )
    )
    if executed:
        (node / "native").mkdir()
        with pytest.raises(ValueError):
            configured.configured_run_nodes(tmp_path)
    else:
        assert configured.configured_run_nodes(tmp_path) == ([], 2)
        assert node.exists()


@pytest.mark.parametrize("unsettled", [False, True])
def test_both_entries_use_one_options_builder_and_keep_callback_authority(monkeypatch, unsettled):
    monkeypatch.setattr(configured, "requires_compulsory_settlement", lambda runtime: unsettled)
    observer = object()
    refinement = dict(consequence_head=object(), consequence_objective_ref="defeat_brock")
    options = configured.native_player_options(
        declaration(),
        object(),
        ("original",),
        N(native_callbacks=lambda: dict(enumerate_bindings=observer)),
        refinement=refinement,
    )
    assert fresh.execute_player_chunk is configured.execute_player_chunk
    assert not options["greedy_selection"]
    assert options["enumerate_bindings"] is observer
    assert options["consequence_head"] is refinement["consequence_head"]
    assert options["resume_branch_refinement_after_settlement"] is unsettled
    for kind in ("trainer", "wild", "blackout", "motion"):
        assert options[f"settle_existing_{kind}"] is unsettled


@pytest.mark.parametrize("fault", [None, "mode", "reason", "partition", "extra"])
def test_automatic_live_renewal_is_explicit_and_cannot_expand_scope(fault):
    plan = dict(
        partition="development",
        automatic_runtime_renewal=dict(
            mode="live_chunks_v1", reason="Renew the same earned emulator."
        ),
    )
    if fault == "partition":
        plan["partition"] = "sealed"
    elif fault == "extra":
        plan["automatic_runtime_renewal"]["reset_costs"] = True
    elif fault:
        plan["automatic_runtime_renewal"][fault] = ""
    if fault:
        with pytest.raises(ValueError):
            configured.declared_automatic_renewal(plan)
    else:
        assert configured.declared_automatic_renewal(plan)
        assert not configured.declared_automatic_renewal({})


@pytest.mark.parametrize(
    "stop,error,changed,actions,expected",
    [
        ("decision_budget", None, True, 9, "automatic_chunk_renewal"),
        ("settlement_budget", None, True, 9, "automatic_chunk_renewal"),
        (
            "execution_failed",
            "ControllerFrameBudgetExhausted",
            True,
            9,
            "automatic_budget_recovery",
        ),
        ("execution_failed", "RouteExecutionError", True, 9, "native_execution_error"),
        ("menu_unavailable", None, True, 9, "menu_unavailable"),
        ("unsafe_terminal", None, True, 9, "automatic_control_recovery"),
        ("decision_budget", None, False, 9, "no_executable_progress"),
        ("decision_budget", None, True, 0, "no_executable_progress"),
        ("curriculum_complete", None, False, 0, "curriculum_complete"),
    ],
)
def test_renewal_distinguishes_budget_control_unknown_errors_and_stationary_loops(
    stop, error, changed, actions, expected
):
    result = dict(
        released=True,
        state_sha256="b" if changed else "a",
        chunk_costs=dict(actions_attempted=actions, frames=80),
        episode=dict(stop_reason=stop, outcomes=[dict(error_type=error)]),
    )
    assert configured.chunk_continuation_reason(result, source_sha256="a") == expected


@pytest.mark.parametrize("budget_stop", [False, True])
def test_shared_native_call_preserves_partial_costs_and_censored_history(
    tmp_path, monkeypatch, budget_stop
):
    output = tmp_path / "runs/segment-001"
    output.mkdir(parents=True)
    emulator = N(_backend=object(), frame_count=3000, pressed_buttons=(), save_state_bytes=lambda: b"earned")
    previous = dict(decisions=12, actions=190, frames=8000, seconds=7.0, heals=2, cash_debits=100)
    observed = []
    runtime = N(
        reader=N(
            read=lambda: N(player_money=80, map_id=1, player_y=2, player_x=3, party_levels=(9,))
        )
    )
    holder = dict(
        runtime=runtime,
        prior_spent=previous,
        plan=N(roster=(N(specimen_ref="original", purpose=N(value="combat")),)),
        observe_history=lambda **kwargs: observed.append(kwargs) or None,
    )
    c = N(digest=lambda path: sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(configured, "requires_compulsory_settlement", lambda runtime: True)
    monkeypatch.setattr(configured, "_field_ready", lambda runtime: True)
    monkeypatch.setattr(configured, "native_checkpoint_facts", lambda runtime: dict(cash=80))
    monkeypatch.setattr(
        configured,
        "capture_player_continuation",
        lambda runtime, **kwargs: dict(
            state_sha256=sha256(b"earned").hexdigest(),
            spent=kwargs["spent"],
            lesson=dict(completed_objectives=[]),
        ),
    )
    calls = []

    def execute(**kwargs):
        calls.append(kwargs)
        native = kwargs["output"]
        native.mkdir()
        (native / "native-costs.json").write_text(
            json.dumps(
                dict(
                    goal_attempts=2,
                    actions_attempted=11,
                    frames=77,
                    seconds=4,
                    restore_attempts=1,
                    observed_cash_debits=35,
                    control_recovery_cash_debits=20,
                )
            )
        )
        return dict(
            model_decisions=1,
            stop_reason="execution_failed" if budget_stop else "decision_budget",
            outcomes=[
                dict(
                    error_type="ControllerFrameBudgetExhausted" if budget_stop else None,
                    before=dict(cash=50),
                    after=dict(cash=80),
                )
            ],
        )

    monkeypatch.setattr(configured, "run_native_continuous_player", execute)
    row, context = configured.execute_player_chunk(
        plan=declaration(),
        configuration=N(sha256="a" * 64),
        c=c,
        emulator=emulator,
        factory=object(),
        menu=N(native_callbacks=lambda: {}),
        holder=holder,
        source=object(),
        output=output,
        model=N(model_sha256="b" * 64),
        limits=configured.NativePlayerLimits(decisions=2),
        memory=object(),
        store=object(),
        ordinal=1,
    )
    assert not calls[0]["greedy_selection"] and calls[0]["settle_existing_motion"]
    assert context["spent"] == dict(
        decisions=14, actions=201, frames=8077, seconds=11, heals=3, cash_debits=135
    )
    assert previous["cash_debits"] == 100
    assert observed == [
        dict(checkpoint_error_type="ControllerFrameBudgetExhausted" if budget_stop else None)
    ]
    assert row["released"] and row["live_driver_running"]
    assert row["worker_stopped"] is False
    assert row["checkpoint_lifecycle"]["guest_backend_closed"] is False
    assert row["checkpoint_lifecycle"]["host_process_exit_confirmed"] is False
    assert (output / "terminal.state").read_bytes() == b"earned"
