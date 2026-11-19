"""ROM-free terminal claims require independently checked task predicates."""

import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_native_player import setup
from test_red_sequence_state_audit import Emulator, events

from pokemon_red_completion import red_native_player as native
from pokemon_red_completion import red_sequence_state_audit as state_module
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_story_unit
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector
from pokemon_red_completion.player_sequence_targets import (
    SEQUENCE_TARGET_CONTRACT,
    TASK_TERMINAL_TARGET_CONTRACT,
    sequence_targets,
)
from pokemon_red_completion.player_sequence_value import (
    SequenceRegressionRow,
    SequenceValueHead,
    fit_sequence_value,
    sequence_feature_width,
)
from pokemon_red_completion.player_short_sequence import SequenceEnd
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


def collect_task(
    tmp_path, monkeypatch, *, terminal=True, budget=False, native_flag=True, initial_flag=False
):
    args, executed = setup(tmp_path, monkeypatch)
    args.update(
        model=upgrade_option_value_model_for_story_unit(args["model"]),
        sequence_horizon=2,
        limits=replace(args["limits"], actions=3, decisions=1),
    )
    em = Emulator()
    monkeypatch.setattr(state_module, "trainer_headers", lambda *a, **k: (NS(event_flag=86),))
    monkeypatch.setattr(
        state_module,
        "PokemonRedStateReader",
        lambda _: NS(
            read=lambda: NS(
                map_id=45,
                battle_state=0,
                player_money=3000,
                event_flags=events(86)
                if (initial_flag or (native_flag and int(em.state) > 0))
                else events(),
            )
        ),
    )
    reader = state_module.ScopedTrainerSequenceStateReader(
        em, rom=b"rom", expected_rom_sha256=sha256(b"rom").hexdigest(), maps=(41, 45), events=(86,)
    )
    original_init = SequenceTraceCollector.__init__

    def init(self, **kw):
        original_init(
            self,
            **kw,
            target_contract=TASK_TERMINAL_TARGET_CONTRACT,
            task_sha256=reader.task_sha256,
        )

    monkeypatch.setattr(SequenceTraceCollector, "__init__", init)
    original_run = native.run_autonomous_options

    def run(**kw):
        original_stop = kw["stop_after_outcome"]

        def stop():
            original_stop()
            if terminal:
                kw["sequence_collector"].mark_task_terminal(
                    task_sha256=reader.task_sha256, boundary_sha256=kw["snapshot"]().sha256
                )
            return not budget

        return original_run(**{**kw, "stop_after_outcome": stop})

    monkeypatch.setattr(native, "run_autonomous_options", run)
    native.run_native_continuous_player(**args)
    root = args["output"]
    read = lambda p: json.loads(p.read_bytes())
    kwargs = dict(
        reader=reader,
        store=args["store"],
        model=args["model"],
        source_sha256=args["source"]["state_sha256"],
        partition=args["source"]["partition"],
        expected_native_plan_sha256=canonical_sha256(read(root / "native-plan.json")),
        expected_actor_plan_sha256=canonical_sha256(read(root / "episode/plan.json")),
        expected_actor_result_sha256=canonical_sha256(read(root / "episode/result.json")),
        expected_declaration_sha256=canonical_sha256(
            read(root / "episode/sequence/declaration.json")
        ),
        expected_catalog_sha256=reader.catalog_sha256,
        expected_task_sha256=reader.task_sha256,
    )
    return root, kwargs, executed


def test_early_native_task_finish_is_observed_without_padding_or_fixed_horizon_claim(
    tmp_path, monkeypatch
):
    root, args, executed = collect_task(tmp_path, monkeypatch)
    [row] = verify_sequence_target_channels(root, **args)
    assert executed == [2] and args["reader"].emulator.frame_count == 0
    assert row.measurement.end is SequenceEnd.TASK_TERMINAL
    assert row.measurement.observed_steps == 1 and row.measurement.horizon == 2
    assert not row.measurement.complete_window and row.measurement.complete_observation
    assert (
        row.targets.values[0] == 0.5
        and row.targets.values[1] is None
        and row.targets.values[6] is None
    )
    assert row.original.target_contract == TASK_TERMINAL_TARGET_CONTRACT
    assert row.measurement.actions == 1 and row.measurement.frames == 2
    assert not row.training_eligible
    with pytest.raises(ValueError, match="explicit task"):
        sequence_targets(row.measurement, covered=args["reader"].target_channels)


