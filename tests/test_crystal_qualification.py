from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_crystal_completion.observation import (
    CRYSTAL_BOX_OBSERVATION_BYTES,
    CrystalInventoryObservation,
    CrystalObservationBundle,
    CrystalPokedexProgress,
    CrystalStorageObservation,
    decode_crystal_box,
    derive_crystal_ownership_progress,
)
from pokemon_crystal_completion.qualification import (
    CRYSTAL_BOOT_FRAMES,
    CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT,
    CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT,
    CRYSTAL_POST_SAVE_STABILITY_FRAMES,
    CrystalBankedObservationQualification,
    CrystalQualificationError,
    CrystalQualificationRuntimeState,
    CrystalQualificationStep,
    execute_crystal_qualification_steps,
    qualification_transcript_sha256,
    read_crystal_qualification_runtime,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_OBSERVATION_SYMBOLS
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import PartyObservation


class _Controller:
    def __init__(self, *, fail_tick: int | None = None) -> None:
        self.frame_count = 0
        self._pressed: set[str] = set()
        self.calls: list[tuple[str, object]] = []
        self.fail_tick = fail_tick
        self.tick_calls = 0

    @property
    def pressed_buttons(self) -> frozenset[str]:
        return frozenset(self._pressed)

    def press(self, button: str) -> None:
        self.calls.append(("press", button))
        self._pressed.add(button)

    def release(self, button: str) -> None:
        self.calls.append(("release", button))
        self._pressed.remove(button)

    def tick(self, frames: int) -> None:
        self.tick_calls += 1
        if self.fail_tick == self.tick_calls:
            raise RuntimeError("injected tick failure")
        self.calls.append(("tick", frames))
        self.frame_count += frames

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        raise AssertionError((bank, address, length))

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        raise AssertionError((bank, address, length))


class _RuntimeMemory:
    def __init__(self, values: dict[str, int]) -> None:
        self.values = values
        self.calls: list[str] = []

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        assert length == 1
        name = next(
            name
            for name, symbol in CRYSTAL_OBSERVATION_SYMBOLS.items()
            if (symbol.bank, symbol.address) == (bank, address)
        )
        self.calls.append(name)
        return bytes((self.values[name],))

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        raise AssertionError((bank, address, length))


def _runtime_values() -> dict[str, int]:
    return {
        "wJohtoBadges": 0,
        "wKantoBadges": 0,
        "wBattleMode": 0,
        "wMapStatus": 2,
        "wMapEventStatus": 0,
        "wScriptMode": 0,
        "wScriptRunning": 0,
        "wJoypadDisable": 0,
        "wPlayerState": 0,
        "wMapGroup": 24,
        "wMapNumber": 7,
        "wXCoord": 3,
        "wYCoord": 3,
    }


def _empty_bundle() -> CrystalObservationBundle:
    party = PartyObservation()
    payload = bytearray(CRYSTAL_BOX_OBSERVATION_BYTES)
    payload[1] = 0xFF
    boxes = tuple(
        decode_crystal_box(bytes(payload), box_number=number) for number in range(1, 15)
    )
    storage = CrystalStorageObservation(current_box_number=1, boxes=boxes)
    return CrystalObservationBundle(
        party=party,
        pokedex=CrystalPokedexProgress(
            registered=CompletionProgress(0, 250),
            seen=CompletionProgress(0, 250),
        ),
        storage=storage,
        inventory=CrystalInventoryObservation(items=(), balls=()),
        ownership=derive_crystal_ownership_progress(party, storage),
    )


def test_fixed_setup_transcript_has_bounded_reproducible_cost() -> None:
    assert sum(step.repetitions for step in CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT) == 40
    assert sum(step.repetitions for step in CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT) == 6
    assert CRYSTAL_BOOT_FRAMES == 4_200
    assert CRYSTAL_POST_SAVE_STABILITY_FRAMES == 600
    assert qualification_transcript_sha256() == (
        "325542d1b7527caa8b43efb4bb74a8b783fd4c7b6ccbcce650e269f2cb8690a3"
    )


def test_step_executor_releases_every_button_and_counts_real_inputs() -> None:
    controller = _Controller()
    steps = (
        CrystalQualificationStep("a", 2, 10),
        CrystalQualificationStep("down", 1, 20),
    )

    actions = execute_crystal_qualification_steps(controller, steps)

    assert actions == 3
    assert controller.frame_count == 58
    assert controller.pressed_buttons == frozenset()
    assert controller.calls == [
        ("press", "a"),
        ("tick", 6),
        ("release", "a"),
        ("tick", 10),
        ("press", "a"),
        ("tick", 6),
        ("release", "a"),
        ("tick", 10),
        ("press", "down"),
        ("tick", 6),
        ("release", "down"),
        ("tick", 20),
    ]


@pytest.mark.parametrize("button", ("", "A", ["a"]))
def test_qualification_step_rejects_invalid_button_values(button: object) -> None:
    with pytest.raises(CrystalQualificationError, match="button is invalid"):
        CrystalQualificationStep(button, 1, 1)  # type: ignore[arg-type]


def test_step_executor_releases_controller_after_an_emulator_failure() -> None:
    controller = _Controller(fail_tick=1)

    with pytest.raises(RuntimeError, match="injected"):
        execute_crystal_qualification_steps(
            controller,
            (CrystalQualificationStep("a", 1, 10),),
        )

    assert controller.pressed_buttons == frozenset()
    assert controller.calls == [("press", "a"), ("release", "a")]


def test_runtime_reader_recognizes_only_the_ready_starting_room() -> None:
    memory = _RuntimeMemory(_runtime_values())

    runtime = read_crystal_qualification_runtime(memory)

    assert runtime.at_starting_bedroom
    assert runtime.input_ready
    assert runtime.badge_count == 0
    assert len(memory.calls) == 26
    assert runtime.public_dict() == {
        "badge_count": 0,
        "at_expected_start_location": True,
        "input_ready": True,
        "private_location_identity_fields": 0,
        "raw_address_fields": 0,
    }
    assert not replace(runtime, script_running=1).input_ready
    assert not replace(runtime, x=4).at_starting_bedroom


def test_runtime_reader_retries_a_torn_whole_state() -> None:
    class TornRuntimeMemory(_RuntimeMemory):
        map_group_reads = 0

        def read_wram(self, bank: int, address: int, length: int) -> bytes:
            symbol = CRYSTAL_OBSERVATION_SYMBOLS["wMapGroup"]
            if (bank, address, length) == (symbol.bank, symbol.address, 1):
                self.map_group_reads += 1
                return bytes((23 if self.map_group_reads == 2 else 24,))
            return super().read_wram(bank, address, length)

    memory = TornRuntimeMemory(_runtime_values())

    runtime = read_crystal_qualification_runtime(memory, maximum_attempts=2)

    assert runtime.at_starting_bedroom
    assert memory.map_group_reads == 4


def test_passed_receipt_is_path_free_and_preserves_zero_experiment_counters() -> None:
    qualification = CrystalBankedObservationQualification(
        source_commit="1" * 40,
        plan_sha256="2" * 64,
        rom_sha1="3" * 40,
        rom_sha256="4" * 64,
        transcript_sha256="5" * 64,
        actions=46,
        frames=33_876,
        runtime=CrystalQualificationRuntimeState(*_runtime_values().values()),
        observation=_empty_bundle(),
        pre_save_storage_rejected=True,
        post_save_observations_identical=True,
        controller_released=True,
        rom_unchanged=True,
    )

    document = qualification.public_dict()

    assert document["status"] == "passed"
    assert document["experiment"] == {
        "context_opened": False,
        "teacher_executed": False,
        "prediction_computed": False,
        "zero_shot_opened": 0,
        "adaptation_opened": 0,
        "sealed_test_opened": 0,
    }
    assert "/Users/" not in str(document)
    assert "0xdc" not in str(document).lower()
    with pytest.raises(CrystalQualificationError, match="ROM SHA-1 is invalid"):
        replace(qualification, rom_sha1="z" * 40)
    with pytest.raises(CrystalQualificationError, match="did not qualify"):
        replace(qualification, controller_released=False)


@pytest.mark.parametrize("maximum_attempts", (0, -1, True, 1.5))
def test_runtime_reader_requires_a_positive_integer_bound(maximum_attempts: object) -> None:
    with pytest.raises(CrystalQualificationError, match="positive attempt bound"):
        read_crystal_qualification_runtime(
            _RuntimeMemory(_runtime_values()),
            maximum_attempts=maximum_attempts,  # type: ignore[arg-type]
        )
