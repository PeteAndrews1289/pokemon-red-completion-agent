"""Loading a title that is not Red.

A living Pokédex needs Blue: ten species are exclusive to it and no amount of
Red planning reaches them. Until this existed the repository could refuse a
cartridge it had already been told to expect, because the fingerprint check
inside the emulator adapter was hard-coded to Red while the check beside it took
the expected cartridge as an argument.

Nothing here needs a ROM. What it pins is that the identity gate is selective in
both directions and that a title's path comes from its own environment variable
-- one variable cannot name several cartridges, and a campaign runs several.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.constants import (
    POKEMON_BLUE_US_REV_0,
    POKEMON_RED_US_REV_0,
    SUPPORTED_ROMS,
)
from pokemon_red_completion.rom import (
    RomFingerprint,
    RomValidationError,
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom_fingerprint,
)


def fingerprint_of(rom) -> RomFingerprint:  # type: ignore[no-untyped-def]
    return RomFingerprint(
        filename="<private>",
        title=rom.title,
        size_bytes=rom.size_bytes,
        sha1=rom.sha1,
        sha256=rom.sha256,
    )


def test_both_cartridges_are_declared() -> None:
    assert set(SUPPORTED_ROMS) == {"red", "blue"}
    assert supported_rom_for("blue") is POKEMON_BLUE_US_REV_0
    assert supported_rom_for("red") is POKEMON_RED_US_REV_0


def test_the_two_cartridges_are_distinguishable() -> None:
    """Same size, different contents. Only the digests separate them."""

    assert POKEMON_BLUE_US_REV_0.size_bytes == POKEMON_RED_US_REV_0.size_bytes
    assert POKEMON_BLUE_US_REV_0.sha256 != POKEMON_RED_US_REV_0.sha256
    assert POKEMON_BLUE_US_REV_0.title != POKEMON_RED_US_REV_0.title


def test_the_gate_accepts_blue_when_blue_is_expected() -> None:
    assert verify_rom_fingerprint(fingerprint_of(POKEMON_BLUE_US_REV_0), POKEMON_BLUE_US_REV_0)


def test_the_gate_refuses_blue_when_red_is_expected() -> None:
    """Memory layouts are revision-specific, so a wrong cartridge must stop."""

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        verify_rom_fingerprint(fingerprint_of(POKEMON_BLUE_US_REV_0), POKEMON_RED_US_REV_0)


def test_the_gate_refuses_red_when_blue_is_expected() -> None:
    """Selective in both directions, or it is not a gate."""

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        verify_rom_fingerprint(fingerprint_of(POKEMON_RED_US_REV_0), POKEMON_BLUE_US_REV_0)


def test_each_title_reads_its_own_environment_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """One variable cannot name several cartridges, and a campaign runs several.

    The Red variable is deliberately set and pointing at a real file here. A
    lookup that quietly fell back to it would load Red while being asked for
    Blue, and the caller would never know -- an earlier version of this test
    left Red unset, so a fallback and a correct refusal produced the same error
    and it passed either way.
    """

    red = tmp_path / "red.gb"
    red.write_bytes(b"\x00")
    blue = tmp_path / "blue.gb"
    blue.write_bytes(b"\x01")
    monkeypatch.setenv("POKEMON_RED_ROM", str(red))
    monkeypatch.delenv("POKEMON_BLUE_ROM", raising=False)

    assert resolve_title_rom_path("red") == red.resolve()
    with pytest.raises(RomValidationError, match="POKEMON_BLUE_ROM"):
        resolve_title_rom_path("blue")

    monkeypatch.setenv("POKEMON_BLUE_ROM", str(blue))
    assert resolve_title_rom_path("blue") == blue.resolve()
    assert resolve_title_rom_path("blue") != resolve_title_rom_path("red")


def test_an_unknown_title_names_the_ones_that_exist() -> None:
    with pytest.raises(RomValidationError, match="known titles are"):
        resolve_title_rom_path("crystal")
    with pytest.raises(RomValidationError, match="known titles are"):
        supported_rom_for("crystal")


def test_the_adapter_verifies_against_the_cartridge_it_was_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Booting is an integration concern; which identity it checks is not.

    The check inside the adapter was hard-coded to Red while the function it
    called took the expected cartridge as an argument, so the repository could
    refuse a cartridge it had been told to expect. This pins the wiring without
    needing either ROM.
    """

    from pokemon_red_completion import emulator as emulator_module

    seen: list[object] = []

    def record(payload: bytes, expected=POKEMON_RED_US_REV_0, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(expected)
        raise RuntimeError("stop before PyBoy")

    monkeypatch.setattr(emulator_module, "verify_rom_bytes", record)
    rom = tmp_path / "cart.gb"
    rom.write_bytes(b"\x00")

    adapter = emulator_module.PyBoyAdapter(rom, expected_rom=POKEMON_BLUE_US_REV_0)
    with pytest.raises(RuntimeError, match="stop before PyBoy"):
        adapter.start()

    assert seen == [POKEMON_BLUE_US_REV_0], "the adapter must check the cartridge it was given"


def test_the_adapter_still_defaults_to_red() -> None:
    """Every existing caller passes no cartridge and must keep meaning Red."""

    import inspect

    from pokemon_red_completion.emulator import PyBoyAdapter

    default = inspect.signature(PyBoyAdapter.__init__).parameters["expected_rom"].default
    assert default is POKEMON_RED_US_REV_0
