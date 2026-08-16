from __future__ import annotations

import ast
import hashlib
import json
import runpy
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import ControllerTiming

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_red_party_development_pp_materialization.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def test_pp_runner_loads_only_exact_bounded_ascii_json(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    payload = b'{"schema":"test"}\n'
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    assert SCRIPT["_load_json"](
        path,
        expected_sha256=digest,
        subject="test input",
    ) == {"schema": "test"}
    for bad_payload, expected_digest in (
        (b"", hashlib.sha256(b"").hexdigest()),
        (b"not-json", hashlib.sha256(b"not-json").hexdigest()),
        (payload, "0" * 64),
    ):
        path.write_bytes(bad_payload)
        with pytest.raises(RuntimeError, match="digest or size|ASCII JSON"):
            SCRIPT["_load_json"](
                path,
                expected_sha256=expected_digest,
                subject="test input",
            )


def test_pp_runner_keeps_private_inputs_outside_the_repository(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "input.json"
    assert SCRIPT["_require_external"](outside, subject="test") == outside
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_require_external"](
            PROJECT_ROOT / "private.json",
            subject="test",
        )


def _successful_ci_payload(
    *,
    run_id: int = 123,
    head_sha: str = "a" * 40,
) -> dict[str, object]:
    return {
        "attempt": 1,
        "conclusion": "success",
        "databaseId": run_id,
        "event": "pull_request",
        "headSha": head_sha,
        "status": "completed",
        "url": (
            f"https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/{run_id}"
        ),
        "workflowName": "CI",
    }


def test_pp_runner_execution_request_is_explicit_and_exact(
    tmp_path: Path,
) -> None:
    assert (
        SCRIPT["_validate_execution_request"](
            execute=False,
            private_root=None,
            out_state=None,
            exact_ci_run=None,
            exact_ci_attempt=None,
        )
        is None
    )
    with pytest.raises(RuntimeError, match="read-only PP preflight"):
        SCRIPT["_validate_execution_request"](
            execute=False,
            private_root=tmp_path,
            out_state=None,
            exact_ci_run=None,
            exact_ci_attempt=None,
        )
    with pytest.raises(RuntimeError, match="requires private root"):
        SCRIPT["_validate_execution_request"](
            execute=True,
            private_root=None,
            out_state=tmp_path / "out.state",
            exact_ci_run=1,
            exact_ci_attempt=1,
        )
    with pytest.raises(RuntimeError, match="CI run identity is invalid"):
        SCRIPT["_validate_execution_request"](
            execute=True,
            private_root=tmp_path,
            out_state=tmp_path / "out.state",
            exact_ci_run=True,
            exact_ci_attempt=1,
        )
    with pytest.raises(RuntimeError, match="CI attempt identity is invalid"):
        SCRIPT["_validate_execution_request"](
            execute=True,
            private_root=tmp_path,
            out_state=tmp_path / "out.state",
            exact_ci_run=123,
            exact_ci_attempt=True,
        )
    assert SCRIPT["_validate_execution_request"](
        execute=True,
        private_root=tmp_path,
        out_state=tmp_path / "out.state",
        exact_ci_run=123,
        exact_ci_attempt=1,
    ) == (tmp_path, tmp_path / "out.state", 123, 1)


def test_pp_runner_authenticates_the_exact_green_source_bound_ci_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def completed(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(_successful_ci_payload()),
            stderr="",
        )

    monkeypatch.setattr(SCRIPT["subprocess"], "run", completed)

    result = SCRIPT["_require_exact_green_ci_run"](
        123,
        1,
        source_commit="a" * 40,
    )

    assert result == _successful_ci_payload()
    assert observed["command"] == (
        "gh",
        "run",
        "view",
        "123",
        "--repo",
        "PeteAndrews1289/pokemon-red-completion-agent",
        "--json",
        "attempt,conclusion,databaseId,event,headSha,status,url,workflowName",
    )
    assert observed["check"] is False
    assert observed["timeout"] == 30


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("attempt", 0),
        ("attempt", True),
        ("attempt", 2),
        ("conclusion", "failure"),
        ("databaseId", 124),
        ("event", "workflow_dispatch"),
        ("headSha", "b" * 40),
        ("status", "in_progress"),
        (
            "url",
            "https://github.com/example/other/actions/runs/123",
        ),
        ("workflowName", "Other"),
    ),
)
def test_pp_runner_rejects_any_wrong_ci_binding_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    payload = _successful_ci_payload()
    payload[field] = value
    monkeypatch.setattr(
        SCRIPT["subprocess"],
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="not the exact successful"):
        SCRIPT["_require_exact_green_ci_run"](
            123,
            1,
            source_commit="a" * 40,
        )


