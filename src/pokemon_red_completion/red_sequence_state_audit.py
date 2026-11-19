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
        if (
            sha256(rom).hexdigest() != expected_rom_sha256
            or type(maps) is not tuple
            or not maps
            or maps != tuple(sorted(set(maps)))
            or any(type(m) is not int or not 0 <= m <= 255 for m in maps)
        ):
            raise ValueError("native sequence cartridge/map scope differs")
        events = {h.event_flag for h in trainer_headers(rom, maps, full_event_offsets=True)}
        events.update(
            int(e)
            for e in (
                EventFlag.BEAT_CERULEAN_RIVAL,
                EventFlag.BEAT_MISTY,
                EventFlag.MET_BILL,
                EventFlag.USED_CELL_SEPARATOR_ON_BILL,
                EventFlag.GOT_SS_TICKET,
                EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
            )
        )
        self.events = tuple(sorted(events))
        self.emulator = emulator
        self.catalog_sha256 = canonical_sha256(
            dict(
                schema="pokemon.red.cerulean-sequence-state-catalog.v1",
                rom_sha256=expected_rom_sha256,
                maps=list(maps),
                events=list(self.events),
                quests=sorted(QUESTS),
            )
        )

    def read(self, path: Path, expected_sha256: str) -> NativeSequenceBoundary:
        state = path.read_bytes()
        if sha256(state).hexdigest() != expected_sha256:
            raise ValueError("native sequence state bytes differ")
        em = self.emulator
        frame = em.frame_count
        em.load_state_bytes(state)
        raw = PokemonRedStateReader(em).read()
        if (
            em.frame_count != frame
            or em.save_state_bytes() != state
            or raw.battle_state != 0
            or type(raw.player_money) is not int
            or not 0 <= raw.player_money <= 999999
            or raw.event_flags is None
            or type(raw.badge_bits) is not int
        ):
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
            expected_sha256,
            raw.player_money,
            tuple(f"event:{e}" for e in events),
            tuple(sorted(quests)),
        )


def scoped_trainer_task_sha256(*, rom_sha256, maps, events):
    """Prospective task identity;private event keys never become model features."""
    return canonical_sha256(
        dict(
            schema="pokemon.red.scoped-trainer-sequence-task.v1",
            rom_sha256=rom_sha256,
            maps=list(maps),
            events=list(events),
        )
    )


class ScopedTrainerSequenceStateReader:
    """Independently read only prospectively scoped cartridge trainer progress.

    No whole-quest completion or battle-loss target is inferred. Other quest
    changes fail the join rather than becoming fabricated zero labels.
    """

    quest_scope = frozenset()
    target_channels = frozenset(
        {"native_progress", "actions", "frames", "observed_cash_debits", "observed_cash_credits"}
    )

    def __init__(self, emulator, *, rom, expected_rom_sha256, maps, events):
        if (
            sha256(rom).hexdigest() != expected_rom_sha256
            or type(maps) is not tuple
            or not maps
            or maps != tuple(sorted(set(maps)))
            or any(type(m) is not int or not 0 <= m <= 255 for m in maps)
            or type(events) is not tuple
            or not events
            or events != tuple(sorted(set(events)))
            or any(type(e) is not int for e in events)
        ):
            raise ValueError("scoped sequence cartridge/catalog differs")
        native_events = {h.event_flag for h in trainer_headers(rom, maps, full_event_offsets=True)}
        if not set(events) <= native_events:
            raise ValueError("scoped sequence event is not in cartridge trainer headers")
        self.emulator, self.events, self.maps = emulator, events, maps
        self.task_sha256 = scoped_trainer_task_sha256(
            rom_sha256=expected_rom_sha256, maps=maps, events=events
        )
        self.task_progress = tuple(f"event:{e}" for e in events)
        self.catalog_sha256 = canonical_sha256(
            dict(
                schema="pokemon.red.scoped-trainer-sequence-catalog.v1",
                rom_sha256=expected_rom_sha256,
                maps=list(maps),
                events=list(events),
                quests=[],
                target_channels=sorted(self.target_channels),
            )
        )

    def read(self, path, expected_sha256):
        state = path.read_bytes()
        if sha256(state).hexdigest() != expected_sha256:
            raise ValueError("scoped sequence state bytes differ")
        em = self.emulator
        frame = em.frame_count
        em.load_state_bytes(state)
        raw = PokemonRedStateReader(em).read()
        if (
            em.frame_count != frame
            or em.save_state_bytes() != state
            or raw.battle_state != 0
            or type(raw.player_money) is not int
            or not 0 <= raw.player_money <= 999999
            or raw.event_flags is None
            or raw.map_id not in self.maps
        ):
            raise ValueError("scoped sequence boundary is not in its ready native scope")
        progress = tuple(f"event:{e}" for e in self.events if event_flag_is_set(raw.event_flags, e))
        return NativeSequenceBoundary(expected_sha256, raw.player_money, progress, ())


