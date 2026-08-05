from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion import cli
from pokemon_red_completion.collection_protocol import (
    COLLECTION_REGISTRY_RELATIVE_PATH,
    parse_collection_registry,
)
from pokemon_red_completion.opening import OpeningChapterError, OpeningProgress
from pokemon_red_completion.play import QualifiedPlayProgress
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    SourceIdentity,
    canonical_sha256,
)
from pokemon_red_completion.rom import RomFingerprint


def _collection_registry():
    return parse_collection_registry(
        (cli.REPOSITORY_ROOT / COLLECTION_REGISTRY_RELATIVE_PATH).read_bytes()
    )


def _runtime_identity():
    payload = {
        "schema": "pokemon-red-runtime-identity-v1",
        "python": {
            "implementation": "CPython",
            "version": "3.14.3",
            "executable_sha256": "d" * 64,
        },
        "pyboy": {
            "distribution_name": "pyboy",
            "distribution_version": "2.7.0",
            "files": [
                {
                    "name": "pyboy/runtime.py",
                    "bytes": 7,
                    "sha256": "e" * 64,
                }
            ],
            "inventory_sha256": "f" * 64,
        },
    }
    return SimpleNamespace(
        pyboy_distribution_version="2.7.0",
        sha256="1" * 64,
        public_dict=lambda: payload,
    )


def test_diagnostic_schedule_is_uncounted_and_content_addressed() -> None:
    offsets, schedule_sha256 = cli._diagnostic_schedule(28_001)
    repeated, repeated_sha256 = cli._diagnostic_schedule(28_001)
    metadata: dict[str, object] = {
        "configuration": {"schema": "test-configuration"},
        "configuration_sha256": "stale",
        "collection": {"attempt": {"counted": True}},
    }

    cli._attach_diagnostic_schedule_metadata(
        metadata,
        seed=28_001,
        offsets=offsets,
        schedule_sha256=schedule_sha256,
    )

    assert offsets == repeated
    assert schedule_sha256 == repeated_sha256
    assert len(offsets) == 71
    collection = metadata["collection"]
    assert isinstance(collection, dict)
    assert collection["attempt"] == {"counted": False}
    assert collection["purpose"] == "pre_registration_robustness_diagnostic"
    configuration = metadata["configuration"]
    assert isinstance(configuration, dict)
    assert metadata["configuration_sha256"] == canonical_sha256(configuration)


def test_diagnostic_schedule_seed_rejects_invalid_values() -> None:
    for invalid in (-1, 1 << 64, True):
        with pytest.raises(ValueError, match="unsigned 64-bit"):
            cli._diagnostic_schedule(invalid)


