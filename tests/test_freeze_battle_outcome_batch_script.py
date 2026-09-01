from __future__ import annotations

import hashlib
import json
import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/freeze_battle_outcome_batch.py")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
        + b"\n"
    )


def _binding(marker: str) -> SimpleNamespace:
    return SimpleNamespace(
        logical_root_sha256=(marker * 64)[:64],
        physical_root_sha256=((marker + "f") * 64)[:64],
    )


def test_capture_specs_are_bounded_unique_path_pairs() -> None:
    first = [Path("train-a.state"), Path("train-a.json")]
    second = [Path("train-b.state"), Path("train-b.json")]

    assert SCRIPT["_capture_specs"]([first, second], "train") == (
        tuple(first),
        tuple(second),
    )
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="repeats an input",
    ):
        SCRIPT["_capture_specs"]([first, first], "train")


def test_train_catalog_specs_preserve_each_producer_commit_and_directory(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    producers = (
        SimpleNamespace(producer_id="predecessor", source_commit="a" * 40),
        SimpleNamespace(producer_id="completion", source_commit="b" * 40),
    )
    captures = (
        SimpleNamespace(
            producer_id="predecessor",
            state_filename="first.state",
            manifest_filename="first.state.json",
            capture_id="first-capture",
            source_state_sha256="1" * 64,
            root_lineage_id="first-root",
            state_sha256="2" * 64,
            manifest_sha256="3" * 64,
        ),
        SimpleNamespace(
            producer_id="completion",
            state_filename="second.state",
            manifest_filename="second.state.json",
            capture_id="second-capture",
            source_state_sha256="4" * 64,
            root_lineage_id="second-root",
            state_sha256="5" * 64,
            manifest_sha256="6" * 64,
        ),
    )
    catalog = SimpleNamespace(producers=producers, captures=captures)
    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")

    specs = SCRIPT["_train_catalog_specs"](
        catalog,
        [["predecessor", str(first)], ["completion", str(second)]],
        catalog_sha256="9" * 64,
        rom_path=rom,
    )

    assert tuple(item.producer_source_commit for item in specs) == (
        "a" * 40,
        "b" * 40,
    )
    assert tuple(item.state_path.parent for item in specs) == (
        first.resolve(),
        second.resolve(),
    )
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="directories differ",
    ):
        SCRIPT["_train_catalog_specs"](
            catalog,
            [["predecessor", str(first)], ["completion", str(first)]],
            catalog_sha256="9" * 64,
            rom_path=rom,
        )


def test_historical_development_catalog_is_a_strict_producer_membership() -> None:
    source_commit = "a" * 40
    document = {
        "schema": "pokemon-red-private-battle-learning-curve-catalog-v2",
        "runner_source_commit": source_commit,
        "slots": [
            {
                "capture_id": "train-one",
                "partition": "train",
                "root_lineage_id": "train-root",
                "source_state_sha256": "1" * 64,
            },
            {
                "capture_id": "development-one",
                "partition": "development",
                "root_lineage_id": "development-root",
                "source_state_sha256": "2" * 64,
            },
        ],
    }

    assert SCRIPT["_historical_development_catalog_members"](
        _canonical(document),
        source_commit=source_commit,
    ) == {"development-one": ("2" * 64, "development-root")}
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="producer catalog differs",
    ):
        SCRIPT["_historical_development_catalog_members"](
            _canonical(document),
            source_commit="b" * 40,
        )