class ScopedStorySequenceStateReader(ScopedTrainerSequenceStateReader):
    """Audit a finite prefix ending at its first new scoped midgame milestone.

    Uses the existing cartridge/event reader, not actor-latched objectives. The
    caller must prospectively bind the complete menu, source and battle scope.
    Saffron requires observed native arrival as well as open guards. This reader
    deliberately cannot certify a later off-location latched Saffron completion;
    collection ends at the first new milestone. No TRAIN admission is granted.
    """

    quest_scope = frozenset({"defeat_erika", "rescue_fuji", "reach_saffron"})
    target_channels = ScopedTrainerSequenceStateReader.target_channels | {"completed_quests"}

    def __init__(
        self,
        emulator,
        *,
        rom,
        expected_rom_sha256,
        maps,
        events,
        objectives,
        include_registrations=False,
        include_field_progress=False,
        include_silph=False,
        retain_saffron_arrival=False,
        include_late_gym_rewards=False,
    ):
        if type(include_silph) is not bool or type(retain_saffron_arrival) is not bool:
            raise ValueError("extended story audit flags require explicit booleans")
        if type(include_late_gym_rewards) is not bool:
            raise ValueError("late gym rewards require explicit boolean scope")
        self.include_late_gym_rewards = include_late_gym_rewards
        if include_late_gym_rewards:
            self.quest_scope = type(self).quest_scope | {"defeat_blaine", "defeat_giovanni"}
        self.include_silph = include_silph
        self.retain_saffron_arrival = retain_saffron_arrival
        if include_silph:
            self.quest_scope = self.quest_scope | {"liberate_silph"}
        if type(include_registrations) is not bool:
            raise ValueError("registration progress requires explicit boolean scope")
        self.include_registrations = include_registrations
        if type(include_field_progress) is not bool:
            raise ValueError("field progress requires explicit boolean scope")
        self.include_field_progress = include_field_progress
        if (
            type(objectives) is not tuple
            or not objectives
            or objectives != tuple(sorted(set(objectives)))
            or not set(objectives) <= self.quest_scope
        ):
            raise ValueError("native story task requires exact supported objectives")
        super().__init__(
            emulator,
            rom=rom,
            expected_rom_sha256=expected_rom_sha256,
            maps=maps,
            events=events,
        )
        self.objectives = objectives
        self.task_progress = tuple("quest:" + objective for objective in objectives)
        self.task_sha256 = canonical_sha256(
            dict(
                schema="pokemon.red.first-new-story-milestone-task.v1",
                rom_sha256=expected_rom_sha256,
                maps=list(maps),
                events=list(events),
                objectives=list(objectives),
                predicate="any-new-native-quest-at-window-terminal",
            )
        )
        self.catalog_sha256 = canonical_sha256(
            dict(
                schema="pokemon.red.scoped-story-sequence-catalog.v1",
                trainer_catalog_sha256=self.catalog_sha256,
                task_sha256=self.task_sha256,
                quest_predicates="erika-reward;fuji-and-flute;saffron-guards-and-arrival-v1",
                target_channels=sorted(self.target_channels),
            )
        )

        if include_registrations:
            self.task_sha256 = canonical_sha256(
                dict(
                    schema="pokemon.red.first-new-story-milestone-task.v2",
                    base_task_sha256=self.task_sha256,
                    progress_coverage="trainer-events;native-story-milestones;owned-national-dex",
                )
            )
            self.catalog_sha256 = canonical_sha256(
                dict(
                    schema="pokemon.red.scoped-story-sequence-catalog.v2",
                    base_catalog_sha256=self.catalog_sha256,
                    task_sha256=self.task_sha256,
                    registration_reader="native-owned-national-dex-v1",
                )
            )

        if include_field_progress:
            self.task_sha256 = canonical_sha256(
                dict(
                    schema="pokemon.red.first-new-story-milestone-task.v3",
                    base_task_sha256=self.task_sha256,
                    field_coverage="native-HM02-gift;carried-Fly-with-Thunder-badge",
                )
            )
            self.catalog_sha256 = canonical_sha256(
                dict(
                    schema="pokemon.red.scoped-story-sequence-catalog.v3",
                    base_catalog_sha256=self.catalog_sha256,
                    task_sha256=self.task_sha256,
                    field_reader="native-Fly-milestones-v1",
                )
            )

        if include_silph or retain_saffron_arrival:
            declaration = dict(
                schema="pokemon.red.extended-story-audit.v1",
                base_task_sha256=self.task_sha256,
                include_silph=include_silph,
                retain_saffron_arrival=retain_saffron_arrival,
                semantics="giovanni-and-president-gift;earlier-native-arrival-in-same-ordered-trace",
            )
            self.task_sha256 = canonical_sha256(declaration)
            self.catalog_sha256 = canonical_sha256(
                dict(
                    base_catalog_sha256=self.catalog_sha256,
                    task_sha256=self.task_sha256,
                    declaration=declaration,
                )
            )

        if include_late_gym_rewards:
            declaration=dict(schema="pokemon.red.native-late-gym-task.v1",base_task_sha256=self.task_sha256,
                predicates="Blaine/Giovanni cartridge victory + badge + TM-reward event",objectives=list(objectives))
            self.task_sha256=canonical_sha256(declaration)
            self.catalog_sha256=canonical_sha256(dict(base_catalog_sha256=self.catalog_sha256,task_sha256=self.task_sha256,declaration=declaration))

    def task_completed(self, initial, terminal):
        return bool((set(terminal) - set(initial)) & set(self.task_progress))

    def read(self, path, expected_sha256):
        result = super().read(path, expected_sha256)
        from .observation import SAFFRON_GUARD_ACCESS_MASK, MapId
        from .red_gym_reward import ERIKA_REWARD

        raw = PokemonRedStateReader(self.emulator).read()
        if (
            type(raw.badge_bits) is not int
            or type(raw.status_flags_1) is not int
            or not 0 <= raw.status_flags_1 <= 255
        ):
            raise ValueError("native story boundary lacks badge/guard facts")
        defeated = event_flag_is_set(raw.event_flags, ERIKA_REWARD.defeated_event)
        badge = bool(raw.badge_bits & ERIKA_REWARD.badge)
        if badge and not defeated:
            raise ValueError("native Rainbow badge lacks Erika victory")
        quests = set()
        if self.include_late_gym_rewards:
            from .red_gym_reward import BLAINE_REWARD, GIOVANNI_REWARD
            for reward in (BLAINE_REWARD, GIOVANNI_REWARD):
                if raw.badge_bits & reward.badge and not event_flag_is_set(raw.event_flags,reward.defeated_event):
                    raise ValueError("native late badge lacks its victory event")
                if reward.received(raw):quests.add(reward.objective_id)
        if ERIKA_REWARD.received(raw):
            quests.add("defeat_erika")
        if all(
            event_flag_is_set(raw.event_flags, e)
            for e in (
                int(EventFlag.RESCUED_MR_FUJI),
                int(EventFlag.RESCUED_MR_FUJI_WORLD),
                int(EventFlag.GOT_POKE_FLUTE),
            )
        ):
            quests.add("rescue_fuji")
        if self.include_silph and all(
            event_flag_is_set(raw.event_flags, int(event))
            for event in (EventFlag.BEAT_SILPH_CO_GIOVANNI, EventFlag.GOT_MASTER_BALL)
        ):
            quests.add("liberate_silph")
        opened = bool(raw.status_flags_1 & SAFFRON_GUARD_ACCESS_MASK)
        if opened and raw.map_id in (
            int(MapId.SAFFRON_CITY),
            int(MapId.SAFFRON_POKECENTER),
        ):
            quests.add("reach_saffron")
        progress = set(result.progress) | {"quest:" + q for q in quests}
        if opened:
            progress.add("story:saffron_guards_open")
        if self.include_field_progress:
            moves = raw.party_moves
            if (
                type(moves) is not tuple
                or not 1 <= len(moves) <= 6
                or any(
                    type(row) is not tuple
                    or len(row) != 4
                    or any(type(move) is not int or not 0 <= move <= 165 for move in row)
                    for row in moves
                )
            ):
                raise ValueError("native carried field-move progress is unknown")
            if event_flag_is_set(raw.event_flags, int(EventFlag.GOT_HM02)):
                progress.add("field:hm02-native-gift")
            if raw.badge_bits & int(Badge.THUNDER) and any(19 in row for row in moves):
                progress.add("field:carried-fly-usable")
        if self.include_registrations:
            frame, state = self.emulator.frame_count, self.emulator.save_state_bytes()
            owned = PokemonRedStateReader(self.emulator).read_pokedex_state().owned_species
            if (
                not isinstance(owned, set | frozenset)
                or any(type(n) is not int or not 1 <= n <= 151 for n in owned)
                or self.emulator.frame_count != frame
                or self.emulator.save_state_bytes() != state
            ):
                raise ValueError("native registration progress is unknown or unstable")
            progress.update(f"owned-dex:{n:03d}" for n in owned)
        return replace(result, progress=tuple(sorted(progress)), quests=tuple(sorted(quests)))


