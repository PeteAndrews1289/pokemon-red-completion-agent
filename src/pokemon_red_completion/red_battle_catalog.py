"""Pinned Pokémon Red mechanics catalog for transferable battle features.

Provenance
----------
The tables below are derived from pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8`` and only from these source files:

* ``constants/pokemon_constants.asm``
* ``constants/type_constants.asm``
* ``data/moves/moves.asm``
* ``data/pokemon/base_stats/*.asm``
* ``data/types/type_matchups.asm``
* ``engine/battle/core.asm`` (Quick Attack and Counter priority)

They contain mechanics metadata only. No ROM bytes, saves, recordings, or
private filesystem data are present.
"""

from __future__ import annotations

import re
from types import MappingProxyType

from pokemon_red_completion.battle_semantics import (
    POKEMON_TYPES,
    BattleFeatureError,
    MoveMechanics,
    SpeciesMechanics,
)

PRET_POKERED_COMMIT = "1e96034092686d006e863cace09e87273051a3d8"
POKEMON_RED_REF_NAMESPACE = "pokemon.red.gb.us.rev0"

_REF_PATTERN = re.compile(rf"^{re.escape(POKEMON_RED_REF_NAMESPACE)}:(move|species):([0-9]{{3}})$")
_PHYSICAL_TYPES = frozenset(
    {"normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost"}
)
_SPECIAL_TYPES = frozenset({"fire", "water", "grass", "electric", "psychic", "ice", "dragon"})
_DAMAGING_ZERO_POWER_EFFECTS = frozenset({"SPECIAL_DAMAGE_EFFECT", "BIDE_EFFECT"})


class RedBattleCatalogError(BattleFeatureError):
    """Raised when a Red reference or mechanics query fails closed."""


class PokemonRedBattleCatalog:
    """Immutable resolver for the pinned US Red revision-zero mechanics."""

    __slots__ = ()

    @property
    def move_count(self) -> int:
        return len(_MOVE_BY_ID)

    @property
    def species_count(self) -> int:
        return len(_SPECIES_BY_ID)

    def resolve_species(self, species_ref: str, /) -> SpeciesMechanics:
        identifier = _parse_ref(species_ref, expected_kind="species")
        try:
            return _SPECIES_BY_ID[identifier]
        except KeyError as error:
            raise RedBattleCatalogError("unknown Pokémon Red species reference") from error

    def resolve_move(self, move_ref: str, /) -> MoveMechanics:
        identifier = _parse_ref(move_ref, expected_kind="move")
        try:
            return _MOVE_BY_ID[identifier]
        except KeyError as error:
            raise RedBattleCatalogError("unknown Pokémon Red move reference") from error

    def type_effectiveness(
        self,
        attacking_type: str,
        defending_types: tuple[str, ...],
        /,
    ) -> float:
        if attacking_type not in POKEMON_TYPES:
            raise RedBattleCatalogError("attacking type is unsupported")
        if not isinstance(defending_types, tuple) or not 1 <= len(defending_types) <= 2:
            raise RedBattleCatalogError("defending_types must contain one or two types")
        if any(type_name not in POKEMON_TYPES for type_name in defending_types):
            raise RedBattleCatalogError("defending type is unsupported")

        # Red stores monotypes by repeating the same byte. Treat that as one
        # defensive type so STAB/type damage is not accidentally squared.
        unique_defenders = tuple(dict.fromkeys(defending_types))
        multiplier = 1.0
        for defending_type in unique_defenders:
            multiplier *= _TYPE_EFFECTS.get((attacking_type, defending_type), 1.0)
        return multiplier


def pokemon_red_move_ref(identifier: int) -> str:
    """Return the stable semantic reference for one nonzero Red move ID."""

    if type(identifier) is not int or not 1 <= identifier <= 0xFF:  # noqa: E721
        raise RedBattleCatalogError("Pokémon Red move identifier must be a nonzero byte")
    return f"{POKEMON_RED_REF_NAMESPACE}:move:{identifier:03d}"


def _parse_ref(value: object, *, expected_kind: str) -> int:
    if not isinstance(value, str):
        raise RedBattleCatalogError("Pokémon Red reference must be a string")
    match = _REF_PATTERN.fullmatch(value)
    if match is None or match.group(1) != expected_kind:
        raise RedBattleCatalogError(f"malformed Pokémon Red {expected_kind} reference")
    return int(match.group(2))


