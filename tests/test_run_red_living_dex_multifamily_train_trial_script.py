# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    red_dual_capability_scenario_specs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/run_red_living_dex_multifamily_train_trial.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="run_red_living_dex_multifamily_train_trial_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _args() -> list[str]:
    return [
        "--expected-source-commit",
        "a" * 40,
        "--context-catalog",
        "/protected/catalog.json",
        "--context-plan",
        "/protected/plan.json",
        "--private-root",
        "/protected/artifacts",
        "--rom",
        "/protected/red.gb",
    ]


def _trial(
    ordinal: int,
    *,
    partition: str,
    family: str,
    candidate_index: int,
) -> dict[str, object]:
    rows = [dict(row) for row in red_dual_capability_scenario_specs()[0].policy_rows()]
    return {
        "partition": partition,
        "context_identity_sha256": _sha(f"context-{ordinal}"),
        "root_consumption_sha256": _sha(f"root-{ordinal}"),
        "family_identity_sha256": family,
        "candidate_index": candidate_index,
        "candidate_rows": rows,
        "mechanics": {"binding": _sha(f"mechanic-{ordinal}")},
    }


def _plan_document(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    train_family = _sha("train-family")
    development_family = _sha("development-family")
    trials = [
        _trial(
            ordinal,
            partition="train" if ordinal < 8 else "development",
            family=train_family if ordinal < 8 else development_family,
            candidate_index=ordinal % 2,
        )
        for ordinal in range(16)
    ]
    globals_ = SCRIPT["_validate_plan_document"].__globals__
    payload: dict[str, object] = {
        "schema": SCRIPT["freezer_v3"].PLAN_SCHEMA,
        "lane_id": SCRIPT["LANE_ID"],
        "status": "frozen_before_prediction_action_or_outcome",
        "source_commit": SCRIPT["FROZEN_SOURCE_COMMIT"],
        "source_bundle_sha256": SCRIPT["FROZEN_SOURCE_BUNDLE_SHA256"],
        "rom_sha256": SCRIPT["POKEMON_RED_US_REV_0"].sha256,
        "registry_sha256": SCRIPT["REGISTRY_SHA256"],
        "context_catalog_sha256": SCRIPT["CONTEXT_CATALOG_SHA256"],
        "context_plan_sha256": SCRIPT["CONTEXT_PLAN_SHA256"],
        "inventory": {"contexts": 16},
        "curriculum": {"train_trials": 8, "development_trials": 8},
        "trials": trials,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "roots_claimed": 0,
    }
    plan_sha256 = canonical_sha256(payload)
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", plan_sha256)
    return {**payload, "plan_sha256": plan_sha256}


def _frozen_trial(document: dict[str, object], ordinal: int = 0) -> object:
    trial = document["trials"][ordinal]  # type: ignore[index]
    return SCRIPT["_FrozenTrial"](ordinal, trial, canonical_sha256(trial))


class _Record:
    def __init__(
        self,
        document: dict[str, object],
        *,
        manifest_sha256: str,
        record_id: str = "record",
        kind: str = "kind",
    ) -> None:
        self._document = document
        self.summary = SimpleNamespace(
            manifest_sha256=manifest_sha256,
            record_sha256=_sha("record"),
            record_id=record_id,
            kind=kind,
            total_bytes=1,
        )

    def read(self) -> dict[str, object]:
        return copy.deepcopy(self._document)


def test_parser_has_no_user_selected_trial_or_context() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.watch is False
    assert parsed.speed is None
    assert not hasattr(parsed, "slot_id")
    assert not hasattr(parsed, "trial_ordinal")
    assert SCRIPT["SELECTED_TRAIN_TRIAL_ORDINAL"] == 0
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_parser"]().parse_args([*_args(), "--speed", "8"])


def test_main_authenticates_public_then_plan_then_inputs_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[object] = []
    gate = object()
    frozen = object()
    inputs = object()
    terminal = SCRIPT["_TrialTerminal"](
        {"schema": SCRIPT["RESULT_SCHEMA"], "status": "settled"},
        True,
    )
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_authenticate_public_gate",
        lambda args: (events.append(("public", args.expected_source_commit)), gate)[1],
    )
    monkeypatch.setitem(
        globals_,
        "_load_frozen_plan",
        lambda args: (events.append(("plan", args.private_root)), frozen)[1],
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_frozen_inputs",
        lambda args, actual_gate, actual_frozen: (
            events.append(("inputs", actual_gate, actual_frozen)),
            inputs,
        )[1],
    )
    monkeypatch.setitem(
        globals_,
        "_execute_selected_trial",
        lambda args, actual_gate, actual_frozen, actual_inputs: (
            events.append(("execute", actual_gate, actual_frozen, actual_inputs)),
            terminal,
        )[1],
    )

    assert SCRIPT["main"](_args()) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "settled"
    assert events == [
        ("public", "a" * 40),
        ("plan", Path("/protected/artifacts")),
        ("inputs", gate, frozen),
        ("execute", gate, frozen, inputs),
    ]