def test_pp_runner_fails_closed_when_ci_evidence_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SCRIPT["subprocess"],
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="not found",
        ),
    )

    with pytest.raises(RuntimeError, match="could not authenticate"):
        SCRIPT["_require_exact_green_ci_run"](
            123,
            1,
            source_commit="a" * 40,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "source_commit",
        "source_bundle",
        "runner_source",
        "reservation_semantic",
        "reservation_file",
        "inventory_semantic",
        "inventory_file",
        "registry_semantic",
        "registry_file",
        "registry_count",
    ),
)
def test_pp_runner_distinguishes_every_frozen_execution_input(
    mutation: str,
) -> None:
    plan = SimpleNamespace(
        source_commit="commit-a",
        source_bundle_sha256="bundle-a",
        runner_source_sha256="runner-a",
        reservation_plan_sha256="reservation-a",
        reservation_plan_file_sha256="reservation-file-a",
        inventory_sha256="inventory-a",
        inventory_file_sha256="inventory-file-a",
        venue_prior_registry_sha256="registry-a",
        venue_prior_registry_file_sha256="registry-file-a",
        venue_prior_count=2,
    )
    reservation = SimpleNamespace(plan_sha256="reservation-a")
    inventory = SimpleNamespace(inventory_sha256="inventory-a")
    registry = SimpleNamespace(registry_sha256="registry-a", entries=(1, 2))
    arguments = {
        "source_commit": "commit-a",
        "source_bundle_sha256": "bundle-a",
        "runner_source_sha256": "runner-a",
        "reservation_plan_file_sha256": "reservation-file-a",
        "checkpoint_inventory_file_sha256": "inventory-file-a",
        "venue_prior_registry_file_sha256": "registry-file-a",
    }
    SCRIPT["_require_execution_input_bindings"](
        plan=plan,
        reservation_plan=reservation,
        inventory=inventory,
        registry=registry,
        **arguments,
    )

    if mutation == "source_commit":
        arguments["source_commit"] = "commit-b"
    elif mutation == "source_bundle":
        arguments["source_bundle_sha256"] = "bundle-b"
    elif mutation == "runner_source":
        arguments["runner_source_sha256"] = "runner-b"
    elif mutation == "reservation_semantic":
        reservation.plan_sha256 = "reservation-b"
    elif mutation == "reservation_file":
        arguments["reservation_plan_file_sha256"] = "reservation-file-b"
    elif mutation == "inventory_semantic":
        inventory.inventory_sha256 = "inventory-b"
    elif mutation == "inventory_file":
        arguments["checkpoint_inventory_file_sha256"] = "inventory-file-b"
    elif mutation == "registry_semantic":
        registry.registry_sha256 = "registry-b"
    elif mutation == "registry_file":
        arguments["venue_prior_registry_file_sha256"] = "registry-file-b"
    elif mutation == "registry_count":
        registry.entries = (1,)
    else:  # pragma: no cover - parametrization owns this branch
        raise AssertionError(mutation)

    with pytest.raises(RuntimeError, match="differ from the frozen plan"):
        SCRIPT["_require_execution_input_bindings"](
            plan=plan,
            reservation_plan=reservation,
            inventory=inventory,
            registry=registry,
            **arguments,
        )


@pytest.mark.parametrize(
    "mutation",
    ("catalog_semantic", "catalog_file", "rom"),
)
def test_pp_runner_distinguishes_context_catalog_and_rom_bindings(
    mutation: str,
) -> None:
    plan = SimpleNamespace(
        context_catalog_sha256="catalog-a",
        context_catalog_file_sha256="catalog-file-a",
        rom_sha256="rom-a",
    )
    catalog_semantic = "catalog-a"
    catalog_file = "catalog-file-a"
    rom = "rom-a"
    SCRIPT["_require_context_catalog_binding"](
        observed_catalog_sha256=catalog_semantic,
        context_catalog_file_sha256=catalog_file,
        plan=plan,
    )
    SCRIPT["_require_rom_binding"](
        observed_rom_sha256=rom,
        plan=plan,
    )

    if mutation == "catalog_semantic":
        catalog_semantic = "catalog-b"
    elif mutation == "catalog_file":
        catalog_file = "catalog-file-b"
    elif mutation == "rom":
        rom = "rom-b"
    else:  # pragma: no cover - parametrization owns this branch
        raise AssertionError(mutation)

    if mutation == "rom":
        with pytest.raises(RuntimeError, match="ROM differs"):
            SCRIPT["_require_rom_binding"](
                observed_rom_sha256=rom,
                plan=plan,
            )
    else:
        with pytest.raises(RuntimeError, match="catalog differs"):
            SCRIPT["_require_context_catalog_binding"](
                observed_catalog_sha256=catalog_semantic,
                context_catalog_file_sha256=catalog_file,
                plan=plan,
            )


@pytest.mark.parametrize(
    "mutation",
    (None, "map", "species", "maximum_level", "binding"),
)
def test_pp_runner_rederives_the_live_venue_from_rom_and_prior(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str | None,
) -> None:
    venue = SCRIPT["ROUTE_11_TRAINING_VENUE"]
    slots = [(14, 21), (15, 23), (17, 21)]
    evidence = SimpleNamespace(
        evidence_sha256="a" * 64,
        operational_contract_sha256="b" * 64,
    )

    class Registry:
        def evidence_for(self, area: object) -> object:
            assert area is venue.band
            return evidence

    wild_species = (21, 23)
    binding = SCRIPT["red_pp_venue_binding_sha256"](
        venue.band,
        map_id=venue.map_id,
        venue_prior_evidence_sha256=evidence.evidence_sha256,
        operational_contract_sha256=evidence.operational_contract_sha256,
        wild_species_ids=wild_species,
        maximum_wild_level=17,
    )
    entry = SimpleNamespace(
        venue_map_id=venue.map_id,
        possible_wild_species_ids=wild_species,
        venue_maximum_wild_level=17,
        venue_binding_sha256=binding,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "wild_tables",
        lambda rom_bytes: {venue.map_id: slots},
    )
    if mutation == "map":
        entry.venue_map_id += 1
    elif mutation == "species":
        entry.possible_wild_species_ids = (21,)
    elif mutation == "maximum_level":
        entry.venue_maximum_wild_level = 16
    elif mutation == "binding":
        entry.venue_binding_sha256 = "c" * 64

    if mutation is None:
        SCRIPT["_require_runtime_venue_binding"](
            registry=Registry(),
            entry=entry,
            rom_bytes=b"rom",
        )
    else:
        with pytest.raises(RuntimeError, match="cartridge-bound prior"):
            SCRIPT["_require_runtime_venue_binding"](
                registry=Registry(),
                entry=entry,
                rom_bytes=b"rom",
            )


