"""Capturing and restoring emulator state.

The round trip itself needs a real emulator and a ROM, so it is exercised by
``scripts/capture_checkpoint.py`` rather than here. What is worth pinning
without one is the boundary: where the file is allowed to go, and that a
missing state is refused rather than half-loaded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter


def test_loading_a_state_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Checked before the backend is touched, so the message names the path."""

    adapter = PyBoyAdapter(tmp_path / "rom.gb")

    with pytest.raises(EmulatorError, match="no saved state"):
        adapter.load_state(tmp_path / "absent.state")


def test_the_adapter_offers_state_capture_at_a_caller_chosen_path() -> None:
    """The no-save property is about PyBoy never writing beside the user's ROM.

    It is enforced by handing PyBoy the ROM as an in-memory stream, so it cannot
    discover or create sibling RAM and RTC files there. Writing a state to a
    path the caller names does not touch that: the destination is explicit and
    belongs outside the repository, because a state is derived from the ROM and
    is private in the same way.
    """

    for name in ("save_state", "load_state"):
        assert callable(getattr(PyBoyAdapter, name, None)), f"{name} should exist"

    doc = " ".join((PyBoyAdapter.save_state.__doc__ or "").split())
    assert "must never be committed" in doc, "the privacy boundary belongs in the docstring"