def test_public_failure_stops_before_private_plan_open(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_opens = 0
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_authenticate_public_gate",
        lambda args: (_ for _ in ()).throw(
            SCRIPT["RedMultifamilyTrainTrialError"]("public_evidence_authentication")
        ),
    )

    def private(args: object) -> object:
        nonlocal private_opens
        del args
        private_opens += 1
        raise AssertionError("private plan opened")

    monkeypatch.setitem(globals_, "_load_frozen_plan", private)

    assert SCRIPT["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert private_opens == 0
    assert result["failure_stage"] == "public_evidence_authentication"
    assert "/protected" not in json.dumps(result)


def test_plan_validator_accepts_only_balanced_root_and_family_disjoint_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)

    SCRIPT["_validate_plan_document"](document)

    repeated_root = copy.deepcopy(document)
    repeated_root["trials"][1]["root_consumption_sha256"] = repeated_root["trials"][0][  # type: ignore[index]
        "root_consumption_sha256"
    ]
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_validate_plan_document"](repeated_root)

    family_leak = copy.deepcopy(document)
    train_family = family_leak["trials"][0]["family_identity_sha256"]  # type: ignore[index]
    for row in family_leak["trials"][8:]:  # type: ignore[index]
        row["family_identity_sha256"] = train_family
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_validate_plan_document"](family_leak)

    imbalanced = copy.deepcopy(document)
    imbalanced["trials"][1]["candidate_index"] = 0  # type: ignore[index]
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_validate_plan_document"](imbalanced)


def test_plan_validator_rejects_effect_or_menu_mutation_even_with_rehashed_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    globals_ = SCRIPT["_validate_plan_document"].__globals__

    mutated = copy.deepcopy(document)
    mutated["controller_actions"] = 1
    payload = {key: value for key, value in mutated.items() if key != "plan_sha256"}
    mutated["plan_sha256"] = canonical_sha256(payload)
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", mutated["plan_sha256"])
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_validate_plan_document"](mutated)

    document = _plan_document(monkeypatch)
    leaked = copy.deepcopy(document)
    leaked["trials"][0]["candidate_rows"][0]["species_ref"] = "private"  # type: ignore[index]
    payload = {key: value for key, value in leaked.items() if key != "plan_sha256"}
    leaked["plan_sha256"] = canonical_sha256(payload)
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", leaked["plan_sha256"])
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_validate_plan_document"](leaked)


def test_loader_preselects_exact_first_train_intervention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    manifest = _sha("manifest")
    globals_ = SCRIPT["_load_frozen_plan"].__globals__
    monkeypatch.setitem(globals_, "FROZEN_PLAN_MANIFEST_SHA256", manifest)
    record = _Record(document, manifest_sha256=manifest)

    class Store:
        def find_sealed_record(self, record_id: str, *, expected_kind: str) -> _Record:
            assert record_id == SCRIPT["freezer_v3"].PLAN_RECORD_ID
            assert expected_kind == SCRIPT["freezer_v3"].PLAN_RECORD_KIND
            return record

    monkeypatch.setitem(globals_, "open_private_root", lambda *args, **kwargs: Store())
    frozen = SCRIPT["_load_frozen_plan"](SimpleNamespace(private_root=Path("/protected/artifacts")))

    assert frozen.selected_trial.ordinal == 0
    assert frozen.selected_trial.partition == "train"
    assert frozen.selected_trial.candidate_index == 0
    assert frozen.selected_trial.document == document["trials"][0]  # type: ignore[index]