def test_pp_runner_rejects_missing_runtime_venue_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(SCRIPT_GLOBALS, "wild_tables", lambda rom_bytes: {})

    with pytest.raises(RuntimeError, match="cannot re-derive"):
        SCRIPT["_require_runtime_venue_binding"](
            registry=SimpleNamespace(evidence_for=lambda area: None),
            entry=SimpleNamespace(),
            rom_bytes=b"rom",
        )


def test_pp_runner_selects_exactly_one_entry_for_the_authorized_partition() -> None:
    partition = SCRIPT["ScenarioPartition"]
    train = SimpleNamespace(partition=partition.TRAIN)
    development = SimpleNamespace(partition=partition.DEVELOPMENT)
    plan = SimpleNamespace(entries=(development, train))

    assert SCRIPT["_selected_entry"](plan, partition.TRAIN) is train
    assert SCRIPT["_selected_entry"](plan, partition.DEVELOPMENT) is development
    with pytest.raises(RuntimeError, match="one selected partition"):
        SCRIPT["_selected_entry"](
            SimpleNamespace(entries=(train, train)),
            partition.TRAIN,
        )
    with pytest.raises(RuntimeError, match="one selected partition"):
        SCRIPT["_selected_entry"](
            SimpleNamespace(entries=(development,)),
            partition.TRAIN,
        )


def test_pp_runner_selects_exactly_one_authenticated_inventory_row() -> None:
    selected = SimpleNamespace(checkpoint_id="source-a")
    other = SimpleNamespace(checkpoint_id="source-b")

    assert (
        SCRIPT["_selected_inventory_entry"](
            SimpleNamespace(entries=(other, selected)),
            "source-a",
        )
        is selected
    )
    for rows in ((other,), (selected, selected)):
        with pytest.raises(RuntimeError, match="authenticated inventory"):
            SCRIPT["_selected_inventory_entry"](
                SimpleNamespace(entries=rows),
                "source-a",
            )


@pytest.mark.parametrize(
    "mutation",
    (
        "capture_id",
        "capture_state",
        "capture_envelope",
        "root_lineage",
        "excluded_root",
        "excluded_state",
        "inventory_checkpoint",
        "inventory_state",
        "inventory_envelope",
        "inventory_semantics",
    ),
)
def test_pp_runner_distinguishes_every_source_capture_binding(
    mutation: str,
) -> None:
    capture = SimpleNamespace(
        capture_id="capture-a",
        state_sha256="state-a",
        envelope_sha256="envelope-a",
    )
    entry = SimpleNamespace(
        source_checkpoint_id="capture-a",
        source_state_sha256="state-a",
        source_envelope_sha256="envelope-a",
        source_root_lineage_id="root-a",
        source_semantic_signature_sha256="semantics-a",
    )
    reservation = SimpleNamespace(
        excluded_root_lineage_ids=(),
        excluded_state_sha256=(),
    )
    inventory = SimpleNamespace(
        checkpoint_id="capture-a",
        state_sha256="state-a",
        envelope_sha256="envelope-a",
        semantic_signature_sha256="semantics-a",
    )
    root_lineage_id = "root-a"
    SCRIPT["_require_source_capture_bindings"](
        capture=capture,
        entry=entry,
        root_lineage_id=root_lineage_id,
        reservation_plan=reservation,
        inventory_entry=inventory,
    )

    if mutation == "capture_id":
        capture.capture_id = "capture-b"
    elif mutation == "capture_state":
        capture.state_sha256 = "state-b"
    elif mutation == "capture_envelope":
        capture.envelope_sha256 = "envelope-b"
    elif mutation == "root_lineage":
        root_lineage_id = "root-b"
    elif mutation == "excluded_root":
        reservation.excluded_root_lineage_ids = ("root-a",)
    elif mutation == "excluded_state":
        reservation.excluded_state_sha256 = ("state-a",)
    elif mutation == "inventory_checkpoint":
        inventory.checkpoint_id = "capture-b"
    elif mutation == "inventory_state":
        inventory.state_sha256 = "state-b"
    elif mutation == "inventory_envelope":
        inventory.envelope_sha256 = "envelope-b"
    elif mutation == "inventory_semantics":
        inventory.semantic_signature_sha256 = "semantics-b"
    else:  # pragma: no cover - parametrization owns this branch
        raise AssertionError(mutation)

    with pytest.raises(RuntimeError, match="frozen lineage|authenticated inventory"):
        SCRIPT["_require_source_capture_bindings"](
            capture=capture,
            entry=entry,
            root_lineage_id=root_lineage_id,
            reservation_plan=reservation,
            inventory_entry=inventory,
        )


def test_pp_runner_requires_an_existing_private_output_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "captures" / "out.state"
    with pytest.raises(RuntimeError, match="must already be a writable"):
        SCRIPT["_require_output_boundary"](output)

    output.parent.mkdir()
    SCRIPT["_require_output_boundary"](output)

    output.symlink_to(tmp_path / "missing-state-target")
    with pytest.raises(RuntimeError, match="symbolic link"):
        SCRIPT["_require_output_boundary"](output)