def _move_category(*, type_name: str, power: int, effect: str) -> str:
    if power == 0 and effect not in _DAMAGING_ZERO_POWER_EFFECTS:
        return "status"
    if type_name in _PHYSICAL_TYPES:
        return "physical"
    if type_name in _SPECIAL_TYPES:
        return "special"
    raise AssertionError(f"unclassified move type: {type_name}")


def _effect_flags(effect: str, *, identifier: int) -> frozenset[str]:
    flags: set[str] = set()
    if any(
        token in effect for token in ("SLEEP", "POISON", "BURN", "FREEZE", "PARALYZE", "TWINEEDLE")
    ):
        flags.add("status")
    if "_UP1_EFFECT" in effect or "_UP2_EFFECT" in effect or effect == "FOCUS_ENERGY_EFFECT":
        flags.add("boost")
    if "_DOWN1_EFFECT" in effect or "_DOWN2_EFFECT" in effect or "_DOWN_SIDE_EFFECT" in effect:
        flags.add("debuff")
    if effect in {"RECOIL_EFFECT", "JUMP_KICK_EFFECT"}:
        flags.add("recoil")
    if effect in {"CHARGE_EFFECT", "FLY_EFFECT"}:
        flags.add("charge")
    if effect == "HYPER_BEAM_EFFECT":
        flags.add("recharge")
    if effect in {"DRAIN_HP_EFFECT", "DREAM_EATER_EFFECT", "LEECH_SEED_EFFECT"}:
        flags.add("drain")
    if effect == "HEAL_EFFECT":
        flags.add("heal")
    if effect in {
        "TWO_TO_FIVE_ATTACKS_EFFECT",
        "ATTACK_TWICE_EFFECT",
        "TWINEEDLE_EFFECT",
    }:
        flags.add("multi_hit")
    if effect in {
        "SPECIAL_DAMAGE_EFFECT",
        "SUPER_FANG_EFFECT",
        "OHKO_EFFECT",
        "BIDE_EFFECT",
    }:
        flags.add("fixed_damage")
    if effect == "TRAPPING_EFFECT":
        flags.add("trapping")
    if effect == "OHKO_EFFECT":
        flags.add("ohko")
    if effect == "EXPLODE_EFFECT":
        flags.add("self_destruct")
    if effect in {"CONFUSION_EFFECT", "CONFUSION_SIDE_EFFECT"}:
        flags.add("confusion")
    if effect in {"FLINCH_SIDE_EFFECT1", "FLINCH_SIDE_EFFECT2"}:
        flags.add("flinch")
    if identifier == 68:
        # Counter's dependency is implemented directly in battle/core.asm
        # rather than represented by the otherwise generic move effect byte.
        flags.add("counter")
    return frozenset(flags)


def _build_moves() -> dict[int, MoveMechanics]:
    moves: dict[int, MoveMechanics] = {}
    for row in _MOVE_SOURCE.splitlines():
        identifier_text, effect, power_text, type_name, accuracy_text, pp_text = row.split("|")
        identifier = int(identifier_text)
        power = int(power_text)
        priority = 1 if identifier == 98 else -1 if identifier == 68 else 0
        mechanics = MoveMechanics(
            type_name=type_name,
            category=_move_category(type_name=type_name, power=power, effect=effect),
            power=power,
            accuracy=int(accuracy_text) / 100.0,
            max_pp=int(pp_text),
            priority=priority,
            effect_flags=_effect_flags(effect, identifier=identifier),
        )
        if identifier in moves:  # pragma: no cover - import-time catalog assertion
            raise AssertionError("duplicate move identifier in pinned catalog")
        moves[identifier] = mechanics
    if set(moves) != set(range(1, 166)):  # pragma: no cover - import-time assertion
        raise AssertionError("pinned move catalog must contain all 165 Red moves")
    return moves


def _build_species() -> dict[int, SpeciesMechanics]:
    species: dict[int, SpeciesMechanics] = {}
    for row in _SPECIES_SOURCE.splitlines():
        identifier_text, type_text = row.split("|")
        identifier = int(identifier_text)
        types = tuple(dict.fromkeys(type_text.split(",")))
        if identifier in species:  # pragma: no cover - import-time catalog assertion
            raise AssertionError("duplicate species identifier in pinned catalog")
        species[identifier] = SpeciesMechanics(types=types)
    if len(species) != 151:  # pragma: no cover - import-time catalog assertion
        raise AssertionError("pinned species catalog must contain all 151 Red species")
    return species