@pytest.mark.parametrize(
    "mutation",
    ("context", "root", "partition", "availability", "duplicate"),
)
def test_selected_context_rejects_every_frozen_root_binding_mutation(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    context = SimpleNamespace(
        context_identity_sha256=trial.context_identity_sha256,
        root_consumption_sha256=trial.root_consumption_sha256,
        root_available=True,
        assignment=SimpleNamespace(partition="train"),
    )
    contexts = (context,)
    if mutation == "context":
        context.context_identity_sha256 = _sha("other-context")
    elif mutation == "root":
        context.root_consumption_sha256 = _sha("other-root")
    elif mutation == "partition":
        context.assignment.partition = "validation"
    elif mutation == "availability":
        context.root_available = False
    elif mutation == "duplicate":
        contexts = (context, copy.copy(context))
    else:  # pragma: no cover - parameter list owns this branch
        raise AssertionError(mutation)

    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="selected_context_authentication",
    ):
        SCRIPT["_selected_context"](contexts, trial)


def test_selected_context_returns_only_the_exact_available_train_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    context = SimpleNamespace(
        context_identity_sha256=trial.context_identity_sha256,
        root_consumption_sha256=trial.root_consumption_sha256,
        root_available=True,
        assignment=SimpleNamespace(partition="train"),
    )

    assert SCRIPT["_selected_context"]((context,), trial) is context


@pytest.mark.parametrize("mutation", ("family", "payload", "duplicate"))
def test_selected_mechanic_rejects_family_or_full_payload_mutation(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    family = trial.family_identity_sha256
    payload = copy.deepcopy(trial.document["mechanics"])
    mechanic = SimpleNamespace(
        family_identity_sha256=family,
        private_dict=lambda: copy.deepcopy(payload),
    )
    mechanics = (mechanic,)
    if mutation == "family":
        mechanic.family_identity_sha256 = _sha("other-family")
    elif mutation == "payload":
        payload["binding"] = _sha("other-mechanic")
    elif mutation == "duplicate":
        mechanics = (mechanic, copy.copy(mechanic))
    else:  # pragma: no cover - parameter list owns this branch
        raise AssertionError(mutation)

    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="frozen_mechanics_authentication",
    ):
        SCRIPT["_selected_mechanic"](mechanics, trial)


