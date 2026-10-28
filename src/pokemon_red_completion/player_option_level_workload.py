"""Portable measured XP work, with no identity or promised completion cost."""

from dataclasses import asdict, dataclass

LEVEL_WORKLOAD_SCHEMA = "pokemon.core.option-level-workload.v1"
LEVEL_WORKLOAD_NAMES = ("present", "current_level", "target_level", "level_gain", "remaining_xp")


@dataclass(frozen=True, slots=True)
class OptionLevelWorkload:
    current_level: int
    target_level: int
    remaining_xp: int

    def __post_init__(self):
        if (type(self.current_level) is not int or type(self.target_level) is not int
                or not 1 <= self.current_level < self.target_level <= 100):
            raise ValueError("level workload requires a bounded actual level-up")
        if type(self.remaining_xp) is not int or not 1 <= self.remaining_xp <= 2_000_000:
            raise ValueError("level workload requires observed positive remaining XP")

    def vector(self):
        return (1., self.current_level / 100, self.target_level / 100,
                (self.target_level - self.current_level) / 100, self.remaining_xp / 2_000_000)

    def public_dict(self):
        return dict(schema=LEVEL_WORKLOAD_SCHEMA, **asdict(self))

    @classmethod
    def from_public(cls, document):
        names = set(cls.__dataclass_fields__)
        if (not isinstance(document, dict) or set(document) != names | {"schema"}
                or document['schema'] != LEVEL_WORKLOAD_SCHEMA):
            raise ValueError("level workload document differs")
        return cls(**{name: document[name] for name in names})


def level_workload_feature_names():
    return tuple("level_workload." + name for name in LEVEL_WORKLOAD_NAMES)


def level_workload_vector(workload):
    return (0.,) * len(LEVEL_WORKLOAD_NAMES) if workload is None else workload.vector()