def test_development_catalog_loader_rejects_digest_or_duplicate_producer(
    tmp_path: Path,
) -> None:
    source_commit = "a" * 40
    payload = _canonical(
        {
            "schema": "pokemon-red-private-battle-learning-curve-catalog-v1",
            "runner_source_commit": source_commit,
            "slots": [
                {
                    "capture_id": "development-one",
                    "partition": "development",
                    "root_lineage_id": "development-root",
                    "source_state_sha256": "2" * 64,
                }
            ],
        }
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    assert SCRIPT["_development_catalogs"](
        [[source_commit, str(catalog), digest]]
    ) == {
        source_commit: (
            digest,
            {"development-one": ("2" * 64, "development-root")},
        )
    }
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="digest differs",
    ):
        SCRIPT["_development_catalogs"](
            [[source_commit, str(catalog), "0" * 64]]
        )
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="catalog repeats",
    ):
        SCRIPT["_development_catalogs"](
            [
                [source_commit, str(catalog), digest],
                [source_commit, str(catalog), digest],
            ]
        )


def test_development_metadata_preflight_happens_without_opening_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_commit = "a" * 40
    source_state_sha256 = "2" * 64
    root_lineage_id = "red-goal-root-" + "3" * 64
    capture_id = "development-one"
    state = tmp_path / "state-does-not-exist.state"
    manifest = tmp_path / "development.state.json"
    manifest.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id=capture_id,
            root_lineage_id=root_lineage_id,
            partition=ScenarioPartition.DEVELOPMENT,
            state_bytes=b"unopened state bytes",
            initial_observation_sha256="4" * 64,
            source_commit=source_commit,
            expected_map=1,
            expected_battle_state=1,
            source_state_sha256=source_state_sha256,
        )
    )
    producer_catalog_sha256 = "5" * 64
    catalogs = {
        source_commit: (
            producer_catalog_sha256,
            {capture_id: (source_state_sha256, root_lineage_id)},
        )
    }
    monkeypatch.setitem(
        SCRIPT["_development_capture_specs"].__globals__,
        "authenticate_battle_scenario_source_binding",
        lambda *args, **kwargs: SimpleNamespace(root_lineage_id=root_lineage_id),
    )

    specs = SCRIPT["_development_capture_specs"](
        [[source_commit, str(state), str(manifest)]],
        catalogs=catalogs,
        catalog=object(),
        registry=object(),
    )

    assert len(specs) == 1
    assert specs[0].state_path == state
    assert not state.exists()
    assert specs[0].producer_catalog_sha256 == producer_catalog_sha256

    def incompatible(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise SCRIPT["BattleOutcomeCaptureAuthenticationError"]("incompatible")

    monkeypatch.setitem(
        SCRIPT["_development_capture_specs"].__globals__,
        "authenticate_battle_scenario_source_binding",
        incompatible,
    )
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="incompatible with the current source catalog",
    ):
        SCRIPT["_development_capture_specs"](
            [[source_commit, str(state), str(manifest)]],
            catalogs=catalogs,
            catalog=object(),
            registry=object(),
        )
    assert not state.exists()


def test_private_freeze_refuses_project_and_rom_sibling_destinations(
    tmp_path: Path,
) -> None:
    project_destination = Path("docs") / "forbidden-battle-freeze.json"
    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")

    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="must remain private",
    ):
        SCRIPT["_private_new_freeze"](project_destination, rom_path=rom)
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="beside the ROM",
    ):
        SCRIPT["_private_new_freeze"](rom_dir / "freeze.json", rom_path=rom)

    private_dir = tmp_path / "private"
    private_dir.mkdir()
    destination = private_dir / "freeze.json"
    assert SCRIPT["_private_new_freeze"](destination, rom_path=rom) == (
        destination.resolve()
    )


def test_freeze_writer_is_exclusive_private_and_durable(tmp_path: Path) -> None:
    destination = tmp_path / "freeze.json"
    payload = b'{"schema":"test"}\n'

    SCRIPT["_write_exclusive"](destination, payload)

    assert destination.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="could not be retained",
    ):
        SCRIPT["_write_exclusive"](destination, payload)