def test_private_trial_claim_precedes_global_root_claim_and_is_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    events: list[object] = []
    written_root: dict[str, str] = {}
    claim_documents: list[dict[str, object]] = []

    class Store:
        def inspect_sealed_record_metadata(self, record_id: str, *, expected_kind: str) -> None:
            events.append(("inspect", record_id, expected_kind))
            return None

        def publish_sealed_record(
            self,
            record_id: str,
            *,
            kind: str,
            record: dict[str, object],
        ) -> _Record:
            events.append(("private_claim", record_id, kind))
            claim_documents.append(copy.deepcopy(record))
            return _Record(
                record,
                manifest_sha256=_sha("claim-manifest"),
                record_id=record_id,
                kind=kind,
            )

    frozen = SCRIPT["_FrozenPlan"](
        Store(),
        SimpleNamespace(manifest_sha256=_sha("plan-manifest")),
        document,
        trial,
    )
    gate = SCRIPT["_PublicGate"](
        "a" * 40,
        SCRIPT["FROZEN_SOURCE_BUNDLE_SHA256"],
        _sha("runner"),
        SimpleNamespace(sha256=_sha("runtime")),
    )
    globals_ = SCRIPT["_claim_trial_and_root"].__globals__
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", document["plan_sha256"])
    monkeypatch.setitem(
        globals_, "open_fixed_account_claim_registry", lambda: Path("/claim-registry")
    )
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda registry, *, exclusive: (
            events.append(("lease", registry, exclusive)),
            nullcontext(),
        )[1],
    )
    monkeypatch.setitem(
        globals_,
        "root_claim_is_available",
        lambda registry, identity: (events.append(("available", identity)), True)[1],
    )

    def write(registry: Path, **fields: str) -> None:
        events.append(("global_claim", fields["root_consumption_sha256"]))
        written_root.update({"schema": "pokemon.red.fresh-composition-root-claim.v1", **fields})

    monkeypatch.setitem(globals_, "write_root_claim", write)
    monkeypatch.setitem(
        globals_,
        "read_root_claim",
        lambda registry, identity: (
            events.append(("verify_global", identity)),
            dict(written_root),
        )[1],
    )

    claim = SCRIPT["_claim_trial_and_root"](gate, frozen, trial)

    event_names = [event[0] for event in events]
    assert event_names == [
        "lease",
        "inspect",
        "inspect",
        "available",
        "private_claim",
        "global_claim",
        "verify_global",
    ]
    assert event_names.index("private_claim") < event_names.index("global_claim")
    assert claim_documents[0]["candidate_index"] == 0
    assert claim_documents[0]["trial_sha256"] == trial.trial_sha256
    assert claim_documents[0]["retry_allowed"] is False
    assert claim.execution_identity_sha256 == written_root["execution_identity_sha256"]


def test_existing_private_claim_refuses_before_root_availability_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    root_checks = 0
    writes = 0

    class Store:
        def inspect_sealed_record_metadata(self, *args: object, **kwargs: object) -> object:
            return object()

    frozen = SCRIPT["_FrozenPlan"](
        Store(),
        SimpleNamespace(manifest_sha256=_sha("manifest")),
        document,
        trial,
    )
    gate = SCRIPT["_PublicGate"](
        "a" * 40,
        SCRIPT["FROZEN_SOURCE_BUNDLE_SHA256"],
        _sha("runner"),
        SimpleNamespace(sha256=_sha("runtime")),
    )
    globals_ = SCRIPT["_claim_trial_and_root"].__globals__
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", document["plan_sha256"])
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("/registry"))
    monkeypatch.setitem(
        globals_, "fixed_account_claim_registry_lease", lambda *args, **kwargs: nullcontext()
    )

    def available(*args: object) -> bool:
        nonlocal root_checks
        root_checks += 1
        return True

    def write(*args: object, **kwargs: object) -> None:
        nonlocal writes
        writes += 1

    monkeypatch.setitem(globals_, "root_claim_is_available", available)
    monkeypatch.setitem(globals_, "write_root_claim", write)

    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="frozen_trial_already_consumed",
    ):
        SCRIPT["_claim_trial_and_root"](gate, frozen, trial)
    assert root_checks == 0
    assert writes == 0


def test_consumed_root_refuses_before_private_claim_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    publications = 0

    class Store:
        def inspect_sealed_record_metadata(self, *args: object, **kwargs: object) -> None:
            return None

        def publish_sealed_record(self, *args: object, **kwargs: object) -> object:
            nonlocal publications
            publications += 1
            raise AssertionError("private claim must not publish")

    frozen = SCRIPT["_FrozenPlan"](
        Store(),
        SimpleNamespace(manifest_sha256=_sha("manifest")),
        document,
        trial,
    )
    gate = SCRIPT["_PublicGate"](
        "a" * 40,
        SCRIPT["FROZEN_SOURCE_BUNDLE_SHA256"],
        _sha("runner"),
        SimpleNamespace(sha256=_sha("runtime")),
    )
    globals_ = SCRIPT["_claim_trial_and_root"].__globals__
    monkeypatch.setitem(globals_, "FROZEN_PLAN_SHA256", document["plan_sha256"])
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("/registry"))
    monkeypatch.setitem(
        globals_, "fixed_account_claim_registry_lease", lambda *args, **kwargs: nullcontext()
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)

    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="frozen_root_already_consumed",
    ):
        SCRIPT["_claim_trial_and_root"](gate, frozen, trial)
    assert publications == 0