_TYPE_EFFECTS = MappingProxyType(
    {
        ("water", "fire"): 2.0,
        ("fire", "grass"): 2.0,
        ("fire", "ice"): 2.0,
        ("grass", "water"): 2.0,
        ("electric", "water"): 2.0,
        ("water", "rock"): 2.0,
        ("ground", "flying"): 0.0,
        ("water", "water"): 0.5,
        ("fire", "fire"): 0.5,
        ("electric", "electric"): 0.5,
        ("ice", "ice"): 0.5,
        ("grass", "grass"): 0.5,
        ("psychic", "psychic"): 0.5,
        ("fire", "water"): 0.5,
        ("grass", "fire"): 0.5,
        ("water", "grass"): 0.5,
        ("electric", "grass"): 0.5,
        ("normal", "rock"): 0.5,
        ("normal", "ghost"): 0.0,
        ("ghost", "ghost"): 2.0,
        ("fire", "bug"): 2.0,
        ("fire", "rock"): 0.5,
        ("water", "ground"): 2.0,
        ("electric", "ground"): 0.0,
        ("electric", "flying"): 2.0,
        ("grass", "ground"): 2.0,
        ("grass", "bug"): 0.5,
        ("grass", "poison"): 0.5,
        ("grass", "rock"): 2.0,
        ("grass", "flying"): 0.5,
        ("ice", "water"): 0.5,
        ("ice", "grass"): 2.0,
        ("ice", "ground"): 2.0,
        ("ice", "flying"): 2.0,
        ("fighting", "normal"): 2.0,
        ("fighting", "poison"): 0.5,
        ("fighting", "flying"): 0.5,
        ("fighting", "psychic"): 0.5,
        ("fighting", "bug"): 0.5,
        ("fighting", "rock"): 2.0,
        ("fighting", "ice"): 2.0,
        ("fighting", "ghost"): 0.0,
        ("poison", "grass"): 2.0,
        ("poison", "poison"): 0.5,
        ("poison", "ground"): 0.5,
        ("poison", "bug"): 2.0,
        ("poison", "rock"): 0.5,
        ("poison", "ghost"): 0.5,
        ("ground", "fire"): 2.0,
        ("ground", "electric"): 2.0,
        ("ground", "grass"): 0.5,
        ("ground", "bug"): 0.5,
        ("ground", "rock"): 2.0,
        ("ground", "poison"): 2.0,
        ("flying", "electric"): 0.5,
        ("flying", "fighting"): 2.0,
        ("flying", "bug"): 2.0,
        ("flying", "grass"): 2.0,
        ("flying", "rock"): 0.5,
        ("psychic", "fighting"): 2.0,
        ("psychic", "poison"): 2.0,
        ("bug", "fire"): 0.5,
        ("bug", "grass"): 2.0,
        ("bug", "fighting"): 0.5,
        ("bug", "flying"): 0.5,
        ("bug", "psychic"): 2.0,
        ("bug", "ghost"): 0.5,
        ("bug", "poison"): 2.0,
        ("rock", "fire"): 2.0,
        ("rock", "fighting"): 0.5,
        ("rock", "ground"): 0.5,
        ("rock", "flying"): 2.0,
        ("rock", "bug"): 2.0,
        ("rock", "ice"): 2.0,
        ("ghost", "normal"): 0.0,
        ("ghost", "psychic"): 0.0,
        ("fire", "dragon"): 0.5,
        ("water", "dragon"): 0.5,
        ("electric", "dragon"): 0.5,
        ("grass", "dragon"): 0.5,
        ("ice", "dragon"): 2.0,
        ("dragon", "dragon"): 2.0,
    }
)

