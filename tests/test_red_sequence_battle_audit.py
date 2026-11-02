"""Real receipt validators on mock battles; not native game qualification."""

from dataclasses import replace

import pytest
from test_red_player_battle_history import publish
from test_red_player_lesson_runtime import Emulator
from test_red_scoped_training_battlers import A, B, battle, prototype
from test_red_sequence_verified_targets import setup as target_setup

from pokemon_red_completion.executor import NativeLessonController
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler
from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers
from pokemon_red_completion.red_sequence_battle_audit import audit_scoped_sequence_losses
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


def setup(tmp_path, monkeypatch, *, duration=2, unresolved=False):
    root, args, _ = target_setup(tmp_path, monkeypatch)
    import json
    plan = json.loads((root / "native-plan.json").read_bytes())
    controller = NativeLessonController(Emulator(), maximum_frames=100)
    p = replace(prototype(tmp_path), session=controller,
                source_state_sha256=args["source_sha256"],
                source_commit=plan["source"]["source_commit"])
    pool = ScopedTrainingBattlers(
        p, contracts=(A, B), output=tmp_path / "battlers", experiment_sha256="c" * 64,
        native_plan_sha256=args["expected_native_plan_sha256"],
    )

    def play(actor, *a, **kw):
        actor.output.mkdir(exist_ok=True)
        publish(actor, wild=kw.get("wild_training", False), unresolved=unresolved)
        controller.input_enabled = True
        try:
            controller.tick(duration)
        finally:
            controller.input_enabled = False
        return False

    monkeypatch.setattr(FrozenTrainerBattler, "_play", play)
    args.update(scoped_battlers=pool, expected_scope_sha256=pool.declaration_sha256)
    return root, args, pool


def loss_args(args):
    return dict(pool=args["scoped_battlers"], **{k: args[k] for k in (
        "expected_native_plan_sha256", "expected_scope_sha256", "expected_actor_plan_sha256",
        "expected_actor_result_sha256", "source_sha256",
    )})


def test_interleaved_losses_reach_targets_but_do_not_claim_bypass_coverage(tmp_path, monkeypatch):
    root, args, pool = setup(tmp_path, monkeypatch)
    battle(pool, A)
    battle(pool, B)
    battle(pool, A)
    audit = audit_scoped_sequence_losses(root, **loss_args(args))
    assert audit.top_level_losses == audit.model_losses == (1, 1, 1)
    assert not audit.complete_actor_coverage_verified and not audit.training_eligible
    complete, partial = verify_sequence_target_channels(root, **args)
    assert complete.original.measurement.blackouts == 0
    assert complete.measurement.blackouts == 2 and partial.measurement.blackouts == 1
    assert complete.targets.values[-1] is None and not any(partial.targets.known)
    assert not complete.training_eligible
    assert audit_scoped_sequence_losses(root, **loss_args(args)) == audit


def test_crossing_goal_boundary_has_no_owner(tmp_path, monkeypatch):
    root, args, pool = setup(tmp_path, monkeypatch, duration=3)
    battle(pool, A)
    with pytest.raises(ValueError, match="unique top-level"):
        audit_scoped_sequence_losses(root, **loss_args(args))


def test_unresolved_battle_cannot_be_zero_loss(tmp_path, monkeypatch):
    root, args, pool = setup(tmp_path, monkeypatch, unresolved=True)
    battle(pool, A)
    with pytest.raises(ValueError, match="unresolved"):
        audit_scoped_sequence_losses(root, **loss_args(args))


@pytest.mark.parametrize("fault", [
    "extra", "extra_invocation", "missing", "changed", "scope", "source",
])
def test_omitted_or_substituted_battle_evidence_rejects(tmp_path, monkeypatch, fault):
    root, args, pool = setup(tmp_path, monkeypatch)
    battle(pool, A)
    if fault == "extra":
        (pool.output / "actor-000/battle-0002").mkdir()
    elif fault == "extra_invocation":
        (pool.output / "battle-001-start.json").write_text("{}")
    elif fault == "missing":
        (pool.output / "actor-000/battle-0001/outcome.json").unlink()
    elif fault == "changed":
        (pool.output / "battle-000-end.json").write_text("{}")
    else:
        args["expected_scope_sha256" if fault == "scope" else "source_sha256"] = "f" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        audit_scoped_sequence_losses(root, **loss_args(args))


def test_zero_recorded_battles_does_not_prove_no_bypass_actor(tmp_path, monkeypatch):
    root, args, _ = setup(tmp_path, monkeypatch)
    audit = audit_scoped_sequence_losses(root, **loss_args(args))
    assert audit.model_losses == (0, 0, 0) and not audit.complete_actor_coverage_verified
    complete, _ = verify_sequence_target_channels(root, **args)
    assert complete.targets.values[-1] is None


def test_scope_must_bind_guarded_source_before_inputs(tmp_path):
    p = prototype(tmp_path)
    with pytest.raises(ValueError, match="before any input"):
        ScopedTrainingBattlers(p, contracts=(A,), output=tmp_path / "pool",
                               experiment_sha256="c" * 64, native_plan_sha256="d" * 64)