def test_controller_and_frame_ports_are_physically_closed_until_claim() -> None:
    events: list[object] = []

    class Controller:
        def execute(self, action: object) -> str:
            events.append(("controller", action))
            return "executed"

    class Frames:
        frame_count = 10

        def tick(self, frames: int) -> None:
            events.append(("frames", frames))
            self.frame_count += frames

        def press(self, button: str) -> None:
            events.append(("press", button))

        def release(self, button: str) -> None:
            events.append(("release", button))

        def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
            events.append(("read_cartridge_ram", bank, address))
            return 0x2A

    controller = SCRIPT["_ClaimGatedController"](Controller())
    frames = SCRIPT["_ClaimGatedFrames"](Frames())

    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="controller_input_before_claim",
    ):
        controller.execute("before")
    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="frame_advance_before_claim",
    ):
        frames.tick(12)
    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="controller_input_before_claim",
    ):
        frames.press("a")
    with pytest.raises(
        SCRIPT["RedMultifamilyTrainTrialError"],
        match="controller_input_before_claim",
    ):
        frames.release("a")
    assert events == []
    assert controller.attempted_before_claim == 1
    assert frames.attempted_frames_before_claim == 12
    assert frames.attempted_buttons_before_claim == 2
    assert isinstance(frames, SCRIPT["ReadOnlyCartridgeRam"])
    assert frames.read_cartridge_ram_u8(2, 0xA123) == 0x2A

    frames.arm()
    controller.arm()
    assert controller.execute("after") == "executed"
    frames.press("a")
    frames.tick(3)
    frames.release("a")
    assert events == [
        ("read_cartridge_ram", 2, 0xA123),
        ("controller", "after"),
        ("press", "a"),
        ("frames", 3),
        ("release", "a"),
    ]
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        controller.arm()
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        frames.arm()


@pytest.mark.parametrize("value", (True, -1, 256, "byte"))
def test_claim_gated_cartridge_ram_port_rejects_invalid_bytes(value: object) -> None:
    class Frames:
        frame_count = 0

        def tick(self, frames: int) -> None:
            del frames

        def read_cartridge_ram_u8(self, bank: int, address: int) -> object:
            del bank, address
            return value

    gated = SCRIPT["_ClaimGatedFrames"](Frames())

    with pytest.raises(TypeError, match="cartridge-RAM reader returned an invalid byte"):
        gated.read_cartridge_ram_u8(0, 0xA000)


def test_claim_gated_cartridge_ram_port_requires_delegate_support() -> None:
    class Frames:
        frame_count = 0

        def tick(self, frames: int) -> None:
            del frames

    gated = SCRIPT["_ClaimGatedFrames"](Frames())

    with pytest.raises(TypeError, match="claim-gated frames lack cartridge-RAM access"):
        gated.read_cartridge_ram_u8(0, 0xA000)


@pytest.mark.parametrize("selected_index", (0, 1))
def test_frozen_intervention_executes_only_selected_binding_and_observes_fresh_ledger(
    selected_index: int,
) -> None:
    events: list[object] = []
    ledger = DependencySpecimenLedger((("pokemon:test", 1),))
    outcome = SimpleNamespace()

    class Report:
        def public_dict(self) -> dict[str, object]:
            return {"settled": True}

    class Selected:
        def execute(self) -> Report:
            events.append(("execute", selected_index))
            return Report()

    class Bound:
        def bind_selection(self, index: int) -> Selected:
            events.append(("bind", index))
            assert index == selected_index
            return Selected()

        def verify_outcome(self, *, selected_kind: object, after_ledger: object) -> object:
            events.append(("verify", selected_kind, after_ledger))
            assert after_ledger is ledger
            return outcome

    def observe() -> DependencySpecimenLedger:
        events.append("observe")
        return ledger

    result = SCRIPT["_run_frozen_intervention"](
        Bound(),
        selected_index,
        observe_after=observe,
    )

    assert result == ("settled", None, outcome, {"settled": True})
    assert events[0:3] == [("bind", selected_index), ("execute", selected_index), "observe"]
    assert [event for event in events if isinstance(event, tuple) and event[0] == "execute"] == [
        ("execute", selected_index)
    ]


