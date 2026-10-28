"""Exact native completion proofs for the two admitted eventless story fights."""

from .observation import MapId


def admitted_eventless_identity(identity):
    return identity in {(242, 42, 1), (242, 42, 2), (242, 42, 3), (230, 30, 7)}


def eventless_battle_ready(reader, identity):
    raw = reader.read()
    if identity == (230, 30, 7):
        return raw.map_id == MapId.GAME_CORNER and any(
            o.sprite_index == 11 and o.picture_id == 24 for o in reader.read_current_map_objects()
        )
    return identity in {(242, 42, 1), (242, 42, 2), (242, 42, 3)} and (
        raw.map_id == MapId.SS_ANNE_2F and reader.read_ss_anne_rival_script() == 2
    )


def eventless_battle_finished(reader, identity, *, won):
    raw = reader.read()
    if identity == (230, 30, 7):
        # Native win hides the poster guard after his departure. Loss instead
        # returns to the independently checked last blackout Center.
        if not won:
            return raw.map_id != MapId.GAME_CORNER
        return raw.map_id == MapId.GAME_CORNER and not any(
            o.sprite_index == 11 for o in reader.read_current_map_objects()
        )
    return identity in {(242, 42, 1), (242, 42, 2), (242, 42, 3)} and (
        reader.read_ss_anne_rival_script() == (4 if won else 0)
    )
