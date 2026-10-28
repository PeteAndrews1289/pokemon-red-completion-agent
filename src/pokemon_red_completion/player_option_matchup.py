"""Explicit prospective battle measurements, never a victory or survival claim."""
from dataclasses import dataclass
from math import isfinite

MATCHUP_SCHEMA = 'pokemon.player.option-matchup.v1'
MATCHUP_NAMES = (
    'present', 'own_members_known', 'own_stats_known', 'opposition_roster_known',
    'moves_and_pp_known', 'declared_combat_fraction', 'living_combat_fraction', 'opponent_fraction',
    'own.attack.minimum', 'own.attack.mean', 'own.defense.minimum', 'own.defense.mean',
    'own.speed.minimum', 'own.speed.mean', 'own.special.minimum', 'own.special.mean',
    'own.max_hp.minimum', 'own.max_hp.mean',
    'opposition.available_offensive_power.minimum', 'opposition.available_offensive_power.mean',
    'opposition.available_type_margin.minimum', 'opposition.available_type_margin.mean',
    'opposition.available_defensive_resistance.minimum', 'opposition.available_defensive_resistance.mean',
    'own.usable_move_fraction.minimum', 'own.usable_move_fraction.mean',
    'own.usable_damaging_move_pp_fraction.minimum', 'own.usable_damaging_move_pp_fraction.mean',
)

@dataclass(frozen=True)
class OptionMatchup:
    """Identity-free, explicitly masked measurements; implicit present is one."""
    values: tuple[float, ...]

    def __post_init__(self):
        if (type(self.values) is not tuple or len(self.values) != 27
                or any(type(v) not in (int, float) or not isfinite(v) for v in self.values)):
            raise ValueError('matchup requires 27 finite immutable measurements')
        d = dict(zip(MATCHUP_NAMES[1:], self.values, strict=True))
        for name, value in d.items():
            lower = -1 if 'type_margin' in name or 'defensive_resistance' in name else 0
            if not lower <= value <= 1:
                raise ValueError('matchup measurement outside declared bounds')
        for name in MATCHUP_NAMES[1:5]:
            if d[name] not in (0, 1):
                raise ValueError('matchup knownness must be binary')
        for name in MATCHUP_NAMES[5:8]:
            if abs(d[name] * 6 - round(d[name] * 6)) > 1e-12:
                raise ValueError('matchup count must describe at most six members')
        if d['living_combat_fraction'] > d['declared_combat_fraction']:
            raise ValueError('living combat count exceeds declared roles')
        if not d['own_members_known'] and any(d[n] for n in (
                'own_stats_known','moves_and_pp_known','declared_combat_fraction','living_combat_fraction')):
            raise ValueError('unknown own roster cannot invent observations')
        if not d['own_stats_known'] and any(d[n] for n in MATCHUP_NAMES[8:18]):
            raise ValueError('unknown actual stats must remain masked')
        if not d['opposition_roster_known']:
            if any(d[n] for n in (MATCHUP_NAMES[7], *MATCHUP_NAMES[18:24])):
                raise ValueError('unknown opposition must remain masked')
        elif d['opponent_fraction'] == 0:
            raise ValueError('known opposition requires a nonempty quote')
        if not d['moves_and_pp_known'] and any(d[n] for n in (*MATCHUP_NAMES[18:22], *MATCHUP_NAMES[24:])):
            raise ValueError('unknown moves and PP must remain masked')
        if not d['living_combat_fraction'] and any(d[n] for n in MATCHUP_NAMES[8:]):
            raise ValueError('empty living roster has known zero capacity')
        for i in range(8, 28, 2):
            if d[MATCHUP_NAMES[i]] > d[MATCHUP_NAMES[i+1]] + 1e-12:
                raise ValueError('minimum exceeds mean')
        object.__setattr__(self, 'values', tuple(float(v) for v in self.values))

    def public_dict(self):
        return dict(schema=MATCHUP_SCHEMA, names=list(MATCHUP_NAMES[1:]), values=list(self.values))

    @classmethod
    def from_public(cls, document):
        if (type(document) is not dict or set(document) != {'schema','names','values'}
                or document['schema'] != MATCHUP_SCHEMA or document['names'] != list(MATCHUP_NAMES[1:])
                or type(document['values']) is not list):
            raise ValueError('matchup public contract differs')
        return cls(tuple(document['values']))


def matchup_feature_names():
    return tuple('matchup.' + name for name in MATCHUP_NAMES)


def matchup_vector(matchup):
    if matchup is None:
        return (0.,) * len(MATCHUP_NAMES)
    if not isinstance(matchup, OptionMatchup):
        raise TypeError('typed matchup required')
    matchup.__post_init__()
    return (1., *matchup.values)