def test_execution_failure_is_censored_without_observer_or_alternate_candidate() -> None:
    events: list[object] = []
    interrupted = SimpleNamespace()

    class Selected:
        def execute(self) -> None:
            events.append("selected")
            raise RuntimeError("failure")

    class Bound:
        def bind_selection(self, index: int) -> Selected:
            events.append(("bind", index))
            return Selected()

        def verify_outcome(self, *, selected_kind: object, after_ledger: object) -> object:
            events.append(("verify", selected_kind, after_ledger))
            assert after_ledger is None
            return interrupted

    def observe() -> object:
        events.append("observer")
        raise AssertionError("observer must not run after failed execution")

    result = SCRIPT["_run_frozen_intervention"](
        Bound(),
        0,
        observe_after=observe,
    )

    assert result == (
        "interrupted",
        "selected_capability_execution",
        interrupted,
        None,
    )
    assert events == [
        ("bind", 0),
        "selected",
        ("verify", SCRIPT["GoalKind"].ACQUIRE_SPECIES, None),
    ]


@pytest.mark.parametrize("projection", ("raises", "malformed"))
def test_optional_report_projection_cannot_erase_independently_verified_outcome(
    projection: str,
) -> None:
    ledger = DependencySpecimenLedger((("pokemon:test", 1),))
    outcome = SimpleNamespace()

    class Report:
        def public_dict(self) -> object:
            if projection == "raises":
                raise RuntimeError("diagnostic projection failed")
            return ["not", "a", "mapping"]

    class Selected:
        def execute(self) -> Report:
            return Report()

    class Bound:
        def bind_selection(self, index: int) -> Selected:
            assert index == 0
            return Selected()

        def verify_outcome(self, *, selected_kind: object, after_ledger: object) -> object:
            assert selected_kind is SCRIPT["GoalKind"].ACQUIRE_SPECIES
            assert after_ledger is ledger
            return outcome

    assert SCRIPT["_run_frozen_intervention"](
        Bound(),
        0,
        observe_after=lambda: ledger,
    ) == ("settled", None, outcome, None)


def test_terminal_is_path_free_train_only_and_never_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)
    published: list[dict[str, object]] = []

    class Store:
        def publish_sealed_record(
            self,
            record_id: str,
            *,
            kind: str,
            record: dict[str, object],
        ) -> _Record:
            published.append(copy.deepcopy(record))
            return _Record(record, manifest_sha256=_sha("terminal-manifest"))

    frozen = SCRIPT["_FrozenPlan"](
        Store(),
        SimpleNamespace(manifest_sha256=_sha("plan-manifest")),
        document,
        trial,
    )
    claim = SCRIPT["_TrialClaim"](
        _sha("trial-identity"),
        _sha("execution"),
        "claim-id",
        SimpleNamespace(manifest_sha256=_sha("claim-manifest")),
    )

    class Outcome:
        def private_dict(self) -> dict[str, object]:
            return {"status": "settled", "reward": 1}

        def public_dict(self) -> dict[str, object]:
            return {"status": "settled", "reward": 1, "species_identity_fields": 0}

    terminal = SCRIPT["_publish_terminal"](
        frozen,
        trial,
        claim,
        status="settled",
        interruption_stage=None,
        outcome=Outcome(),
        execution_summary={"settled": True},
        controller_actions=10,
        attempted_controller_actions=10,
        emulator_frames_advanced=100,
    )

    assert terminal.settled is True
    assert terminal.public["partition"] == "train"
    assert terminal.public["causal_train_examples_added"] == 1
    assert terminal.public["verified_development_outcomes_added"] == 0
    assert terminal.public["model_fits_added"] == 0
    assert terminal.public["authority_promotions_added"] == 0
    assert terminal.public["transfer_results_added"] == 0
    assert terminal.public["retry_allowed"] is False
    assert "/protected" not in json.dumps(terminal.public)
    assert published[0]["retry_allowed"] is False


