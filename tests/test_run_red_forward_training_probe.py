"""Probe orchestration: no claim during inspection and no retry after a claim."""

import runpy
from dataclasses import make_dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_forward_probe import fixture, load

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_red_forward_training_probe.py"


def harness(
    monkeypatch,
    *,
    read_only=False,
    claimed=False,
    preflight=None,
    fault=None,
    controller_return=False,
):
    module = runpy.run_path(str(SCRIPT))
    namespace = module["_run"].__globals__
    base = namespace["base"]
    f = fixture()
    probe = load(f)
    events = []
    holder = {"claimed": claimed}
    snapshot = SimpleNamespace(summary=SimpleNamespace(record_sha256="e" * 64))

    def find(record_id, *, expected_kind):
        events.append(("find", expected_kind))
        if expected_kind == "red_forward_probe_claim":
            return snapshot if holder["claimed"] else None
        assert expected_kind == base.CHECKPOINT_KIND
        return None if fault == "checkpoint" else snapshot

    def publish(record_id, *, kind, record):
        assert not holder["claimed"]
        holder["claimed"] = True
        events.append(("claim", record))
        return snapshot

    values = dict(
        private_root=SimpleNamespace(find_sealed_record=find, publish_sealed_record=publish),
        save_terminal_checkpoints=fault != "retention",
        pair_id="probe-1",
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        capture=SimpleNamespace(state_sha256="3" * 64),
        profile=SimpleNamespace(profile_sha256=probe.profile_sha256),
        continuation_root_lineage_id="train-root",
        protected_paths=(Path("protected"),),
        rom_path=Path("not-a-cartridge"),
        dashboard_port=None,
        decision_limit=2,
        forward_story_objective=None,
        forward_resource_budget=None,
        causal_record=None
        if fault == "missing_controller_model"
        else SimpleNamespace(model=f.tail),
    )
    ready = make_dataclass("Ready", [(key, object) for key in values])(**values)
    args = SimpleNamespace(
        probe_fit_record_id="fit-id",
        probe_fit_record_sha256="d" * 64,
        probe_model_sha256=probe.model.sha256,
        probe_tail_seed=41,
        probe_read_only=read_only,
        probe_frozen_controller_return=controller_return,
    )
    monkeypatch.setattr(base, "_prepare", lambda _: ready)
    monkeypatch.setitem(namespace, "load_red_forward_probe", lambda *a, **k: probe)

    def controller_loader(*args, **kwargs):
        assert kwargs["behavior_model"] is f.tail
        events.append(("controller_load",))
        if fault == "controller_admission":
            raise ValueError("controller batch differs")
        return probe

    monkeypatch.setitem(namespace, "load_red_forward_controller_probe", controller_loader)

    def scope(actual, spec):
        assert actual is ready and spec is probe
        events.append(("scope",))
        if fault == "scope":
            raise ValueError("wrong scope")

    def inspect(actual):
        assert actual.forward_story_objective == "defeat_bruno"
        assert actual.forward_resource_budget == 2
        assert ready.forward_story_objective is None
        events.append(("preflight",))
        return {"status": "ready", "available_goal_count": 2} if preflight is None else preflight

    monkeypatch.setattr(base, "_require_forward_probe_scope", scope)
    monkeypatch.setattr(base, "_action_free_preflight", inspect)
    monkeypatch.setattr(base, "_challenger_authority", lambda _: "unused-tail-shell")

    def run(actual, **kwargs):
        assert actual is ready and kwargs["forward_probe"] is probe
        assert kwargs["arm_id"] == base.FORWARD_PROBE_ARM_ID
        assert holder["claimed"] and events[-1][0] == "claim"
        events.append(("run",))
        if fault == "execution":
            raise OSError("spent input failed")
        return SimpleNamespace(
            trajectory_manifest_sha256="f" * 64,
            episode=SimpleNamespace(public_dict=lambda: {"complete": True}),
        )

    monkeypatch.setattr(base, "_run_arm", run)
    monkeypatch.setattr(
        base,
        "_sha256",
        lambda _: (
            "changed" if fault == "protected" and any(e[0] == "run" for e in events) else "same"
        ),
    )
    monkeypatch.setattr(
        base,
        "rom_adjacent_artifacts",
        lambda _: (
            {"changed": "bad"} if fault == "adjacent" and any(e[0] == "run" for e in events) else {}
        ),
    )
    return SimpleNamespace(run=lambda: module["_run"](args), events=events, holder=holder)