class NativeRegistrationSequenceStateReader:
    """Read owned-dex and medicine stock for the existing public task predicate.

    No story, XP or battle-loss truth is inferred. Stock is the priced positive
    net depletion between the exact window endpoints, not a purchase claim or
    a claim about gross consumption replenished inside a window.
    """

    quest_scope = frozenset()
    target_channels = frozenset({"native_progress", "actions", "frames",
        "cash_outflow_plus_priced_medicine_depletion", "observed_cash_credits"})

    def __init__(self, emulator, *, rom, expected_rom_sha256):
        from .player_sequence_targets import registration_task_catalog
        from .red_league_field_recovery import _REPLACEMENT_PRICES
        if sha256(rom).hexdigest() != expected_rom_sha256:
            raise ValueError("registration reader cartridge differs")
        self.emulator = emulator
        self.prices = {int(k): v for k, v in _REPLACEMENT_PRICES.items()}
        self.stock = {}
        self.task_sha256 = registration_task_catalog(expected_rom_sha256)["task_sha256"]
        self.catalog_sha256 = canonical_sha256(dict(
            schema="pokemon.red.native-registration-stock-reader.v1",
            task_sha256=self.task_sha256, prices=self.prices,
            stock_semantics="positive-net-window-endpoint-depletion",
            target_channels=sorted(self.target_channels)))

    def task_completed(self, initial, terminal):
        return bool(set(terminal) - set(initial))

    def read(self, path, expected_sha256):
        state = path.read_bytes()
        if sha256(state).hexdigest() != expected_sha256:
            raise ValueError("registration reader state bytes differ")
        em = self.emulator
        frame = em.frame_count
        em.load_state_bytes(state)
        reader = PokemonRedStateReader(em)
        raw = reader.read()
        owned = reader.read_pokedex_state().owned_species
        bag = raw.bag_items
        if (em.frame_count != frame or em.save_state_bytes() != state
                or raw.battle_state != 0 or type(raw.player_money) is not int
                or not 0 <= raw.player_money <= 999999
                or not isinstance(owned, (set, frozenset))
                or any(type(n) is not int or not 1 <= n <= 151 for n in owned)
                or type(bag) is not tuple
                or any(type(row) is not tuple or len(row) != 2
                    or any(type(x) is not int for x in row)
                    or not 0 < row[0] <= 255 or not 0 < row[1] <= 99 for row in bag)
                or len({row[0] for row in bag}) != len(bag)):
            raise ValueError("registration/stock boundary is not stable native field state")
        self.stock[expected_sha256] = dict(bag)
        return NativeSequenceBoundary(expected_sha256, raw.player_money,
            tuple(f"owned-dex:{n:03d}" for n in sorted(owned)), ())

    def priced_medicine_depletion(self, before_sha256, after_sha256):
        if before_sha256 not in self.stock or after_sha256 not in self.stock:
            raise ValueError("medicine endpoint was not independently read")
        before, after = self.stock[before_sha256], self.stock[after_sha256]
        return sum(price * max(0, before.get(item, 0) - after.get(item, 0))
            for item, price in self.prices.items())


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
    root: Path,
    *,
    reader: CeruleanSequenceStateReader,
    source_sha256: str,
    expected_plan_sha256: str,
    expected_result_sha256: str,
    expected_catalog_sha256: str,
) -> NativeSequenceStateAudit:
    if reader.catalog_sha256 != expected_catalog_sha256:
        raise ValueError("native sequence progress catalog differs")
    quest_scope = getattr(reader, "quest_scope", QUESTS)
    projection: RecordedSequenceProjection = read_sequence_receipts(
        root,
        source_sha256=source_sha256,
        expected_plan_sha256=expected_plan_sha256,
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
        new = _retain_observed_saffron_arrival(
            old, new, enabled=getattr(reader, "retain_saffron_arrival", False)
        )
        before, after = row["before"], row["after"]
        old_reported, new_reported = (set(x["completed_objectives"]) for x in (before, after))
        if (
            old.state_sha256 != row["before_state_sha256"]
            or type(before["cash"]) is not int
            or type(after["cash"]) is not int
            or (before["cash"], after["cash"]) != (old.cash, new.cash)
            or old_reported != prior_reported
            or old_reported & quest_scope != set(old.quests)
            or new_reported & quest_scope != set(new.quests)
            or not new_reported - old_reported <= quest_scope
            or not set(old.progress) <= set(new.progress)
            or not set(old.quests) <= set(new.quests)
        ):
            raise ValueError("native sequence cash/quest/progress differs from receipts")
        boundaries.append(dict(before=asdict(old), after=asdict(new)))
        if row["learning_eligible"]:
            # Preserve measured costs/support from the original projection.
            steps.append(
                replace(projection.choices[len(steps)], progress=new.progress, quests=new.quests)
            )
            if len(steps) == 1:
                initial = old  # leading support is not caused by the first model choice
        elif steps:
            steps[-1] = replace(steps[-1], progress=new.progress, quests=new.quests)
        old, prior_reported = new, new_reported
    if len(steps) != len(projection.choices):
        raise ValueError("native sequence model choice census differs")
    return NativeSequenceStateAudit(
        source_sha256,
        expected_plan_sha256,
        reader.catalog_sha256,
        canonical_sha256(boundaries),
        tuple(steps),
        initial.progress,
        initial.quests,
    )


def _retain_observed_saffron_arrival(old, new, *, enabled=False):
    """Carry only an earlier native arrival through this ordered sealed chain.

    Guard access alone or a future arrival cannot earn prior quest credit. The
    caller separately checks exact source/interval hashes and monotone events.
    Legacy stateless readers retain their existing behavior.
    """
    if type(enabled) is not bool:
        raise ValueError("native arrival retention requires a boolean")
    if not enabled or "reach_saffron" not in old.quests:
        return new
    if "story:saffron_guards_open" not in new.progress:
        raise ValueError("native Saffron arrival lost its open guards")
    return replace(
        new,
        progress=tuple(sorted(set(new.progress) | {"quest:reach_saffron"})),
        quests=tuple(sorted(set(new.quests) | {"reach_saffron"})),
    )
