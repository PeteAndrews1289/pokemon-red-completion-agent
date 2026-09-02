from __future__ import annotations

import argparse
import hashlib
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/qualify_battle_outcome_clustered_curriculum.py")
RUN_GLOBALS = SCRIPT["_run"].__globals__
QUALIFY_GLOBALS = SCRIPT["_qualify_under_shared_lease"].__globals__
MAIN_GLOBALS = SCRIPT["main"].__globals__


def _root(index: int, marker: str) -> str:
    return f"{index:02x}{marker * 62}"


def _prepared(index: int) -> tuple[SimpleNamespace, object]:
    return (
        SimpleNamespace(
            logical_root_sha256=_root(index, "a"),
            physical_root_sha256=_root(index, "b"),
        ),
        object(),
    )


def test_retained_train_catalog_specs_bind_one_authenticated_producer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    directory = tmp_path / "train"
    directory.mkdir()
    rom_directory = tmp_path / "roms"
    rom_directory.mkdir()
    rom_path = rom_directory / "red.gb"
    rom_path.write_bytes(b"rom")
    captures = tuple(
        SimpleNamespace(
            producer_id="predecessor",
            state_filename=f"capture-{index}.state",
            manifest_filename=f"capture-{index}.state.json",
            capture_id=f"capture-{index}",
            source_state_sha256=f"{index + 1:064x}",
            root_lineage_id=f"root-{index}",
            state_sha256=f"{index + 10:064x}",
            manifest_sha256=f"{index + 20:064x}",
        )
        for index in range(5)
    )
    catalog = SimpleNamespace(
        producer=SimpleNamespace(
            source_commit="c" * 40,
            capture_directory_sha256=hashlib.sha256(
                str(directory.resolve()).encode("utf-8")
            ).hexdigest(),
        ),
        captures=captures,
    )
    freezer = RUN_GLOBALS["batch_freezer"]
    monkeypatch.setattr(
        freezer,
        "_private_capture_directory",
        lambda path, **_kwargs: path.resolve(),
    )

    specs = SCRIPT["_retained_train_catalog_specs"](
        catalog,
        directory,
        catalog_sha256="d" * 64,
        rom_path=rom_path,
    )

    assert len(specs) == 5
    assert {item.partition for item in specs} == {ScenarioPartition.TRAIN}
    assert {item.producer_source_commit for item in specs} == {"c" * 40}
    assert {item.producer_catalog_sha256 for item in specs} == {"d" * 64}
    assert tuple(item.state_path for item in specs) == tuple(
        directory.resolve() / item.state_filename for item in captures
    )

    catalog.producer.capture_directory_sha256 = "0" * 64
    with pytest.raises(
        SCRIPT["BattleOutcomeClusteredQualificationError"],
        match="producer directory differs",
    ):
        SCRIPT["_retained_train_catalog_specs"](
            catalog,
            directory,
            catalog_sha256="d" * 64,
            rom_path=rom_path,
        )


def test_qualification_observes_every_root_once_and_writes_only_after_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prefix = _prepared(1)
    train = tuple(_prepared(index) for index in range(2, 7))
    development = tuple(_prepared(index) for index in range(7, 15))
    forbidden = SimpleNamespace(
        logical_root_sha256=_root(15, "a"),
        physical_root_sha256=_root(15, "b"),
    )
    retained = SimpleNamespace(
        original_prior_sha256="1" * 64,
        forbidden_development=forbidden,
    )
    observed: list[tuple[tuple[str, str], ...]] = []

    class Lease:
        def observe(self, root_pairs):  # type: ignore[no-untyped-def]
            observed.append(tuple(root_pairs))
            return SimpleNamespace(
                registry_state_sha256="2" * 64,
                availability_for=lambda logical, _physical: logical
                != prefix[0].logical_root_sha256,
            )

    monkeypatch.setitem(
        QUALIFY_GLOBALS,
        "claim_first_availability_snapshot_lease",
        lambda _path: nullcontext(Lease()),
    )
    built_candidates: list[SimpleNamespace] = []

    def pressure(binding, _features, _model, **kwargs):  # type: ignore[no-untyped-def]
        candidate = SimpleNamespace(
            binding=binding,
            claim_available=kwargs["claim_available"],
        )
        built_candidates.append(candidate)
        return candidate

    monkeypatch.setitem(
        QUALIFY_GLOBALS,
        "build_battle_outcome_pressure_candidate",
        pressure,
    )
    captured: dict[str, object] = {}
    curriculum = SimpleNamespace(canonical_bytes=lambda: b"curriculum\n")

    def build(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return curriculum

    monkeypatch.setitem(
        QUALIFY_GLOBALS,
        "build_battle_outcome_clustered_curriculum",
        build,
    )
    monkeypatch.setitem(
        QUALIFY_GLOBALS,
        "parse_battle_outcome_clustered_curriculum",
        lambda payload: curriculum if payload == b"curriculum\n" else None,
    )
    written: list[tuple[Path, bytes]] = []
    monkeypatch.setattr(
        QUALIFY_GLOBALS["batch_freezer"],
        "_write_exclusive",
        lambda path, payload: written.append((path, payload)),
    )

    result = SCRIPT["_qualify_under_shared_lease"](
        curriculum_id="clustered-v1",
        retained_prefix=retained,
        base_model=object(),
        prefix=prefix,
        fresh_train=train,
        development=development,
        registry_path=tmp_path / "claims",
        train_catalog_sha256="3" * 64,
        development_catalog_sha256="4" * 64,
        destination=tmp_path / "curriculum.json",
    )

    assert result is curriculum
    assert len(observed) == 1
    assert len(observed[0]) == 15
    assert len(set(observed[0])) == 15
    assert observed[0][0] == (
        forbidden.logical_root_sha256,
        forbidden.physical_root_sha256,
    )
    assert [item.claim_available for item in built_candidates] == [
        False,
        *([True] * 13),
    ]
    assert len(captured["fresh_train"]) == 5  # type: ignore[arg-type]
    assert len(captured["development"]) == 8  # type: ignore[arg-type]
    assert captured["claim_registry_sha256"] == "2" * 64
    assert written == [(tmp_path / "curriculum.json", b"curriculum\n")]


def test_cli_failure_is_path_free_and_effect_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        MAIN_GLOBALS,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: argparse.Namespace()),
    )
    monkeypatch.setitem(
        MAIN_GLOBALS,
        "_run",
        lambda _args: (_ for _ in ()).throw(RuntimeError("/private/capture.state")),
    )

    assert SCRIPT["main"]([]) == 1
    output = capsys.readouterr().out
    assert "/private/capture.state" not in output
    assert '"status": "failed_closed"' in output
    assert '"controller_actions": 0' in output
    assert '"root_claims_created": 0' in output
    assert '"model_fits": 0' in output