def test_pp_runner_requires_the_exact_unoccupied_output_pair(
    tmp_path: Path,
) -> None:
    entry = SimpleNamespace(output_capture_id="prepared-train-01")
    output = tmp_path / "prepared-train-01.state"
    envelope = Path(f"{output}.json")

    assert SCRIPT["_require_fresh_output_identity"](output, entry) == envelope

    wrong = tmp_path / "prepared-development-01.state"
    with pytest.raises(RuntimeError, match="differs from the frozen plan"):
        SCRIPT["_require_fresh_output_identity"](wrong, entry)

    output.write_bytes(b"occupied")
    with pytest.raises(RuntimeError, match="occupied"):
        SCRIPT["_require_fresh_output_identity"](output, entry)
    output.unlink()

    envelope.write_bytes(b"occupied")
    with pytest.raises(RuntimeError, match="occupied"):
        SCRIPT["_require_fresh_output_identity"](output, entry)


def test_pp_runner_rejects_a_dangling_output_envelope_symlink(
    tmp_path: Path,
) -> None:
    entry = SimpleNamespace(output_capture_id="prepared-train-01")
    output = tmp_path / "prepared-train-01.state"
    envelope = Path(f"{output}.json")
    envelope.symlink_to(tmp_path / "missing-envelope-target.json")

    with pytest.raises(RuntimeError, match="occupied"):
        SCRIPT["_require_fresh_output_identity"](output, entry)


def test_pp_runner_requires_every_input_and_output_inside_one_private_root(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    protected = private_root / "plan.json"
    protected.write_bytes(b"{}\n")
    output = private_root / "prepared.state"

    assert (
        SCRIPT["_require_designated_private_root"](
            private_root,
            protected_inputs=(protected,),
            output_state=output,
        )
        == private_root
    )
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="does not contain every"):
        SCRIPT["_require_designated_private_root"](
            private_root,
            protected_inputs=(outside,),
            output_state=output,
        )
    with pytest.raises(RuntimeError, match="must remain inside"):
        SCRIPT["_require_designated_private_root"](
            private_root,
            protected_inputs=(protected,),
            output_state=tmp_path / "outside.state",
        )


def test_pp_runner_output_claim_is_exclusive_owner_only_and_durable(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out.state"
    payload = SCRIPT["_OUTPUT_STATE_CLAIM"]

    digest = SCRIPT["_write_exclusive"](output, payload)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert output.read_bytes() == payload
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](output, payload)


def test_pp_runner_revalidates_the_exact_output_claim_bytes(tmp_path: Path) -> None:
    output = tmp_path / "out.state"
    output.write_bytes(SCRIPT["_OUTPUT_STATE_CLAIM"])
    expected = hashlib.sha256(output.read_bytes()).hexdigest()

    SCRIPT["_require_output_claim_unchanged"](output, expected)
    output.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed before controller"):
        SCRIPT["_require_output_claim_unchanged"](output, expected)
    output.unlink()
    with pytest.raises(RuntimeError, match="changed before controller"):
        SCRIPT["_require_output_claim_unchanged"](output, expected)


class _FrameCounter:
    frame_count = 100


class _Executor:
    def __init__(self, frames: _FrameCounter, timing: ControllerTiming) -> None:
        self.frames = frames
        self.timing = timing
        self.calls = 0

    def execute(self, action: MacroAction) -> object:
        self.calls += 1
        self.frames.frame_count += action.repeat * (
            self.timing.wait_frames
            if action.kind is MacroActionKind.WAIT
            else self.timing.press_frames + self.timing.release_frames
        )
        return action


def test_pp_runner_refuses_the_action_that_would_cross_a_hard_bound() -> None:
    timing = ControllerTiming(press_frames=2, release_frames=3, wait_frames=4)
    frames = _FrameCounter()
    delegate = _Executor(frames, timing)
    executor = SCRIPT["_HardBoundedCountingExecutor"](
        delegate,
        emulator=frames,
        timing=timing,
        start_frame=100,
        maximum_actions=2,
        maximum_frames=9,
    )

    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
    assert frames.frame_count == 108
    assert delegate.calls == 1
    with pytest.raises(RuntimeError, match="beyond its frozen bound"):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert frames.frame_count == 108
    assert delegate.calls == 1


def test_pp_runner_allows_an_action_ending_at_the_exact_frame_cap() -> None:
    timing = ControllerTiming(press_frames=2, release_frames=3, wait_frames=4)
    frames = _FrameCounter()
    delegate = _Executor(frames, timing)
    executor = SCRIPT["_HardBoundedCountingExecutor"](
        delegate,
        emulator=frames,
        timing=timing,
        start_frame=100,
        maximum_actions=1,
        maximum_frames=8,
    )

    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=2))

    assert frames.frame_count == 108
    assert executor.actions_executed == 1
    assert delegate.calls == 1


def test_pp_runner_refuses_the_action_after_the_exact_action_cap() -> None:
    timing = ControllerTiming(press_frames=2, release_frames=3, wait_frames=4)
    frames = _FrameCounter()
    delegate = _Executor(frames, timing)
    executor = SCRIPT["_HardBoundedCountingExecutor"](
        delegate,
        emulator=frames,
        timing=timing,
        start_frame=100,
        maximum_actions=1,
        maximum_frames=1_000,
    )

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert executor.actions_executed == 1
    assert delegate.calls == 1
    with pytest.raises(RuntimeError, match="beyond its frozen bound"):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert executor.actions_executed == 1
    assert delegate.calls == 1