@pytest.mark.parametrize("fault", ["native_flag", "already_complete", "task", "claim", "stop"])
def test_claim_or_stop_reason_cannot_replace_native_task_proof(tmp_path, monkeypatch, fault):
    root, args, _ = collect_task(
        tmp_path,
        monkeypatch,
        native_flag=fault != "native_flag",
        initial_flag=fault == "already_complete",
        budget=fault == "stop",
    )
    if fault == "task":
        args["expected_task_sha256"] = "f" * 64
    if fault == "claim":
        p = root / "episode/sequence/task-terminal.json"
        d = json.loads(p.read_bytes())
        d["terminal_sha256"] = "e" * 64
        p.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        verify_sequence_target_channels(root, **args)


@pytest.mark.parametrize("budget", [False, True])
def test_short_prefix_without_declared_native_task_claim_remains_censored(
    tmp_path, monkeypatch, budget
):
    root, args, executed = collect_task(tmp_path, monkeypatch, terminal=False, budget=budget)
    [row] = verify_sequence_target_channels(root, **args)
    assert row.measurement.end is SequenceEnd.INTERRUPTED and not any(row.targets.known)
    assert executed == [2] and row.measurement.frames == 2


def test_task_targets_have_distinct_head_identity_and_cannot_mix_with_legacy():
    width = sequence_feature_width(16)
    rows = tuple(
        SequenceRegressionRow(
            f"{i:064x}",
            (float(i),) + (0.0,) * (width - 1),
            (1.0, None, float(i), float(i), 0.0, 0.0, None),
            "train",
            16,
            TASK_TERMINAL_TARGET_CONTRACT,
        )
        for i in range(2)
    )
    head = fit_sequence_value(rows, ridge=1.0, horizon=2, behavior_model_sha256="b" * 64)
    assert (
        head.document()["schema"].endswith(".v3")
        and head.target_contract == TASK_TERMINAL_TARGET_CONTRACT
    )
    assert (
        SequenceValueHead.from_document(head.document(), expected_sha256=head.model_sha256) == head
    )
    legacy = fit_sequence_value(
        tuple(replace(r, target_contract=SEQUENCE_TARGET_CONTRACT) for r in rows),
        ridge=1.0,
        horizon=2,
        behavior_model_sha256="b" * 64,
    )
    assert head.model_sha256 != legacy.model_sha256 and head.dataset_sha256 != legacy.dataset_sha256
    with pytest.raises(ValueError):
        fit_sequence_value(
            (rows[0], replace(rows[1], target_contract=SEQUENCE_TARGET_CONTRACT)),
            ridge=1.0,
            horizon=2,
            behavior_model_sha256="b" * 64,
        )


@pytest.mark.parametrize("task", [None, "bad", True])
def test_terminal_collection_requires_exact_prospective_task_identity(task):
    with pytest.raises(ValueError):
        SequenceTraceCollector(
            source_sha256="a" * 64,
            partition="train",
            horizon=2,
            target_contract=TASK_TERMINAL_TARGET_CONTRACT,
            task_sha256=task,
        )


def test_terminal_teacher_declaration_is_explicit_and_versioned():
    from test_sampled_sequence_teacher import setup as teacher_setup

    from pokemon_red_completion.red_teacher_case import TERMINAL_SEQUENCE_SCHEMA, validate_plan_case

    data = teacher_setup()
    case = data["case"]
    case.update(
        schema=TERMINAL_SEQUENCE_SCHEMA, sequence_target_contract=TASK_TERMINAL_TARGET_CONTRACT
    )
    spec = validate_plan_case(data["plan"], data["source_row"])
    assert spec.sequence_mode and spec.terminal_sequence_mode
    case["sequence_target_contract"] = SEQUENCE_TARGET_CONTRACT
    with pytest.raises(ValueError):
        validate_plan_case(data["plan"], data["source_row"])


def test_later_native_success_cannot_complete_an_earlier_window(tmp_path, monkeypatch):
    from pokemon_red_completion import red_sequence_verified_targets as verifier

    root, args, _ = collect_task(tmp_path, monkeypatch)
    original = verifier.audit_sequence_state_channels

    def with_later_success(*a, **kw):
        state = original(*a, **kw)
        [terminal] = state.steps
        return replace(state, steps=(replace(terminal, progress=()), terminal))

    monkeypatch.setattr(verifier, "audit_sequence_state_channels", with_later_success)
    with pytest.raises(ValueError, match="predicate was not newly completed"):
        verify_sequence_target_channels(root, **args)
