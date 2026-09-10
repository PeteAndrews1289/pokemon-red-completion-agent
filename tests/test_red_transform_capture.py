"""Isolated unit tests for wild encounter Transform identity and capture status protection.

Tests verify:
- Independent RAM bytes for original species (0xCFD8) vs displayed species (0xCFE5)
- Transformed bit 3 at 0xD069 (mask 8) and live types at 0xCFEA/CFEB
- Address and mask distractors (wCurOpponent at 0xD059, status bytes 1 and 2)
- Rejection of invalid species IDs, invalid type codes, and nontransformed display mismatch
- Inactive / trainer / fainted battle states return None without reading RAM
- Preparer latches original identity across calls and permits legitimate transformed forms
- Target change rejected even when transformed
- Strict HP, party, and bag protection guards retained
- Live Ground type blocks Thunder Wave, including rechecking after switch
- Escape moves rechecked after switch to avoid lost encounters
- Attempt bounds strictly retained across preparer calls
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_capture_status_runtime as runtime
from pokemon_red_completion.observation import (
    ENEMY_TRANSFORMED_MASK,
    GEN1_INTERNAL_SPECIES_IDS,
    GEN1_TYPE_CODES,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    SemanticStateError,
    WildCaptureIdentity,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_capture_status_runtime import (
    RedCaptureStatusError,
    RedCaptureStatusPreparer,
)
from pokemon_red_completion.red_capture_support import red_capture_status_options


class Memory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = dict(values)
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        addr = int(address)
        self.reads.append(addr)
        return self.values.get(addr, 0)


# --- State Reader & Dataclass Tests ---


def test_wild_capture_identity_independent_ram_bytes_ditto_transform_hypno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Original species at 0xCFD8 survives Transform; displayed species at 0xCFE5 changes."""
    # Pinned pret/pokered constants verification
    assert int(RamAddress.ENEMY_SPECIES_2) == 0xCFD8
    assert int(RamAddress.ENEMY_SPECIES) == 0xCFE5
    assert int(RamAddress.ENEMY_SPECIES) - int(RamAddress.ENEMY_SPECIES_2) == 13
    assert int(RamAddress.ENEMY_TYPE_1) == 0xCFEA
    assert int(RamAddress.ENEMY_TYPE_2) == 0xCFEB
    assert int(RamAddress.ENEMY_BATTLE_STATUS_3) == 0xD069
    assert ENEMY_TRANSFORMED_MASK == 0x08

    # Set independent RAM bytes:
    # 76 is Ditto, 129 is Hypno, 24 is Psychic type, transformed mask 8
    memory = Memory(
        {
            int(RamAddress.ENEMY_SPECIES_2): 76,  # originalDitto76
            int(RamAddress.ENEMY_SPECIES): 129,  # displayHypno129
            int(RamAddress.ENEMY_TYPE_1): 24,  # Psychic
            int(RamAddress.ENEMY_TYPE_2): 24,  # Psychic
            int(RamAddress.ENEMY_BATTLE_STATUS_3): 0x08,  # transformed flag
            # Distractors: wCurOpponent / status bytes 1 & 2 must NOT be consumed
            int(RamAddress.CURRENT_OPPONENT): 15,  # Pidgey distractor in CURRENT_OPPONENT
            int(RamAddress.ENEMY_BATTLE_STATUS_1): 0x08,  # distractor bit in status 1
            0xD068: 0x08,  # independent distractor byte: status 2
        }
    )
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(
        game_started=True,
        map_id=35,
        player_x=5,
        player_y=30,
        party_count=2,
        battle_state=1,  # wild encounter
        enemy_hp=48,
        enemy_species_id=129,
    )
    monkeypatch.setattr(reader, "read", lambda: raw)

    identity = reader.read_wild_capture_identity()
    assert identity is not None
    assert identity.original_species_id == 76
    assert identity.displayed_species_id == 129
    assert identity.transformed is True
    assert identity.type_ids == (24, 24)
    assert identity.type_names == ("psychic",)

    # Verify memory reads:
    assert int(RamAddress.ENEMY_SPECIES_2) in memory.reads
    assert int(RamAddress.ENEMY_SPECIES) in memory.reads
    assert int(RamAddress.ENEMY_TYPE_1) in memory.reads
    assert int(RamAddress.ENEMY_TYPE_2) in memory.reads
    assert int(RamAddress.ENEMY_BATTLE_STATUS_3) in memory.reads
    # Crucially, CURRENT_OPPONENT was NOT read
    assert int(RamAddress.CURRENT_OPPONENT) not in memory.reads