def test_pp_runner_refuses_the_next_battle_and_step_at_the_exact_caps() -> None:
    SCRIPT["_require_next_battle_capacity"](
        battles_completed=31,
        maximum_completed_battles=32,
    )
    with pytest.raises(RuntimeError, match="refused a battle"):
        SCRIPT["_require_next_battle_capacity"](
            battles_completed=32,
            maximum_completed_battles=32,
        )

    SCRIPT["_require_next_encounter_step_capacity"](
        encounter_steps=9_999,
        maximum_encounter_steps=10_000,
    )
    with pytest.raises(RuntimeError, match="refused a step"):
        SCRIPT["_require_next_encounter_step_capacity"](
            encounter_steps=10_000,
            maximum_encounter_steps=10_000,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("actions_executed", 250_001),
        ("frames_executed", 5_000_001),
        ("battles_completed", 33),
        ("encounter_steps", 10_001),
    ),
)
def test_pp_runner_runtime_bound_gate_distinguishes_every_counter(
    field: str,
    value: int,
) -> None:
    counters = {
        "actions_executed": 250_000,
        "frames_executed": 5_000_000,
        "battles_completed": 32,
        "encounter_steps": 10_000,
    }
    plan = SimpleNamespace(
        bounds=SimpleNamespace(
            maximum_controller_actions=250_000,
            maximum_frames=5_000_000,
            maximum_completed_battles=32,
            maximum_encounter_steps=10_000,
        )
    )
    SCRIPT["_require_runtime_bounds"](
        plan=plan,
        actions=SimpleNamespace(actions_executed=counters["actions_executed"]),
        frames_executed=counters["frames_executed"],
        battles_completed=counters["battles_completed"],
        encounter_steps=counters["encounter_steps"],
    )
    counters[field] = value

    with pytest.raises(RuntimeError, match="exhausted a frozen"):
        SCRIPT["_require_runtime_bounds"](
            plan=plan,
            actions=SimpleNamespace(actions_executed=counters["actions_executed"]),
            frames_executed=counters["frames_executed"],
            battles_completed=counters["battles_completed"],
            encounter_steps=counters["encounter_steps"],
        )


@pytest.mark.parametrize(
    ("current_total", "maximum_total", "expected"),
    (
        (80, 80, False),
        (67, 100, False),
        (66, 100, True),
        (34, 100, True),
    ),
)
def test_pp_runner_middle_bin_gate_uses_exact_frozen_boundaries(
    current_total: int,
    maximum_total: int,
    expected: bool,
) -> None:
    assert SCRIPT["_require_middle_pp_state"](current_total, maximum_total) is expected


@pytest.mark.parametrize(
    ("current_total", "maximum_total", "message"),
    (
        (33, 100, "skipped past"),
        (-1, 100, "invalid"),
        (101, 100, "invalid"),
        (0, 0, "invalid"),
        (True, 100, "invalid"),
    ),
)
def test_pp_runner_middle_bin_gate_rejects_low_or_invalid_evidence(
    current_total: int,
    maximum_total: int,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        SCRIPT["_require_middle_pp_state"](current_total, maximum_total)


@pytest.mark.parametrize(
    "mutation",
    (None, "not_battle", "species", "missing_level", "zero_level", "high_level"),
)
def test_pp_runner_authenticates_each_live_wild_encounter(
    mutation: str | None,
) -> None:
    raw = SimpleNamespace(
        battle_state=1,
        enemy_species_id=21,
        enemy_level=15,
    )
    entry = SimpleNamespace(
        possible_wild_species_ids=(21, 23),
        venue_maximum_wild_level=17,
    )
    if mutation == "not_battle":
        raw.battle_state = 0
    elif mutation == "species":
        raw.enemy_species_id = 24
    elif mutation == "missing_level":
        raw.enemy_level = None
    elif mutation == "zero_level":
        raw.enemy_level = 0
    elif mutation == "high_level":
        raw.enemy_level = 18

    if mutation is None:
        SCRIPT["_require_declared_wild_encounter"](raw, entry)
    else:
        with pytest.raises(RuntimeError, match="undeclared wild"):
            SCRIPT["_require_declared_wild_encounter"](raw, entry)


def _safe_move_state() -> SimpleNamespace:
    return SimpleNamespace(
        active_party_index=0,
        active_party_species_id=28,
        battler_level=50,
        battler_moves=(44, 39, 58, 57),
        battler_status=0,
        battler_hp=80,
        battler_max_hp=100,
        battler_pp=(10, 10, 0, 5),
        player_disabled_move_slot=None,
    )


def _safe_move_entry() -> SimpleNamespace:
    return SimpleNamespace(
        target_species_id=28,
        target_level=50,
        target_move_ids=(44, 39, 58, 57),
        safe_move_slots=(1, 3, 4),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("active_party_index", 1),
        ("active_party_species_id", 29),
        ("battler_level", None),
        ("battler_level", 49),
        ("battler_level", 52),
        ("battler_moves", (45, 39, 58, 57)),
        ("battler_status", None),
        ("battler_status", 8),
        ("battler_hp", None),
        ("battler_hp", 0),
        ("battler_hp", 50),
        ("battler_hp", 101),
        ("battler_max_hp", None),
        ("battler_max_hp", 0),
        ("battler_pp", None),
        ("battler_pp", (10, 10, 0)),
        ("player_disabled_move_slot", True),
        ("player_disabled_move_slot", -1),
        ("player_disabled_move_slot", 5),
    ),
)
def test_pp_runner_safe_move_policy_distinguishes_every_safety_predicate(
    field: str,
    value: object,
) -> None:
    state = _safe_move_state()
    setattr(state, field, value)

    with pytest.raises(RuntimeError, match="per-turn safety"):
        SCRIPT["_select_safe_move"](state, _safe_move_entry())


