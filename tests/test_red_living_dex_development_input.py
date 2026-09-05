from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_red_living_dex_development_batch import _assignments
from test_red_living_dex_setup_recipe import _store

from pokemon_red_completion import red_living_dex_development_input as inputs
from pokemon_red_completion.red_living_dex_development_input import (
    RedLivingDexDevelopmentInputError,
    load_red_living_dex_development_batch_assignments,
    source_private_storage_is_separate,
)


def test_exact_input_loader_reads_owner_only_state_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, historical_binding, supplement_binding = _assignments()
    cases = {
        "historical-10": (historical_binding, 10),
        "historical-11": (historical_binding, 11),
        "supplement-0": (supplement_binding, 0),
        "supplement-1": (supplement_binding, 1),
        "supplement-2": (supplement_binding, 2),
    }
    monkeypatch.setattr(inputs, "_CASES", cases)

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        selection, _root = expected[(binding.private_plan_sha256, ordinal)]
        return selection, {}

    monkeypatch.setattr(inputs, "load_red_living_dex_development_selection", load)
    roots: dict[str, Path] = {}
    by_key = {
        (assignment.binding.private_plan_sha256, assignment.ordinal): assignment
        for assignment in assignments
    }
    capture_root = tmp_path / "captures"
    capture_root.mkdir()
    for label, (binding, ordinal) in cases.items():
        root = by_key[(binding.private_plan_sha256, ordinal)].root
        state = capture_root / f"{label}.state"
        envelope = Path(f"{state}.json")
        state.write_bytes(root.state_bytes)
        envelope.write_bytes(root.envelope_bytes)
        state.chmod(0o600)
        envelope.chmod(0o600)
        roots[label] = state

    loaded = load_red_living_dex_development_batch_assignments(
        _store(tmp_path),
        private_root=tmp_path,
        roots=roots,
    )

    assert loaded == assignments


def test_exact_input_loader_rejects_group_readable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, historical_binding, supplement_binding = _assignments()
    cases = {
        "historical-10": (historical_binding, 10),
        "historical-11": (historical_binding, 11),
        "supplement-0": (supplement_binding, 0),
        "supplement-1": (supplement_binding, 1),
        "supplement-2": (supplement_binding, 2),
    }
    monkeypatch.setattr(inputs, "_CASES", cases)

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        selection, _root = expected[(binding.private_plan_sha256, ordinal)]
        return selection, {}

    monkeypatch.setattr(inputs, "load_red_living_dex_development_selection", load)
    roots: dict[str, Path] = {}
    by_key = {
        (assignment.binding.private_plan_sha256, assignment.ordinal): assignment
        for assignment in assignments
    }
    capture_root = tmp_path / "captures"
    capture_root.mkdir()
    for label, (binding, ordinal) in cases.items():
        root = by_key[(binding.private_plan_sha256, ordinal)].root
        state = capture_root / f"{label}.state"
        envelope = Path(f"{state}.json")
        state.write_bytes(root.state_bytes)
        envelope.write_bytes(root.envelope_bytes)
        state.chmod(0o600)
        envelope.chmod(0o600)
        roots[label] = state
    roots["supplement-2"].chmod(0o640)

    with pytest.raises(
        RedLivingDexDevelopmentInputError,
        match="selected_root_authentication",
    ):
        load_red_living_dex_development_batch_assignments(
            _store(tmp_path),
            private_root=tmp_path,
            roots=roots,
        )


def test_storage_separation_detects_same_device(tmp_path: Path) -> None:
    source = tmp_path / "source"
    private = tmp_path / "private"
    source.mkdir()
    private.mkdir()

    assert source_private_storage_is_separate(source, private) is False