def test_wild_capture_identity_pre_transformed_and_mask_distractors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before Transform, original and display match; other bits in status 3 are ignored."""
    memory = Memory(
        {
            int(RamAddress.ENEMY_SPECIES_2): 76,
            int(RamAddress.ENEMY_SPECIES): 76,
            int(RamAddress.ENEMY_TYPE_1): 0,  # Normal
            int(RamAddress.ENEMY_TYPE_2): 0,  # Normal
            int(RamAddress.ENEMY_BATTLE_STATUS_3): 0xF7,  # All bits set except bit 3 (transformed)
        }
    )
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(True, 35, 5, 30, 2, 1, enemy_hp=48, enemy_species_id=76)
    monkeypatch.setattr(reader, "read", lambda: raw)

    identity = reader.read_wild_capture_identity()
    assert identity is not None
    assert identity.original_species_id == 76
    assert identity.displayed_species_id == 76
    assert identity.transformed is False
    assert identity.type_ids == (0, 0)
    assert identity.type_names == ("normal",)

    # Now set bit 3 with other bits also set
    memory.values[int(RamAddress.ENEMY_BATTLE_STATUS_3)] = 0x08 | 0x40
    identity2 = reader.read_wild_capture_identity()
    assert identity2 is not None
    assert identity2.transformed is True


def test_wild_capture_identity_returns_none_for_inactive_trainer_or_fainted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None returned if not live wild battle or enemy HP <= 0 without reading RAM."""
    memory = Memory(
        {
            int(RamAddress.ENEMY_SPECIES_2): 76,
            int(RamAddress.ENEMY_SPECIES): 76,
        }
    )
    reader = PokemonRedStateReader(memory)
    base_raw = RawGameState(True, 35, 5, 30, 2, 1, enemy_hp=20)

    for state in (
        replace(base_raw, battle_state=0),  # overworld / no battle
        replace(base_raw, battle_state=2),  # trainer battle
        replace(base_raw, enemy_hp=0),  # fainted opponent
        replace(base_raw, enemy_hp=None),  # missing opponent HP
    ):
        monkeypatch.setattr(reader, "read", lambda state=state: state)
        memory.reads.clear()
        assert reader.read_wild_capture_identity() is None
        assert memory.reads == []


def test_wild_capture_identity_rejects_nontransformed_display_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject display species change when transformed flag is False."""
    memory = Memory(
        {
            int(RamAddress.ENEMY_SPECIES_2): 76,  # Ditto
            int(RamAddress.ENEMY_SPECIES): 129,  # Hypno
            int(RamAddress.ENEMY_TYPE_1): 0,
            int(RamAddress.ENEMY_TYPE_2): 0,
            int(RamAddress.ENEMY_BATTLE_STATUS_3): 0x00,  # NOT transformed
        }
    )
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(True, 35, 5, 30, 2, 1, enemy_hp=20, enemy_species_id=129)
    monkeypatch.setattr(reader, "read", lambda: raw)

    with pytest.raises(SemanticStateError, match="wild capture identity differs"):
        reader.read_wild_capture_identity()

    # Direct snapshot construction also rejects
    with pytest.raises(ValueError, match="nontransformed wild capture identity species mismatch"):
        WildCaptureIdentity(76, 129, False, (0, 0))


def test_wild_capture_identity_validates_species_and_type_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmapped internal species or invalid type codes must fail closed."""
    assert 76 in GEN1_INTERNAL_SPECIES_IDS
    assert 129 in GEN1_INTERNAL_SPECIES_IDS
    assert 0 not in GEN1_INTERNAL_SPECIES_IDS
    assert 255 not in GEN1_INTERNAL_SPECIES_IDS
    assert 6 not in GEN1_TYPE_CODES  # Unused Bird type
    assert 24 in GEN1_TYPE_CODES  # Psychic

    # Invalid original species
    memory = Memory(
        {
            int(RamAddress.ENEMY_SPECIES_2): 255,
            int(RamAddress.ENEMY_SPECIES): 76,
            int(RamAddress.ENEMY_TYPE_1): 0,
            int(RamAddress.ENEMY_TYPE_2): 0,
            int(RamAddress.ENEMY_BATTLE_STATUS_3): 0,
        }
    )
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(True, 35, 5, 30, 2, 1, enemy_hp=20)
    monkeypatch.setattr(reader, "read", lambda: raw)
    with pytest.raises(SemanticStateError, match="invalid original species"):
        reader.read_wild_capture_identity()

    # Invalid type code
    memory.values[int(RamAddress.ENEMY_SPECIES_2)] = 76
    memory.values[int(RamAddress.ENEMY_TYPE_1)] = 99
    with pytest.raises(SemanticStateError, match="invalid type IDs"):
        reader.read_wild_capture_identity()