def test_private_reader_rejects_links_and_group_writable_inputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private.json"
    source.write_bytes(b'{"schema":"test"}\n')
    assert SCRIPT["_read_bounded_private_file"](
        source,
        maximum_bytes=1024,
        subject="test input",
    ) == source.read_bytes()

    symlink = tmp_path / "linked.json"
    symlink.symlink_to(source)
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="unavailable",
    ):
        SCRIPT["_read_bounded_private_file"](
            symlink,
            maximum_bytes=1024,
            subject="test input",
        )

    hardlink = tmp_path / "hardlinked.json"
    hardlink.hardlink_to(source)
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="unavailable",
    ):
        SCRIPT["_read_bounded_private_file"](
            source,
            maximum_bytes=1024,
            subject="test input",
        )
    hardlink.unlink()

    source.chmod(0o660)
    with pytest.raises(
        SCRIPT["BattleOutcomeBatchFreezeError"],
        match="unavailable",
    ):
        SCRIPT["_read_bounded_private_file"](
            source,
            maximum_bytes=1024,
            subject="test input",
        )


def test_atomic_builder_holds_one_shared_claim_lease_through_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix_binding = _binding("a")
    forbidden_binding = _binding("b")
    train_binding = _binding("c")
    development_binding = _binding("d")
    retained = SimpleNamespace(
        train=prefix_binding,
        forbidden_development=forbidden_binding,
        original_prior_sha256="1" * 64,
    )
    active = False
    observed_pairs: tuple[tuple[str, str], ...] = ()
    written: tuple[Path, bytes] | None = None
    snapshot = SimpleNamespace(
        availability_for=lambda logical, physical: logical
        not in {
            prefix_binding.logical_root_sha256,
            forbidden_binding.logical_root_sha256,
        }
    )

    class Lease:
        def __enter__(self) -> Lease:
            nonlocal active
            assert not active
            active = True
            return self

        def observe(
            self,
            pairs: tuple[tuple[str, str], ...],
        ) -> SimpleNamespace:
            nonlocal observed_pairs
            assert active
            observed_pairs = pairs
            return snapshot

        def __exit__(self, *args: object) -> None:
            nonlocal active
            assert active
            active = False

    freeze = SimpleNamespace(canonical_bytes=lambda: b"canonical-freeze\n")
    inventory = object()

    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "claim_first_availability_snapshot_lease",
        lambda path: Lease(),
    )
    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "build_battle_outcome_pressure_candidate",
        lambda binding, features, model, **kwargs: SimpleNamespace(
            binding=binding,
            available=kwargs["claim_available"],
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "build_battle_outcome_pressure_inventory",
        lambda **kwargs: inventory,
    )
    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "build_battle_outcome_batch_freeze",
        lambda **kwargs: freeze,
    )
    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "parse_battle_outcome_batch_freeze",
        lambda payload: freeze,
    )

    def write_while_locked(destination: Path, payload: bytes) -> None:
        nonlocal written
        assert active
        written = destination, payload

    monkeypatch.setitem(
        SCRIPT["_freeze_under_shared_lease"].__globals__,
        "_write_exclusive",
        write_while_locked,
    )
    destination = tmp_path / "freeze.json"

    result = SCRIPT["_freeze_under_shared_lease"](
        roster_id="red-battle-v2-test",
        retained_prefix=retained,
        base_model=object(),
        prefix=(prefix_binding, object()),
        screened=(
            (train_binding, object()),
            (development_binding, object()),
        ),
        registry_path=tmp_path,
        destination=destination,
        consumer_source_commit="e" * 40,
        consumer_source_bundle_sha256="f" * 64,
        capture_catalog_sha256s=("9" * 64,),
    )

    assert result is freeze
    assert active is False
    assert written == (destination, b"canonical-freeze\n")
    assert observed_pairs == (
        (
            prefix_binding.logical_root_sha256,
            prefix_binding.physical_root_sha256,
        ),
        (
            forbidden_binding.logical_root_sha256,
            forbidden_binding.physical_root_sha256,
        ),
        (
            train_binding.logical_root_sha256,
            train_binding.physical_root_sha256,
        ),
        (
            development_binding.logical_root_sha256,
            development_binding.physical_root_sha256,
        ),
    )
