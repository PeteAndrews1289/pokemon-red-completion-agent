from __future__ import annotations

import hashlib
import inspect
import json
import runpy
import stat
import subprocess
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest
from test_party_development_outcome_campaign import _WIDTHS, _plan
from test_party_development_outcome_dataset import _frozen_input_catalog

from pokemon_red_completion.observation import ReadOnlyCartridgeRam
from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialClaim,
)
from pokemon_red_completion.party_development_outcome_results import (
    PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
    PartyDevelopmentOutcomeTrialResult,
    build_party_development_trial_terminal,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
)
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_outcomes import OutcomeEvidenceStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_red_party_development_outcome_campaign.py"
FREEZER_PATH = PROJECT_ROOT / "scripts" / "freeze_red_party_development_outcome_campaign.py"
RUNNER = runpy.run_path(str(RUNNER_PATH))
FREEZER = runpy.run_path(str(FREEZER_PATH))


def _store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()
    return initialize_private_root(
        private,
        repository_root=repository,
        allow_same_device=True,
        git_worktree_probe=lambda _path: False,
    )


def _audit_document() -> dict[str, object]:
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    return {
        "schema": "pokemon.red.party-development-frozen-input-catalog-v1-audit.v1",
        "status": "input_integrity_verified_outcomes_closed",
        "catalog": {
            "catalog_file_sha256": "1" * 64,
            "catalog_sha256": catalog.catalog_sha256,
            "prospective_catalog_sha256": catalog.prospective_catalog_sha256,
            "question_count": 14,
            "candidate_row_count": 55,
        },
        "catalog_source": {
            "source_commit": catalog.source_commit,
            "source_bundle_sha256": catalog.source_bundle_sha256,
        },
        "acceptance": {
            "all_candidate_menus_reconstructed": True,
            "all_capture_envelope_joins_reconstructed": True,
            "all_reservation_joins_reconstructed": True,
            "all_root_lineages_reconstructed": True,
            "all_source_profile_joins_reconstructed": True,
            "committed_catalog_source_reproduced": True,
            "input_files_unchanged": True,
            "path_and_target_scan_clean": True,
            "rom_adjacent_artifacts_unchanged": True,
        },
        "protected_access": {
            "answers_selected": 0,
            "controller_actions": 0,
            "crystal_cases_opened": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "outcomes_opened": 0,
            "sealed_red_cases_opened": 0,
            "teacher_queries": 0,
            "authority_promoted": False,
        },
    }


def test_campaign_private_loader_requires_exact_external_ascii_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input.json"
    payload = b'{"schema":"test"}\n'
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    document, observed = RUNNER["_load_private_json"](
        path,
        expected_sha256=digest,
        subject="test input",
    )

    assert document == {"schema": "test"}
    assert observed == payload
    with pytest.raises(RuntimeError, match="digest or size differs"):
        RUNNER["_load_private_json"](
            path,
            expected_sha256="0" * 64,
            subject="test input",
        )
    with pytest.raises(RuntimeError, match="outside the repository"):
        RUNNER["_require_external"](
            PROJECT_ROOT / "private.json",
            subject="test input",
        )


@pytest.mark.parametrize("script", [RUNNER, FREEZER])
@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema":"first","schema":"second"}\n',
        b'{"schema":"test","value":NaN}\n',
    ],
)
def test_campaign_private_loaders_reject_ambiguous_json(
    tmp_path: Path,
    script: dict[str, object],
    payload: bytes,
) -> None:
    path = tmp_path / "ambiguous.json"
    path.write_bytes(payload)

    with pytest.raises(RuntimeError, match="not valid ASCII JSON"):
        script["_load_private_json"](
            path,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            subject="ambiguous input",
        )


@pytest.mark.parametrize(
    ("execute", "watch", "private_root", "authorization", "message"),
    [
        (False, True, None, None, "watch mode"),
        (False, False, Path("private"), None, "must not receive"),
        (False, False, None, "1" * 64, "without execution"),
        (True, False, None, "1" * 64, "needs the private artifact root"),
        (True, False, Path("private"), None, "exact plan authorization"),
        (True, False, Path("private"), "NOT-A-DIGEST", "exact plan authorization"),
    ],
)
def test_campaign_execution_flags_fail_closed_before_protected_reads(
    execute: bool,
    watch: bool,
    private_root: Path | None,
    authorization: str | None,
    message: str,
) -> None:
    args = Namespace(
        execute=execute,
        watch=watch,
        private_artifact_root=private_root,
        execute_authorized_plan_sha256=authorization,
    )

    with pytest.raises(RuntimeError, match=message):
        RUNNER["_validate_execution_request"](args)


def test_campaign_execution_requires_the_exact_frozen_plan_digest() -> None:
    args = Namespace(
        execute=True,
        watch=False,
        private_artifact_root=Path("private"),
        execute_authorized_plan_sha256="1" * 64,
    )

    RUNNER["_validate_execution_request"](
        args,
        expected_plan_sha256="1" * 64,
    )
    with pytest.raises(RuntimeError, match="exact prospectively frozen"):
        RUNNER["_validate_execution_request"](
            args,
            expected_plan_sha256="2" * 64,
        )


