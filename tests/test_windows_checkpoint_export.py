"""A failed battle export must not mask the native error or erase costs."""

import json
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as script


@pytest.mark.parametrize("primary_message", ["", "retained acquisition assertion"])
@pytest.mark.parametrize("primary_source", ["execution", "admission"])
def test_missing_battle_outcome_preserves_primary_failure_and_partial_costs(
    tmp_path, monkeypatch, primary_message, primary_source
):
    native = tmp_path / "native"
    native.mkdir()
    meter = dict(goal_attempts=4, actions_attempted=1319, frames=83748,
                 seconds=32.5, restore_attempts=1, observed_cash_debits=0,
                 observed_cash_rewards=960)
    (native / "native-costs.json").write_text(json.dumps(meter))
    previous = dict(decisions=874, actions=755205, frames=62795788,
                    seconds=14318.5, heals=836, cash_debits=77214)
    raw = N(player_money=1517, map_id=31, player_y=15, player_x=38,
            party_levels=(43, 46, 42, 52, 45, 50))
    emulator = N(frame_count=83748, pressed_buttons=(),
                 save_state_bytes=lambda: b"exact-partial-terminal")
    holder = dict(plan=N(roster=()), prior_spent=previous,
                  runtime=N(reader=N(read=lambda: raw)))

    def fail_native(**kwargs):
        if primary_source == "execution":
            raise AssertionError(primary_message)
        return dict(stop_reason="menu_unavailable", outcomes=[], admission_failure=dict(
            error_type="AssertionError", error=primary_message, failure_phase="admission"))

    def fail_history(**kwargs):
        raise FileNotFoundError("battle-0003/outcome.json")

    holder["observe_history"] = fail_history
    monkeypatch.setattr(script, "run_native_continuous_player", fail_native)
    monkeypatch.setattr(script, "native_player_options", lambda *a: dict(
        greedy_selection=True, resume_branch_refinement_after_settlement=False))
    monkeypatch.setattr(script, "player_wiring_declaration", lambda *a: {})
    monkeypatch.setattr(script, "_field_ready", lambda *a: True)
    monkeypatch.setattr(script, "native_checkpoint_facts", lambda *a: dict(
        badges=6, registrations=75))

    def no_fabricated_context(*a, **kwargs):
        pytest.fail("an unauthenticated battle must not produce a continuation")

    monkeypatch.setattr(script, "capture_player_continuation", no_fabricated_context)
    result, exported = script.execute_player_chunk(
        plan={"seed": 1}, configuration=N(sha256="c" * 64),
        c=N(digest=lambda p: sha256(p.read_bytes()).hexdigest()),
        emulator=emulator, factory=None, menu=None, holder=holder, source=None,
        output=tmp_path, model=N(model_sha256="m" * 64),
        limits=script.NativePlayerLimits(), memory=None, store=None, ordinal=1,
    )
    assert exported is None
    assert result["passed"] is False
    assert result["error_type"] == "AssertionError"
    assert result["error"] == primary_message
    assert result["checkpoint_export_error"]["error_type"] == "FileNotFoundError"
    assert result["context_sha256"] is None
    assert result["released"] is True
    assert result["state_sha256"] == sha256(b"exact-partial-terminal").hexdigest()
    assert result["spent"] == dict(decisions=878, actions=756524, frames=62879536,
                                  seconds=14351.0, heals=837, cash_debits=77214)
    assert result["chunk_costs"] == meter
    assert not (tmp_path / "CONTEXT.json").exists()
    expected = "native_admission_error" if primary_source == "admission" else "native_execution_error"
    assert script.chunk_continuation_reason(result, source_sha256="a" * 64) == expected
