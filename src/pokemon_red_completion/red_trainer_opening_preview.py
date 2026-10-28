"""Conditional fresh-trainer move preference using the existing frozen move head.

This is a preview, never an observed battle or a win forecast. The caller must
authenticate the quoted opponent and a route preserving the observed party.
Only the known starting lead and ordinary damaging-move scope are supported.
No player integration or goal preference is supplied by this module.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass
import re

from .battle_semantics import BattleFeatureProjector
from .provenance import canonical_sha256
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref, pokemon_red_species_ref
from .red_battle_scenario import red_battle_move_unsupported_reason
from .red_status_battle_features import project_for_head
from .red_trainer_practice_features import MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES
from .red_trainer_practice_head import TrainerHeadModel


class OpeningPreviewUnavailable(ValueError):
    """Required observed facts or the declared opening scope are unavailable."""


@dataclass(frozen=True, slots=True)
class TrainerOpeningPreview:
    source_sha256: str
    head_sha256: str
    input_sha256: str
    opponent_quote_sha256: str
    assumptions: tuple[str, ...]
    feature_names: tuple[str, ...]
    candidate_slots: tuple[int, ...]
    candidate_vectors: tuple[tuple[float, ...], ...]
    probabilities: tuple[float, ...]
    preferred_slot: int

    def public_dict(self):
        return dict(schema="pokemon.red.conditional-opening-preview.v1", **asdict(self))


def _hash(value, name):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise OpeningPreviewUnavailable(f"{name} must be a source hash")


def _integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise OpeningPreviewUnavailable(f"{name} outside observed bounds")
    return value


def _fresh_trainer_view(before, *, opponent_species_id, opponent_level, opponent_base_stats, machine_lesson=None, stats_peer=None):
    """Validate and build shared pre-input facts; callers supply scope and pins."""
    if type(before) is not dict:
        raise OpeningPreviewUnavailable("pre-input snapshot missing")
    before = deepcopy(before)
    source = before.get("state_sha256")
    _hash(source, "snapshot")
    if any(type(before.get(n)) is not int or before[n] != 0 for n in ("actions", "frames")):
        raise OpeningPreviewUnavailable("snapshot must precede diagnostic inputs")
    lesson_state = before.get("lesson", {})
    if lesson_state.get("in_battle") is not False:
        raise OpeningPreviewUnavailable("observed field boundary required")
    party = lesson_state.get("party")
    if not isinstance(party, list) or not 1 <= len(party) <= 6:
        raise OpeningPreviewUnavailable("observed party missing")
    boundary = before.get("machine_boundary")
    if boundary is None and stats_peer is not None:
        if (type(stats_peer) is not dict or stats_peer.get("state_sha256") != source
                or stats_peer.get("lesson", {}).get("party") != party
                or any(type(stats_peer.get(n)) is not int or stats_peer[n] != 0 for n in ("actions", "frames"))
                or stats_peer.get("lesson", {}).get("in_battle") is not False):
            raise OpeningPreviewUnavailable("stats peer does not match exact pre-input source and party")
        boundary = deepcopy(stats_peer.get("machine_boundary"))
    if not isinstance(boundary, dict):
        raise OpeningPreviewUnavailable("observed full party stats missing")
    stats = boundary.get("party_stats")
    if not isinstance(stats, list) or len(stats) != len(party):
        raise OpeningPreviewUnavailable("full party stat count differs")
    members = []
    specimens = set()
    for index, (mon, values) in enumerate(zip(party, stats, strict=True)):
        if (not isinstance(mon, dict) or mon.get("status") != "healthy"
                or not isinstance(mon.get("specimen_ref"), str)
                or not mon["specimen_ref"] or mon["specimen_ref"] in specimens):
            raise OpeningPreviewUnavailable("known healthy distinct party members required")
        specimens.add(mon["specimen_ref"])
        if not isinstance(values, (tuple, list)) or len(values) != 4:
            raise OpeningPreviewUnavailable("four observed party stats required")
        values = tuple(_integer(v, 1, 999, "party stat") for v in values)
        maximum = _integer(mon.get("max_hp"), 1, 999, "maximum HP")
        hp = _integer(mon.get("hp"), 1, maximum, "current HP")
        level = _integer(mon.get("level"), 1, 100, "level")
        moves = mon.get("moves")
        if not isinstance(moves, list) or len(moves) != 4:
            raise OpeningPreviewUnavailable("four observed move slots required")
        projected_moves = []
        for slot, pair in enumerate(moves):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise OpeningPreviewUnavailable("move/PP pair missing")
            mid, pp = (_integer(pair[0], 0, 165, "move"), _integer(pair[1], 0, 63, "PP"))
            if mid == 0:
                if pp != 0:raise OpeningPreviewUnavailable("empty move has PP")
                continue
            projected_moves.append(dict(slot_index=slot, move_ref=pokemon_red_move_ref(mid), pp=pp))
        species = _integer(mon.get("species_id"), 1, 255, "party species")
        members.append(dict(party_index=index, species_ref=pokemon_red_species_ref(species),
            level=level, hp=hp, max_hp=maximum, hp_ratio=hp/maximum, status=None,
            stats=dict(zip(("attack", "defense", "speed", "special"), values, strict=True)),
            moves=projected_moves))
    if machine_lesson is not None:
        if type(machine_lesson) is not dict or set(machine_lesson) != {"lesson", "move_change"}:
            raise OpeningPreviewUnavailable("existing machine lesson document required")
        change = machine_lesson["lesson"]
        if type(change) is not dict or type(machine_lesson["move_change"]) is not dict:
            raise OpeningPreviewUnavailable("machine lesson facts missing")
        if (type(change.get("party_slot")) is not int or change["party_slot"] != 1
                or type(change.get("species_id")) is not int or change["species_id"] != party[0]["species_id"]
                or change.get("before_moves") != [m[0] for m in party[0]["moves"]]):
            raise OpeningPreviewUnavailable("lesson must match observed starting lead")
        slot = _integer(change.get("replace_slot"), 1, 4, "replacement slot")-1
        mid = _integer(change.get("move_id"), 1, 165, "proposed move")
        move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(mid))
        pp = machine_lesson["move_change"].get("proposed_current_pp")
        if type(pp) is not int or pp != move.max_pp:
            raise OpeningPreviewUnavailable("new lesson must declare base PP")
        members[0]["moves"] = [m for m in members[0]["moves"] if m["slot_index"] != slot]
        members[0]["moves"].append(dict(slot_index=slot,move_ref=pokemon_red_move_ref(mid),pp=pp))
        members[0]["moves"].sort(key=lambda m:m["slot_index"])
    bases = opponent_base_stats
    if type(bases) is not dict or set(bases) != {"attack", "defense", "speed", "special"}:
        raise OpeningPreviewUnavailable("quoted public opponent bases required")
    bases = {k:_integer(v,1,255,"opponent public base") for k,v in bases.items()}
    foe_level = _integer(opponent_level,1,100,"quoted opponent level")
    foe = pokemon_red_species_ref(_integer(opponent_species_id,1,255,"quoted opponent species"))
    view = dict(mode="battle",features=dict(menu=dict(kind="battle_main"),
        party=dict(count=len(members),active_index=0,lead=members[0],members=members),
        battle=dict(active=True,kind="trainer",opponent_species_ref=foe,opponent_level=foe_level,
            opponent_hp_ratio=1.0,opponent_status=None,opponent_public_base_stats=bases,
            player_attack_stage=0,player_accuracy_stage=0,opponent_defense_stage=0,
            player_special_stage=0,player_disabled_move_slot=None)))
    return view


def preview_fresh_trainer_moves(
    before, *, opponent_species_id, opponent_level, opponent_base_stats,
    opponent_quote_sha256, head, expected_head_sha256, fresh_trainer,
    approach_preserves_party, machine_lesson=None, stats_peer=None,
):
    """Return a source-bound conditional move distribution, or fail unavailable.

    ``before`` is an authenticated pre-input consequence snapshot. A missing
    machine boundary may be joined only to an identical-source, identical-party
    pre-input peer. A lesson is the existing validated machine-lesson document;
    this function does not authorize or execute it. Unknown dynamic state is
    never filled from a later battle. Opponent assumptions are labeled below.
    """
    if fresh_trainer is not True or approach_preserves_party is not True:
        raise OpeningPreviewUnavailable("fresh trainer and party-preserving approach required")
    if (not isinstance(head, TrainerHeadModel) or head.schema_id != MOVE_SCHEMA_ID
            or head.feature_names != MOVE_FEATURE_NAMES):
        raise OpeningPreviewUnavailable("only the ordinary stat move head is qualified")
    _hash(expected_head_sha256, "head")
    if canonical_sha256(head.to_dict()) != expected_head_sha256:
        raise OpeningPreviewUnavailable("frozen move head identity differs")
    _hash(opponent_quote_sha256, "opponent quote")
    view = _fresh_trainer_view(before, opponent_species_id=opponent_species_id,
        opponent_level=opponent_level, opponent_base_stats=opponent_base_stats,
        machine_lesson=machine_lesson, stats_peer=stats_peer)
    source = before["state_sha256"]
    members = view["features"]["party"]["members"]
    base = BattleFeatureProjector(RED_BATTLE_CATALOG,mask_counter_without_prior_damage=True).project(view)
    rich = project_for_head(view,base,head)
    moves = {m["slot_index"]:m for m in members[0]["moves"]}
    legal = tuple(slot+1 for slot,allowed in zip(base.slot_indices,base.legal_mask,strict=True)
        if allowed and red_battle_move_unsupported_reason(
            int(moves[slot]["move_ref"].rsplit(":",1)[1]),moves[slot]["pp"],catalog=RED_BATTLE_CATALOG) is None)
    if not legal:
        raise OpeningPreviewUnavailable("no ordinary supported attack; no Struggle or status fallback preview")
    vectors = tuple(rich.candidate_vectors[rich.candidate_slots.index(s)] for s in legal)
    probabilities = tuple(float(v) for v in head.probabilities(vectors))
    return TrainerOpeningPreview(source,expected_head_sha256,canonical_sha256(view),opponent_quote_sha256,
        ("fresh opponent at full HP", "healthy opponent and neutral stages", "no disable",
         "observed party unchanged during approach", "conditional on attack; control/switch unpredicted",
         "ordinary supported damaging-move scope; not a win probability"),
        rich.feature_names,legal,vectors,probabilities,legal[head.predict_index(vectors)])


OPENING_PREFERENCE_FEATURE_NAMES = (
    "opening_preference_known",
    "removed_before_mass",
    "proposed_after_mass",
)


@dataclass(frozen=True, slots=True)
class TrainerOpeningPreference:
    """Portable ranking summaries with separate source-bound preview evidence.

    These values describe conditional participation in the frozen move head.
    They are not action frequencies, preparation value, or win probabilities.
    No native learner schema or model accepts them through this module.
    """

    feature_names: tuple[str, ...]
    values: tuple[float, ...]
    before: TrainerOpeningPreview
    after: TrainerOpeningPreview
    lesson_sha256: str | None
    replaced_slot: int | None
    removed_move: tuple[int, int] | None
    proposed_move: tuple[int, int] | None
    snapshot_sha256: str
    stats_peer_sha256: str | None

    def public_dict(self):
        return dict(
            schema="pokemon.red.conditional-opening-preference.v1",
            feature_names=self.feature_names,
            values=self.values,
            before=self.before.public_dict(),
            after=self.after.public_dict(),
            lesson_sha256=self.lesson_sha256,
            replaced_slot=self.replaced_slot,
            removed_move=self.removed_move,
            proposed_move=self.proposed_move,
            removed_slot_legal=self.replaced_slot in self.before.candidate_slots if self.replaced_slot is not None else None,
            proposed_slot_legal=self.replaced_slot in self.after.candidate_slots if self.replaced_slot is not None else None,
            snapshot_sha256=self.snapshot_sha256,
            stats_peer_sha256=self.stats_peer_sha256,
        )


def preview_machine_preference(before, *, machine_lesson=None, stats_peer=None, **opening):
    """Compare one authenticated source with its declared machine lesson.

    Both previews are constructed here from the same facts and frozen head;
    callers cannot splice independently supplied previews. A direct option is
    qualified only after constructing its baseline. Unsupported removed or
    proposed attacks have zero mass within the ordinary attack scope. Missing
    evidence raises OpeningPreviewUnavailable, never a known-zero descriptor.
    The caller still owns source/quote authentication and native lesson legality.
    """
    snapshot = deepcopy(before)
    peer = deepcopy(stats_peer)
    lesson = deepcopy(machine_lesson)
    baseline = preview_fresh_trainer_moves(snapshot, stats_peer=peer, **opening)
    if lesson is None:
        return TrainerOpeningPreference(
            OPENING_PREFERENCE_FEATURE_NAMES, (1.0, 0.0, 0.0), baseline, baseline,
            None, None, None, None, canonical_sha256(snapshot),
            canonical_sha256(peer) if snapshot.get("machine_boundary") is None and peer is not None else None,
        )
    proposed = preview_fresh_trainer_moves(
        snapshot, machine_lesson=lesson, stats_peer=peer, **opening,
    )
    slot = lesson["lesson"]["replace_slot"]
    removed_mass = dict(zip(baseline.candidate_slots, baseline.probabilities, strict=True)).get(slot, 0.0)
    proposed_mass = dict(zip(proposed.candidate_slots, proposed.probabilities, strict=True)).get(slot, 0.0)
    return TrainerOpeningPreference(
        OPENING_PREFERENCE_FEATURE_NAMES, (1.0, removed_mass, proposed_mass),
        baseline, proposed, canonical_sha256(lesson), slot,
        tuple(snapshot["lesson"]["party"][0]["moves"][slot-1]),
        (lesson["lesson"]["move_id"], lesson["move_change"]["proposed_current_pp"]),
        canonical_sha256(snapshot),
        canonical_sha256(peer) if snapshot.get("machine_boundary") is None and peer is not None else None,
    )