def test_controller_probe_explicit_readonly_load_does_not_claim_or_act(monkeypatch):
    h = harness(monkeypatch, read_only=True, controller_return=True)
    result = h.run()
    assert h.events[0] == ("controller_load",)
    assert not h.holder["claimed"] and result["controller_actions"] == 0
    assert result["first_actor_predictions"] == 0


@pytest.mark.parametrize("fault", ["missing_controller_model", "controller_admission"])
def test_controller_fit_failure_cannot_fall_back_or_act(monkeypatch, fault):
    h = harness(monkeypatch, controller_return=True, fault=fault)
    with pytest.raises(ValueError):
        h.run()
    assert not h.holder["claimed"]
    assert not any(event[0] in {"scope", "preflight", "claim", "run"} for event in h.events)


def test_controller_first_actor_uses_the_same_one_shot_claim_owner(monkeypatch):
    h = harness(monkeypatch, controller_return=True)
    result = h.run()
    assert result["automatic_promotion"] is False
    assert [event[0] for event in h.events].index("claim") < [event[0] for event in h.events].index(
        "run"
    )


def test_read_only_authenticates_and_preflights_without_claim_or_actor(monkeypatch):
    h = harness(monkeypatch, read_only=True)
    result = h.run()
    assert result["read_only"] is True and result["episode_created"] is False
    assert result["controller_actions"] == result["emulator_frames"] == 0
    assert result["first_actor_predictions"] == 0
    assert not h.holder["claimed"]
    assert [e[0] for e in h.events] == ["scope", "find", "preflight"]


def test_live_probe_claim_precedes_actor_and_has_distinct_nonpromotion_result(monkeypatch):
    h = harness(monkeypatch)
    result = h.run()
    assert h.holder["claimed"] and result["episode_id"] == "probe-1-forward-probe"
    assert result["trajectory_manifest_sha256"] == "f" * 64
    assert result["checkpoint_sha256"] == "e" * 64
    assert result["automatic_promotion"] is result["native_training_admission"] is False
    assert result["sealed_red_accesses"] == result["crystal_accesses"] == 0
    assert result["probe"]["first_actor_model_sha256"] != result["probe"]["tail_model_sha256"]
    claim = next(e[1] for e in h.events if e[0] == "claim")
    assert claim["no_retry_after_claim"] and not claim["model_fitted"]


@pytest.mark.parametrize("read_only", [False, True])
def test_claimed_probe_cannot_be_reopened_or_reinspected_by_execution_driver(
    monkeypatch, read_only
):
    h = harness(monkeypatch, claimed=True, read_only=read_only)
    with pytest.raises(ValueError, match="already claimed"):
        h.run()
    assert [e[0] for e in h.events] == ["scope", "find"]


@pytest.mark.parametrize(
    "preflight",
    [
        {"status": "ready_for_forced_bridge", "available_goal_count": 1},
        {"status": "ready", "available_goal_count": True},
        {"status": "ready", "available_goal_count": "2"},
        {"status": "ready", "available_goal_count": 0},
        {"status": "ready"},
    ],
)
def test_nonchoice_or_malformed_preflight_cannot_claim(monkeypatch, preflight):
    h = harness(monkeypatch, preflight=preflight)
    with pytest.raises(ValueError, match="genuine current choice"):
        h.run()
    assert not h.holder["claimed"] and not any(e[0] == "run" for e in h.events)


@pytest.mark.parametrize("fault", ["scope", "retention"])
def test_missing_scope_or_retention_stops_before_preflight_and_claim(monkeypatch, fault):
    h = harness(monkeypatch, fault=fault)
    with pytest.raises(ValueError):
        h.run()
    assert not h.holder["claimed"] and not any(e[0] == "preflight" for e in h.events)


@pytest.mark.parametrize("fault", ["execution", "protected", "adjacent", "checkpoint"])
def test_post_claim_failure_never_turns_into_a_retryable_success(monkeypatch, fault):
    h = harness(monkeypatch, fault=fault)
    with pytest.raises((ValueError, OSError)):
        h.run()
    assert h.holder["claimed"] and sum(e[0] == "run" for e in h.events) == 1
    with pytest.raises(ValueError, match="already claimed"):
        h.run()
    assert sum(e[0] == "run" for e in h.events) == 1


def test_help_needs_no_cartridge_fit_or_private_store():
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(SCRIPT))["main"](["--help"])
    assert stopped.value.code == 0