def test_pp_runner_safe_move_policy_uses_first_enabled_positive_pp_slot() -> None:
    state = _safe_move_state()
    entry = _safe_move_entry()
    assert SCRIPT["_select_safe_move"](state, entry) == 1

    state.player_disabled_move_slot = 1
    assert SCRIPT["_select_safe_move"](state, entry) == 4

    state.battler_pp = (1, 0, 0, 0)
    with pytest.raises(RuntimeError, match="no safe declared move"):
        SCRIPT["_select_safe_move"](state, entry)


def test_pp_runner_requires_ready_field_control_after_each_battle() -> None:
    raw = SimpleNamespace(battle_state=0)
    SCRIPT["_require_ready_field_control"](raw, input_ready=True)
    raw.battle_state = 1
    with pytest.raises(RuntimeError, match="ready field control"):
        SCRIPT["_require_ready_field_control"](raw, input_ready=True)
    raw.battle_state = 0
    with pytest.raises(RuntimeError, match="ready field control"):
        SCRIPT["_require_ready_field_control"](raw, input_ready=False)


def _terminal_state() -> SimpleNamespace:
    return SimpleNamespace(
        game_started=True,
        map_id=22,
        battle_state=0,
        party_hp=(100, 90, 80, 70, 60, 50),
        party_status=(0, 0, 0, 0, 0, 0),
        party_levels=(50, 40, 40, 40, 40, 40),
    )


def _terminal_entry() -> SimpleNamespace:
    return SimpleNamespace(
        venue_map_id=22,
        target_party_slot=1,
        target_level=50,
        maximum_total_pp=80,
        middle_pp_ceiling=53,
        current_total_pp=80,
        minimum_pp_consumption=27,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        None,
        "game",
        "map",
        "battle",
        "readiness",
        "buttons",
        "hp_shape",
        "faint",
        "status",
        "level_low",
        "level_high",
        "maximum",
        "above_middle",
        "below_middle",
        "minimum_consumption",
        "no_battle",
    ),
)
def test_pp_runner_terminal_gate_distinguishes_every_acceptance_predicate(
    mutation: str | None,
) -> None:
    raw = _terminal_state()
    entry = _terminal_entry()
    values: dict[str, object] = {
        "input_ready": True,
        "pressed_buttons": (),
        "final_total": 53,
        "final_maximum": 80,
        "battles_completed": 1,
    }
    if mutation == "game":
        raw.game_started = False
    elif mutation == "map":
        raw.map_id = 23
    elif mutation == "battle":
        raw.battle_state = 1
    elif mutation == "readiness":
        values["input_ready"] = False
    elif mutation == "buttons":
        values["pressed_buttons"] = ("a",)
    elif mutation == "hp_shape":
        raw.party_hp = raw.party_hp[:-1]
    elif mutation == "faint":
        raw.party_hp = (0, *raw.party_hp[1:])
    elif mutation == "status":
        raw.party_status = (8, *raw.party_status[1:])
    elif mutation == "level_low":
        raw.party_levels = (49, *raw.party_levels[1:])
    elif mutation == "level_high":
        raw.party_levels = (52, *raw.party_levels[1:])
    elif mutation == "maximum":
        values["final_maximum"] = 81
    elif mutation == "above_middle":
        values["final_total"] = 54
        entry.minimum_pp_consumption = 26
    elif mutation == "below_middle":
        values["final_total"] = 26
    elif mutation == "minimum_consumption":
        entry.minimum_pp_consumption = 28
    elif mutation == "no_battle":
        values["battles_completed"] = 0

    if mutation is None:
        SCRIPT["_require_terminal_acceptance"](raw, entry, **values)
    else:
        with pytest.raises(RuntimeError, match="terminal state"):
            SCRIPT["_require_terminal_acceptance"](raw, entry, **values)


def test_pp_runner_protected_state_helper_rejects_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = SimpleNamespace()
    reader = SimpleNamespace(
        read=lambda: raw,
        read_pokedex_state=lambda: SimpleNamespace(),
        read_all_box_states=lambda: SimpleNamespace(),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_party_experience",
        lambda emulator, subject: (1, 2, 3, 4, 5, 6),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "red_pp_protected_state_sha256",
        lambda *args, **kwargs: "a" * 64,
    )
    entry = SimpleNamespace(target_party_slot=1)

    assert (
        SCRIPT["_require_protected_state"](
            reader,
            SimpleNamespace(),
            entry,
            "a" * 64,
        )
        is raw
    )
    with pytest.raises(RuntimeError, match="changed protected"):
        SCRIPT["_require_protected_state"](
            reader,
            SimpleNamespace(),
            entry,
            "b" * 64,
        )