# --- Support Options Tests ---


def test_status_options_honors_live_type_names_and_blocks_thunder_wave() -> None:
    """Thunder Wave fails against live Ground type, while sleep moves remain usable."""
    party = PartyObservation(
        (
            PartyMemberObservation(
                1,
                25,
                20,
                50,
                50,
                moves=(
                    MoveObservation(86, 20),  # Thunder Wave (electric)
                    MoveObservation(95, 20),  # Hypnosis (normal sleep)
                ),
            ),
        )
    )

    # Opponent is Ditto (normal) -> Thunder Wave and Hypnosis both available
    options_ditto = red_capture_status_options(party, enemy_species_id=76)
    assert {opt.condition for opt in options_ditto} == {
        StatusCondition.PARALYSIS,
        StatusCondition.SLEEP,
    }

    # Opponent transformed into Ground type -> Thunder Wave blocked
    options_ground = red_capture_status_options(
        party,
        enemy_species_id=129,
        live_type_names=("ground",),
    )
    assert len(options_ground) == 1
    assert options_ground[0].condition is StatusCondition.SLEEP

    # Legacy caller with enemy_species_id of Ground type (e.g. Diglett 59)
    options_diglett = red_capture_status_options(party, enemy_species_id=59)
    assert len(options_diglett) == 1
    assert options_diglett[0].condition is StatusCondition.SLEEP


# --- Runtime Preparer Tests ---


class TransformWorld:
    """Mock battle world providing explicit read_wild_capture_identity."""

    def __init__(self) -> None:
        self.raw = RawGameState(
            game_started=True,
            map_id=35,
            player_x=5,
            player_y=30,
            party_count=2,
            battle_state=1,
            enemy_species_id=76,
            enemy_hp=50,
            active_party_index=0,
            active_party_hp=50,
            active_party_max_hp=50,
            party_species_ids=(48, 28),
            bag_items=((4, 20),),
        )
        self.identity = WildCaptureIdentity(
            original_species_id=76,
            displayed_species_id=76,
            transformed=False,
            type_ids=(0, 0),
        )
        self.moves = (33, 45, 0, 0)
        self.party = PartyObservation(
            (
                PartyMemberObservation(
                    1, 48, 13, 50, 50, moves=(MoveObservation(95, 10),)
                ),  # Hypnosis
                PartyMemberObservation(2, 28, 63, 200, 200, moves=(MoveObservation(57, 10),)),
            )
        )
        self.status = 0
        self.turns = 0
        self.boundaries = 0

    def read(self) -> RawGameState:
        return self.raw

    def read_wild_capture_identity(self) -> WildCaptureIdentity | None:
        if self.raw.battle_state != 1 or self.raw.enemy_hp is None or self.raw.enemy_hp <= 0:
            return None
        return self.identity

    def read_enemy_capture_status(self) -> int:
        return self.status

    def read_enemy_capture_moves(self) -> tuple[int, ...] | None:
        return self.moves

    def turn(self, *_args: object, **kwargs: object) -> SimpleNamespace:
        self.turns += 1
        first = self.party.members[0]
        self.party = replace(
            self.party,
            members=(
                replace(first, moves=(replace(first.moves[0], current_pp=10 - self.turns),)),
                self.party.members[1],
            ),
        )
        return SimpleNamespace(move_executed=True)


