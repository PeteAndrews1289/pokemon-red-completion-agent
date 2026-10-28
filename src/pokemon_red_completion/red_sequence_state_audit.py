"""Native boundary targets for the Cerulean sequence experiment.

Uses existing revision-specific readers, never executes controller input. This
verifies state channels, NOT source ancestry, selected executor or TRAIN eligibility.
Progress identities are private deduplication keys, never policy features.
"""

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

from .gen1_trainer_sight import trainer_headers
from .observation import Badge, EventFlag, PokemonRedStateReader, event_flag_is_set
from .player_short_sequence import MeasuredSequenceStep
from .provenance import canonical_sha256
from .red_sequence_receipts import RecordedSequenceProjection, read_sequence_receipts

QUESTS = frozenset({"defeat_misty", "help_bill"})


@dataclass(frozen=True)
class NativeSequenceBoundary:
    state_sha256: str
    cash: int
    progress: tuple[str, ...]
    quests: tuple[str, ...]


class CeruleanSequenceStateReader:
    """Read a caller-owned, isolated audit emulator, never a live player session.

Caller supplies an authenticated exact-Red cartridge and prospective map scope.
Catalog/hash must be pinned by the eventual experiment before collection. Merely
constructing this reader does not provide experiment or source authority.
"""

    def __init__(self, emulator, *, rom: bytes, expected_rom_sha256: str, maps: tuple[int, ...]):
        if (sha256(rom).hexdigest() != expected_rom_sha256
            or type(maps) is not tuple or not maps or maps != tuple(sorted(set(maps)))
            or any(type(m) is not int or not 0 <= m <= 255 for m in maps)):
            raise ValueError("native sequence cartridge/map scope differs")
        events = {h.event_flag for h in trainer_headers(rom, maps, full_event_offsets=True)}
        events.update(int(e) for e in (
            EventFlag.BEAT_CERULEAN_RIVAL, EventFlag.BEAT_MISTY, EventFlag.MET_BILL,
            EventFlag.USED_CELL_SEPARATOR_ON_BILL, EventFlag.GOT_SS_TICKET,
            EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
        ))
        self.events = tuple(sorted(events))
        self.emulator = emulator
        self.catalog_sha256 = canonical_sha256(dict(
            schema="pokemon.red.cerulean-sequence-state-catalog.v1",
            rom_sha256=expected_rom_sha256, maps=list(maps), events=list(self.events),
            quests=sorted(QUESTS),
        ))

    def read(self, path: Path, expected_sha256: str) -> NativeSequenceBoundary:
        state = path.read_bytes()
        if sha256(state).hexdigest() != expected_sha256:
            raise ValueError("native sequence state bytes differ")
        em = self.emulator
        frame = em.frame_count
        em.load_state_bytes(state)
        raw = PokemonRedStateReader(em).read()
        if (em.frame_count != frame or em.save_state_bytes() != state
            or raw.battle_state != 0 or type(raw.player_money) is not int
            or not 0 <= raw.player_money <= 999999 or raw.event_flags is None
            or type(raw.badge_bits) is not int):
            raise ValueError("native sequence boundary is not a stable field state")
        events = tuple(e for e in self.events if event_flag_is_set(raw.event_flags, e))
        misty = event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_MISTY))
        cascade = bool(raw.badge_bits & int(Badge.CASCADE))
        if cascade and not misty:
            raise ValueError("native Cascade badge lacks its victory event")
        quests = []
        if misty and cascade:
            quests.append("defeat_misty")
        if event_flag_is_set(raw.event_flags, int(EventFlag.GOT_SS_TICKET)):
            quests.append("help_bill")
        return NativeSequenceBoundary(
            expected_sha256, raw.player_money, tuple(f"event:{e}" for e in events),
            tuple(sorted(quests)),
        )


@dataclass(frozen=True)
class NativeSequenceStateAudit:
    source_sha256: str
    plan_sha256: str
    catalog_sha256: str
    boundaries_sha256: str
    steps: tuple[MeasuredSequenceStep, ...]
    initial_progress: tuple[str, ...]
    initial_quests: tuple[str, ...]
    # Counts remain diagnostic until joined with input, authority and source audits.
    training_eligible: bool = False
    battle_losses_verified: bool = False


def audit_sequence_state_channels(
    root: Path, *, reader: CeruleanSequenceStateReader, source_sha256: str,
    expected_plan_sha256: str, expected_result_sha256: str, expected_catalog_sha256: str,
) -> NativeSequenceStateAudit:
    if reader.catalog_sha256 != expected_catalog_sha256:
        raise ValueError("native sequence progress catalog differs")
    projection: RecordedSequenceProjection = read_sequence_receipts(
        root, source_sha256=source_sha256, expected_plan_sha256=expected_plan_sha256,
        expected_result_sha256=expected_result_sha256,
    )
    rows = json.loads((root / "result.json").read_bytes())["outcomes"]
    boundaries = []
    steps: list[MeasuredSequenceStep] = []
    old = reader.read(root / "step-000/before.state", source_sha256)
    initial = old
    prior_reported = set(rows[0]["before"]["completed_objectives"])
    for ordinal, row in enumerate(rows):
        folder = root / f"step-{ordinal:03d}"
        new = reader.read(folder / "terminal.state", row["terminal_state_sha256"])
        before, after = row["before"], row["after"]
        old_reported, new_reported = (set(x["completed_objectives"]) for x in (before, after))
        if (old.state_sha256 != row["before_state_sha256"]
            or type(before["cash"]) is not int or type(after["cash"]) is not int
            or (before["cash"], after["cash"]) != (old.cash, new.cash)
            or old_reported != prior_reported
            or old_reported & QUESTS != set(old.quests)
            or new_reported & QUESTS != set(new.quests)
            or not new_reported - old_reported <= QUESTS
            or not set(old.progress) <= set(new.progress)
            or not set(old.quests) <= set(new.quests)):
            raise ValueError("native sequence cash/quest/progress differs from receipts")
        boundaries.append(dict(before=asdict(old), after=asdict(new)))
        if row["learning_eligible"]:
            # Preserve measured costs/support from the original projection.
            steps.append(replace(projection.choices[len(steps)], progress=new.progress,
                                 quests=new.quests))
            if len(steps) == 1:
                initial = old  # leading support is not caused by the first model choice
        elif steps:
            steps[-1] = replace(steps[-1], progress=new.progress, quests=new.quests)
        old, prior_reported = new, new_reported
    if len(steps) != len(projection.choices):
        raise ValueError("native sequence model choice census differs")
    return NativeSequenceStateAudit(
        source_sha256, expected_plan_sha256, reader.catalog_sha256,
        canonical_sha256(boundaries), tuple(steps), initial.progress, initial.quests,
    )
