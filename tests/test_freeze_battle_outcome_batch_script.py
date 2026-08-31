from __future__ import annotations

import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = runpy.run_path("scripts/freeze_battle_outcome_batch.py")


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