def setup_transform_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TransformWorld, RedCaptureStatusPreparer]:
    world = TransformWorld()
    monkeypatch.setattr(
        runtime, "PokemonRedPartyReader", lambda _: SimpleNamespace(read=lambda: world.party)
    )
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", world.turn)
    monkeypatch.setattr(
        runtime,
        "advance_battle_to_policy_boundary",
        lambda *_args, **_kwargs: setattr(world, "boundaries", world.boundaries + 1),
    )

    def switch(
        _actions: object, _reader: object, _emulator: object, index: int, **_kwargs: object
    ) -> None:
        world.raw = replace(world.raw, active_party_index=index)

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    preparer = RedCaptureStatusPreparer(object(), object(), world)
    return world, preparer


def test_status_runtime_latches_original_identity_and_accepts_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preparer latches original species 76 and allows opponent to transform into Hypno 129."""
    world, prepare = setup_transform_runtime(monkeypatch)

    # First call: untransformed Ditto
    assert prepare() is True
    assert prepare.latched_original_species_id == 76
    assert world.turns == 3

    # Opponent transforms into Hypno 129
    world.raw = replace(world.raw, enemy_species_id=129)
    world.identity = WildCaptureIdentity(
        original_species_id=76,
        displayed_species_id=129,
        transformed=True,
        type_ids=(24, 24),
    )

    # Second call across balls for same preparer: latched original identity 76 retained
    assert prepare() is True
    assert prepare.latched_original_species_id == 76


def test_status_runtime_rejects_target_change_even_when_transformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If original species changes, preparer raises RedCaptureStatusError even if transformed."""
    world, prepare = setup_transform_runtime(monkeypatch)
    assert prepare() is True
    assert prepare.latched_original_species_id == 76

    # Opponent changed to a different Pokémon (original species 15 Pidgey, displayed 129)
    world.raw = replace(world.raw, enemy_species_id=129)
    world.identity = WildCaptureIdentity(
        original_species_id=15,
        displayed_species_id=129,
        transformed=True,
        type_ids=(24, 24),
    )

    with pytest.raises(RedCaptureStatusError, match="target, party or bag"):
        prepare()


@pytest.mark.parametrize(
    "change",
    [
        {"enemy_hp": 49},
        {"party_species_ids": (48,)},
        {"bag_items": ((4, 19),)},
    ],
)
def test_status_runtime_retains_hp_party_and_bag_guards_with_transformed_opponent(
    monkeypatch: pytest.MonkeyPatch,
    change,
) -> None:
    """HP change, party change, or bag change during transform must be rejected."""
    world, prepare = setup_transform_runtime(monkeypatch)

    # Legitimate Transform: 76 -> 129, HP 50 preserved
    world.raw = replace(world.raw, enemy_species_id=129)
    world.identity = WildCaptureIdentity(
        original_species_id=76,
        displayed_species_id=129,
        transformed=True,
        type_ids=(24, 24),
    )

    def corrupt_drift(*args: object, **kwargs: object) -> SimpleNamespace:
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, **change)
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", corrupt_drift)
    with pytest.raises(RedCaptureStatusError, match="target, party or bag"):
        prepare()


def test_status_runtime_rechecks_live_types_after_switch_avoiding_wrong_status_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transformed Porygon's Conversion must not fall back to its Normal catalog type."""
    world, prepare = setup_transform_runtime(monkeypatch)
    # Helper in slot 1 has Thunder Wave (electric move 86)
    world.party = PartyObservation(
        (
            PartyMemberObservation(
                1, 25, 20, 50, 50, moves=(MoveObservation(86, 20),)
            ),  # Pikachu Thunder Wave
            PartyMemberObservation(
                2, 28, 63, 200, 200, moves=(MoveObservation(57, 10),)
            ),  # Blastoise active
        )
    )
    world.raw = replace(world.raw, active_party_index=1, enemy_species_id=170)
    world.identity = WildCaptureIdentity(76, 170, True, (0, 0))

    # Conversion changes live typing in reply to the switch; appearance stays Porygon.
    def switch_with_transform(
        _actions: object, _reader: object, _emulator: object, index: int, **_kwargs: object
    ) -> None:
        world.raw = replace(world.raw, active_party_index=index, enemy_species_id=170)
        world.identity = WildCaptureIdentity(
            original_species_id=76,
            displayed_species_id=170,
            transformed=True,
            type_ids=(4, 4),  # Ground type!
        )

    monkeypatch.setattr(runtime, "switch_active_battler", switch_with_transform)

    def forbidden_move(*_args: object, **_kwargs: object) -> SimpleNamespace:
        pytest.fail("Thunder Wave must NOT be used on a newly transformed Ground opponent")

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", forbidden_move)

    # Prepare executes: switches to helper, rechecks live types, detects Ground, breaks safely!
    assert prepare() is True
    # Zero move turns executed on Ground opponent
    assert world.turns == 0