def test_pp_runner_protected_input_and_rom_guards_detect_changes(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected.json"
    protected.write_bytes(b'{"value":1}\n')
    expected = {protected: hashlib.sha256(protected.read_bytes()).hexdigest()}
    SCRIPT["_require_protected_files_unchanged"](expected)
    protected.write_bytes(b'{"value":2}\n')
    with pytest.raises(RuntimeError, match="changed an authenticated"):
        SCRIPT["_require_protected_files_unchanged"](expected)

    rom = tmp_path / "red.gb"
    rom.write_bytes(b"rom")
    adjacent = SCRIPT["rom_adjacent_artifacts"](rom)
    Path(f"{rom}.ram").write_bytes(b"sidecar")
    with pytest.raises(RuntimeError, match="created a ROM-adjacent artifact"):
        SCRIPT["_require_rom_adjacent_unchanged"](
            rom,
            adjacent,
            operation="test",
        )


class _RecordingWriter:
    def __init__(self) -> None:
        self.records: list[tuple[str, Mapping[str, object]]] = []

    def append(
        self,
        stream: str,
        record: Mapping[str, object],
        *,
        durable: bool = False,
    ) -> None:
        assert durable is True
        self.records.append((stream, record))


def test_pp_runner_retains_path_free_failure_after_progress() -> None:
    writer = _RecordingWriter()

    def fail(progress_sink: object) -> dict[str, object]:
        assert callable(progress_sink)
        progress_sink({"battles_completed": 1})
        raise RuntimeError("failed beside /private/root/source.state")

    with pytest.raises(RuntimeError, match="failed beside"):
        SCRIPT["_execute_with_retention"](writer, fail)

    assert [stream for stream, _record in writer.records] == [
        "progress",
        "failure",
    ]
    failure = writer.records[-1][1]
    assert failure["exception_message"] == "failed beside [private-path]"
    assert failure["exception_message_redacted"] is True
    assert failure["private_path_fields"] == 0


def test_pp_runner_commits_the_capture_only_after_all_postconditions() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    run_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    closure = next(
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.FunctionDef) and node.name == "execute_and_validate"
    )
    call_lines: dict[str, list[int]] = {}
    for node in ast.walk(closure):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_lines.setdefault(node.func.id, []).append(node.lineno)
    protected_lines = sorted(call_lines["_require_protected_files_unchanged"])
    execute_line = min(call_lines["_execute_preparation"])
    authenticate_line = min(call_lines["_authenticate_materialized_output"])
    publish_line = min(call_lines["_publish_output_envelope"])

    assert len(protected_lines) == 2
    assert execute_line < protected_lines[0] < authenticate_line
    assert authenticate_line < protected_lines[1] < publish_line


@pytest.mark.parametrize(
    "mutation",
    (
        "file_digest",
        "map",
        "battle",
        "readiness",
        "faint",
        "status",
        "level",
        "total_receipt",
        "maximum_receipt",
        "above_middle",
        "below_middle",
    ),
)
def test_pp_runner_reload_authentication_distinguishes_every_terminal_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    output = tmp_path / "prepared.state"
    output.write_bytes(b"saved-state")
    state = {
        "ready": True,
        "current_total": 50,
        "maximum_total": 80,
    }
    raw = SimpleNamespace(
        map_id=22,
        battle_state=0,
        party_hp=(100, 90, 80, 70, 60, 50),
        party_status=(0, 0, 0, 0, 0, 0),
        party_levels=(51, 40, 40, 40, 40, 40),
    )
    entry = SimpleNamespace(
        protected_state_sha256="protected-a",
        venue_map_id=22,
        target_party_slot=1,
        target_level=50,
        middle_pp_ceiling=53,
    )
    terminal = {
        "output_state_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "final_total_pp": 50,
        "maximum_total_pp": 80,
    }

    if mutation == "file_digest":
        terminal["output_state_sha256"] = "0" * 64
    elif mutation == "map":
        raw.map_id = 23
    elif mutation == "battle":
        raw.battle_state = 1
    elif mutation == "readiness":
        state["ready"] = False
    elif mutation == "faint":
        raw.party_hp = (0, 90, 80, 70, 60, 50)
    elif mutation == "status":
        raw.party_status = (8, 0, 0, 0, 0, 0)
    elif mutation == "level":
        raw.party_levels = (52, 40, 40, 40, 40, 40)
    elif mutation == "total_receipt":
        terminal["final_total_pp"] = 49
    elif mutation == "maximum_receipt":
        terminal["maximum_total_pp"] = 81
    elif mutation == "above_middle":
        state["current_total"] = 54
        terminal["final_total_pp"] = 54
    elif mutation == "below_middle":
        state["current_total"] = 26
        terminal["final_total_pp"] = 26
    else:  # pragma: no cover - parametrization owns this branch
        raise AssertionError(mutation)

    class FakeEmulator:
        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def load_state(self, path: Path) -> None:
            assert path == output

    class FakeReader:
        def __init__(self, emulator: object) -> None:
            assert isinstance(emulator, FakeEmulator)

        def read_input_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(ready=state["ready"])

    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "PyBoyAdapter",
        lambda *args, **kwargs: FakeEmulator(),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "PokemonRedStateReader", FakeReader)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_require_protected_state",
        lambda *args, **kwargs: raw,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_current_target_pp",
        lambda *args, **kwargs: (
            state["current_total"],
            state["maximum_total"],
        ),
    )

    with pytest.raises(RuntimeError, match="authentication|changed before"):
        SCRIPT["_authenticate_materialized_output"](
            rom_path=tmp_path / "red.gb",
            output_state=output,
            entry=entry,
            terminal=terminal,
        )