def test_interrupted_terminal_is_durable_but_never_becomes_a_training_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trial = _frozen_trial(document)

    class Store:
        def publish_sealed_record(
            self,
            record_id: str,
            *,
            kind: str,
            record: dict[str, object],
        ) -> _Record:
            return _Record(record, manifest_sha256=_sha("terminal-manifest"))

    frozen = SCRIPT["_FrozenPlan"](
        Store(),
        SimpleNamespace(manifest_sha256=_sha("plan-manifest")),
        document,
        trial,
    )
    claim = SCRIPT["_TrialClaim"](
        _sha("trial-identity"),
        _sha("execution"),
        "claim-id",
        SimpleNamespace(manifest_sha256=_sha("claim-manifest")),
    )

    class Outcome:
        def private_dict(self) -> dict[str, object]:
            return {"status": "interrupted", "reward": None}

        def public_dict(self) -> dict[str, object]:
            return {"status": "interrupted", "reward": None}

    terminal = SCRIPT["_publish_terminal"](
        frozen,
        trial,
        claim,
        status="interrupted",
        interruption_stage="selected_capability_execution",
        outcome=Outcome(),
        execution_summary=None,
        controller_actions=3,
        attempted_controller_actions=4,
        emulator_frames_advanced=30,
    )

    assert terminal.settled is False
    assert terminal.public["trial_consumed"] is True
    assert terminal.public["retry_allowed"] is False
    assert terminal.public["causal_train_examples_added"] == 0
    assert terminal.public["independent_post_transition_observation"] is False


def test_source_orders_claim_before_selected_execution_and_has_no_model_or_teacher_path() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    execution = source[
        source.index("def _execute_selected_trial(") : source.index(
            "def _authenticate_historical_replay("
        )
    ]

    zero_effect = execution.index("preclaim_zero_effect_authentication")
    claim = execution.index("claim = _claim_trial_and_root(")
    frame_arm = execution.index("frames.arm()")
    controller_arm = execution.index("controller_gate.arm()")
    selected = execution.index("_run_frozen_intervention(")
    terminal = execution.index("terminal = _publish_terminal(")
    assert zero_effect < claim < frame_arm < controller_arm < selected < terminal
    assert execution.count("_run_frozen_intervention(") == 1
    assert "score_red_living_dex_option" not in source
    assert "bind_bounded_evolution_offer" not in source
    assert "teacher_fallback" not in source
    assert "--slot-id" not in source
    assert "--trial" not in source


def test_failure_receipt_never_claims_the_private_consumption_state() -> None:
    result = SCRIPT["_failure_receipt"]("selected_trial_execution")

    assert result["status"] == "failed_closed"
    assert result["claim_state"] == (
        "inspect_private_trial_and_global_root_registry_before_any_retry"
    )
    assert result["authority_promotions_added"] == 0
    assert result["transfer_results_added"] == 0
    assert "/protected" not in json.dumps(result)


def test_selected_bounds_are_candidate_specific_and_finite() -> None:
    acquire = SCRIPT["_selected_limits"](0)
    evolve = SCRIPT["_selected_limits"](1)

    assert 0 < acquire[0] < evolve[0]
    assert 0 < acquire[1] < evolve[1]
    with pytest.raises(SCRIPT["RedMultifamilyTrainTrialError"]):
        SCRIPT["_selected_limits"](2)


def test_plan_reconstruction_helpers_are_exact_frozen_bytes() -> None:
    for relative, expected in SCRIPT["FROZEN_SUPPORT_SHA256S"].items():
        assert hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() == expected


def test_counterbalance_fixture_really_contains_four_of_each_per_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _plan_document(monkeypatch)
    trials = document["trials"]

    assert Counter(row["candidate_index"] for row in trials[:8]) == Counter({0: 4, 1: 4})  # type: ignore[index]
    assert Counter(row["candidate_index"] for row in trials[8:]) == Counter({0: 4, 1: 4})  # type: ignore[index]