_MOVE_SOURCE = """\
001|NO_ADDITIONAL_EFFECT|40|normal|100|35
002|NO_ADDITIONAL_EFFECT|50|normal|100|25
003|TWO_TO_FIVE_ATTACKS_EFFECT|15|normal|85|10
004|TWO_TO_FIVE_ATTACKS_EFFECT|18|normal|85|15
005|NO_ADDITIONAL_EFFECT|80|normal|85|20
006|PAY_DAY_EFFECT|40|normal|100|20
007|BURN_SIDE_EFFECT1|75|fire|100|15
008|FREEZE_SIDE_EFFECT1|75|ice|100|15
009|PARALYZE_SIDE_EFFECT1|75|electric|100|15
010|NO_ADDITIONAL_EFFECT|40|normal|100|35
011|NO_ADDITIONAL_EFFECT|55|normal|100|30
012|OHKO_EFFECT|1|normal|30|5
013|CHARGE_EFFECT|80|normal|75|10
014|ATTACK_UP2_EFFECT|0|normal|100|30
015|NO_ADDITIONAL_EFFECT|50|normal|95|30
016|NO_ADDITIONAL_EFFECT|40|normal|100|35
017|NO_ADDITIONAL_EFFECT|35|flying|100|35
018|SWITCH_AND_TELEPORT_EFFECT|0|normal|85|20
019|FLY_EFFECT|70|flying|95|15
020|TRAPPING_EFFECT|15|normal|75|20
021|NO_ADDITIONAL_EFFECT|80|normal|75|20
022|NO_ADDITIONAL_EFFECT|35|grass|100|10
023|FLINCH_SIDE_EFFECT2|65|normal|100|20
024|ATTACK_TWICE_EFFECT|30|fighting|100|30
025|NO_ADDITIONAL_EFFECT|120|normal|75|5
026|JUMP_KICK_EFFECT|70|fighting|95|25
027|FLINCH_SIDE_EFFECT2|60|fighting|85|15
028|ACCURACY_DOWN1_EFFECT|0|normal|100|15
029|FLINCH_SIDE_EFFECT2|70|normal|100|15
030|NO_ADDITIONAL_EFFECT|65|normal|100|25
031|TWO_TO_FIVE_ATTACKS_EFFECT|15|normal|85|20
032|OHKO_EFFECT|1|normal|30|5
033|NO_ADDITIONAL_EFFECT|35|normal|95|35
034|PARALYZE_SIDE_EFFECT2|85|normal|100|15
035|TRAPPING_EFFECT|15|normal|85|20
036|RECOIL_EFFECT|90|normal|85|20
037|THRASH_PETAL_DANCE_EFFECT|90|normal|100|20
038|RECOIL_EFFECT|100|normal|100|15
039|DEFENSE_DOWN1_EFFECT|0|normal|100|30
040|POISON_SIDE_EFFECT1|15|poison|100|35
041|TWINEEDLE_EFFECT|25|bug|100|20
042|TWO_TO_FIVE_ATTACKS_EFFECT|14|bug|85|20
043|DEFENSE_DOWN1_EFFECT|0|normal|100|30
044|FLINCH_SIDE_EFFECT1|60|normal|100|25
045|ATTACK_DOWN1_EFFECT|0|normal|100|40
046|SWITCH_AND_TELEPORT_EFFECT|0|normal|100|20
047|SLEEP_EFFECT|0|normal|55|15
048|CONFUSION_EFFECT|0|normal|55|20
049|SPECIAL_DAMAGE_EFFECT|1|normal|90|20
050|DISABLE_EFFECT|0|normal|55|20
051|DEFENSE_DOWN_SIDE_EFFECT|40|poison|100|30
052|BURN_SIDE_EFFECT1|40|fire|100|25
053|BURN_SIDE_EFFECT1|95|fire|100|15
054|MIST_EFFECT|0|ice|100|30
055|NO_ADDITIONAL_EFFECT|40|water|100|25
056|NO_ADDITIONAL_EFFECT|120|water|80|5
057|NO_ADDITIONAL_EFFECT|95|water|100|15
058|FREEZE_SIDE_EFFECT1|95|ice|100|10
059|FREEZE_SIDE_EFFECT1|120|ice|90|5
060|CONFUSION_SIDE_EFFECT|65|psychic|100|20
061|SPEED_DOWN_SIDE_EFFECT|65|water|100|20
062|ATTACK_DOWN_SIDE_EFFECT|65|ice|100|20
063|HYPER_BEAM_EFFECT|150|normal|90|5
064|NO_ADDITIONAL_EFFECT|35|flying|100|35
065|NO_ADDITIONAL_EFFECT|80|flying|100|20
066|RECOIL_EFFECT|80|fighting|80|25
067|FLINCH_SIDE_EFFECT2|50|fighting|90|20
068|NO_ADDITIONAL_EFFECT|1|fighting|100|20
069|SPECIAL_DAMAGE_EFFECT|1|fighting|100|20
070|NO_ADDITIONAL_EFFECT|80|normal|100|15
071|DRAIN_HP_EFFECT|20|grass|100|20
072|DRAIN_HP_EFFECT|40|grass|100|10
073|LEECH_SEED_EFFECT|0|grass|90|10
074|SPECIAL_UP1_EFFECT|0|normal|100|40
075|NO_ADDITIONAL_EFFECT|55|grass|95|25
076|CHARGE_EFFECT|120|grass|100|10
077|POISON_EFFECT|0|poison|75|35
078|PARALYZE_EFFECT|0|grass|75|30
079|SLEEP_EFFECT|0|grass|75|15
080|THRASH_PETAL_DANCE_EFFECT|70|grass|100|20
081|SPEED_DOWN1_EFFECT|0|bug|95|40
082|SPECIAL_DAMAGE_EFFECT|1|dragon|100|10
083|TRAPPING_EFFECT|15|fire|70|15
084|PARALYZE_SIDE_EFFECT1|40|electric|100|30
085|PARALYZE_SIDE_EFFECT1|95|electric|100|15
086|PARALYZE_EFFECT|0|electric|100|20
087|PARALYZE_SIDE_EFFECT1|120|electric|70|10
088|NO_ADDITIONAL_EFFECT|50|rock|65|15
089|NO_ADDITIONAL_EFFECT|100|ground|100|10
090|OHKO_EFFECT|1|ground|30|5
091|CHARGE_EFFECT|100|ground|100|10
092|POISON_EFFECT|0|poison|85|10
093|CONFUSION_SIDE_EFFECT|50|psychic|100|25
094|SPECIAL_DOWN_SIDE_EFFECT|90|psychic|100|10
095|SLEEP_EFFECT|0|psychic|60|20
096|ATTACK_UP1_EFFECT|0|psychic|100|40
097|SPEED_UP2_EFFECT|0|psychic|100|30
098|NO_ADDITIONAL_EFFECT|40|normal|100|30
099|RAGE_EFFECT|20|normal|100|20
100|SWITCH_AND_TELEPORT_EFFECT|0|psychic|100|20
101|SPECIAL_DAMAGE_EFFECT|0|ghost|100|15
102|MIMIC_EFFECT|0|normal|100|10
103|DEFENSE_DOWN2_EFFECT|0|normal|85|40
104|EVASION_UP1_EFFECT|0|normal|100|15
105|HEAL_EFFECT|0|normal|100|20
106|DEFENSE_UP1_EFFECT|0|normal|100|30
107|EVASION_UP1_EFFECT|0|normal|100|20
108|ACCURACY_DOWN1_EFFECT|0|normal|100|20
109|CONFUSION_EFFECT|0|ghost|100|10
110|DEFENSE_UP1_EFFECT|0|water|100|40
111|DEFENSE_UP1_EFFECT|0|normal|100|40
112|DEFENSE_UP2_EFFECT|0|psychic|100|30
113|LIGHT_SCREEN_EFFECT|0|psychic|100|30
114|HAZE_EFFECT|0|ice|100|30
115|REFLECT_EFFECT|0|psychic|100|20
116|FOCUS_ENERGY_EFFECT|0|normal|100|30
117|BIDE_EFFECT|0|normal|100|10
118|METRONOME_EFFECT|0|normal|100|10
119|MIRROR_MOVE_EFFECT|0|flying|100|20
120|EXPLODE_EFFECT|130|normal|100|5
121|NO_ADDITIONAL_EFFECT|100|normal|75|10
122|PARALYZE_SIDE_EFFECT2|20|ghost|100|30
123|POISON_SIDE_EFFECT2|20|poison|70|20
124|POISON_SIDE_EFFECT2|65|poison|100|20
125|FLINCH_SIDE_EFFECT1|65|ground|85|20
126|BURN_SIDE_EFFECT2|120|fire|85|5
127|NO_ADDITIONAL_EFFECT|80|water|100|15
128|TRAPPING_EFFECT|35|water|75|10
129|SWIFT_EFFECT|60|normal|100|20
130|CHARGE_EFFECT|100|normal|100|15
131|TWO_TO_FIVE_ATTACKS_EFFECT|20|normal|100|15
132|SPEED_DOWN_SIDE_EFFECT|10|normal|100|35
133|SPECIAL_UP2_EFFECT|0|psychic|100|20
134|ACCURACY_DOWN1_EFFECT|0|psychic|80|15
135|HEAL_EFFECT|0|normal|100|10
136|JUMP_KICK_EFFECT|85|fighting|90|20
137|PARALYZE_EFFECT|0|normal|75|30
138|DREAM_EATER_EFFECT|100|psychic|100|15
139|POISON_EFFECT|0|poison|55|40
140|TWO_TO_FIVE_ATTACKS_EFFECT|15|normal|85|20
141|DRAIN_HP_EFFECT|20|bug|100|15
142|SLEEP_EFFECT|0|normal|75|10
143|CHARGE_EFFECT|140|flying|90|5
144|TRANSFORM_EFFECT|0|normal|100|10
145|SPEED_DOWN_SIDE_EFFECT|20|water|100|30
146|NO_ADDITIONAL_EFFECT|70|normal|100|10
147|SLEEP_EFFECT|0|grass|100|15
148|ACCURACY_DOWN1_EFFECT|0|normal|70|20
149|SPECIAL_DAMAGE_EFFECT|1|psychic|80|15
150|SPLASH_EFFECT|0|normal|100|40
151|DEFENSE_UP2_EFFECT|0|poison|100|40
152|NO_ADDITIONAL_EFFECT|90|water|85|10
153|EXPLODE_EFFECT|170|normal|100|5
154|TWO_TO_FIVE_ATTACKS_EFFECT|18|normal|80|15
155|ATTACK_TWICE_EFFECT|50|ground|90|10
156|HEAL_EFFECT|0|psychic|100|10
157|NO_ADDITIONAL_EFFECT|75|rock|90|10
158|FLINCH_SIDE_EFFECT1|80|normal|90|15
159|ATTACK_UP1_EFFECT|0|normal|100|30
160|CONVERSION_EFFECT|0|normal|100|30
161|NO_ADDITIONAL_EFFECT|80|normal|100|10
162|SUPER_FANG_EFFECT|1|normal|90|10
163|NO_ADDITIONAL_EFFECT|70|normal|100|20
164|SUBSTITUTE_EFFECT|0|normal|100|10
165|RECOIL_EFFECT|50|normal|100|10"""

