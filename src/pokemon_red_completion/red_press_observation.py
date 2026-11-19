"""Read-only per-press cartridge observations for later world-model learning.

Each recorded press can carry a compact view of what the cartridge showed just
before and just after it: map, position, facing, movement mode, battle and menu
state, lead/enemy HP, money, badges, plus the full 20x18 screen tile map after
the press.  Reading Work RAM never ticks the emulator or presses a button, so it
cannot change a decision, an input or a frame.  These records are observation
data only: no runtime policy reads them, and nothing is fitted from them here.

Addresses are the verified pret/pokered symbols already used by the observer
(``RamAddress``); they are valid only behind the repository's ROM fingerprint gate.
"""

from __future__ import annotations

import base64
import zlib

from .observation import RamAddress

PRESS_OBSERVATION_SCHEMA = "pokemon.red.native-press-observation.v1"
PRESS_OBSERVATION_KIND = "red_native_press_observation"
# Sealed records refuse any text containing "/" (path guard), hence these spellings.
ADDRESS_TABLE = "pret-pokered@1e96034092686d006e863cace09e87273051a3d8"
SCREEN_TILES = (RamAddress.TILE_MAP, 20 * 18)

# (field, address, byte count); multi-byte values are big-endian like the cartridge.
VIEW_FIELDS = (
    ("map", RamAddress.CURRENT_MAP, 1),
    ("x", RamAddress.PLAYER_X, 1),
    ("y", RamAddress.PLAYER_Y, 1),
    ("facing", RamAddress.PLAYER_FACING_DIRECTION, 1),
    ("moving_direction", RamAddress.PLAYER_MOVING_DIRECTION, 1),
    ("walk_bike_surf", RamAddress.WALK_BIKE_SURF_STATE, 1),
    ("tile_in_front", RamAddress.TILE_IN_FRONT_OF_PLAYER, 1),
    ("walk_counter", RamAddress.WALK_COUNTER, 1),
    ("in_battle", RamAddress.IS_IN_BATTLE, 1),
    ("battle_result", RamAddress.BATTLE_RESULT, 1),
    ("joy_ignore", RamAddress.JOY_IGNORE, 1),
    ("menu_item", RamAddress.CURRENT_MENU_ITEM, 1),
    ("max_menu_item", RamAddress.MAX_MENU_ITEM, 1),
    ("menu_top_y", RamAddress.TOP_MENU_ITEM_Y, 1),
    ("menu_top_x", RamAddress.TOP_MENU_ITEM_X, 1),
    ("status_flags_5", RamAddress.STATUS_FLAGS_5, 1),
    ("movement_flags", RamAddress.MOVEMENT_FLAGS, 1),
    ("party_count", RamAddress.PARTY_COUNT, 1),
    ("lead_hp", RamAddress.PARTY_MON_1_HP, 2),
    ("enemy_species", RamAddress.ENEMY_SPECIES, 1),
    ("enemy_hp", RamAddress.ENEMY_HP, 2),
    ("money_bcd", RamAddress.PLAYER_MONEY, 3),
    ("badges", RamAddress.OBTAINED_BADGES, 1),
    ("bag_items", RamAddress.NUM_BAG_ITEMS, 1),
    ("repel_steps", RamAddress.REPEL_REMAINING_STEPS, 1),
)


def _read(reader, address: int, count: int) -> bytes:
    return bytes(reader(int(address) + offset) for offset in range(count))


# Compact on disk: each view is the hex of the raw bytes in VIEW_FIELDS order
# (about 60 characters instead of ~600 for named JSON); decode_view restores names.
VIEW_LAYOUT = "pokemon.red.press-view.v1"
VIEW_BYTES = sum(count for _, _, count in VIEW_FIELDS)


def read_view(reader) -> str | None:
    """Return the raw view as hex (VIEW_FIELDS order), or None if RAM is unreadable."""
    try:
        return b"".join(_read(reader, address, count) for _, address, count in VIEW_FIELDS).hex()
    except (TypeError, ValueError, AttributeError):
        return None


def decode_view(encoded: str) -> dict[str, object]:
    """Named fields for offline analysis; money stays BCD hex like the cartridge stores it."""
    raw = bytes.fromhex(encoded)
    if len(raw) != VIEW_BYTES:
        raise ValueError("press observation view has the wrong size")
    view: dict[str, object] = {}
    position = 0
    for name, _, count in VIEW_FIELDS:
        chunk = raw[position : position + count]
        position += count
        view[name] = chunk.hex() if name == "money_bcd" else int.from_bytes(chunk, "big")
    return view


def read_screen(reader) -> str | None:
    """Return the screen tile map as urlsafe-base64(zlib(360 bytes)), or None if unreadable."""
    try:
        raw = _read(reader, *SCREEN_TILES)
    except (TypeError, ValueError, AttributeError):
        return None
    return base64.urlsafe_b64encode(zlib.compress(raw, 6)).decode("ascii")


def decode_screen(encoded: str) -> bytes:
    """Inverse of :func:`read_screen` for offline analysis (20 columns x 18 rows)."""
    raw = zlib.decompress(base64.urlsafe_b64decode(encoded.encode("ascii")))
    if len(raw) != SCREEN_TILES[1]:
        raise ValueError("press observation screen has the wrong size")
    return raw


def press_observation(*, declaration, ordinal, action, before_frame, after_frame,
                      succeeded, before, after, screen_after) -> dict[str, object]:
    return dict(
        schema=PRESS_OBSERVATION_SCHEMA,
        address_table=ADDRESS_TABLE,
        view_layout=VIEW_LAYOUT,
        declaration=declaration,
        ordinal=ordinal,
        action=action.kind.value,
        value=action.value,
        repeat=action.repeat,
        before_frame=before_frame,
        after_frame=after_frame,
        succeeded=succeeded,
        before=before,
        after=after,
        screen_after=screen_after,
        observation_only=True,
        automatic_fit=False,
    )
