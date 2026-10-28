"""TRAIN-only, read-only Red effect-dispatch observation; never an actor interface.

Entry/return are JumpMoveEffect in pret/pokered 1e96034092686d006e863cace09e87273051a3d8.
Verified against the exact revision-zero cartridge before any hook is installed.
PyBoy instrumentation patches executable ROM bytes temporarily, not game RAM.
"""

from contextlib import contextmanager

from .constants import POKEMON_RED_US_REV_0
from .observation import RamAddress
from .rom import verify_rom_bytes
from .scenario_lab import ScenarioPartition

TRACE_SCHEMA = "pokemon.red.training.selected-effect-trace.v1"
BANK, ENTRY, RETURN = 15, 0x7132, 0x7135
DISPATCH = bytes.fromhex("cd38710601c9f0f3a7fad3cf2803facdcf3d8721507106004f092a666fe9")
ENEMY_CONFUSION_COUNTER = 0xD070
ENEMY_DISABLED_MOVE = 0xD072
_SUPPORTED = {105: (0x38, "heal"), 135: (0x38, "heal"), 156: (0x38, "rest"),
              109: (0x31, "confusion"), 48: (0x31, "confusion"), 50: (0x56, "disable")}


def effect_label(record):
    """Attribute only measured changes inside a matched native effect invocation."""
    a, b = record["before"], record["after"]
    unknown = {"kind": "unknown", "application_success": None}
    identity = ("turn", "move", "effect", "stack", "player_species", "enemy_species",
                "player_slot", "enemy_slot", "battle")
    if any(a[k] != b[k] for k in identity) or a["turn"] != 0 or a["battle"] != 2:
        return {**unknown, "reason": "unmatched_player_effect"}
    supported = _SUPPORTED.get(a["move"])
    if supported is None or a["effect"] != supported[0]:
        return {**unknown, "reason": "unsupported_move_effect"}
    family = supported[1]
    if family in {"heal", "rest"}:
        if not 0 < a["player_hp"] <= b["player_hp"] <= b["player_max_hp"]:
            return {**unknown, "reason": "invalid_healing_transition"}
        changed = b["player_hp"] > a["player_hp"]
        if family == "rest":
            changed |= b["player_status"] == 2 and a["player_status"] != 2
    elif family == "confusion":
        if a["enemy_confused"]:
            if (b["enemy_confused"] != a["enemy_confused"] or
                    b["enemy_confusion_counter"] != a["enemy_confusion_counter"]):
                return {**unknown, "reason": "unexpected_confusion_rewrite"}
            changed = False
        else:
            changed = b["enemy_confused"] and b["enemy_confusion_counter"] > 0
    else:
        if a["enemy_disabled"] and a["enemy_disabled"] != b["enemy_disabled"]:
            return {**unknown, "reason": "unexpected_disable_rewrite"}
        changed = not a["enemy_disabled"] and bool(b["enemy_disabled"])
    return {"kind": "observed", "family": family, "application_success": int(changed),
            "hp_gained_inside_effect": b["player_hp"] - a["player_hp"],
            "reason": "matched_native_effect_boundary"}


class RedStatusEffectTrace:
    """One diagnostic episode; callbacks only read memory and append bounded records."""

    def __init__(self, backend, rom: bytes, *, partition, maximum_records=32):
        if partition is not ScenarioPartition.TRAIN:
            raise ValueError("effect telemetry is TRAIN-only")
        if type(maximum_records) is not int or not 1 <= maximum_records <= 64:
            raise ValueError("effect telemetry needs a bounded record limit")
        verify_rom_bytes(rom, POKEMON_RED_US_REV_0)
        offset = BANK * 0x4000 + ENTRY - 0x4000
        if rom[offset:offset + len(DISPATCH)] != DISPATCH:
            raise ValueError("effect dispatcher bytes differ")
        if bytes(backend.memory[BANK, ENTRY+i] for i in range(len(DISPATCH))) != DISPATCH:
            raise ValueError("loaded effect dispatcher differs")
        self.backend = backend
        self.maximum_records = maximum_records
        self.records: list[dict] = []
        self.pending = None
        self.used = False

    def snapshot(self):
        m = self.backend.memory

        def u16(address):
            return m[address] * 256 + m[address+1]

        turn = m[0xFFF3]
        return {"turn": turn, "move": m[0xCFD2 if turn == 0 else 0xCFCC],
                "effect": m[0xCFD3 if turn == 0 else 0xCFCD],
                "stack": self.backend.register_file.SP,
                "player_species": m[0xD014], "enemy_species": m[RamAddress.ENEMY_SPECIES],
                "player_slot": m[RamAddress.PLAYER_MON_NUMBER],
                "enemy_slot": m[RamAddress.ENEMY_MON_PARTY_POS],
                "battle": m[RamAddress.IS_IN_BATTLE],
                "player_hp": u16(0xD015), "player_max_hp": u16(0xD023),
                "player_status": m[0xD018], "enemy_status": m[RamAddress.ENEMY_STATUS],
                "enemy_confused": bool(m[RamAddress.ENEMY_BATTLE_STATUS_1] & 0x80),
                "enemy_confusion_counter": m[ENEMY_CONFUSION_COUNTER],
                "enemy_disabled": m[ENEMY_DISABLED_MOVE],
                "frame": self.backend.frame_count}

    def enter(self, _context):
        if self.pending is not None or len(self.records) >= self.maximum_records:
            raise ValueError("nested or excessive effect invocations")
        self.pending = self.snapshot()

    def leave(self, _context):
        if self.pending is None:
            raise ValueError("effect return without entry")
        record = {"schema": TRACE_SCHEMA, "before": self.pending, "after": self.snapshot()}
        record["label"] = effect_label(record)
        self.records.append(record)
        self.pending = None

    @contextmanager
    def installed(self):
        if self.used:
            raise ValueError("effect trace is single-use")
        self.used = True
        installed = []
        try:
            for address, callback in ((ENTRY, self.enter), (RETURN, self.leave)):
                self.backend.hook_register(BANK, address, callback, None)
                installed.append(address)
            yield self
            if self.pending is not None:
                raise ValueError("unclosed effect invocation")
        finally:
            for address in reversed(installed):
                self.backend.hook_deregister(BANK, address)