_SPECIES_SOURCE = """\
001|ground,rock
002|normal
003|poison
004|normal
005|normal,flying
006|electric
007|poison,ground
008|water,psychic
009|grass,poison
010|grass,psychic
011|normal
012|grass,psychic
013|poison
014|ghost,poison
015|poison
016|poison,ground
017|ground
018|ground,rock
019|water,ice
020|fire
021|psychic
022|water,flying
023|water
024|water,poison
025|ghost,poison
026|bug,flying
027|water
028|water
029|bug
030|grass
033|fire
034|rock,ground
035|normal,flying
036|normal,flying
037|water,psychic
038|psychic
039|rock,ground
040|normal
041|fighting
042|psychic
043|fighting
044|fighting
045|poison
046|bug,grass
047|water
048|psychic
049|rock,ground
051|fire
053|electric
054|electric
055|poison
057|fighting
058|water
059|ground
060|normal
064|normal,flying
065|bug,poison
066|dragon,flying
070|normal,flying
071|water
072|ice,psychic
073|fire,flying
074|ice,flying
075|electric,flying
076|normal
077|normal
078|water
082|fire
083|fire
084|electric
085|electric
088|dragon
089|dragon
090|rock,water
091|rock,water
092|water
093|water
096|ground
097|ground
098|rock,water
099|rock,water
100|normal
101|normal
102|normal
103|fire
104|electric
105|water
106|fighting
107|poison,flying
108|poison
109|bug,grass
110|water
111|water,fighting
112|bug,poison
113|bug,poison
114|bug,poison
116|normal,flying
117|fighting
118|ground
119|bug,poison
120|water,ice
123|bug
124|bug
125|bug,flying
126|fighting
128|water
129|psychic
130|poison,flying
131|psychic
132|normal
133|water
136|poison
138|water
139|water,ice
141|electric
142|normal
143|poison
144|normal
145|ground
147|ghost,poison
148|psychic
149|psychic
150|normal,flying
151|normal,flying
152|water,psychic
153|grass,poison
154|grass,poison
155|water,poison
157|water
158|water
163|fire
164|fire
165|normal
166|normal
167|poison
168|poison
169|rock,ground
170|normal
171|rock,flying
173|electric
176|fire
177|water
178|fire
179|water
180|fire,flying
185|grass,poison
186|grass,poison
187|grass,poison
188|grass,poison
189|grass,poison
190|grass,poison"""

_MOVE_BY_ID = MappingProxyType(_build_moves())
_SPECIES_BY_ID = MappingProxyType(_build_species())

RED_BATTLE_CATALOG = PokemonRedBattleCatalog()
