"""Explicit local completion, never inferred from an unavailable goal menu."""

from dataclasses import asdict, dataclass
from hashlib import sha256

from .provenance import canonical_sha256
from .red_goal_skills import _raw_party_fully_restored


@dataclass(frozen=True)
class PlayerCurriculumCompletion:
    curriculum_sha256: str
    state_sha256: str

    def public_dict(self):
        return dict(
            schema="pokemon.red.player-curriculum-completion.v1",
            **asdict(self),
            model_queries=0,
            full_game_completion=False,
        )


@dataclass(frozen=True)
class NativePlayerCurriculum:
    """Frozen objectives and specimen-level targets, plus full-party restoration."""

    objectives: tuple[str, ...]
    target_levels: tuple[tuple[str, int], ...]

    def __post_init__(self):
        if (
            not isinstance(self.objectives, tuple)
            or not self.objectives
            or any(not isinstance(x, str) or not x for x in self.objectives)
            or len(set(self.objectives)) != len(self.objectives)
        ):
            raise ValueError("curriculum needs distinct declared objectives")
        if (
            not isinstance(self.target_levels, tuple)
            or not self.target_levels
            or any(
                not isinstance(x, tuple)
                or len(x) != 2
                or not isinstance(x[0], str)
                or not x[0]
                or type(x[1]) is not int
                or not 1 <= x[1] <= 100
                for x in self.target_levels
            )
            or len({x[0] for x in self.target_levels}) != len(self.target_levels)
        ):
            raise ValueError("curriculum needs distinct declared specimen level targets")

    def completion(self, boundary):
        lesson = boundary.lesson_snapshot
        members = {m["specimen_ref"]: m for m in lesson["party"]}
        if (
            not set(self.objectives) <= set(lesson["completed_objectives"])
            or any(
                ref not in members or members[ref]["level"] < level
                for ref, level in self.target_levels
            )
            or lesson["in_battle"]
            or not boundary.observation.input_ready
            or not _raw_party_fully_restored(boundary.observation.raw)
        ):
            return None
        return PlayerCurriculumCompletion(
            canonical_sha256(asdict(self)), sha256(boundary.state).hexdigest()
        )


@dataclass(frozen=True)
class NativeRegionalCurriculum(NativePlayerCurriculum):
    """Declared intermediate travel endpoint, not completion of its story goal."""

    destination_map: int

    def __post_init__(self):
        super().__post_init__()
        if type(self.destination_map) is not int or not 0 <= self.destination_map <= 255:
            raise ValueError("regional curriculum requires a declared map")

    def completion(self, boundary):
        if boundary.observation.raw.map_id != self.destination_map:
            return None
        return super().completion(boundary)


@dataclass(frozen=True)
class NativeResourceCurriculum(NativePlayerCurriculum):
    """Resource/acquisition completion in addition to the original local contract.

    Required species are actual local owned flags, never a merged/global ledger.
    Stock is terminal stock, not a requirement to buy something already possessed.
    The selected goal's verifier independently proves its purchase/capture outcome.
    """

    required_species: tuple[str, ...] = ()
    required_stock: tuple[tuple[int, int], ...] = ()

    def __post_init__(self):
        super().__post_init__()
        if (
            type(self.required_species) is not tuple
            or any(not isinstance(s, str) or not s for s in self.required_species)
            or len(set(self.required_species)) != len(self.required_species)
            or type(self.required_stock) is not tuple
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not int
                or not 1 <= row[0] <= 255
                or type(row[1]) is not int
                or not 1 <= row[1] <= 99
                for row in self.required_stock
            )
            or len(dict(self.required_stock)) != len(self.required_stock)
            or not (self.required_species or self.required_stock)
        ):
            raise ValueError("resource curriculum needs explicit valid species/stock requirements")

    def completion(self, boundary):
        raw = boundary.observation.raw
        bag = raw.bag_items
        if bag is None:
            return None
        inventory = dict(bag)
        if (
            len(inventory) != len(bag)
            or any(type(n) is not int or not 1 <= n <= 99 for n in inventory.values())
            or any(inventory.get(item, 0) < n for item, n in self.required_stock)
            or not set(self.required_species)
            <= set(boundary.observation.collection_observation.owned_species)
        ):
            return None
        return super().completion(boundary)