def test_route_command_prints_validated_hall_of_fame_route(capsys) -> None:
    assert cli.main(["route"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["id"] == "power_on"
    assert payload[-1]["id"] == "enter_hall_of_fame"
    assert payload[-1]["prerequisites"] == ["defeat_champion"]
    assert len(payload) >= 30


def test_private_data_init_does_not_resolve_a_rom_and_prints_no_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = Path("/private/external/trajectories")
    observed: dict[str, object] = {}

    def fail_if_rom_resolved(argument: object) -> None:
        pytest.fail(f"ROM resolution was unexpectedly attempted for {argument!r}")

    def fake_initialize(root: Path, *, repository_root: Path) -> object:
        observed.update(root=root, repository_root=repository_root)
        return object()

    monkeypatch.setattr(cli, "resolve_rom_path", fail_if_rom_resolved)
    monkeypatch.setattr(cli, "initialize_private_root", fake_initialize)

    assert (
        cli.main(
            [
                "private-data",
                "init",
                "--private-root",
                str(private_root),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "schema": "private-root-init-v1",
        "status": "ready",
    }
    assert captured.err == ""
    assert str(private_root) not in captured.out
    assert observed == {
        "root": private_root,
        "repository_root": cli.REPOSITORY_ROOT,
    }


def test_private_data_init_redacts_private_root_from_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = Path("/private/external/trajectories")

    def fail_initialize(root: Path, *, repository_root: Path) -> None:
        del repository_root
        raise PrivateArtifactError(f"unsafe private root: {root}")

    monkeypatch.setattr(cli, "initialize_private_root", fail_initialize)

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "private-data",
                "init",
                "--private-root",
                str(private_root),
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "unsafe private root: <private>" in captured.err
    assert str(private_root) not in captured.err


def test_collection_status_is_read_only_before_the_campaign_starts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    private_root_path = Path("/private/external/trajectories")
    rom_path = Path("/private/Pokemon Red.gb")
    observed: dict[str, object] = {}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            observed["collection_id"] = collection_id
            return FakeSession()

        def begin_episode(self, _episode_id: str) -> None:
            pytest.fail("collection status must not begin an episode")

    class FakeLedger:
        @classmethod
        def open_existing(cls, **kwargs):
            observed["ledger"] = kwargs
            return None

    campaign_identity = object()
    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: rom_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda root: observed.update(registry_root=root) or registry,
    )
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda *args, **kwargs: (
            observed.update(metadata_call=(args, kwargs))
            or {"source": {}, "rom_identity": {}, "runtime_sha256": "a" * 64}
        ),
    )
    monkeypatch.setattr(
        cli,
        "_campaign_identity",
        lambda selected_registry, metadata: campaign_identity,
    )
    monkeypatch.setattr(
        cli,
        "find_dry_run_qualification",
        lambda store, identity, dry_run: (
            observed.update(
                dry_run_store=store,
                dry_run_identity=identity,
                dry_run=dry_run,
            )
            or None
        ),
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda root, *, repository_root: (
            observed.update(private_root=root, repository_root=repository_root) or FakeRoot()
        ),
    )
    monkeypatch.setattr(cli, "CollectionOutcomeLedger", FakeLedger)

    assert (
        cli.main(
            [
                "collection",
                "status",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(rom_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "pokemon-red-collection-status-v1"
    assert payload["campaign_started"] is False
    assert payload["dry_run_qualified"] is False
    assert payload["dry_run_qualification"] is None
    assert payload["declared_slots"] == 12
    assert payload["counts"]["pending"] == 12
    assert payload["ledger"] is None
    assert observed["collection_id"] == registry.collection_id
    assert observed["ledger"]["identity"] is campaign_identity
    assert str(private_root_path) not in json.dumps(payload)
    assert str(rom_path) not in json.dumps(payload)


def test_collection_status_reports_a_qualified_dry_run_and_started_campaign(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    private_root_path = Path("/private/external/trajectories")
    rom_path = Path("/private/Pokemon Red.gb")
    observed: dict[str, object] = {}
    receipt = {
        "schema": "pokemon-red-collection-outcome-ledger-v1",
        "collection_id": registry.collection_id,
        "declared_slots": 12,
        "counts": {
            "complete": 1,
            "failed": 0,
            "interrupted": 0,
            "invalid": 0,
            "pending": 11,
        },
        "slots": [],
        "ledger_sha256": "a" * 64,
    }
    qualification_payload = {
        "schema": "pokemon-red-schedule-dry-run-qualification-v1",
        "dry_run_id": registry.schedule_dry_run.dry_run_id,
        "status": "qualified",
    }

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            observed["collection_id"] = collection_id
            return FakeSession()

    class FakeQualification:
        def public_dict(self) -> dict[str, object]:
            return qualification_payload

    class FakeLedger:
        @classmethod
        def open_existing(cls, **kwargs):
            observed["ledger"] = kwargs
            return cls()

        def public_receipt(self) -> dict[str, object]:
            return receipt

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: rom_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda *args, **kwargs: {
            "source": {},
            "rom_identity": {},
            "runtime_sha256": "b" * 64,
        },
    )
    campaign_identity = object()
    monkeypatch.setattr(
        cli,
        "_campaign_identity",
        lambda selected_registry, metadata: campaign_identity,
    )
    monkeypatch.setattr(
        cli,
        "find_dry_run_qualification",
        lambda store, identity, dry_run: (
            observed.update(
                qualification_store=store,
                qualification_identity=identity,
                qualification_dry_run=dry_run,
            )
            or FakeQualification()
        ),
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda root, *, repository_root: FakeRoot(),
    )
    monkeypatch.setattr(cli, "CollectionOutcomeLedger", FakeLedger)

    assert (
        cli.main(
            [
                "collection",
                "status",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(rom_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["campaign_started"] is True
    assert payload["dry_run_qualified"] is True
    assert payload["dry_run_qualification"] == qualification_payload
    assert payload["counts"] == receipt["counts"]
    assert payload["ledger"] == receipt
    assert observed["collection_id"] == registry.collection_id
    assert observed["qualification_identity"] is campaign_identity
    assert observed["ledger"]["identity"] is campaign_identity
    assert str(private_root_path) not in json.dumps(payload)
    assert str(rom_path) not in json.dumps(payload)


def test_campaign_identity_pins_source_runtime_execution_and_rom() -> None:
    registry = _collection_registry()
    identity = cli._campaign_identity(
        registry,
        {
            "source": {
                "git_commit": "a" * 40,
                "worktree_dirty": False,
            },
            "runtime_sha256": "b" * 64,
            "rom_identity": {
                "sha1": "c" * 40,
                "sha256": "d" * 64,
            },
        },
    )

    assert identity.registry_sha256 == registry.registry_sha256
    assert identity.source_commit == "a" * 40
    assert identity.source_bundle_sha256 == registry.execution.source_bundle_sha256
    assert identity.teacher_execution_sha256 == registry.execution.teacher_execution_sha256
    assert identity.runtime_sha256 == "b" * 64
    assert identity.rom_sha1 == "c" * 40
    assert identity.rom_sha256 == "d" * 64


def test_battle_learning_requires_explicit_diagnostic_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_rom_resolved(argument: object) -> None:
        pytest.fail(f"ROM resolution was unexpectedly attempted for {argument!r}")

    monkeypatch.setattr(cli, "resolve_rom_path", fail_if_rom_resolved)

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "learn",
                "battle",
                "train",
                "--private-root",
                "/private/external",
                "--episode-id",
                "episode-001",
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "requires --diagnostic" in captured.err


def test_preassigned_battle_fit_requires_a_clean_source_before_private_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_rom = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_rom)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, True),
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda *args, **kwargs: pytest.fail("dirty source must fail before private data opens"),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "learn",
                "battle",
                "fit",
                "--private-root",
                "/private/external/trajectories",
                "--rom",
                str(private_rom),
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "clean worktree" in captured.err


def test_preassigned_battle_fit_refuses_an_opened_test_partition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    test_slot = next(slot for slot in cli._collection_slots(registry) if slot.partition == "test")
    private_rom = Path("/private/Pokemon Red.gb")

    class FakeSession:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            assert collection_id == registry.collection_id
            return FakeSession()

        def open_episode(self, episode_id: str) -> object:
            pytest.fail(f"test refusal must happen before opening {episode_id}")

    class FakeLedger:
        def reconcile(self) -> tuple[object, ...]:
            return (SimpleNamespace(slot=test_slot),)

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_rom)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, False),
    )
    monkeypatch.setattr(cli, "require_clean_source", lambda _source: None)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(cli, "_recording_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli, "_campaign_identity", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "open_private_root", lambda *args, **kwargs: FakeRoot())
    monkeypatch.setattr(cli, "find_dry_run_qualification", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli.CollectionOutcomeLedger,
        "open_existing",
        lambda *args, **kwargs: FakeLedger(),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "learn",
                "battle",
                "fit",
                "--private-root",
                "/private/external/trajectories",
                "--rom",
                str(private_rom),
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "test partition must remain unopened" in captured.err


def test_preassigned_battle_fit_authenticates_seven_roots_and_publishes_candidate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pokemon_red_completion import battle_dataset, battle_training

    registry = _collection_registry()
    slots = cli._collection_slots(registry)
    learning_slots = tuple(slot for slot in slots if slot.partition != "test")
    manifests = {
        slot.assignment_id: canonical_sha256({"slot": slot.assignment_id})
        for slot in learning_slots
    }
    private_rom = Path("/private/Pokemon Red.gb")
    observed: dict[str, object] = {"opened": [], "streams": []}

    class FakeSession:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeSummary:
        def public_dict(self) -> dict[str, object]:
            return {"kind": "battle_model", "status": "complete"}

    class FakeWriter:
        summary = FakeSummary()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def append(self, stream: str, record: object) -> None:
            cast_streams = observed["streams"]
            assert isinstance(cast_streams, list)
            cast_streams.append((stream, record))

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            assert collection_id == registry.collection_id
            return FakeSession()

        def open_episode(self, episode_id: str) -> object:
            cast_opened = observed["opened"]
            assert isinstance(cast_opened, list)
            cast_opened.append(episode_id)
            return SimpleNamespace(episode_id=episode_id)

        def begin_artifact(self, artifact_id: str, *, kind: str) -> FakeWriter:
            observed.update(artifact_id=artifact_id, artifact_kind=kind)
            return FakeWriter()

    class FakeLedger:
        def reconcile(self) -> tuple[object, ...]:
            return tuple(
                SimpleNamespace(
                    slot=slot,
                    status="complete",
                    episode_manifest_sha256=manifests[slot.assignment_id],
                )
                for slot in learning_slots
            )

    fake_model = SimpleNamespace(to_dict=lambda: {"weights": [1.0]})

    class FakeResult:
        model = fake_model
        model_sha256 = "a" * 64
        corpus_manifest_roster_sha256 = "b" * 64

        def public_receipt(self) -> dict[str, object]:
            return {
                "schema": "battle-imitation-preassigned-validation-v1",
                "scope": {"train_episodes": 5, "validation_episodes": 2},
                "qualification": {
                    "freeze_eligible": True,
                    "test_partition_opened": False,
                },
            }

    slot_by_episode = {slot.episode_id: slot for slot in learning_slots}

    def fake_load(reader: object, *args: object, **kwargs: object) -> object:
        episode_id = reader.episode_id
        slot = slot_by_episode[episode_id]
        return SimpleNamespace(
            episode_id=episode_id,
            root_lineage_id=slot.root_lineage_id,
            partition=slot.partition,
            regime="within_game",
            manifest_sha256=manifests[slot.assignment_id],
        )

    def fake_train(train: tuple[object, ...], validation: tuple[object, ...], **kwargs: object):
        assert len(train) == 5
        assert len(validation) == 2
        return FakeResult()

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_rom)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, False),
    )
    monkeypatch.setattr(cli, "require_clean_source", lambda _source: None)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(cli, "_recording_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli, "_campaign_identity", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "open_private_root", lambda *args, **kwargs: FakeRoot())
    monkeypatch.setattr(cli, "find_dry_run_qualification", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli.CollectionOutcomeLedger,
        "open_existing",
        lambda *args, **kwargs: FakeLedger(),
    )
    monkeypatch.setattr(battle_dataset, "load_battle_episode", fake_load)
    monkeypatch.setattr(battle_training, "train_preassigned_battle_ranker", fake_train)
    monkeypatch.setattr(cli.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))

    assert (
        cli.main(
            [
                "learn",
                "battle",
                "fit",
                "--private-root",
                "/private/external/trajectories",
                "--rom",
                str(private_rom),
                "--epochs",
                "25",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["qualification"]["freeze_eligible"]
    assert payload["qualification"]["test_partition_opened"] is False
    assert len(observed["opened"]) == 7
    assert set(observed["opened"]) == {slot.episode_id for slot in learning_slots}
    assert observed["artifact_id"] == "red-battle-candidate-fixed"
    assert observed["artifact_kind"] == "battle_model"
    assert [stream for stream, _ in observed["streams"]] == [
        "model",
        "training",
        "metrics",
    ]


def test_battle_learning_writes_only_a_private_typed_model_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pokemon_red_completion import battle_dataset, battle_training

    private_root_path = Path("/private/external/trajectories")
    observed: dict[str, object] = {"records": []}

    class FakeSummary:
        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "private-json-artifact-summary-v1",
                "artifact_id": "red-battle-ranker-fixed",
                "kind": "battle_model",
                "status": "complete",
                "stream_records": {"metrics": 1, "model": 1, "training": 1},
                "total_records": 3,
                "total_bytes": 2048,
                "manifest_sha256": "c" * 64,
            }

    class FakeWriter:
        summary = FakeSummary()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def append(self, stream: str, record: object) -> None:
            cast_records = observed["records"]
            assert isinstance(cast_records, list)
            cast_records.append((stream, record))

    fake_writer = FakeWriter()

    class FakeRoot:
        def open_episode(self, episode_id: str) -> object:
            observed["episode_id"] = episode_id
            return object()

        def begin_artifact(self, artifact_id: str, *, kind: str) -> FakeWriter:
            observed.update(artifact_id=artifact_id, artifact_kind=kind)
            return fake_writer

    fake_dataset = SimpleNamespace(
        partition="unassigned",
        episode_qualified=False,
        promotion_eligible=False,
        manifest_sha256="a" * 64,
        public_summary=lambda: {
            "schema": "battle-episode-dataset-summary-v1",
            "decisions": 422,
            "promotion_eligible": False,
        },
    )
    fake_model = SimpleNamespace(to_dict=lambda: {"model_id": "masked-linear", "weights": [1.0]})

    class FakeResult:
        model = fake_model
        model_sha256 = "b" * 64

        def public_receipt(self) -> dict[str, object]:
            return {
                "schema": "battle-imitation-diagnostic-v1",
                "status": "complete",
                "qualification": {
                    "promotion_eligible": False,
                    "held_out_evaluation": False,
                },
            }

    def fake_open_private_root(root: Path, *, repository_root: Path) -> FakeRoot:
        observed.update(private_root=root, repository_root=repository_root)
        return FakeRoot()

    def fake_load(
        reader: object,
        projector: object,
        *,
        required_provenance: object,
    ) -> object:
        observed.update(
            reader=reader,
            projector=projector,
            required_provenance=required_provenance,
        )
        return fake_dataset

    def fake_train(dataset: object, *, config: object) -> FakeResult:
        observed.update(dataset=dataset, config=config)
        return FakeResult()

    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, False),
    )
    monkeypatch.setattr(cli, "open_private_root", fake_open_private_root)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: _collection_registry(),
    )
    monkeypatch.setattr(battle_dataset, "load_battle_episode", fake_load)
    monkeypatch.setattr(battle_training, "train_diagnostic_battle_ranker", fake_train)
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="fixed"),
    )
    monkeypatch.setattr(
        cli,
        "resolve_rom_path",
        lambda argument: pytest.fail("learning must not resolve a ROM"),
    )

    assert (
        cli.main(
            [
                "learn",
                "battle",
                "train",
                "--private-root",
                str(private_root_path),
                "--episode-id",
                "episode-001",
                "--diagnostic",
                "--epochs",
                "25",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["qualification"]["held_out_evaluation"] is False
    assert payload["source"] == {"git_commit": "d" * 40, "worktree_dirty": False}
    assert payload["private_artifact"]["kind"] == "battle_model"
    assert str(private_root_path) not in captured.out
    assert captured.err == ""
    assert observed["episode_id"] == "episode-001"
    assert observed["artifact_id"] == "red-battle-ranker-fixed"
    assert observed["artifact_kind"] == "battle_model"
    assert [stream for stream, _ in observed["records"]] == [
        "model",
        "training",
        "metrics",
    ]


@pytest.mark.parametrize(
    "run_id",
    [
        "red-battle-v74-01-train",
        "red-battle-v74-06-validation",
        "red-battle-v74-08-test",
    ],
)
def test_battle_learning_rejects_preregistered_ids_before_opening_private_data(
    run_id: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    assignment = registry.assignment(run_id)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, False),
    )
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda *args, **kwargs: pytest.fail(
            "a preregistered episode must be rejected before private data is opened"
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "learn",
                "battle",
                "train",
                "--private-root",
                "/private/external/trajectories",
                "--episode-id",
                assignment.episode_id,
                "--diagnostic",
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "cannot open a preregistered collection episode" in captured.err


@pytest.mark.parametrize("partition", ["train", "validation", "test"])
def test_battle_learning_rejects_forged_assigned_headers_from_diagnostic_lane(
    partition: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pokemon_red_completion import battle_dataset, battle_training

    class FakeRoot:
        def open_episode(self, episode_id: str) -> object:
            assert episode_id == "diagnostic-forged-assignment"
            return object()

    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda *args, **kwargs: SourceIdentity("d" * 40, False),
    )
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: _collection_registry(),
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda *args, **kwargs: FakeRoot(),
    )
    monkeypatch.setattr(
        battle_dataset,
        "load_battle_episode",
        lambda *args, **kwargs: SimpleNamespace(
            partition=partition,
            episode_qualified=False,
        ),
    )
    monkeypatch.setattr(
        battle_training,
        "train_diagnostic_battle_ranker",
        lambda *args, **kwargs: pytest.fail("a sealed partition must never reach training"),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "learn",
                "battle",
                "train",
                "--private-root",
                "/private/external/trajectories",
                "--episode-id",
                "diagnostic-forged-assignment",
                "--diagnostic",
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "preassigned train, validation, and test episodes are sealed" in captured.err


def test_bootstrap_command_prints_only_public_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        def public_dict(self) -> dict[str, object]:
            return {"status": "ok", "clean_power_on": True}

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)
    monkeypatch.setattr(cli, "run_bootstrap_smoke", lambda path: FakeReport())

    assert cli.main(["bootstrap", "--rom", str(private_path)]) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {"clean_power_on": True, "status": "ok"}
    assert str(private_path) not in output


def test_opening_command_wires_watch_progress_and_public_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = ("power_on", "begin_adventure", "choose_starter")
        next_objective = "receive_pokedex"

        def public_dict(self) -> dict[str, object]:
            return {
                "status": "ok",
                "objective_progress": {
                    "verified": 3,
                    "total": 36,
                    "next": "receive_pokedex",
                },
            }

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_opening_chapter(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
    ) -> FakeReport:
        assert path == private_path
        assert watch is True
        assert speed == 4
        progress(
            OpeningProgress(
                checkpoint_id="bedroom_ready",
                label="Bedroom input ready",
                completed=1,
                total=6,
                frames_executed=9_804,
            )
        )
        progress(
            OpeningProgress(
                checkpoint_id="starter_obtained",
                label="Selected and verified Squirtle",
                completed=6,
                total=6,
                frames_executed=20_000,
            )
        )
        return FakeReport()

    monkeypatch.setattr(cli, "run_opening_chapter", fake_run_opening_chapter)

    assert (
        cli.main(
            [
                "opening",
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "4",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "objective_progress": {
            "next": "receive_pokedex",
            "total": 36,
            "verified": 3,
        },
        "status": "ok",
    }
    assert captured.err.splitlines() == [
        "[1/6] Bedroom input ready",
        "[6/6] Selected and verified Squirtle",
        "Objectives: 3/36 verified | Next: Deliver Oak's Parcel and receive the Pokédex",
    ]
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err


def test_opening_command_defaults_to_headless_unlimited_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = ("power_on",)
        next_objective = "begin_adventure"

        def public_dict(self) -> dict[str, object]:
            return {"status": "ok"}

    private_path = Path("/private/Pokemon Red.gb")
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_opening_chapter(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
    ) -> FakeReport:
        observed.update(path=path, watch=watch, speed=speed, progress=progress)
        return FakeReport()

    monkeypatch.setattr(cli, "run_opening_chapter", fake_run_opening_chapter)

    assert cli.main(["opening", "--rom", str(private_path)]) == 0

    captured = capsys.readouterr()
    assert observed == {
        "path": private_path,
        "watch": False,
        "speed": None,
        "progress": cli._print_opening_progress,
    }
    assert json.loads(captured.out) == {"status": "ok"}
    assert captured.err == "Objectives: 1/36 verified | Next: Complete the opening sequence\n"


def test_opening_command_rejects_speed_without_watch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["opening", "--speed", "2"])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "--speed requires --watch" in captured.err


def test_opening_command_reports_opening_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fail_opening(*args, **kwargs):
        raise OpeningChapterError("The opening teacher missed a verified gate.")

    monkeypatch.setattr(cli, "run_opening_chapter", fail_opening)

    with pytest.raises(SystemExit) as error:
        cli.main(["opening", "--rom", str(private_path)])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "The opening teacher missed a verified gate." in captured.err
    assert str(private_path) not in captured.err


def test_play_command_runs_the_continuous_watched_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = (
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
            "help_bill",
            "reach_vermilion",
            "defeat_misty",
        )
        next_objective = "obtain_cut"

        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "qualified-play-v5",
                "status": "ok",
                "game_complete": False,
            }

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_qualified_play(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
        battle_model,
        battle_control_model,
        execute_battle_control_model: bool,
        battle_control_confidence_threshold: float,
        battle_model_confidence_threshold: float,
        require_battle_model_teacher_agreement: bool,
        battle_correction_sink,
        battle_control_sink,
        battle_start_offsets,
    ) -> FakeReport:
        assert path == private_path
        assert watch is True
        assert speed == 4
        assert battle_model is None
        assert battle_control_model is None
        assert execute_battle_control_model is False
        assert battle_control_confidence_threshold == 0.0
        assert battle_model_confidence_threshold == 0.5
        assert require_battle_model_teacher_agreement is True
        assert battle_correction_sink is None
        assert battle_control_sink is None
        assert battle_start_offsets is None
        progress(
            QualifiedPlayProgress(
                checkpoint_id="bedroom_ready",
                label="Bedroom input ready",
                completed=1,
                total=73,
                frames_executed=9_804,
            )
        )
        progress(
            QualifiedPlayProgress(
                checkpoint_id="vermilion_reached",
                label="Reached stable Vermilion City",
                completed=73,
                total=73,
                frames_executed=501_922,
            )
        )
        return FakeReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_run_qualified_play)

    assert (
        cli.main(
            [
                "play",
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "4",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "game_complete": False,
        "schema": "qualified-play-v5",
        "status": "ok",
    }
    assert captured.err.splitlines() == [
        "[1/73] Bedroom input ready",
        "[73/73] Reached stable Vermilion City",
        "Objectives: 10/36 verified | Next: Obtain HM01 Cut aboard the S.S. Anne",
        "Completion verified: Champion defeated and Hall of Fame entered.",
    ]
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err


def test_play_command_finalizes_private_battle_corrections(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    appended: list[tuple[str, dict[str, object]]] = []

    class FakeModel:
        model_id = "pokemon.core.battle.masked-linear-ranker.v1"
        feature_names = ("feature",)

        def to_json(self) -> str:
            return "{}"

    class FakeSummary:
        def public_dict(self) -> dict[str, object]:
            return {"artifact_id": "red-battle-corrections-test", "status": "complete"}

    class FakeWriter:
        summary = FakeSummary()

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback) -> bool:
            assert exception_type is None
            return False

        def append(self, stream: str, record) -> None:
            appended.append((stream, dict(record)))

    class FakeRoot:
        def begin_artifact(self, artifact_id: str, *, kind: str) -> FakeWriter:
            assert artifact_id.startswith("red-battle-corrections-")
            assert kind == "battle_corrections"
            return FakeWriter()

    class FakeReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None
        battle_policy_report = {"correction_records": 1}

        def public_dict(self) -> dict[str, object]:
            return {"status": "ok", "game_complete": True}

    private_rom = Path("/private/Pokemon Red.gb")
    corrections_root = Path("/private/corrections")
    model_path = Path("/private/model/model.jsonl")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_rom)
    monkeypatch.setattr(cli, "load_battle_model_artifact", lambda path: FakeModel())
    monkeypatch.setattr(cli, "open_private_root", lambda *args, **kwargs: FakeRoot())

    def fake_play(*args, battle_correction_sink, **kwargs) -> FakeReport:
        assert battle_correction_sink is not None
        battle_correction_sink({"record_type": "battle_policy_correction"})
        return FakeReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_play)

    assert (
        cli.main(
            [
                "play",
                "--rom",
                str(private_rom),
                "--battle-model",
                str(model_path),
                "--battle-corrections-root",
                str(corrections_root),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["game_complete"] is True
    assert payload["battle_corrections"]["status"] == "complete"
    assert [stream for stream, _ in appended] == ["metadata", "corrections", "summary"]
    assert appended[-1][1]["game_complete"] is True


def test_play_command_finalizes_private_battle_control_labels(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    appended: list[tuple[str, dict[str, object]]] = []

    class FakeModel:
        model_id = "pokemon.core.battle.masked-mlp-ranker.v1"
        feature_names = tuple(f"feature-{index}" for index in range(102))

        def to_json(self) -> str:
            return "{}"

    class FakeWriter:
        summary = SimpleNamespace(
            public_dict=lambda: {"status": "complete", "artifact_id": "control"}
        )

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback) -> bool:
            assert exception_type is None
            return False

        def append(self, stream: str, record) -> None:
            appended.append((stream, dict(record)))

    class FakeRoot:
        def begin_artifact(self, artifact_id: str, *, kind: str) -> FakeWriter:
            assert artifact_id.startswith("red-battle-control-")
            assert kind == "battle_control_labels"
            return FakeWriter()

    class FakeReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None
        battle_policy_report = {"control_records": 1}

        def public_dict(self) -> dict[str, object]:
            return {"status": "ok", "game_complete": True}

    private_rom = Path("/private/Pokemon Red.gb")
    control_root = Path("/private/control")
    model_path = Path("/private/model/model.jsonl")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_rom)
    monkeypatch.setattr(cli, "load_battle_model_artifact", lambda path: FakeModel())
    monkeypatch.setattr(cli, "open_private_root", lambda *args, **kwargs: FakeRoot())

    def fake_play(*args, battle_control_sink, **kwargs) -> FakeReport:
        assert battle_control_sink is not None
        battle_control_sink({"record_type": "battle_control_label"})
        return FakeReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_play)

    assert (
        cli.main(
            [
                "play",
                "--rom",
                str(private_rom),
                "--battle-model",
                str(model_path),
                "--allow-model-disagreement",
                "--battle-control-root",
                str(control_root),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["battle_control_labels"]["status"] == "complete"
    assert [stream for stream, _ in appended] == ["metadata", "labels", "summary"]


def test_play_command_stops_cleanly_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_qualified_play", interrupt)

    assert cli.main(["play", "--rom", str(private_path)]) == 130

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ("Stopped safely without saving. No success report was emitted.\n")
    assert str(private_path) not in captured.err


def test_record_command_wires_private_episode_and_prints_path_free_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakePlayReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None

        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "qualified-play-v5",
                "status": "ok",
                "game_complete": True,
            }

    class FakeEpisodeSummary:
        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "private-episode-summary-v1",
                "episode_id": expected_episode_id,
                "status": "complete",
                "stream_records": {"episode": 1, "executions": 42},
                "total_records": 43,
                "total_bytes": 4096,
                "manifest_sha256": "a" * 64,
            }

    class FakeWriter:
        summary = FakeEpisodeSummary()

        def __enter__(self) -> FakeWriter:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeSink:
        def __init__(
            self,
            writer: FakeWriter,
            *,
            episode_id: str,
            game_id: str,
        ) -> None:
            assert writer is fake_writer
            observed.update(
                sink_episode_id=episode_id,
                sink_game_id=game_id,
            )

        def write_episode_header(self, *, metadata: object) -> None:
            observed["header"] = metadata

    private_path = Path("/private/Pokemon Red.gb")
    private_root_path = Path("/private/external/trajectories")
    expected_episode_id = "red-teacher-1234567890abcdef1234567890abcdef"
    fake_writer = FakeWriter()
    observed: dict[str, object] = {}
    fake_metadata = {
        "adapter_id": cli.POKEMON_RED_ADAPTER_ID,
        "ontology_id": cli.POKEMON_CORE_ONTOLOGY_ID,
        "source": {"git_commit": "a" * 40, "worktree_dirty": False},
    }
    fake_root = SimpleNamespace(
        begin_episode=lambda episode_id: observed.update(begin_episode=episode_id) or fake_writer
    )

    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_open_private_root(root: Path, *, repository_root: Path) -> object:
        observed.update(private_root=root, repository_root=repository_root)
        return fake_root

    monkeypatch.setattr(cli, "open_private_root", fake_open_private_root)
    monkeypatch.setattr(cli, "EpisodeTrajectorySink", FakeSink)
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda path, *, episode_id, watch, speed, assignment, execution, schedule_dry_run: (
            observed.update(
                metadata_rom=path,
                metadata_episode_id=episode_id,
                metadata_watch=watch,
                metadata_speed=speed,
                metadata_assignment=assignment,
                metadata_execution=execution,
                metadata_schedule_dry_run=schedule_dry_run,
            )
            or fake_metadata
        ),
    )
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="1234567890abcdef1234567890abcdef"),
    )

    def fake_run_qualified_play(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
        trajectory_sink: FakeSink,
        trajectory_episode_id: str,
        battle_start_offsets: object,
    ) -> FakePlayReport:
        observed.update(
            rom=path,
            watch=watch,
            speed=speed,
            progress=progress,
            trajectory_sink=trajectory_sink,
            trajectory_episode_id=trajectory_episode_id,
            battle_start_offsets=battle_start_offsets,
        )
        return FakePlayReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_run_qualified_play)

    assert (
        cli.main(
            [
                "record",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "2",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "episode": {
            "episode_id": expected_episode_id,
            "manifest_sha256": "a" * 64,
            "schema": "private-episode-summary-v1",
            "status": "complete",
            "stream_records": {"episode": 1, "executions": 42},
            "total_bytes": 4096,
            "total_records": 43,
        },
        "game_complete": True,
        "schema": "private-trajectory-recording-v1",
        "status": "ok",
    }
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err
    assert str(private_root_path) not in captured.out
    assert str(private_root_path) not in captured.err
    assert observed["private_root"] == private_root_path
    assert observed["repository_root"] == cli.REPOSITORY_ROOT
    assert observed["begin_episode"] == expected_episode_id
    assert observed["sink_episode_id"] == expected_episode_id
    assert observed["sink_game_id"] == cli.POKEMON_RED_GAME_ID
    assert observed["rom"] == private_path
    assert observed["watch"] is True
    assert observed["speed"] == 2
    assert observed["progress"] is cli._print_qualified_progress
    assert observed["trajectory_episode_id"] == expected_episode_id
    assert observed["battle_start_offsets"] is None
    assert observed["metadata_rom"] == private_path
    assert observed["metadata_episode_id"] == expected_episode_id
    assert observed["metadata_watch"] is True
    assert observed["metadata_speed"] == 2
    assert observed["metadata_assignment"] is None
    assert observed["metadata_execution"] is None
    assert observed["metadata_schedule_dry_run"] is None
    assert observed["header"] == fake_metadata


def test_planned_record_requires_dry_run_before_sealing_or_emulator_start(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    assignment = registry.assignment("red-battle-v74-01-train")
    private_path = Path("/private/Pokemon Red.gb")
    private_root_path = Path("/private/external/trajectories")
    observed: dict[str, object] = {}

    class FakeSession:
        def __enter__(self):
            observed["session_entered"] = True
            return self

        def __exit__(self, *args: object) -> bool:
            observed["session_exited"] = True
            return False

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            observed["collection_id"] = collection_id
            return FakeSession()

        def begin_episode(self, _episode_id: str) -> None:
            pytest.fail("missing dry-run qualification must not claim an episode")

    class FakeLedger:
        @classmethod
        def open_or_seal(cls, **kwargs):
            pytest.fail("missing dry-run qualification must not seal the campaign")

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda *args, **kwargs: {"planned": True},
    )
    campaign_identity = object()
    monkeypatch.setattr(
        cli,
        "_campaign_identity",
        lambda selected_registry, metadata: campaign_identity,
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda root, *, repository_root: FakeRoot(),
    )

    def reject_qualification(store, identity, dry_run) -> None:
        observed.update(
            qualification_store=store,
            qualification_identity=identity,
            qualification_dry_run=dry_run,
        )
        raise cli.CollectionLedgerError("schedule dry run is not qualified")

    monkeypatch.setattr(cli, "require_dry_run_qualification", reject_qualification)
    monkeypatch.setattr(cli, "CollectionOutcomeLedger", FakeLedger)
    monkeypatch.setattr(
        cli,
        "run_qualified_play",
        lambda *args, **kwargs: pytest.fail(
            "missing dry-run qualification must not start the emulator"
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "record",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(private_path),
                "--collection-run",
                assignment.run_id,
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "schedule dry run is not qualified" in captured.err
    assert observed["collection_id"] == registry.collection_id
    assert observed["session_entered"] is True
    assert observed["session_exited"] is True
    assert observed["qualification_identity"] is campaign_identity
    assert observed["qualification_dry_run"] == registry.schedule_dry_run
    assert str(private_root_path) not in captured.err
    assert str(private_path) not in captured.err


def test_planned_record_uses_the_frozen_identity_and_exact_offsets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    assignment = registry.assignment("red-battle-v74-01-train")
    private_path = Path("/private/Pokemon Red.gb")
    private_root_path = Path("/private/external/trajectories")
    observed: dict[str, object] = {}

    class FakeReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None

        def public_dict(self) -> dict[str, object]:
            return {"game_complete": True}

    class FakeSummary:
        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "private-episode-summary-v1",
                "episode_id": assignment.episode_id,
                "status": "complete",
                "stream_records": {"episode": 1},
                "total_records": 1,
                "total_bytes": 1,
                "manifest_sha256": "a" * 64,
            }

    class FakeWriter:
        summary = FakeSummary()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeSink:
        def __init__(self, writer, *, episode_id: str, game_id: str) -> None:
            observed.update(
                sink_writer=writer,
                sink_episode_id=episode_id,
                sink_game_id=game_id,
            )

        def write_episode_header(self, *, metadata: object) -> None:
            observed["header"] = metadata

    fake_writer = FakeWriter()

    class FakeSession:
        def __enter__(self):
            observed["session_entered"] = True
            return self

        def __exit__(self, *args: object) -> bool:
            observed["session_exited"] = True
            return False

    class FakeRoot:
        def begin_episode(self, episode_id: str) -> FakeWriter:
            observed["begin_episode"] = episode_id
            return fake_writer

        def collection_session(self, collection_id: str) -> FakeSession:
            observed["session_collection_id"] = collection_id
            return FakeSession()

        def open_episode(self, episode_id: str) -> object:
            observed["open_episode"] = episode_id
            return object()

    class FakeOutcome:
        status = "complete"
        game_complete = True

    class FakeLedger:
        @classmethod
        def open_or_seal(cls, **kwargs):
            observed["ledger_open"] = kwargs
            return cls()

        def reconcile(self):
            observed["ledger_reconciled"] = True
            return ()

        def require_pending(self, slot):
            observed["pending_slot"] = slot

        def reconcile_slot(self, slot):
            observed["reconciled_slot"] = slot
            return FakeOutcome()

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda root: observed.update(registry_root=root) or registry,
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda root, *, repository_root: (
            observed.update(private_root=root, repository_root=repository_root) or FakeRoot()
        ),
    )
    monkeypatch.setattr(cli, "EpisodeTrajectorySink", FakeSink)
    monkeypatch.setattr(
        cli,
        "audit_schedule_attestations",
        lambda reader, **kwargs: observed.update(
            schedule_reader=reader,
            schedule_audit=kwargs,
        ),
    )
    monkeypatch.setattr(cli, "CollectionOutcomeLedger", FakeLedger)
    campaign_identity = object()
    monkeypatch.setattr(
        cli,
        "_campaign_identity",
        lambda selected_registry, metadata: (
            observed.update(campaign_registry=selected_registry, campaign_metadata=metadata)
            or campaign_identity
        ),
    )
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda path, *, episode_id, watch, speed, assignment, execution, schedule_dry_run: (
            observed.update(
                metadata_path=path,
                metadata_episode_id=episode_id,
                metadata_assignment=assignment,
                metadata_execution=execution,
                metadata_schedule_dry_run=schedule_dry_run,
            )
            or {"planned": True}
        ),
    )
    monkeypatch.setattr(
        cli,
        "require_dry_run_qualification",
        lambda store, identity, dry_run: observed.update(
            qualification_store=store,
            qualification_identity=identity,
            qualification_dry_run=dry_run,
        ),
    )
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: pytest.fail("planned collection must not allocate a random episode"),
    )

    def fake_run(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
        trajectory_sink: FakeSink,
        trajectory_episode_id: str,
        battle_start_offsets,
    ) -> FakeReport:
        observed.update(
            run_path=path,
            run_watch=watch,
            run_speed=speed,
            run_progress=progress,
            run_sink=trajectory_sink,
            run_episode_id=trajectory_episode_id,
            run_offsets=battle_start_offsets,
        )
        return FakeReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_run)

    assert (
        cli.main(
            [
                "record",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(private_path),
                "--collection-run",
                assignment.run_id,
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out)["episode"]["episode_id"] == assignment.episode_id
    assert assignment.run_id not in captured.out
    assert observed["registry_root"] == cli.REPOSITORY_ROOT
    assert observed["begin_episode"] == assignment.episode_id
    assert observed["open_episode"] == assignment.episode_id
    assert observed["schedule_audit"]["offsets"] == assignment.offsets
    assert observed["schedule_audit"]["schedule_sha256"] == assignment.schedule_sha256
    assert observed["session_collection_id"] == registry.collection_id
    assert observed["session_entered"] is True
    assert observed["session_exited"] is True
    assert observed["ledger_reconciled"] is True
    assert observed["pending_slot"].assignment_id == assignment.assignment_id
    assert observed["reconciled_slot"].assignment_id == assignment.assignment_id
    assert observed["ledger_open"]["identity"] is campaign_identity
    assert observed["qualification_identity"] is campaign_identity
    assert observed["qualification_dry_run"] == registry.schedule_dry_run
    assert observed["metadata_episode_id"] == assignment.episode_id
    assert observed["metadata_assignment"] == assignment
    assert observed["metadata_execution"] == registry.execution
    assert observed["metadata_schedule_dry_run"] is None
    assert observed["run_episode_id"] == assignment.episode_id
    assert observed["run_offsets"] == assignment.offsets
    assert observed["header"] == {"planned": True}


def test_schedule_dry_run_uses_disjoint_offsets_without_touching_the_campaign_ledger(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _collection_registry()
    dry_run = registry.schedule_dry_run
    private_path = Path("/private/Pokemon Red.gb")
    private_root_path = Path("/private/external/trajectories")
    observed: dict[str, object] = {}

    class FakeReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None

        def public_dict(self) -> dict[str, object]:
            return {"game_complete": True}

    class FakeSession:
        def __enter__(self):
            observed["session_entered"] = True
            return self

        def __exit__(self, *args: object) -> bool:
            observed["session_exited"] = True
            return False

    class FakeRoot:
        def collection_session(self, collection_id: str) -> FakeSession:
            observed["session_collection_id"] = collection_id
            return FakeSession()

    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda root, *, repository_root: (
            observed.update(private_root=root, repository_root=repository_root) or FakeRoot()
        ),
    )
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="1234567890abcdef1234567890abcdef"),
    )
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda path, *, episode_id, watch, speed, assignment, execution, schedule_dry_run: (
            observed.update(
                metadata_path=path,
                metadata_episode_id=episode_id,
                metadata_assignment=assignment,
                metadata_execution=execution,
                metadata_dry_run=schedule_dry_run,
            )
            or {"dry_run": True}
        ),
    )

    def capture(_root, **kwargs):
        observed["capture"] = kwargs
        return (
            FakeReport(),
            {
                "schema": "private-episode-summary-v1",
                "episode_id": kwargs["episode_id"],
                "status": "complete",
                "stream_records": {"episode": 1},
                "total_records": 1,
                "total_bytes": 1,
                "manifest_sha256": "a" * 64,
            },
        )

    monkeypatch.setattr(cli, "_capture_private_recording", capture)
    campaign_identity = object()
    monkeypatch.setattr(
        cli,
        "_campaign_identity",
        lambda selected_registry, metadata: (
            observed.update(
                campaign_registry=selected_registry,
                campaign_metadata=metadata,
            )
            or campaign_identity
        ),
    )

    class FakeQualification:
        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "pokemon-red-schedule-dry-run-qualification-v1",
                "status": "qualified",
            }

    monkeypatch.setattr(
        cli,
        "publish_dry_run_qualification",
        lambda store, identity, selected_dry_run, selected_episode_id: (
            observed.update(
                qualification_store=store,
                qualification_identity=identity,
                qualification_dry_run=selected_dry_run,
                qualification_episode_id=selected_episode_id,
            )
            or FakeQualification()
        ),
    )

    assert (
        cli.main(
            [
                "record",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(private_path),
                "--schedule-dry-run",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    expected_episode_id = "red-dry-run-1234567890abcdef1234567890abcdef"
    assert payload["episode"]["episode_id"] == expected_episode_id
    assert observed["metadata_episode_id"] == expected_episode_id
    assert observed["metadata_assignment"] is None
    assert observed["metadata_execution"] == registry.execution
    assert observed["metadata_dry_run"] == dry_run
    assert observed["capture"]["battle_start_offsets"] == dry_run.offsets
    assert observed["session_collection_id"] == registry.collection_id
    assert observed["session_entered"] is True
    assert observed["session_exited"] is True
    assert observed["qualification_identity"] is campaign_identity
    assert observed["qualification_dry_run"] == dry_run
    assert observed["qualification_episode_id"] == expected_episode_id
    assert payload["dry_run_qualification"]["status"] == "qualified"


def test_record_rejects_an_unknown_collection_run_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = Path("/private/Pokemon Red.gb")
    sensitive_run = "../../private-run"
    registry = _collection_registry()
    monkeypatch.setattr(cli, "resolve_rom_path", lambda _argument: private_path)
    monkeypatch.setattr(
        cli,
        "load_committed_collection_registry",
        lambda _root: registry,
    )
    monkeypatch.setattr(
        cli,
        "open_private_root",
        lambda *args, **kwargs: pytest.fail("unknown run must fail before private storage"),
    )
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: pytest.fail("unknown run must not allocate a random episode"),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "record",
                "--private-root",
                "/private/external/trajectories",
                "--rom",
                str(private_path),
                "--collection-run",
                sensitive_run,
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert sensitive_run not in captured.err
    assert str(private_path) not in captured.err
    assert "safe lowercase identifier" in captured.err


def test_record_command_rejects_speed_without_watch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "record",
                "--private-root",
                "/private/external/trajectories",
                "--speed",
                "2",
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "--speed requires --watch" in captured.err


def test_recording_metadata_requires_an_identified_clean_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: SourceIdentity("a" * 40, True),
    )

    with pytest.raises(EvaluationIdentityError, match="clean worktree"):
        cli._recording_metadata(
            Path("/private/Pokemon Red.gb"),
            episode_id="red-teacher-example",
            watch=False,
            speed=None,
        )


def test_recording_metadata_is_reproducible_and_omits_private_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_rom = Path("/private/Pokemon Red.gb")
    source = SourceIdentity("a" * 40, False)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: source,
    )
    monkeypatch.setattr(
        cli,
        "verify_rom",
        lambda path: RomFingerprint(
            filename=path.name,
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="b" * 40,
            sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(cli, "build_runtime_identity", _runtime_identity)

    metadata = cli._recording_metadata(
        private_rom,
        episode_id="red-teacher-example",
        watch=False,
        speed=None,
    )

    serialized = json.dumps(metadata, sort_keys=True)
    assert str(private_rom) not in serialized
    assert private_rom.name not in serialized
    assert metadata["source"] == source.public_dict()
    assert metadata["rom_identity"]["sha256"] == "c" * 64
    assert metadata["runtime"]["pyboy"]["distribution_version"] == "2.7.0"
    assert metadata["runtime_sha256"] == "1" * 64
    assert metadata["configuration_sha256"] == canonical_sha256(metadata["configuration"])
    assert metadata["split"]["root_lineage_id"] == "red-teacher-example"


def test_planned_recording_metadata_binds_assignment_and_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_rom = Path("/private/Pokemon Red.gb")
    registry = _collection_registry()
    assignment = registry.assignment("red-battle-v74-01-train")
    source = SourceIdentity("a" * 40, False)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: source,
    )
    monkeypatch.setattr(
        cli,
        "verify_rom",
        lambda path: RomFingerprint(
            filename=path.name,
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="b" * 40,
            sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(cli, "build_runtime_identity", _runtime_identity)
    monkeypatch.setattr(
        cli,
        "committed_source_bundle_sha256",
        lambda _root, *, revision: registry.execution.source_bundle_sha256,
    )
    monkeypatch.setattr(
        cli,
        "working_source_bundle_sha256",
        lambda _root: registry.execution.source_bundle_sha256,
    )
    monkeypatch.setattr(cli, "require_published_source", lambda _root, _source: None)

    metadata = cli._recording_metadata(
        private_rom,
        episode_id=assignment.episode_id,
        watch=False,
        speed=None,
        assignment=assignment,
        execution=replace(
            registry.execution,
            source_commit=source.git_commit,
        ),
    )

    configuration = metadata["configuration"]
    assert isinstance(configuration, dict)
    schedule = configuration["battle_start_schedule"]
    assert isinstance(schedule, dict)
    assert schedule["offsets"] == [offset.public_dict() for offset in assignment.offsets]
    assert schedule["assignment_id"] == assignment.assignment_id
    assert schedule["registry_sha256"] == assignment.registry_sha256
    assert schedule["schedule_sha256"] == assignment.schedule_sha256
    assert metadata["configuration_sha256"] == canonical_sha256(configuration)
    assert metadata["split"] == assignment.metadata_dict()["split"]
    collection = metadata["collection"]
    assert isinstance(collection, dict)
    assert collection["run_id"] == assignment.run_id
    assert collection["harness_seed"] == assignment.harness_seed
    assert collection["attempt"]["counted"] is True
    assert collection["perturbation_schedule"] == "preregistered_battle_start_offsets"
    assert str(private_rom) not in json.dumps(metadata, sort_keys=True)

    watched = cli._recording_metadata(
        private_rom,
        episode_id=assignment.episode_id,
        watch=True,
        speed=4,
        assignment=assignment,
        execution=replace(
            registry.execution,
            source_commit=source.git_commit,
        ),
    )
    assert (
        watched["configuration"]["behavior_configuration"]
        == metadata["configuration"]["behavior_configuration"]
    )
    assert (
        watched["configuration"]["assignment_configuration_sha256"]
        == configuration["assignment_configuration_sha256"]
    )
    assert watched["configuration"]["presentation"] == {"watch": True, "speed": 4}
    assert watched["configuration_sha256"] != metadata["configuration_sha256"]

    with pytest.raises(ValueError, match="planned episode identity"):
        cli._recording_metadata(
            private_rom,
            episode_id="red-teacher-wrong",
            watch=False,
            speed=None,
            assignment=assignment,
            execution=registry.execution,
        )


def test_scheduled_metadata_rejects_a_commit_change_after_registry_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _collection_registry()
    assignment = registry.assignment("red-battle-v74-01-train")
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: SourceIdentity("a" * 40, False),
    )

    with pytest.raises(EvaluationIdentityError, match="commit changed"):
        cli._recording_metadata(
            Path("/private/Pokemon Red.gb"),
            episode_id=assignment.episode_id,
            watch=False,
            speed=None,
            assignment=assignment,
            execution=replace(
                registry.execution,
                source_commit="b" * 40,
            ),
        )


def test_dry_run_metadata_is_unassigned_non_counted_and_registry_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_rom = Path("/private/Pokemon Red.gb")
    registry = _collection_registry()
    dry_run = registry.schedule_dry_run
    source = SourceIdentity("a" * 40, False)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: source,
    )
    monkeypatch.setattr(cli, "require_published_source", lambda _root, _source: None)
    monkeypatch.setattr(
        cli,
        "verify_rom",
        lambda path: RomFingerprint(
            filename=path.name,
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="b" * 40,
            sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(cli, "build_runtime_identity", _runtime_identity)
    monkeypatch.setattr(
        cli,
        "committed_source_bundle_sha256",
        lambda _root, *, revision: registry.execution.source_bundle_sha256,
    )
    monkeypatch.setattr(
        cli,
        "working_source_bundle_sha256",
        lambda _root: registry.execution.source_bundle_sha256,
    )

    metadata = cli._recording_metadata(
        private_rom,
        episode_id="red-dry-run-example",
        watch=True,
        speed=2,
        execution=replace(
            registry.execution,
            source_commit=source.git_commit,
        ),
        schedule_dry_run=dry_run,
    )

    collection = metadata["collection"]
    assert isinstance(collection, dict)
    assert collection["attempt"] == {"counted": False}
    assert collection["registry_sha256"] == registry.registry_sha256
    assert (
        collection["execution"]["teacher_execution_sha256"]
        == registry.execution.teacher_execution_sha256
    )
    assert metadata["split"]["partition"] == "unassigned"
    assert metadata["split"]["root_lineage_id"] == "red-dry-run-example"
    schedule = metadata["configuration"]["battle_start_schedule"]
    assert schedule["registry_sha256"] == registry.registry_sha256
    assert schedule["teacher_execution_sha256"] == registry.execution.teacher_execution_sha256
    assert schedule["offsets"] == [offset.public_dict() for offset in dry_run.offsets]