def test_pp_runner_detects_output_bytes_changed_during_reload_authentication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "prepared.state"
    output.write_bytes(b"saved-state")
    terminal = {
        "output_state_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "final_total_pp": 50,
        "maximum_total_pp": 80,
    }
    raw = SimpleNamespace(
        map_id=22,
        battle_state=0,
        party_hp=(100, 90, 80, 70, 60, 50),
        party_status=(0, 0, 0, 0, 0, 0),
        party_levels=(51, 40, 40, 40, 40, 40),
    )
    entry = SimpleNamespace(
        protected_state_sha256="protected-a",
        venue_map_id=22,
        target_party_slot=1,
        target_level=50,
        middle_pp_ceiling=53,
    )

    class MutatingEmulator:
        def __enter__(self) -> MutatingEmulator:
            return self

        def __exit__(self, *args: object) -> None:
            output.write_bytes(b"changed-during-reload")

        def load_state(self, path: Path) -> None:
            assert path == output

    class ReadyReader:
        def __init__(self, emulator: object) -> None:
            assert isinstance(emulator, MutatingEmulator)

        def read_input_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(ready=True)

    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "PyBoyAdapter",
        lambda *args, **kwargs: MutatingEmulator(),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "PokemonRedStateReader", ReadyReader)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_require_protected_state",
        lambda *args, **kwargs: raw,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_current_target_pp",
        lambda *args, **kwargs: (50, 80),
    )

    with pytest.raises(RuntimeError, match="changed during reload"):
        SCRIPT["_authenticate_materialized_output"](
            rom_path=tmp_path / "red.gb",
            output_state=output,
            entry=entry,
            terminal=terminal,
        )


def test_pp_runner_claims_once_before_controller_and_has_no_learning_actor() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    calls = [
        (node.func.id, node.lineno)
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    lines_by_name: dict[str, list[int]] = {}
    for name, line in calls:
        lines_by_name.setdefault(name, []).append(line)

    plan_append = next(
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "plan"
    )
    claim_line = next(
        line for line in lines_by_name["_write_exclusive"] if line > plan_append.lineno
    )
    execute_line = min(lines_by_name["_execute_preparation"])

    assert plan_append.lineno < claim_line < execute_line
    assert source.count("_execute_preparation(") == 2
    assert "transient_zero_pp_main_is_dialogue=False" in source
    assert "active_party_index != 0" in source
    assert "policy_state.active_party_species_id != entry.target_species_id" in source
    assert "teacher" not in {
        (node.module or "").split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "candidate_menu" not in {
        (node.module or "").split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


def test_pp_runner_wires_testable_live_predicates_into_the_execution_loop() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_execute_preparation"
    )
    called = [
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert {
        "_require_declared_wild_encounter",
        "_require_middle_pp_state",
        "_require_protected_state",
        "_require_ready_field_control",
        "_require_terminal_acceptance",
        "_select_safe_move",
    } <= set(called)
    assert called.count("_require_protected_state") == 3
    for name in (
        "_require_declared_wild_encounter",
        "_require_middle_pp_state",
        "_require_ready_field_control",
        "_require_terminal_acceptance",
        "_select_safe_move",
    ):
        assert called.count(name) == 1


def test_pp_runner_wires_every_authorization_guard_before_attempt_claim() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    run_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    named_calls = {
        node.func.id: node.lineno
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    begin_artifact_line = next(
        node.lineno
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "begin_artifact"
    )
    required = (
        "_require_execution_input_bindings",
        "_require_context_catalog_binding",
        "_require_source_capture_bindings",
        "_require_rom_binding",
        "_require_runtime_venue_binding",
        "_require_exact_green_ci_run",
        "_require_fresh_output_identity",
        "_require_designated_private_root",
    )

    assert all(name in named_calls for name in required)
    assert all(named_calls[name] < begin_artifact_line for name in required)


def test_pp_runner_binds_ci_and_output_guards_to_live_run_values() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    run_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    calls = {
        node.func.id: node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {
            "_require_exact_green_ci_run",
            "_require_fresh_output_identity",
            "_require_designated_private_root",
        }
    }

    ci_call = calls["_require_exact_green_ci_run"]
    assert [ast.unparse(value) for value in ci_call.args] == [
        "exact_ci_run",
        "exact_ci_attempt",
    ]
    assert {item.arg: ast.unparse(item.value) for item in ci_call.keywords} == {
        "source_commit": "source.git_commit",
    }

    output_call = calls["_require_fresh_output_identity"]
    assert [ast.unparse(value) for value in output_call.args] == ["output_state", "entry"]
    assert not output_call.keywords

    root_call = calls["_require_designated_private_root"]
    assert [ast.unparse(value) for value in root_call.args] == ["requested_root"]
    assert {item.arg: ast.unparse(item.value) for item in root_call.keywords} == {
        "protected_inputs": "private_input_paths",
        "output_state": "output_state",
    }


def test_pp_runner_read_only_preflight_returns_before_attempt_claim() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.index("if execution_request is None:") < source.index("begin_artifact")
    assert '"controller_actions": 0' in source
    assert '"learner_outcomes_opened": 0' in source
    assert '"model_predictions": 0' in source
    assert '"teacher_queries": 0' in source


def test_pp_runner_main_preserves_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = SimpleNamespace(
        parse_args=lambda argv: SimpleNamespace(),
        error=lambda message: pytest.fail(message),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "_parser", lambda: parser)

    def interrupted(args: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setitem(SCRIPT_GLOBALS, "_run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        SCRIPT["main"]([])