def test_status_runtime_rechecks_escape_moves_after_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If opponent transforms during switch and gains an escape move, bypass immediately."""
    world, prepare = setup_transform_runtime(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1)

    def switch_with_teleport(
        _actions: object, _reader: object, _emulator: object, index: int, **_kwargs: object
    ) -> None:
        world.raw = replace(world.raw, active_party_index=index, enemy_species_id=148)  # Abra
        world.identity = WildCaptureIdentity(
            original_species_id=76,
            displayed_species_id=148,
            transformed=True,
            type_ids=(24, 24),
        )
        world.moves = (100, 0, 0, 0)  # Teleport (escape move)

    monkeypatch.setattr(runtime, "switch_active_battler", switch_with_teleport)

    assert prepare() is True
    assert prepare.bypassed_for_escape is True
    assert world.turns == 0


def test_status_runtime_retains_attempt_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preparer strictly bounds attempts across calls; cannot exceed maximum_attempts."""
    world, prepare = setup_transform_runtime(monkeypatch)
    assert prepare() is True
    assert prepare.attempts == 3
    assert world.turns == 3

    # Call again with attempts exhausted
    assert prepare() is True
    assert prepare.attempts == 3
    assert world.turns == 3  # No extra turns taken


def test_ditto_transforms_into_selected_sleep_helper_then_gets_observed_sleep(monkeypatch):
    world, prepare = setup_transform_runtime(monkeypatch)
    world.party = replace(world.party, members=(
        replace(world.party.members[0], species_id=129), world.party.members[1],
    ))
    world.raw = replace(world.raw, party_species_ids=(129, 28), active_party_index=1)
    switches = []

    def switch(_actions, _reader, _emulator, index, **_kwargs):
        switches.append(index)
        world.raw = replace(world.raw, active_party_index=index)
        if index == 0:
            world.raw = replace(world.raw, enemy_species_id=129)
            world.identity = WildCaptureIdentity(76, 129, True, (24, 24))

    def sleep(*args, **kwargs):
        outcome = world.turn(*args, **kwargs)
        world.status = 3
        return outcome

    monkeypatch.setattr(runtime, 'switch_active_battler', switch)
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', sleep)
    assert prepare() is True
    assert switches == [0, 1]
    assert world.turns == 1
    assert prepare.reports[0]['status_success'] is True
    assert prepare.reports[0]['original_species_id'] == 76
    assert prepare.reports[0]['displayed_species_id'] == 129
    assert prepare.reports[0]['transformed'] is True


def test_transform_reply_to_status_move_rechecks_escape_before_another_attempt(monkeypatch):
    world, prepare = setup_transform_runtime(monkeypatch)

    def transform_reply(*args, **kwargs):
        outcome = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, enemy_species_id=148)
        world.identity = WildCaptureIdentity(76, 148, True, (24, 24))
        world.moves = (100, 0, 0, 0)
        return outcome

    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', transform_reply)
    assert prepare() is True
    assert world.turns == 1
    assert prepare.bypassed_for_escape is True
    assert prepare.reports[0]['status_success'] is False


@pytest.mark.parametrize('types', [(), ('invalid',), ('ground',)*3, 'ground'])
def test_explicit_live_types_cannot_silently_disable_immunity(types):
    with pytest.raises(ValueError, match='live capture types'):
        red_capture_status_options(PartyObservation(()), live_type_names=types)