def test_campaign_protected_input_guard_detects_bytes_and_rom_sidecars(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected.json"
    rom = tmp_path / "cartridge.gb"
    protected.write_bytes(b"frozen")
    rom.write_bytes(b"rom")
    files = {
        protected: hashlib.sha256(protected.read_bytes()).hexdigest(),
        rom: hashlib.sha256(rom.read_bytes()).hexdigest(),
    }
    before = RUNNER["rom_adjacent_artifacts"](rom)

    RUNNER["_require_protected_inputs_unchanged"](
        files,
        rom_path=rom,
        rom_before=before,
    )
    protected.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed a protected input"):
        RUNNER["_require_protected_inputs_unchanged"](
            files,
            rom_path=rom,
            rom_before=before,
        )

    protected.write_bytes(b"frozen")
    Path(f"{rom}.ram").write_bytes(b"sidecar")
    with pytest.raises(RuntimeError, match="changed a protected input"):
        RUNNER["_require_protected_inputs_unchanged"](
            files,
            rom_path=rom,
            rom_before=before,
        )


def test_campaign_freezer_rechecks_protected_files_from_disk(tmp_path: Path) -> None:
    protected = tmp_path / "catalog.json"
    protected.write_bytes(b"frozen")
    files = {protected: hashlib.sha256(protected.read_bytes()).hexdigest()}

    FREEZER["_require_protected_inputs_unchanged"](files)
    protected.write_bytes(b"changed")

    with pytest.raises(RuntimeError, match="changed or raced"):
        FREEZER["_require_protected_inputs_unchanged"](files)


def test_campaign_freezer_accepts_only_the_verified_14_55_audit() -> None:
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    document = _audit_document()

    FREEZER["_validate_input_audit"](
        document,
        catalog=catalog,
        catalog_file_sha256="1" * 64,
    )

    changed = json.loads(json.dumps(document))
    changed["catalog"]["candidate_row_count"] = 54
    with pytest.raises(RuntimeError, match="does not verify"):
        FREEZER["_validate_input_audit"](
            changed,
            catalog=catalog,
            catalog_file_sha256="1" * 64,
        )

    empty = json.loads(json.dumps(document))
    empty["acceptance"] = {}
    empty["protected_access"] = {}
    with pytest.raises(RuntimeError, match="does not verify"):
        FREEZER["_validate_input_audit"](
            empty,
            catalog=catalog,
            catalog_file_sha256="1" * 64,
        )


def test_campaign_runner_binds_the_exact_audit_digest_in_its_plan() -> None:
    plan = _plan()
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    document = _audit_document()
    rebound = replace(plan, input_audit_result_sha256=canonical_sha256(document))

    RUNNER["_validate_input_audit"](
        document,
        plan=rebound,
        catalog=catalog,
    )

    document["acceptance"]["input_files_unchanged"] = False
    with pytest.raises(RuntimeError, match="does not authorize"):
        RUNNER["_validate_input_audit"](
            document,
            plan=rebound,
            catalog=catalog,
        )


def test_freezer_output_is_exclusive_private_and_not_replaceable(
    tmp_path: Path,
) -> None:
    output = tmp_path / "campaign-plan.json"
    payload = b'{"schema":"campaign"}\n'

    FREEZER["_write_exclusive"](output, payload)

    assert output.read_bytes() == payload
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(RuntimeError, match="already exists"):
        FREEZER["_write_exclusive"](output, payload)


def _successful_ci_payload(run_id: int = 123) -> dict[str, object]:
    return {
        "attempt": 1,
        "conclusion": "success",
        "databaseId": run_id,
        "event": "pull_request",
        "headSha": "a" * 40,
        "status": "completed",
        "url": (
            "https://github.com/PeteAndrews1289/"
            f"pokemon-red-completion-agent/actions/runs/{run_id}"
        ),
        "workflowName": "CI",
    }


@pytest.mark.parametrize("script", [RUNNER, FREEZER])
def test_campaign_tools_authenticate_exact_green_ci(
    monkeypatch: pytest.MonkeyPatch,
    script: dict[str, object],
) -> None:
    payload = _successful_ci_payload()
    module = script["subprocess"]
    monkeypatch.setattr(
        module,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    result = script["_require_exact_green_ci_run"](
        123,
        1,
        source_commit="a" * 40,
    )
    assert result is None or result == payload

    payload["headSha"] = "b" * 40
    with pytest.raises(RuntimeError, match="not the exact successful"):
        script["_require_exact_green_ci_run"](
            123,
            1,
            source_commit="a" * 40,
        )


@pytest.mark.parametrize("script", [RUNNER, FREEZER])
def test_campaign_tools_reject_invalid_ci_identity_before_query(
    monkeypatch: pytest.MonkeyPatch,
    script: dict[str, object],
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        script["subprocess"],
        "run",
        lambda *_args, **_kwargs: calls.append(object()),
    )

    with pytest.raises(RuntimeError, match="CI identity is invalid"):
        script["_require_exact_green_ci_run"](
            True,
            1,
            source_commit="a" * 40,
        )

    assert calls == []


def test_prepared_question_execution_reservation_uses_frozen_output_state() -> None:
    catalog = _frozen_input_catalog(candidate_widths=_WIDTHS)
    question = catalog.questions[0]
    original = next(
        item
        for item in _frozen_input_catalog(candidate_widths=_WIDTHS).questions
        if item.scenario_id == question.scenario_id
    )
    # A real reservation has more diagnostic fields than a frozen question.
    # Reuse the test catalog helper's reservation source through the existing
    # fixture factory and alter only the fields this execution adapter owns.
    from test_red_party_development_adapter import _reservation

    reservation = replace(
        _reservation(
            kind=question.binding.kind,
            preparation=PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION,
        ),
        scenario_id=question.scenario_id,
        partition=question.binding.partition,
        goal=question.binding.goal,
    )

    executed = RUNNER["_execution_reservation"](reservation, original)

    assert executed.source_checkpoint_id == original.capture_id
    assert executed.source_state_sha256 == original.binding.initial_state_sha256
    assert executed.source_envelope_sha256 == original.capture_envelope_sha256
    assert executed.preparation.value == "none"
    assert executed.target_pp_bin is None


def test_claim_without_terminal_is_permanently_censored_before_resume(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    assignment = plan.assignments[0]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    store.publish_sealed_record(
        RUNNER["_claim_id"](plan, assignment),
        kind=RUNNER["_CLAIM_KIND"],
        record=claim.private_dict(),
    )

    loaded = RUNNER["_load_claim"](store, plan, assignment)
    assert loaded == claim
    assert RUNNER["_load_terminal"](store, plan, assignment) is None

    censored = RUNNER["_publish_censored_terminal"](
        store,
        plan,
        assignment,
        claim,
    )

    assert censored.status is OutcomeEvidenceStatus.CENSORED
    assert RUNNER["_load_terminal"](store, plan, assignment) == censored


def test_complete_terminal_cannot_be_replaced_by_different_bytes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    assignment = plan.assignments[0]
    claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": OutcomeEvidenceStatus.INVALID.value,
        "failure_code": "execution_error",
        "retry_after_controller_input": False,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=OutcomeEvidenceStatus.INVALID,
        evidence_sha256=canonical_sha256(evidence),
        failure_code="execution_error",
    )
    terminal = build_party_development_trial_terminal(result, evidence=evidence)
    terminal_id = RUNNER["_terminal_id"](plan, assignment)
    store.publish_sealed_record(
        terminal_id,
        kind=RUNNER["_TERMINAL_KIND"],
        record=terminal,
    )

    changed = dict(terminal)
    changed["terminal_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="different content"):
        store.publish_sealed_record(
            terminal_id,
            kind=RUNNER["_TERMINAL_KIND"],
            record=changed,
        )


def test_runner_source_orders_durable_claim_before_trial_execution() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    collection = source.index("with store.collection_session(collection_id):")
    loop = source.index("for assignment in plan.active_assignments:", collection)
    publish = source.index("store.publish_sealed_record(", loop)
    execute = source.index("result, evidence = _execute_trial(", loop)

    assert publish < execute
    assert "candidate_decision_authority" not in source


class _CompleteReadPort:
    def __init__(self) -> None:
        self.frame_count = 0

    def read_u8(self, _address: int) -> int:
        return 0

    def read_cartridge_ram_u8(self, _bank: int, _address: int) -> int:
        return 0

    def press(self, _button: str) -> None:
        return None

    def release(self, _button: str) -> None:
        return None

    def tick(self, frames: int) -> None:
        self.frame_count += frames


def test_trial_ports_keep_complete_observation_outside_controller_proxy() -> None:
    emulator = _CompleteReadPort()

    ports = RUNNER["_build_trial_execution_ports"](
        emulator,
        maximum_frames=10,
    )

    assert ports.observation_emulator is emulator
    assert ports.reader._memory is emulator
    assert ports.party_reader.memory is emulator
    assert isinstance(ports.reader._memory, ReadOnlyCartridgeRam)
    assert not isinstance(ports.controller, ReadOnlyCartridgeRam)
    ports.controller.tick(6)
    assert ports.controller.frames_executed == 6


def test_preflight_and_execution_share_the_qualified_port_constructor() -> None:
    execute_source = inspect.getsource(RUNNER["_execute_trial"])
    preflight_source = inspect.getsource(RUNNER["_reconstruct_questions"])

    for source in (execute_source, preflight_source):
        assert "_build_trial_execution_ports(" in source
        assert "PokemonRedStateReader(" not in source
        assert "PokemonRedPartyReader(" not in source
    assert "ports.controller.frames_executed != 0" in preflight_source
