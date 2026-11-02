"""Teacher-only, revision-pinned gift mechanics fixture; never a policy action.

The caller retains a fresh opening origin before this intervention. Native warp
loading and GivePokemon still execute in the cartridge. Artificial story/party
facts cannot earn completion credit or ordinary training/economy admission.
"""

from .observation import EventFlag, MapId, RamAddress
from .red_safari_training_setup import RED_ROM_SHA256

# Pinned pokered SilphCo11FTeamRocketLeavesScript and toggle_constants.asm.
# Removed flags use one=hidden. Reproduce the story's changes, not every NPC:
# the gift scientist, items and unrelated trainers keep their original state.
_LIBERATION_HIDE = (
    *range(0x0A, 0x11), 0x17, 0x18,
    *range(0x8A, 0x90), *range(0x91, 0x94), *range(0x97, 0x9B),
    *range(0x9E, 0xA1), *range(0xA3, 0xA7), *range(0xAB, 0xB3),
    *range(0xB7, 0xBA),
)
_LIBERATION_SHOW = tuple(range(0x11, 0x17))


def prepare_isolated_gift(memory, *, rom_sha256, isolated_training_setup,
                          controller_released, battle_state, full_party=False,
                          approach_fixture=False):
    if (rom_sha256 != RED_ROM_SHA256 or isolated_training_setup is not True
            or controller_released is not True or type(battle_state) is not int
            or battle_state != 0 or type(full_party) is not bool
            or type(approach_fixture) is not bool):
        raise ValueError("gift setup requires isolated released Red control")
    expected = {
        int(RamAddress.CURRENT_MAP): int(MapId.OAKS_LAB),
        int(RamAddress.OAKS_LAB_SCRIPT): 10,
        int(RamAddress.PARTY_COUNT): 1,
        0xD3AE: 2, 0xD365: int(MapId.PALLET_TOWN),
        **{0xD3AF + i: b for i, b in enumerate((11, 4, 2, 255, 11, 5, 2, 255))},
    }
    if (any(int(memory[a]) != b for a, b in expected.items())
            or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("fresh gift setup boundary differs")
    changes = {
        int(RamAddress.OAKS_LAB_SCRIPT): 18,
        0xD365: int(MapId.SAFFRON_CITY),
        0xD3B1: 4, 0xD3B2: int(MapId.SILPH_CO_7F),
        0xD3B5: 4, 0xD3B6: int(MapId.SILPH_CO_7F),
    }
    for flag in (EventFlag.BEAT_SILPH_CO_GIOVANNI, EventFlag.BEAT_SILPH_CO_RIVAL):
        a = int(RamAddress.EVENT_FLAGS) + int(flag) // 8
        changes[a] = changes.get(a, int(memory[a])) | 1 << (int(flag) % 8)
    if approach_fixture:
        # Native post-story entrance/door prerequisites, not a route repair.
        # 0x703 is the second 3F trainer, adjacent to the gift access corridor.
        for flag in (EventFlag.RESCUED_MR_FUJI, EventFlag.RESCUED_MR_FUJI_WORLD,
                     EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2,
                     EventFlag.BEAT_SILPH_CO_3F_TRAINER_0, 0x703):
            a = int(RamAddress.EVENT_FLAGS) + int(flag) // 8
            changes[a] = changes.get(a, int(memory[a])) | 1 << (int(flag) % 8)
        changes.update({0xD3B1: 0, 0xD3B2: int(MapId.SILPH_CO_1F),
                        0xD3B5: 0, 0xD3B6: int(MapId.SILPH_CO_1F)})
        for indices, hidden in ((_LIBERATION_HIDE, True), (_LIBERATION_SHOW, False)):
            for index in indices:
                address = int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + index // 8
                prior = changes.get(address, int(memory[address]))
                mask = 1 << (index % 8)
                changes[address] = prior | mask if hidden else prior & ~mask
    if full_party:
        # Disclosed copies of this fixture's own starter, including OT/nickname.
        # Not a native capture, learner label, or earned-save modification.
        species = int(memory[int(RamAddress.PARTY_SPECIES)])
        if species in (0, 255):
            raise ValueError("fixture starter is invalid")
        changes[int(RamAddress.PARTY_COUNT)] = 6
        for slot in range(1, 6):
            changes[int(RamAddress.PARTY_SPECIES) + slot] = species
            for base, stride in ((int(RamAddress.PARTY_MON_1), 44),
                                 (0xD273, 11), (0xD2B5, 11)):
                for offset in range(stride):
                    changes[base + slot * stride + offset] = int(memory[base + offset])
        changes[int(RamAddress.PARTY_SPECIES) + 6] = 255
    receipt = tuple(dict(address=a, before=int(memory[a]), after=b)
                    for a, b in sorted(changes.items()))
    for row in receipt:
        memory[row["address"]] = row["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in receipt):
        raise ValueError("gift fixture readback failed; retain terminal")
    return receipt


def add_isolated_gift_history(memory, *, rom_sha256, isolated_training_setup,
                             controller_released, battle_state, registered_species):
    """Disclosed fixture history; never award these setup flags as learned gains."""
    if (rom_sha256 != RED_ROM_SHA256 or isolated_training_setup is not True
            or controller_released is not True or type(battle_state) is not int
            or battle_state != 0 or int(memory[int(RamAddress.CURRENT_MAP)]) != MapId.SILPH_CO_1F
            or not isinstance(registered_species, tuple)
            or any(type(s) is not int or not 1 <= s <= 151 or s == 131 for s in registered_species)
            or len(set(registered_species)) != len(registered_species)
            or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("gift history requires an untouched isolated approach fixture")
    changes = {}
    for base in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
        for s in registered_species:
            a = base + (s - 1) // 8
            changes[a] = changes.get(a, int(memory[a])) | 1 << ((s - 1) % 8)
    receipt = tuple(dict(address=a, before=int(memory[a]), after=v)
                    for a, v in sorted(changes.items()))
    for r in receipt:
        memory[r["address"]] = r["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in receipt):
        raise ValueError("gift history readback failed")
    return receipt
