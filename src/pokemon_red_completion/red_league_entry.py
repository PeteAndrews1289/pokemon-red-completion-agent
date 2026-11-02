"""Observe the cartridge-owned lobby reset before a planned League entry.

Forecasting events is not permission to write them. This route observer requires
the actual settled lobby to match the projected event array before room entry.
"""
from dataclasses import dataclass

from .observation import MapId
from .route_executor import RouteExecutionError


def forecast_league_entry_events(raw, *, development_retry_reentry=False,
                                 challenge_started=None):
    """Read-only forecast of a declared native lobby reset from Indigo outside.

    This is not current completion evidence. The existing entry observer must
    still verify the actual cartridge reset before allowing the first room.
    """
    if type(development_retry_reentry) is not bool:
        raise TypeError("League retry permission must be an explicit boolean")
    if challenge_started is not None and type(challenge_started) is not bool:
        raise TypeError("League reset latch must be an observed boolean")
    if (not development_retry_reentry or raw.map_id != MapId.INDIGO_PLATEAU
            or raw.battle_state or raw.event_flags is None or challenge_started is None):
        return raw.event_flags
    from .red_league_funding import projected_fresh_league_events

    return projected_fresh_league_events(
        raw.event_flags, challenge_started=challenge_started,
    )[0]


@dataclass
class LeagueLobbyResetObserver:
    delegate: object
    reader: object
    expected_events: bytes
    verified: bool = False

    def observe(self):
        current = self.delegate.observe()
        if current.map_id == MapId.INDIGO_PLATEAU_LOBBY and current.ready:
            if (self.reader.read().event_flags != self.expected_events
                    or self.reader.read_league_challenge_started()):
                raise RouteExecutionError("actual lobby reset differs from projected entry events")
            self.verified = True
        if current.map_id == MapId.LORELEIS_ROOM and not self.verified:
            raise RouteExecutionError("room entry preceded verified lobby reset")
        return current
