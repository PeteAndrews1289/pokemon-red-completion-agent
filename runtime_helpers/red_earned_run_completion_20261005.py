"""Forward completion adapter: reuse existing builders, never reopen old runs."""

import json
import os
import sys
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import red_silph_coverage_20261005 as previous

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort, gen1_field_capabilities
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import (
    RED_FLY_TOWN_NAMES,
    EventFlag,
    ItemId,
    event_flag_is_set,
)
from pokemon_red_completion.red_capture_checkpoint import (
    create_capture_journal,
    load_capture_checkpoint,
    write_capture_checkpoint,
)
from pokemon_red_completion.red_capture_lead import RedCaptureLeadPlan
from pokemon_red_completion.red_capture_preparation import prepare_observed_lead
from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget
from pokemon_red_completion.red_champion_story import RedCartridgeChampionSkill
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_gym_reward import SABRINA_REWARD
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedChampionController,
    ScopedAssistedLeagueRetryController,
)
from pokemon_red_completion.red_one_off_capture import (
    OneOffCaptureBudget,
    OneOffCaptureRequest,
    run_one_off_capture,
)
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_continuation import (
    _battle,
    accumulate_player_costs,
    capture_player_continuation,
    refresh_preparation_roster,
)
from pokemon_red_completion.red_player_curriculum import (
    NativeRegionalCurriculum,
    PlayerCurriculumCompletion,
)
from pokemon_red_completion.red_player_story_battle import story_battle_binding
from pokemon_red_completion.red_sabrina_continuation import sabrina_contract
from pokemon_red_completion.red_snorlax_capture import route12_snorlax_target
from pokemon_red_completion.red_static_capture_runtime import settle_static_capture
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.red_trainer_story import RedCartridgeLoreleiSkill

p, c, doc, audit = previous.p, previous.c, previous.doc, previous.audit
_saved = {
    name: getattr(p.cerulean, name) for name in previous.silph.tower.hideout.erika.lavender._names
}
_reserve = p.cerulean.f.RESERVE
try:
    import earned_blaine_20261002 as blaine
    import earned_champion_20261002 as champion
    import earned_giovanni_20261002 as giovanni
    import earned_koga_20261002 as koga
    import earned_safari_hms_20261002 as safari
    import earned_victory_road_20261002 as victory
finally:
    for _name, _value in _saved.items():
        setattr(p.cerulean, _name, _value)
    p.cerulean.f.RESERVE = _reserve

ROOT = c.BASE / "red-earned-run-completion-20261005-v1"
PARENT = previous.ROOT
SOURCE = PARENT / "fresh-pilot/runs/segment-22"
SOURCE_SHA = "61ee538c0c0a075323e724e11c138006bf7843b4fdc5efae2bba460247a2cdfe"
CONTEXT_SHA = "94f268cf4aa263ef603a6b473f46cbc8decd843f10939e0e5d74f177d01efa5e"
REPORT = c.REPO / "docs/work-sessions/2026-10-05-earned-run-completion.md"
START = datetime(2026, 10, 5, 14, 47, 11, tzinfo=UTC)
# The human authorized an outcome rather than another per-checkpoint deadline.
# Existing workers still impose finite input/frame/time/stuck limits.
HORIZON = datetime.max.replace(tzinfo=UTC)
LIMITS = dict(decisions=100000, actions=20000000, frames=2000000000, seconds=604800, heals=1000000)
STAGE_TARGETS = ("reach_fuchsia", "defeat_koga")
RESERVE = CapturePreparationBudget(ItemId.GREAT_BALL, 10, 10)
STAGES = {
    "koga": (STAGE_TARGETS, int(c.MapId.FUCHSIA_POKECENTER)),
    "safari": (("obtain_surf", "obtain_strength"), int(c.MapId.FUCHSIA_POKECENTER)),
    "sabrina": (("defeat_sabrina",), int(c.MapId.SAFFRON_POKECENTER)),
    "blaine": (
        ("reach_cinnabar", "obtain_secret_key", "defeat_blaine"),
        int(c.MapId.CINNABAR_POKECENTER),
    ),
    "giovanni": (("defeat_giovanni",), int(c.MapId.VIRIDIAN_POKECENTER)),
    "victory": (("cross_victory_road",), int(c.MapId.INDIGO_PLATEAU_LOBBY)),
    "league-preparation": (
        ("cross_victory_road", "obtain_surf", "obtain_strength"),
        int(c.MapId.INDIGO_PLATEAU_LOBBY),
    ),
    "league": (("defeat_champion",), int(c.MapId.HALL_OF_FAME)),
    "collection": (("postgame_collection",), int(c.MapId.PALLET_TOWN)),
}
# Prospective first challenge, not a survival certificate. Actual losses/PP
# determine further preparation; do not grind a guessed perfect team first.
LEAGUE_LEVELS = {28: 65, 132: 35}
LEAGUE_DEVELOPMENT_DEFICIT = 30


def league_declared_deficit(output):
    """Keep pre-pivot receipts reconstructable with their actual declaration."""
    stage_record = output / "STAGE.json"
    if stage_record.exists():
        record = doc(stage_record)
        if "maximum_level_deficit" in record:
            return record["maximum_level_deficit"]
    if output.name.startswith("segment-"):
        return 5 if int(output.name.rsplit("-", 1)[1]) < 103 else LEAGUE_DEVELOPMENT_DEFICIT
    return LEAGUE_DEVELOPMENT_DEFICIT


def scoped_lorelei_skill(runtime, *args, **kwargs):
    kwargs["maximum_level_deficit"] = runtime.league_story_battle_controller.declared_level_deficit
    return RedCartridgeLoreleiSkill(runtime, *args, **kwargs)


def scoped_champion_skill(runtime, *args, **kwargs):
    kwargs["maximum_level_deficit"] = runtime.league_story_battle_controller.declared_level_deficit
    return RedCartridgeChampionSkill(runtime, *args, **kwargs)


@dataclass(frozen=True)
class RetainedSegmentLayout:
    """Read existing receipts in place; never copy progress into old chunk names."""

    path: Path

    def glob(self, pattern):
        return self.path.glob(pattern.replace("chunk-*", "segment-*", 1))

    def __truediv__(self, child):
        return self.path / child


@dataclass(frozen=True)
class CompletionStageCurriculum(NativeRegionalCurriculum):
    required_moves: tuple[int, ...] = ()

    def completion(self, boundary):
        raw = boundary.observation.raw
        if any(
            not any(
                hp > 0 and move in moves
                for hp, moves in zip(raw.party_hp, raw.party_moves, strict=True)
            )
            for move in self.required_moves
        ):
            return None
        return super().completion(boundary)


def league_levels_ready(raw):
    levels = dict(zip(raw.party_species_ids, raw.party_levels, strict=True))
    return all(levels.get(species, 0) >= level for species, level in LEAGUE_LEVELS.items())


def victory_transport_needed(raw):
    """Never undo an earned badge-corridor or cave transition with Fly."""
    return raw.map_id not in {
        int(c.MapId.ROUTE_23),
        int(c.MapId.VICTORY_ROAD_1F),
        int(c.MapId.VICTORY_ROAD_2F),
        int(c.MapId.VICTORY_ROAD_3F),
        int(c.MapId.INDIGO_PLATEAU),
        int(c.MapId.INDIGO_PLATEAU_LOBBY),
    }


@dataclass(frozen=True)
class LeaguePreparationCurriculum(CompletionStageCurriculum):
    def completion(self, boundary):
        if not league_levels_ready(boundary.observation.raw):
            return None
        return super().completion(boundary)


@dataclass(frozen=True)
class LeagueVictoryCurriculum(CompletionStageCurriculum):
    def completion(self, boundary):
        raw = boundary.observation.raw
        if (
            raw.map_id != int(c.MapId.HALL_OF_FAME)
            or raw.badge_bits != 255
            or raw.battle_state != 0
            or not boundary.observation.input_ready
            or not event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
            or "defeat_champion" not in boundary.lesson_snapshot["completed_objectives"]
        ):
            return None
        # A native League victory does not magically heal its fainted reserves.
        return PlayerCurriculumCompletion(
            c.canonical_sha256(asdict(self)), c.sha256(boundary.state).hexdigest()
        )


@dataclass(frozen=True)
class WholeRunCollectionCurriculum(CompletionStageCurriculum):
    def completion(self, boundary):
        from red_earned_collection_connection_20261005 import collection_targets_met

        from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored

        raw = boundary.observation.raw
        proof = ROOT / "HALL-OF-FAME-PROOF.json"
        if (
            not proof.exists()
            or raw.badge_bits != 255
            or raw.battle_state
            or not boundary.observation.input_ready
            or not _raw_party_fully_restored(raw)
            or not collection_targets_met(boundary.observation)
        ):
            return None
        verified_hall_of_fame()
        if not returned_hall_of_fame_roster(boundary):
            return None
        return PlayerCurriculumCompletion(
            c.canonical_sha256(asdict(self)), c.sha256(boundary.state).hexdigest()
        )


def verified_hall_of_fame():
    """Verify earned concurrent proof retained before native credits clear League flags."""
    row = doc(ROOT / "HALL-OF-FAME-PROOF.json")
    directory = Path(row["directory"])
    assert (
        directory.parent == p.ROOT / "runs" and doc(directory / "STAGE.json")["stage"] == "league"
    )
    assert row["terminal_sha256"] == c.digest(directory / "terminal.state")
    assert row["context_sha256"] == c.digest(directory / "CONTEXT.json")
    assert row["champion_and_hall_of_fame"] and row["badges"] == 255
    return row


def returned_hall_of_fame_roster(boundary):
    """A healthy helper party is not the returned original six."""
    proof = verified_hall_of_fame()
    original = doc(Path(proof["directory"]) / "CONTEXT.json")["preparation"]["roster"]
    refs = {m["specimen_ref"] for m in original}
    active = [m["specimen_ref"] for m in boundary.lesson_snapshot["party"]]
    return len(refs) == len(active) == len(set(active)) == 6 and set(active) == refs


def stage_from(parent):
    facts = audit.native_state(parent / "terminal.state")
    completed = set(doc(parent / "CONTEXT.json")["lesson"]["completed_objectives"])
    if "defeat_champion" in completed:
        return "collection"
    marker = parent / "STAGE.json"
    if marker.exists():
        retained_stage = doc(marker)["stage"]
        if retained_stage == "league" and facts["map"] in {
            int(c.MapId.INDIGO_PLATEAU),
            int(c.MapId.INDIGO_PLATEAU_LOBBY),
        }:
            with c.PyBoyAdapter(c.ROM) as emulator:
                emulator.load_state_bytes((parent / "terminal.state").read_bytes())
                if not league_levels_ready(c.PokemonRedStateReader(emulator).read()):
                    return "league-preparation"
        if retained_stage == "collection":
            return "collection"
        required, destination = STAGES[retained_stage]
        if (
            not set(required) <= completed
            or facts["map"] != destination
            or facts["hp"] != facts["max_hp"]
            or any(facts["status"])
        ):
            return retained_stage  # The actual earned aftermath still needs its ordinary return.
        if retained_stage == "league-preparation":
            with c.PyBoyAdapter(c.ROM) as emulator:
                emulator.load_state_bytes((parent / "terminal.state").read_bytes())
                if not league_levels_ready(c.PokemonRedStateReader(emulator).read()):
                    return retained_stage
    healthy = facts["hp"] == facts["max_hp"] and not any(facts["status"])
    if "defeat_koga" not in completed or (
        "obtain_surf" not in completed and (facts["map"] != STAGES["koga"][1] or not healthy)
    ):
        return "koga"
    moves = {
        move
        for member in facts["party"]["members"]
        for move in (m["move_id"] for m in member["moves"])
    }
    if not {"obtain_surf", "obtain_strength"} <= completed or not {57, 70} <= moves:
        return "safari"
    if "defeat_sabrina" not in completed:
        return "sabrina"
    if "defeat_blaine" not in completed:
        return "blaine"
    if "defeat_giovanni" not in completed:
        return "giovanni"
    if "cross_victory_road" not in completed:
        return "victory"
    with c.PyBoyAdapter(c.ROM) as emulator:
        emulator.load_state_bytes((parent / "terminal.state").read_bytes())
        ready = league_levels_ready(c.PokemonRedStateReader(emulator).read())
    return "league" if ready else "league-preparation"


def stage_for_plan(plan):
    targets = tuple(plan["targets"])
    return next(name for name, (required, _) in STAGES.items() if targets == required)


def authenticate(check_code=False):
    previous.authenticate(check_code=False)
    close = doc(PARENT / "CLOSEOUT.json")
    assert close["complete"] and close["native_stopped"] and close["audit_stopped"]
    assert close["terminal_sha256"] == c.digest(SOURCE / "terminal.state") == SOURCE_SHA
    assert close["context_sha256"] == c.digest(SOURCE / "CONTEXT.json") == CONTEXT_SHA
    assert doc(PARENT / "STATUS.json")["active_worker"] is None
    assert doc(SOURCE / "DELTA-AUDIT.json")["passed"]


def prospective_native_run(**kwargs):
    assert kwargs["run_id"] == "overnight-fresh-20261005"
    kwargs["run_id"] = ROOT.name
    limits = kwargs.get("limits")
    kwargs["settle_existing_trainer"] = limits is None or limits.decisions >= 2
    if RETAINED_CAPTURE:
        # One-off recovery must not run the generic wild flee preface.
        kwargs["settle_existing_wild"] = False
        kwargs["settle_existing_capture"] = True
    arm = kwargs.get("arm_id", "")
    if arm.startswith("segment-") and int(arm.rsplit("-", 1)[1]) >= 264:
        kwargs["allow_collection_restoration"] = True
    scope = nullcontext()
    if arm.startswith("segment-") and int(arm.rsplit("-", 1)[1]) >= 248:
        from red_earned_collection_connection_20261005 import bounded_collection_transport

        # Escort preparation can rebind transport after discovery. Keep the
        # same prospective allowance active for that actual execution too.
        scope = bounded_collection_transport(Path(arm))
    with scope:
        return previous.ORIGINAL_NATIVE_RUN(**kwargs)


RETAINED_CAPTURE = False


def configure():
    p.coordinator.ROOT, p.coordinator.REPORT = ROOT, REPORT
    p.coordinator.START = START
    p.coordinator.DEADLINE = p.coordinator.CLOSEOUT = HORIZON
    p.coordinator.authenticate = authenticate
    p.coordinator.port.ROOT, p.coordinator.port.START = ROOT, START
    p.coordinator.port.DEADLINE = HORIZON
    p.coordinator.port.authenticate = authenticate
    p.ROOT, p.START, p.LIMITS = ROOT / "fresh-pilot", previous.ORIGINAL_OPENING, LIMITS
    p.run_native_continuous_player = prospective_native_run
    p.EARLY_RESERVE = RESERVE
    koga.ROOT = p.ROOT
    koga.old.RESERVE = RESERVE
    koga.core = core
    koga.needs_restoration = needs_restoration
    audit.ROOT = ROOT
    audit.assembler_for = lambda plan: partial(assembly, stage=stage_for_plan(plan))
    safari.ROOT = p.ROOT
    safari.core = partial(core, stage="safari")
    safari.complete = safari_complete
    original_rewards = __import__(
        "pokemon_red_completion.red_player_safari_rewards", fromlist=["safari_rewards_binding"]
    ).safari_rewards_binding

    def preserve_ice_beam(*args, **kwargs):
        kwargs["replace_slot"] = 4  # Current save: Ice Beam3, BubbleBeam4.
        return original_rewards(*args, **kwargs)

    safari.safari_rewards_binding = preserve_ice_beam
    champion.ROOT = RetainedSegmentLayout(p.ROOT)
    champion.complete = lambda rt: (
        rt.reader.read().map_id == int(c.MapId.HALL_OF_FAME)
        and event_flag_is_set(rt.reader.read().event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
        and rt.reader.read().badge_bits == 255
        and p._field_ready(rt)
    )
    champion.core = partial(core, stage="league")
    champion.RedCartridgeChampionSkill = scoped_champion_skill
    champion.m.RedCartridgeLoreleiSkill = scoped_lorelei_skill


def prepare():
    authenticate()
    assert not ROOT.exists(), "Existing continuation cannot be initialized again"
    facts = audit.native_state(SOURCE / "terminal.state")
    assert facts["field_ready"] and facts["hp"] == facts["max_hp"]
    assert not any(facts["status"])
    ROOT.mkdir(mode=0o700)
    p.ROOT.mkdir(mode=0o700)
    inherited = doc(SOURCE / "CONTEXT.json")["spent"]
    declaration = dict(
        source_directory=str(SOURCE),
        source_sha256=SOURCE_SHA,
        context_sha256=CONTEXT_SHA,
        previous_spent=inherited,
        limits=LIMITS,
        same_origin=True,
        new_initialization=False,
        origin_sha256=doc(previous.PARENT_ROOT / "fresh-pilot/PLAYER-PLAN.json")["origin_sha256"],
        original_opening=str(p.START),
        partition="development",
        official_exam=False,
        automatic_fit=False,
        state_edits=0,
        progress_stitching=False,
        work_order_sha256=c.digest(REPORT),
        helper_sha256=c.digest(Path(__file__)),
        scope="Same-save Champion/Hall of Fame and124native registrations;then user evaluation",
        assistance=(
            "Supplied work order/routes/phase mechanics/preparation/"
            "control screening remain explicit"
        ),
        candidate_model_file=str(previous.CANDIDATE),
        candidate_sha256=previous.CANDIDATE_SHA,
        stop_on_goal_completion=True,
        no_agent_imposed_session_deadline=True,
        native_worker_maximum_seconds=1800,
        native_worker_maximum_decisions=100,
        reassess_minutes=15,
        local_triage_minutes=10,
    )
    p._record(ROOT / "PLAN.json", declaration)
    p._record(p.ROOT / "PLAYER-PLAN.json", declaration)
    p.coordinator.port.status(latest_fresh_export=str(SOURCE))
    print(json.dumps(dict(prepared=True, same_save=True, inherited_spent=inherited)), flush=True)


def needs_restoration(raw, *, case=None):
    """Reuse ordinary nursing when meaningful, not for every spent PP/map crossing."""
    if raw.map_id in {int(c.MapId.FUCHSIA_CITY), int(c.MapId.FUCHSIA_GYM)}:
        return True
    if not raw.party_hp or not raw.party_max_hp or not raw.party_status:
        return True
    if len(raw.party_hp) != len(raw.party_max_hp):
        return True
    if any(raw.party_status) or any(
        hp * 10 < maximum * 7 for hp, maximum in zip(raw.party_hp, raw.party_max_hp, strict=True)
    ):
        return True
    if not raw.party_moves or not raw.party_pp:
        return True
    return any(
        not any(move and pp for move, pp in zip(moves, pps, strict=True))
        for moves, pps in zip(raw.party_moves, raw.party_pp, strict=True)
    )


def supply_profile(profile):
    providers = []
    for spec in profile.providers:
        parameters = p._thaw(spec.parameters)
        if spec.kind is c.GoalKind.RESUPPLY:
            parameters.update(
                map_id=int(c.MapId.SAFFRON_MART),
                purchases=[
                    dict(
                        absolute_index=0,
                        item_id=int(ItemId.GREAT_BALL),
                        quantity=10,
                        unit_price=600,
                    )
                ],
            )
        providers.append((spec.kind, spec.mechanic, parameters))
    return c.parse_red_goal_context_profile(
        c.build_red_goal_context_profile_payload(
            profile_id="earned-run-actual-great-ball-stock-v1", providers=tuple(providers)
        )
    )


def core(parent, output, *, stage="koga"):
    payload, factory0, menu, holder, source = p.assembly(parent, output)

    def factory(controller):
        rt = factory0(controller)
        rt = replace(rt, profile=supply_profile(rt.profile))
        actor = holder["actor"]
        raw = rt.reader.read()
        if stage == "league-preparation":
            from red_earned_preparation_actor_20261005 import PreparedWildBattler

            actor = PreparedWildBattler(
                **{field.name: getattr(actor, field.name) for field in fields(actor) if field.init}
            )
        contract = None
        reward = None
        if (
            stage == "sabrina"
            and not SABRINA_REWARD.received(raw)
            and raw.map_id
            in {int(c.MapId.SAFFRON_POKECENTER), int(c.MapId.SAFFRON_CITY), SABRINA_REWARD.map_id}
        ):
            contract = sabrina_contract(c.ROM.read_bytes(), raw)
            reward = SABRINA_REWARD
        if (
            stage == "koga"
            and not koga.KOGA_REWARD.received(raw)
            and raw.map_id == koga.KOGA_REWARD.map_id
        ):
            if p._field_ready(rt):
                row = koga.gym_story_option(
                    rt,
                    controller,
                    reward=koga.KOGA_REWARD,
                    route=koga.route_for(c.ROM.read_bytes()),
                    battler=actor,
                    preparation_plan=holder["plan"],
                )
                if row is not None and row[1].opposition_known:
                    contract = koga.KOGA_REWARD.contract(c.ROM.read_bytes(), raw)
            elif raw.battle_state == 2 and rt.reader.read_active_trainer_identity() == (238, 38, 1):
                contract = koga.engaged_story_contract(
                    rt.reader, c.ROM.read_bytes(), objective_id="defeat_koga"
                )
            if contract is not None:
                reward = koga.KOGA_REWARD
        if stage in {"blaine", "giovanni"}:
            wanted = blaine.BLAINE_REWARD if stage == "blaine" else giovanni.GIOVANNI_REWARD
            if raw.map_id == wanted.map_id and not wanted.received(raw):
                identity = (wanted.trainer_class, wanted.trainer_class - 200, wanted.trainer_set)
                admitted = (
                    raw.battle_state == 2 and rt.reader.read_active_trainer_identity() == identity
                )
                if p._field_ready(rt):
                    route = replace(koga.route_for(c.ROM.read_bytes()), allow_surf=True)
                    admitted = (
                        story_battle_binding(
                            rt,
                            controller,
                            contract=wanted.contract(c.ROM.read_bytes(), raw),
                            route=route,
                            battler=actor,
                            reward=wanted,
                        )
                        is not None
                    )
                if admitted:
                    contract, reward = wanted.contract(c.ROM.read_bytes(), raw), wanted
        if (
            stage == "victory"
            and raw.map_id == int(c.MapId.ROUTE_22)
            and not event_flag_is_set(raw.event_flags, 1318)
        ):
            contract = victory.rival_contract(rt)
        if stage == "league" and not league_requires_lobby_reset(raw) and not champion.complete(rt):
            if champion.champion_ready(raw):
                contract = champion.champion_contract(rt)
            else:
                target = champion.previous.retry_target(raw)
                if target is not None:
                    contract = champion.previous.contract(rt, *target)
        if contract is not None:
            candidate = TrainerPracticeThreeHeadModel.from_dict(doc(previous.CANDIDATE))
            scope = DevelopmentStoryScope(
                actor.source_state_sha256,
                actor.root_lineage_id,
                previous.CANDIDATE_SHA,
                c.canonical_sha256(candidate.to_dict()),
                c.digest(ROOT / "PLAN.json"),
                diagnostic_stay_when_productive=True,
                diagnostic_prompt_stay=(
                    contract.objective_id not in {"defeat_lance", "defeat_champion"}
                ),
                contract=contract,
                gym_reward=reward,
                screen_capped_status_moves=True,
            )
            actor = replace(
                actor,
                model=candidate,
                model_sha256=previous.CANDIDATE_SHA,
                qualification_sha256=scope.identity,
                development_story_scope=scope,
                pp_depleted_switch_screen=stage == "league",
            )
            actor.require_story_contract(contract)
            rt = replace(
                rt,
                trainer_battle_model_sha256=actor.model_sha256,
                trainer_battle_qualification_sha256=scope.identity,
            )
            if stage == "league":
                owner_type = (
                    ScopedAssistedChampionController
                    if contract.objective_id == "defeat_champion"
                    else ScopedAssistedLeagueRetryController
                )
                owner = owner_type(
                    actor,
                    contract,
                    (ROOT / "PLAN.json").read_bytes(),
                    80,
                    declared_model_sha256=previous.CANDIDATE_SHA,
                    declared_level_deficit=league_declared_deficit(output),
                )
                owner.require_identity()
                actor.pp_reentry_screen_active(actor.story_authority())
                rt = replace(
                    rt,
                    league_story_battle_controller=owner,
                    trainer_story_world=victory.phases.ground_route(c.ROM.read_bytes()).route_world,
                )
                holder["owner"] = owner
        if (
            stage == "league"
            and parent.name.startswith("segment-")
            and (int(parent.name.rsplit("-", 1)[1]) >= 103)
        ):
            # Prospective actual-loss response; older observations stay unchanged.
            rt.adapter.include_pp_restoration = True
        holder.update(
            actor=actor, history=NativeBattlerHistory(actor, initial=holder["history"].initial)
        )
        rt = replace(rt, trainer_battle_runner=actor.run)
        holder["runtime"] = rt
        return rt

    return payload, factory, menu, holder, source, None, None


def _retained_capture_loss_binding(rt, actions, target):
    """Use the existing exact Route12 loss proof only after all balls are gone."""
    from pokemon_red_completion.red_player_wild_recovery import interrupted_wild_binding
    from pokemon_red_completion.goal_manager import GoalDecisionOutcome

    raw = rt.reader.read()
    stock = dict(raw.bag_items or ())
    if target.species_number != 143 or any(stock.get(int(item), 0) for item in (
        ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL, ItemId.MASTER_BALL,
    )):
        raise ValueError("retained capture loss needs exhausted carried balls")
    # The historical proof is lead-centric. A fainted member or a non-lead
    # battler uses the same consumed-event proof through the whole-party RUN
    # executor, so an exhausted catch can still end instead of stopping play.
    hp, active = getattr(raw, "party_hp", None) or (), getattr(raw, "active_party_index", None)
    whole_party = bool(hp) and (any(value <= 0 for value in hp) or active != 0)
    recovery = interrupted_wild_binding(
        rt, actions, consumed_static_target=target, rom=c.ROM.read_bytes(),
        **({"allow_static_party_faints": True} if whole_party else {}),
    )
    if recovery is None:
        raise ValueError("retained capture loss lacks its exact live encounter")

    def verify_loss(report):
        verdict = recovery.verify(report)
        return (GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            if verdict.status is GoalDecisionOutcome.SUCCEEDED else verdict)

    return replace(recovery,
        binding_ref="pokemon.red:retained-capture:" + c.sha256(rt.emulator.save_state_bytes()).hexdigest(),
        verify=verify_loss)


def retained_capture_binding(rt, actions, *, parent, output):
    """Continue the paused one-off;record exact Route12 loss after true exhaustion."""
    raw = rt.reader.read()
    target = route12_snorlax_target(c.ROM.read_bytes())
    identity = rt.reader.read_wild_capture_identity() if raw.battle_state == 1 else None
    if identity is not None and (raw.map_id, identity.original_species_id, raw.enemy_level) != (
            target.map_id, target.internal_species, target.level):
        from red_earned_unique_collection_20261006 import enabled, UNIQUE_NUMBERS
        from pokemon_red_completion.red_static_capture import red_static_capture_targets
        if enabled(__import__(__name__), output):
            target = next((t for t in red_static_capture_targets(c.ROM.read_bytes())
                if t.species_number in UNIQUE_NUMBERS and (raw.map_id,
                    identity.original_species_id,raw.enemy_level)==(t.map_id,t.internal_species,t.level)), target)
    if identity is None or (raw.map_id, identity.original_species_id, raw.enemy_level) != (
        target.map_id,
        target.internal_species,
        target.level,
    ):
        return None
    receipt_parent = parent
    pattern = "snorlax-*/*-paused/receipt.json" if target.species_number == 143 else "static-*/*-paused/receipt.json"
    receipts = sorted(receipt_parent.glob(pattern))
    while not receipts and (receipt_parent / "PLAN.json").exists():
        receipt_parent = Path(doc(receipt_parent / "PLAN.json")["source_directory"])
        assert (receipt_parent / "terminal.state").read_bytes() == (
            parent / "terminal.state"
        ).read_bytes()
        receipts = sorted(receipt_parent.glob(pattern))
    if not receipts:
        raise ValueError("live one-off needs its exact retained paused receipt")
    receipt = receipts[-1]
    data = doc(receipt)
    saved = load_capture_checkpoint(
        receipt.parent,
        expected_receipt_sha256=c.digest(receipt),
        expected_origin_sha256=data["origin_state_sha256"],
        expected_target=target,
        expected_allocation_sha256=data["allocation_sha256"],
    )
    assert saved.state == (parent / "terminal.state").read_bytes()
    saved.require_live_resume(rt.reader, target, emulator=rt.emulator)
    prepare = saved.status_preparer(rt.emulator, actions, rt.reader)
    # Prospective ordinary-game extension; keep all five earlier committed throws.
    budget = (replace(saved.budget, max_throws=saved.budget.initial_ball_count)
        if target.species_number == 143 else saved.budget)
    if target.species_number == 143 and budget.throws_committed == budget.initial_ball_count:
        stock = dict(raw.bag_items or ())
        # Continue the same retained encounter with carried ordinary stock.
        # Preserve the existing Poke Ball preference and Master-only behavior;
        # Great/Ultra stock must not be mistaken for an empty bag.
        ball = next((item for item in (
            ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL,
            ItemId.MASTER_BALL,
        ) if stock.get(int(item), 0) > 0), None)
        if ball is None:
            return _retained_capture_loss_binding(rt, actions, target)
        count = stock[int(ball)]
        budget = OneOffCaptureBudget(
            OneOffCaptureRequest(target.internal_species, target.level, ball),
            count,
            count,
        )
    initial_owned = rt.reader.read_pokedex_state().owned_species
    origin = rt.emulator.save_state_bytes()
    used, completed, terminal, report, lost = False, False, None, None, False
    journal = output / ("snorlax-retained" if target.species_number == 143
        else f"static-{target.species_number}-retained")
    decisions, receipt_hashes = [], []
    parent_receipt = saved.receipt_sha256

    def checkpoint(phase):
        nonlocal parent_receipt
        parent_receipt = write_capture_checkpoint(
            journal / f"{len(receipt_hashes):03d}-{phase}",
            state=rt.emulator.save_state_bytes(),
            origin_state_sha256=data["origin_state_sha256"],
            target=target,
            budget=budget,
            status_attempts=prepare.attempts,
            maximum_status_attempts=saved.maximum_status_attempts,
            preserve_viable_active=saved.preserve_viable_active,
            minimum_prepared_helper_level=saved.minimum_prepared_helper_level,
            phase=phase,
            parent_receipt_sha256=parent_receipt,
        )
        receipt_hashes.append(parent_receipt)

    def execute():
        nonlocal used, completed, terminal, report, lost, budget
        if used or rt.emulator.save_state_bytes() != origin:
            raise ValueError("retained one-off binding stale or consumed")
        used = True
        create_capture_journal(journal)
        if target.species_number == 143:
            p._record(
            output / "CAPTURE-ALLOWANCE-EXTENSION.json",
            dict(
                prior_receipt_sha256=saved.receipt_sha256,
                prior_budget=asdict(saved.budget),
                prospective_budget=asdict(budget),
                retained_prior_throws=saved.budget.throws_committed,
                source_reset=False,
                learned_ball_choice=False,
                ordinary_game_mode=True,
            ),
            )
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        checkpoint("paused")
        def before_throw():
            from pokemon_red_completion.red_one_off_capture import OneOffCapturePaused
            from pokemon_red_completion.red_capture_status_runtime import (
                CaptureStatusDrift, RedCaptureStatusError)
            try:
                ready = prepare()
            except RedCaptureStatusError as error:
                # Nobody is above half health to act as a prepared catcher. An
                # ordinary player keeps throwing with whoever is in; the ball
                # executor still proves the live encounter, lead and bag first.
                if (target.species_number != 143
                        or error.reason_code != CaptureStatusDrift.NO_HEALTHY_CATCHER
                        or rt.reader.read().battle_state != 1):
                    raise
                ready = True
            if target.species_number != 143 and rt.reader.read_enemy_capture_status() not in (
                    1,2,3,4,5,6,7,0x20,0x40):
                raise OneOffCapturePaused("retained unique status is absent; no ball spent")
            return ready
        from red_remaining_static_20261004 import native_catcher_recovery
        try:
          with native_catcher_recovery() if target.species_number != 143 else nullcontext():
            from pokemon_red_completion.red_one_off_capture import OneOffCapturePaused
            # One pass per carried ball kind: when a kind is spent and another
            # is still in the bag, the same live encounter continues with it.
            for _ in range(4):
                try:
                    captured = run_one_off_capture(
                        rt.emulator,
                        actions,
                        rt.reader,
                        budget.request,
                        max_throws=budget.max_throws,
                        budget=budget,
                        before_throw=before_throw,
                        status_preparer=prepare,
                        select_replacement=lambda now: max(
                            ((hp, i)
                             for i, hp in enumerate(now.party_hp)
                             if hp > 0 and i != now.active_party_index),
                            default=(0, -1),
                        )[1],
                        record_decision=decisions.append,
                        commit_throw=lambda _: checkpoint("throw_intent"),
                    )
                    break
                except OneOffCapturePaused as error:
                    stock = dict(rt.reader.read().bag_items or ())
                    if (target.species_number != 143
                            or str(error) not in {
                                "throw budget exhausted; live encounter retained without Run",
                                "throw budget exhausted at catcher faint"}
                            or budget.throws_committed != budget.initial_ball_count):
                        raise
                    ball = next((item for item in (
                        ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL,
                        ItemId.MASTER_BALL) if stock.get(int(item), 0) > 0), None)
                    if ball is not None:
                        count = stock[int(ball)]
                        budget = OneOffCaptureBudget(
                            OneOffCaptureRequest(target.internal_species, target.level, ball),
                            count,
                            count,
                        )
                        continue
                    recovery = _retained_capture_loss_binding(rt, actions, target)
                    recovery_report = recovery.execute()
                    recovery_verdict = recovery.verify(recovery_report)
                    if recovery_verdict.failure_reason is not GoalFailureReason.RESOURCE_LOST:
                        raise ValueError("retained capture loss was not independently verified")
                    lost = True
                    break
            else:
                raise ValueError("retained capture exceeded its finite ball-kind passes")
            if not lost:
                settled = settle_static_capture(
                    actions,
                    rt.reader,
                    target,
                    captured=captured,
                    budget=budget,
                    initial_money=raw.player_money,
                    initial_owned=initial_owned,
                )
                completed = settled.captured and settled.consumed_event and settled.source_removed
        finally:
            checkpoint("settled" if completed or lost else "paused")
        terminal = rt.emulator.save_state_bytes()
        report = GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(
                mechanic="static_capture",
                captured=completed,
                **({"lost_static_target": asdict(target)} if lost else {}),
                capture_resume=True,
                source_reset=False,
                prior_throws=saved.budget.throws_committed,
                throws_committed=budget.throws_committed,
                decisions=decisions,
                receipts=receipt_hashes,
                learned_ball_selection=False,
            ),
        )
        return report

    def verify(candidate):
        now = rt.reader.read()
        if (lost and candidate is report
                and terminal == rt.emulator.save_state_bytes()
                and p._field_ready(rt) and not rt.emulator.pressed_buttons
                and rt.reader.read_pokedex_state().owned_species == initial_owned
                and event_flag_is_set(now.event_flags, target.event_flag)
                and now.player_money == raw.player_money):
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        passed = (
            completed
            and candidate is report
            and terminal == rt.emulator.save_state_bytes()
            and p._field_ready(rt)
            and not rt.emulator.pressed_buttons
            and rt.reader.read_pokedex_state().owned_species == initial_owned | {target.species_number}
            and event_flag_is_set(now.event_flags, target.event_flag)
            and now.player_money == raw.player_money
        )
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:retained-capture:" + c.sha256(origin).hexdigest(),
        c.GoalKind.RECOVER_CONTROL,
        0.1,
        0.2,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def strongest_field_lead(rt, actions):
    if not p._field_ready(rt):
        return None
    party = rt.adapter.observe().party
    viable = tuple(
        i
        for i, member in enumerate(party.members)
        if member.hp * 10 >= member.max_hp * 7 and member.status.value == "healthy"
    )
    if not viable:
        return None
    plan = RedCaptureLeadPlan(max(viable, key=lambda i: party.members[i].level), party)
    if not plan.requires_swap:
        return None
    source, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or rt.emulator.save_state_bytes() != source:
            raise ValueError("native field lead stale or consumed")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        prepare_observed_lead(rt, actions, plan, label="supplied strongest story lead")
        terminal = rt.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(
                supplied_not_learned=True,
                native_party_permutation=True,
                original_slot=plan.target_index + 1,
                level=plan.target_member.level,
            ),
        )

    def verify(_):
        passed = used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
        if passed:
            plan.require_result(rt.adapter.observe().party)
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:strongest-field-lead:" + c.sha256(source).hexdigest(),
        c.GoalKind.RECOVER_CONTROL,
        0.01,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def koga_assembly(parent, output):
    # The old route builder discarded its already assembled resource inventory.
    # Capture that SAME assembly, not another runtime/actor, and expose its shop.
    original = koga.old.regional.assembly
    captured = {}

    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        captured["menu"] = result[2]
        return result

    koga.old.regional.assembly = capture
    try:
        payload, factory, menu, holder, source = koga.assembly(parent, output)
    finally:
        koga.old.regional.assembly = original

    def base(runtime, actions, observation):
        binding = retained_capture_binding(runtime, actions, parent=parent, output=output)
        if binding is None:
            binding = strongest_field_lead(runtime, actions)
        if binding is None:
            binding = p.engaged_story_binding(
                runtime,
                actions,
                rom=c.ROM.read_bytes(),
                battler=holder["actor"],
                objective_id="reach_fuchsia",
            )
        if binding is not None:
            return p.GoalBindingSet(
                tuple(
                    binding.opportunity
                    if kind is binding.kind
                    else p.GoalOpportunity(
                        "earned-run:" + kind.value,
                        kind,
                        p.GoalAvailability.UNAVAILABLE,
                        unavailable_reason=p.GoalUnavailableReason.TEMPORARILY_BLOCKED,
                    )
                    for kind in c.GoalKind
                ),
                (binding,),
            )
        ordinary = menu.enumerate_base(runtime, actions, observation)
        if not p._field_ready(runtime) or any(
            binding.kind is c.GoalKind.RECOVER_CONTROL for binding in ordinary.bindings
        ):
            return ordinary
        target = route12_snorlax_target(c.ROM.read_bytes())
        if event_flag_is_set(runtime.reader.read().event_flags, target.event_flag):
            # The special capture stock offer was needed only before this encounter.
            return ordinary
        resources = captured["menu"].enumerate_base(runtime, actions, observation)
        shops = tuple(
            binding for binding in resources.bindings if binding.kind is c.GoalKind.RESUPPLY
        )
        if not shops:
            return ordinary
        return p.GoalBindingSet(
            tuple(
                opportunity
                for opportunity in ordinary.opportunities
                if opportunity.kind is not c.GoalKind.RESUPPLY
            )
            + tuple(binding.opportunity for binding in shops),
            tuple(
                binding for binding in ordinary.bindings if binding.kind is not c.GoalKind.RESUPPLY
            )
            + shops,
            allow_resource_variants=resources.allow_resource_variants,
        )

    return (
        payload,
        factory,
        p.NativeStoryBranchInventory(base, menu.enumerate_branches),
        holder,
        source,
    )


def safari_complete(rt):
    proof = safari.native_proof(rt)
    return bool(
        all(proof["events"].values())
        and proof["hm03"] == proof["hm04"] == 1
        and proof["teeth"] == 0
        and proof["surf_living"]
        and proof["strength_living"]
        and proof["soul_badge"]
        and proof["healthy"]
        and proof["field_ready"]
        and proof["map"] == int(c.MapId.FUCHSIA_POKECENTER)
    )


def regional(parent, output, *, stage):
    return koga.old.regional.assembly(
        parent,
        output,
        base_assembly=partial(core, stage=stage),
        capture_reserve=RESERVE,
        attempt_root=p.ROOT / "runs",
    )


def forward_target(rt, route, *, destination):
    """Reuse native capabilities and stop at the first real map boundary."""
    live = route.route_world.with_current_observation(rt.reader)
    start = Gen1TraversalObserver(
        rt.reader, capability_projector=partial(gen1_field_capabilities, rt.emulator)
    ).observe()
    plan = live.plan_feasible_to_map(start, destination, goal_at=(3, 3))
    first = next((s for s in plan.steps if s.expected_map != start.map_id), None)
    return (first.expected_map, first.expected_at) if first else (destination, plan.terminal_at)


def center_anchor_approach(rt, actions):
    """Place a healthy new arrival at the nurse before the existing anchor dialogue."""
    raw = rt.reader.read()
    if (
        not p._field_ready(rt)
        or raw.map_id != int(c.MapId.CINNABAR_POKECENTER)
        or rt.reader.read_last_blackout_map() == int(c.MapId.CINNABAR_ISLAND)
        or (raw.player_y, raw.player_x) == (3, 3)
    ):
        return None
    route = replace(
        koga.route_for(c.ROM.read_bytes()), destination_map=raw.map_id, destination_at=(3, 3)
    )
    source, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or source != rt.emulator.save_state_bytes():
            raise ValueError("stale native nurse approach")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        route(actions, rt.reader, rt.emulator)
        terminal = rt.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(supplied_not_learned=True, native_nurse_approach=True),
        )

    def verify(_):
        after = rt.reader.read()
        unchanged = all(
            getattr(after, key) == getattr(raw, key)
            for key in (
                "party_species_ids",
                "party_levels",
                "party_moves",
                "party_hp",
                "party_pp",
                "party_status",
                "bag_items",
                "badge_bits",
                "player_money",
            )
        )
        passed = (
            used
            and terminal == rt.emulator.save_state_bytes()
            and p._field_ready(rt)
            and (after.map_id, after.player_y, after.player_x) == (raw.map_id, 3, 3)
            and unchanged
        )
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:nurse-approach:" + c.sha256(source).hexdigest(),
        c.GoalKind.RESTORE_TEAM,
        0.01,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def inventory_clearance_binding(rt, actions, *, archive_items=(), keep_scope=False):
    """Conserve completed story keys in the existing native item PC, not sales."""
    from pokemon_red_completion import sabrina as storage
    from pokemon_red_completion.red_story_item_storage import archive_completed_story_keys

    archive_items = tuple(ItemId(item) for item in archive_items)
    if type(keep_scope) is not bool:
        raise ValueError("collection Scope retention must be boolean")
    if not set(archive_items) <= {ItemId.TM34_BIDE, ItemId.TM46_PSYWAVE, ItemId.TM27_FISSURE}:
        raise ValueError("only the declared surplus machines may be archived")
    raw = rt.reader.read()
    if not p._field_ready(rt) or len(raw.bag_items or ()) < 19:
        return None
    discarded_from_bag = {
        int(ItemId.SILPH_SCOPE),
        int(ItemId.CARD_KEY),
        int(ItemId.LIFT_KEY),
        int(ItemId.SS_TICKET),
    }
    discarded_from_bag.update(map(int, archive_items))
    if keep_scope:
        discarded_from_bag.discard(int(ItemId.SILPH_SCOPE))
    available = discarded_from_bag & dict(raw.bag_items).keys()
    if not available:
        return None
    flight = flight_binding(
        rt, actions, town=int(c.MapId.SAFFRON_CITY), objective="cross_victory_road"
    )
    if flight is not None:
        return flight
    route = koga.route_for(c.ROM.read_bytes())
    origin, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or origin != rt.emulator.save_state_bytes():
            raise ValueError("stale native completed-key storage")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        replace(route, destination_map=int(c.MapId.SAFFRON_POKECENTER), destination_at=(3, 3))(
            actions, rt.reader, rt.emulator
        )
        before = rt.reader.read()
        pc_before = dict(rt.reader.read_pc_items())
        expected_bag, expected_pc = dict(before.bag_items), dict(pc_before)
        for item in available:
            quantity = expected_bag.pop(item)
            expected_pc[item] = expected_pc.get(item, 0) + quantity
        if len(expected_pc) > 50 or any(count > 99 for count in expected_pc.values()):
            raise ValueError("native item PC lacks capacity for the declared storage")
        archived_keys = storage._sabrina_capacity_deposit_items(dict(before.bag_items))
        result = (
            archive_completed_story_keys(rt.emulator, rt.reader, actions)
            if archived_keys is not None and archived_keys
                and not (keep_scope and ItemId.SILPH_SCOPE in archived_keys)
            else None
        )
        extra = [
            item
            for item in map(ItemId, sorted(available))
            if int(item) in dict(rt.reader.read().bag_items)
        ]
        if extra:
            replace(route, destination_map=int(c.MapId.SAFFRON_POKECENTER), destination_at=(4, 13))(
                actions, rt.reader, rt.emulator
            )
            for item in extra:
                storage._deposit_pc_item(
                    actions, rt.reader, rt.emulator, item, storage.DEFAULT_SILPH_TIMING
                )
            replace(route, destination_map=int(c.MapId.SAFFRON_POKECENTER), destination_at=(3, 3))(
                actions, rt.reader, rt.emulator
            )
        after = rt.reader.read()
        assert dict(after.bag_items) == expected_bag
        assert dict(rt.reader.read_pc_items()) == expected_pc
        assert all(
            getattr(after, key) == getattr(before, key)
            for key in (
                "party_species_ids",
                "party_levels",
                "party_moves",
                "party_hp",
                "party_pp",
                "party_status",
                "badge_bits",
                "player_money",
                "event_flags",
            )
        )
        terminal = rt.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(
                native_story_key_storage=True,
                supplied_not_learned=True,
                stored_items=sorted(available),
                archived=result,
                pc_before=sorted(pc_before.items()),
                pc_after=sorted(expected_pc.items()),
                sold_items=0,
                inventory_conserved=True,
            ),
        )

    def verify(_):
        passed = used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:completed-key-storage:" + c.sha256(origin).hexdigest(),
        c.GoalKind.RECOVER_CONTROL,
        0.1,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def retained_corridor_binding(rt, actions, *, output):
    """Continue the actual corridor with its existing authenticated guard dialogue."""
    from pokemon_red_completion.red_badge_corridor import traverse_badge_corridor

    if not p._field_ready(rt) or rt.reader.read().map_id != int(c.MapId.ROUTE_23):
        return None
    origin, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        assert not used and origin == rt.emulator.save_state_bytes()
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count

        def record(name, value):
            def plain(row):
                if is_dataclass(row):
                    return plain(asdict(row))
                if isinstance(row, dict):
                    return {str(k): plain(v) for k, v in row.items()}
                if isinstance(row, (tuple, list, set, frozenset)):
                    return [plain(v) for v in row]
                return row

            p._record(output / ("retained-corridor-" + name + ".json"), plain(value))

        final = traverse_badge_corridor(
            c.ROM.read_bytes(),
            rt.reader,
            rt.emulator,
            actions,
            record=record,
            maximum_flees=40,
            allow_retained_boundary=True,
        )
        terminal = rt.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(supplied_not_learned=True, retained_corridor=True, map=final.map_id),
        )

    def verify(_):
        passed = used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:retained-corridor:" + c.sha256(origin).hexdigest(),
        c.GoalKind.ADVANCE_STORY,
        0.1,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
        story_objective_ref="cross_victory_road",
    )


def flight_binding(rt, actions, *, town, objective):
    """Connect the already-owned native Fly executor, with actual visited-town guards."""
    if not p._field_ready(rt) or town not in rt.reader.read_fly_destinations():
        return None
    raw = rt.reader.read()
    start = Gen1TraversalObserver(rt.reader).observe()
    if start.map_id == town or (start.map_id >= 0x25 and start.last_outside_map == town):
        return None
    if start.map_id < 0x25:
        if start.mode != "land" or start.map_id == 11:
            return None
        plan = None
    else:
        route = replace(koga.route_for(c.ROM.read_bytes()), allow_surf=True)
        plan = route.route_world.with_current_observation(rt.reader).plan_feasible_to_map(
            start, start.last_outside_map
        )
    source, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or rt.emulator.save_state_bytes() != source:
            raise ValueError("stale supplied native flight")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        if plan is not None:
            replace(route, destination_map=start.last_outside_map, destination_at=plan.terminal_at)(
                actions, rt.reader, rt.emulator
            )
            label, target = "indoor departure before native Fly", start.last_outside_map
        else:
            Gen1FieldMovePort(actions, rt.reader, rt.emulator).execute(
                MacroAction(
                    MacroActionKind.FIELD_MOVE,
                    "fly:" + RED_FLY_TOWN_NAMES[town].lower().replace(" ", "_"),
                )
            )
            label, target = "native Fly to observed visited town", town
        now = rt.reader.read()
        for key in (
            "player_money",
            "bag_items",
            "party_species_ids",
            "party_levels",
            "party_hp",
            "party_pp",
            "party_moves",
            "party_status",
            "badge_bits",
        ):
            assert getattr(now, key) == getattr(raw, key)
        assert now.map_id == target and p._field_ready(rt)
        terminal = rt.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a0,
            rt.emulator.frame_count - f0,
            dict(
                supplied_not_learned=True,
                transport=label,
                destination=target,
                objective=objective,
                objective_completed=False,
            ),
        )

    def verify(_):
        return (
            GoalVerification.succeeded()
            if terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:native-flight:" + c.sha256(source).hexdigest(),
        c.GoalKind.ADVANCE_STORY,
        0.01,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
        story_objective_ref=objective,
    )


def preparation_machine_choice(moves, bag):
    """Disclosed owned coverage lessons; never obtain or manufacture a machine."""
    if 85 not in moves and bag.get(int(ItemId.TM24_THUNDERBOLT), 0) and 0 in moves:
        return int(ItemId.TM24_THUNDERBOLT), moves.index(0) + 1
    if 57 not in moves and bag.get(int(ItemId.HM03_SURF), 0):
        if 0 in moves:
            return int(ItemId.HM03_SURF), moves.index(0) + 1
        if 133 in moves:
            return int(ItemId.HM03_SURF), moves.index(133) + 1
    return None


def league_requires_lobby_reset(raw):
    # Whiteout preserves stale room flags until ordinary native lobby re-entry.
    return raw.map_id == int(c.MapId.INDIGO_PLATEAU)


def league_pp_restore_needed(raw):
    if 28 not in raw.party_species_ids:
        return False
    slot = raw.party_species_ids.index(28)
    useful = [
        (move, pp & 63) for move, pp in zip(raw.party_moves[slot], raw.party_pp[slot], strict=True)
    ]
    return raw.party_hp[slot] > 0 and (
        sum(pp for move, pp in useful if move in {57, 58, 70, 89, 91}) <= 4
        or not sum(pp for move, pp in useful if move in {57, 58, 89, 91})
        or (
            getattr(raw, "map_id", None) == int(c.MapId.BRUNOS_ROOM)
            and sum(pp for move, pp in useful if move in {57, 58, 89, 91}) < 12
        )
        or (
            getattr(raw, "map_id", None) == int(c.MapId.LANCES_ROOM)
            and sum(pp for move, pp in useful if move in {57, 58, 89, 91}) < 16
        )
    )


def league_coverage_needed(raw):
    return (
        28 in raw.party_species_ids and 89 not in raw.party_moves[raw.party_species_ids.index(28)]
    )


def league_coverage_binding(rt, actions, *, output):
    """Earn native TM26 and replace Tail Whip, preserving the three existing attacks."""
    from pokemon_red_completion.red_field_item import collect_visible_field_item, red_field_items
    from pokemon_red_completion.red_machine_teaching import (
        execute_machine_lesson,
        plan_machine_lesson,
    )
    from pokemon_red_completion.red_pc_storage import (
        close_generic_pc_session,
        face_pc_boundary,
        open_reds_pc,
        withdraw_single_pc_item,
    )
    from pokemon_red_completion.surge import _pulse

    if (
        not p._field_ready(rt)
        or not (ROOT / "CHAMPION-COVERAGE-PIVOT.json").exists()
        or (output.name.startswith("segment-") and int(output.name.rsplit("-", 1)[1]) <= 134)
    ):
        return None
    raw = rt.reader.read()
    if not league_coverage_needed(raw):
        return None
    route = victory.phases.ground_route(c.ROM.read_bytes())
    origin, used, terminal = rt.emulator.save_state_bytes(), False, None
    bag = dict(raw.bag_items)
    if bag.get(226, 0):
        slot = raw.party_species_ids.index(28) + 1
        lesson = plan_machine_lesson(
            c.ROM.read_bytes(),
            rt.reader,
            item_id=226,
            party_slot=slot,
            replace_slot=raw.party_moves[slot - 1].index(39) + 1,
        )
        label = "teach-owned-earthquake"

        def operation():
            execute_machine_lesson(rt.emulator, actions, rt.reader, lesson, rom=c.ROM.read_bytes())
            return asdict(lesson)
    else:
        flight = flight_binding(
            rt, actions, town=int(c.MapId.SAFFRON_CITY), objective="defeat_champion"
        )
        if flight is not None:
            return flight
        if not bag.get(int(ItemId.CARD_KEY), 0):
            assert dict(rt.reader.read_pc_items()).get(int(ItemId.CARD_KEY)) == 1
            label = "withdraw-earned-card-key"

            def operation():
                replace(
                    route, destination_map=int(c.MapId.SAFFRON_POKECENTER), destination_at=(4, 13)
                )(actions, rt.reader, rt.emulator)
                face_pc_boundary(actions, rt.reader, "up")
                open_reds_pc(actions, rt.reader)
                report = withdraw_single_pc_item(actions, rt.reader, item_id=int(ItemId.CARD_KEY))
                close_generic_pc_session(actions, rt.reader)
                return asdict(report)
        else:
            (target,) = red_field_items(c.ROM.read_bytes(), 226)
            assert (target.map_id, target.at) == (234, (12, 2))
            label = "collect-native-earthquake"

            def operation():
                # The native door is block (5,4), i.e. x10/y8. Card Key
                # interaction opens it; the observed route then reaches the item.
                replace(route, destination_map=234, destination_at=(9, 10))(
                    actions, rt.reader, rt.emulator
                )
                face_pc_boundary(actions, rt.reader, "up")
                before = rt.reader.read()
                _pulse(actions, MacroActionKind.INTERACT, frames=120)
                for _ in range(12):
                    _pulse(actions, MacroActionKind.CANCEL, frames=120)
                    if p._field_ready(rt):
                        break
                after = rt.reader.read()
                for name in (
                    "bag_items",
                    "player_money",
                    "party_species_ids",
                    "party_levels",
                    "party_hp",
                    "party_pp",
                    "party_moves",
                    "party_status",
                ):
                    assert getattr(after, name) == getattr(before, name), name
                # The east adjacent tile is a desk, not floor. The observed
                # west tile is walkable and faces the same cartridge item.
                replace(route, destination_map=target.map_id, destination_at=(12, 1))(
                    actions, rt.reader, rt.emulator
                )
                face_pc_boundary(actions, rt.reader, "right")
                collect_visible_field_item(actions, rt.reader, target)
                return dict(item=226, actual_quantity=1, native_pickup=True)

    def execute():
        nonlocal used, terminal
        if used or origin != rt.emulator.save_state_bytes():
            raise ValueError("stale earned coverage option")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        result = operation()
        terminal = rt.emulator.save_state_bytes()
        receipt = dict(supplied_not_learned=True, native_only=True, result=result)
        p._record(output / (label.upper() + ".json"), receipt)
        return GoalExecutionReport(
            actions.actions_executed - a0, rt.emulator.frame_count - f0, receipt
        )

    def verify(_):
        return (
            GoalVerification.succeeded()
            if used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:" + label + ":" + c.sha256(origin).hexdigest(),
        c.GoalKind.RESUPPLY,
        0.1,
        0.02,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def earned_champion_reserve_recipient(raw):
    """Current actual useful reserve, not the old Raticate-only checkpoint."""
    if (
        raw.map_id != int(c.MapId.LANCES_ROOM)
        or not event_flag_is_set(raw.event_flags, EventFlag.BEAT_LANCE)
        or event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
    ):
        return None
    for index, species in enumerate(raw.party_species_ids):
        if (
            species == 132
            and 85 in raw.party_moves[index]
            and (raw.party_pp[index][raw.party_moves[index].index(85)] & 63)
            and (raw.party_hp[index] < raw.party_max_hp[index] or raw.party_status[index])
        ):
            return index
    return None


def earned_champion_reserve_care(rt, actions, observation, *, output):
    if not p._field_ready(rt) or (
        output.name.startswith("segment-") and int(output.name.rsplit("-", 1)[1]) < 144
    ):
        return None
    recipient = earned_champion_reserve_recipient(rt.reader.read())
    if recipient is None:
        return None
    return (
        champion.m.RedFaintAwareFieldRestoreGoalProvider(
            actions,
            rt.reader,
            rt.emulator,
            rt.adapter,
            allowed_items=champion.m.legacy.HEALING,
            eligible_party_indices=frozenset({recipient}),
        )
        .offer(observation)
        .binding
    )


HIDDEN_LEAGUE_ELIXIRS = (
    (int(c.MapId.CERULEAN_CITY), int(c.MapId.ROUTE_25), (1, 10)),
    (int(c.MapId.LAVENDER_TOWN), int(c.MapId.POKEMON_TOWER_5F), (12, 4)),
)


def collect_observed_hidden_elixir(rt, actions, *, map_id, at):
    """One taught hidden-item interaction, with actual exact native gain proof."""
    from pokemon_red_completion.surge import _pulse

    raw = rt.reader.read()
    facing = rt.reader.read_player_facing()
    dy, dx = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[facing]
    assert p._field_ready(rt) and raw.map_id == map_id
    assert (raw.player_y + dy, raw.player_x + dx) == at
    expected = dict(raw.bag_items)
    expected[82] = expected.get(82, 0) + 1
    assert len(expected) <= 20 and expected[82] <= 99
    boxes, dex, pc = (
        rt.reader.read_all_box_states(),
        rt.reader.read_pokedex_state(),
        rt.reader.read_pc_items(),
    )
    protected = (
        "map_id",
        "player_y",
        "player_x",
        "player_money",
        "party_species_ids",
        "party_levels",
        "party_hp",
        "party_max_hp",
        "party_pp",
        "party_moves",
        "party_status",
        "badge_bits",
        "battle_state",
    )
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(48):
        current = rt.reader.read()
        assert all(getattr(current, k) == getattr(raw, k) for k in protected)
        assert rt.reader.read_all_box_states() == boxes
        assert rt.reader.read_pokedex_state() == dex and rt.reader.read_pc_items() == pc
        assert dict(current.bag_items) in (dict(raw.bag_items), expected)
        if dict(current.bag_items) == expected and p._field_ready(rt):
            return dict(item=82, native_gain=1, hidden_item=True, map=map_id, at=at)
        _pulse(actions, MacroActionKind.CANCEL, frames=120)
    raise ValueError("hidden Elixir was not actually gained; retain native aftermath")


def league_hidden_pp_supply_binding(rt, actions, *, output):
    """Two finite legitimate pickups, not a respawn or a new item factory."""
    from pokemon_red_completion.red_pc_storage import face_pc_boundary
    from pokemon_red_completion.route_plan import RoutePlanningError

    if (
        not p._field_ready(rt)
        or not (ROOT / "HIDDEN-PP-SUPPLY-PIVOT.json").exists()
        or (output.name.startswith("segment-") and int(output.name.rsplit("-", 1)[1]) < 154)
    ):
        return None
    raw = rt.reader.read()
    if raw.map_id in {245, 246, 247, 113, 120, 118}:
        return None
    pending = [
        (index, row)
        for index, row in enumerate(HIDDEN_LEAGUE_ELIXIRS)
        if not (ROOT / f"HIDDEN-ELIXIR-{index}.json").exists()
    ]
    if not pending:
        return None
    index, (town, map_id, target) = pending[0]
    flight = flight_binding(rt, actions, town=town, objective="defeat_champion")
    if flight is not None:
        return flight
    route = victory.phases.ground_route(c.ROM.read_bytes())
    world = route.route_world.with_current_observation(rt.reader)
    start = Gen1TraversalObserver(rt.reader).observe()
    poses = []
    for dy, dx, facing in ((1, 0, "up"), (-1, 0, "down"), (0, 1, "left"), (0, -1, "right")):
        at = (target[0] + dy, target[1] + dx)
        if min(at) < 0:
            continue
        try:
            plan = world.plan_feasible_to_map(start, map_id, goal_at=at)
        except RoutePlanningError:
            continue
        poses.append((plan.cost, at, facing))
    if not poses:
        raise ValueError("no observed feasible hidden-Elixir adjacency")
    _, at, facing = min(poses)
    origin, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or origin != rt.emulator.save_state_bytes():
            raise ValueError("stale hidden-Elixir supply")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        replace(route, destination_map=map_id, destination_at=at)(actions, rt.reader, rt.emulator)
        face_pc_boundary(actions, rt.reader, facing)
        result = collect_observed_hidden_elixir(rt, actions, map_id=map_id, at=target)
        terminal = rt.emulator.save_state_bytes()
        receipt = dict(
            result=result,
            native_pickup=True,
            supplied_not_learned=True,
            source_sha256=c.sha256(origin).hexdigest(),
            terminal_sha256=c.sha256(terminal).hexdigest(),
        )
        p._record(output / f"HIDDEN-ELIXIR-{index}.json", receipt)
        p._record(ROOT / f"HIDDEN-ELIXIR-{index}.json", dict(directory=str(output), **receipt))
        return GoalExecutionReport(
            actions.actions_executed - a0, rt.emulator.frame_count - f0, receipt
        )

    def verify(_):
        return (
            GoalVerification.succeeded()
            if used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:hidden-elixir:" + c.sha256(origin).hexdigest(),
        c.GoalKind.RESUPPLY,
        0.1,
        0.02,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def league_pp_support_binding(rt, actions, *, output):
    """Reuse exact owned-Elixir application and one real cartridge pickup."""
    from pokemon_red_completion.red_field_item import collect_visible_field_item, red_field_items
    from pokemon_red_completion.red_field_pp_restore import RedFieldPpRestoreGoalProvider
    from pokemon_red_completion.red_pc_storage import face_pc_boundary

    if not p._field_ready(rt) or not (ROOT / "PP-SUPPLY-PIVOT.json").exists():
        return None
    raw = rt.reader.read()
    held = dict(raw.bag_items or ()).get(int(ItemId.ELIXIR), 0)
    rooms = {
        int(m)
        for m in (
            c.MapId.LORELEIS_ROOM,
            c.MapId.BRUNOS_ROOM,
            c.MapId.AGATHAS_ROOM,
            c.MapId.LANCES_ROOM,
        )
    }
    if raw.map_id in rooms:
        if held and league_pp_restore_needed(raw):
            return (
                RedFieldPpRestoreGoalProvider(
                    actions, rt.reader, rt.emulator, rt.adapter, allow_fainted_reserves=True
                )
                .offer(rt.adapter.observe())
                .binding
            )
        return None
    supplied = ROOT / "ELIXIR-SUPPLY.json"
    if held or supplied.exists():
        if raw.map_id not in {int(c.MapId.INDIGO_PLATEAU), int(c.MapId.INDIGO_PLATEAU_LOBBY)}:
            return flight_binding(
                rt, actions, town=int(c.MapId.INDIGO_PLATEAU), objective="defeat_champion"
            )
        return None
    # The cartridge whiteout already heals this actual aftermath. Injured
    # arrivals still use the existing nurse; do not loop an indoor Fly departure.
    if raw.map_id == int(c.MapId.INDIGO_PLATEAU) and (
        not koga.old.v._raw_party_fully_restored(raw)
    ):
        return None
    flight = flight_binding(
        rt, actions, town=int(c.MapId.LAVENDER_TOWN), objective="defeat_champion"
    )
    if flight is not None:
        return flight
    (target,) = red_field_items(c.ROM.read_bytes(), int(ItemId.ELIXIR))
    assert (target.map_id, target.at) == (145, (10, 12))
    if len(raw.bag_items or ()) >= 20:
        raise ValueError("native Elixir detour needs actual bag space")
    route = victory.phases.ground_route(c.ROM.read_bytes())
    origin, used, terminal = rt.emulator.save_state_bytes(), False, None

    def execute():
        nonlocal used, terminal
        if used or origin != rt.emulator.save_state_bytes():
            raise ValueError("stale native Elixir detour")
        used = True
        a0, f0 = actions.actions_executed, rt.emulator.frame_count
        replace(route, destination_map=target.map_id, destination_at=(10, 13))(
            actions, rt.reader, rt.emulator
        )
        face_pc_boundary(actions, rt.reader, "left")
        collect_visible_field_item(actions, rt.reader, target)
        terminal = rt.emulator.save_state_bytes()
        receipt = dict(
            item=int(ItemId.ELIXIR),
            actual_quantity=1,
            native_pickup=True,
            source_sha256=c.sha256(origin).hexdigest(),
            terminal_sha256=c.sha256(terminal).hexdigest(),
            supplied_not_learned=True,
            source_reset=False,
        )
        p._record(output / "ELIXIR-PICKUP.json", receipt)
        p._record(supplied, dict(directory=str(output), **receipt))
        return GoalExecutionReport(
            actions.actions_executed - a0, rt.emulator.frame_count - f0, receipt
        )

    def verify(_):
        return (
            GoalVerification.succeeded()
            if used
            and terminal == rt.emulator.save_state_bytes()
            and p._field_ready(rt)
            and dict(rt.reader.read().bag_items).get(int(ItemId.ELIXIR)) == 1
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "earned-run:native-elixir:" + c.sha256(origin).hexdigest(),
        c.GoalKind.RESUPPLY,
        0.1,
        0.02,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def league_preparation_assembly(parent, output):
    """Native XP and nurses through the already implemented wild preparation skill."""
    import lorelei_current_party_20260929 as tools

    from pokemon_red_completion.hideout import HideoutTiming
    from pokemon_red_completion.party_preparation import PreparationPlan, PreparationPurpose
    from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored
    from pokemon_red_completion.red_machine_teaching import (
        execute_machine_lesson,
        plan_machine_lesson,
    )
    from pokemon_red_completion.red_party_preparation import observe_preparation_members
    from pokemon_red_completion.red_wild_preparation import execute_wild_preparation

    payload, factory, _, holder, source = regional(parent, output, stage="league-preparation")
    route = victory.phases.ground_route(c.ROM.read_bytes())

    def base(rt, actions, observation):
        raw = rt.reader.read()
        if not p._field_ready(rt):
            raise ValueError("retain live preparation scene for existing recovery")
        origin, used, terminal = rt.emulator.save_state_bytes(), False, None
        lesson = None
        if 132 in raw.party_species_ids:
            slot = raw.party_species_ids.index(132) + 1
            lesson_choice = preparation_machine_choice(
                raw.party_moves[slot - 1], dict(raw.bag_items)
            )
            if lesson_choice is not None:
                lesson = plan_machine_lesson(
                    c.ROM.read_bytes(),
                    rt.reader,
                    item_id=lesson_choice[0],
                    party_slot=slot,
                    replace_slot=lesson_choice[1],
                )
        healthy = _raw_party_fully_restored(raw)
        home = raw.map_id == int(c.MapId.INDIGO_PLATEAU_LOBBY)
        anchored = rt.reader.read_last_blackout_map() == int(c.MapId.INDIGO_PLATEAU)
        training = home and healthy and anchored and not league_levels_ready(raw)
        if home and healthy and anchored and league_levels_ready(raw):
            return p.GoalBindingSet((), ())
        kind = c.GoalKind.DEVELOP_TEAM if training or lesson else c.GoalKind.RESTORE_TEAM
        if training and lesson is None:
            members = observe_preparation_members(rt.emulator, holder["plan"])
            member = min(
                (
                    m
                    for m in members
                    if m.observation.species_id in LEAGUE_LEVELS
                    and m.observation.level < LEAGUE_LEVELS[m.observation.species_id]
                ),
                key=lambda m: (m.observation.species_id != 28, m.observation.slot),
            )
            target = LEAGUE_LEVELS[member.observation.species_id]
            roster = tuple(
                replace(
                    m,
                    purpose=PreparationPurpose.COMBAT,
                    purpose_reason="disclosed preparation for cartridge League opposition",
                    milestone_level=None,
                )
                if m.specimen_ref == member.specimen_ref
                else m
                for m in members
            )
            plan = PreparationPlan(
                roster,
                65,
                5,
                ((member.specimen_ref, target),),
                "supplied anticipation of cartridge Champion maximum65; native XP only",
                holder["plan"].budget,
            )
            live = replace(route, route_world=route.route_world.with_current_observation(rt.reader))
            start = Gen1TraversalObserver(
                rt.reader, capability_projector=partial(gen1_field_capabilities, rt.emulator)
            ).observe()
            corridor = tools.preparation_corridor(live, start)

        def execute():
            nonlocal used, terminal
            if used or origin != rt.emulator.save_state_bytes():
                raise ValueError("stale native League preparation")
            used = True
            a0, f0 = actions.actions_executed, rt.emulator.frame_count
            if lesson is not None:
                execute_machine_lesson(
                    rt.emulator, actions, rt.reader, lesson, rom=c.ROM.read_bytes()
                )
                result = dict(
                    owned_machine_lesson=asdict(lesson),
                    native_lesson=True,
                    source="actually owned compatible machine; disclosed Snorlax preparation",
                )
            elif training:
                ordinal = len(tuple(output.glob("preparation-*.json")))

                def record(name, value):
                    nonlocal ordinal
                    ordinal += 1
                    p._record(
                        output / f"preparation-{ordinal:03d}.json", dict(name=name, value=value)
                    )

                result = execute_wild_preparation(
                    rom=c.ROM.read_bytes(),
                    reader=rt.reader,
                    actions=actions,
                    emulator=rt.emulator,
                    battler=holder["actor"],
                    adapter=rt.adapter,
                    source_raw=raw,
                    plan=plan,
                    attempts=(),
                    record=record,
                    cost_snapshot=lambda: (actions.actions_executed, rt.emulator.frame_count),
                    hideout_timing=HideoutTiming(),
                    route=live,
                    corridor=corridor,
                    maximum_battles=32,
                    minimum_ready_members=2,
                    recovery_home_map=int(c.MapId.INDIGO_PLATEAU_LOBBY),
                    prepare_transport_escort=True,
                    restore_on_return=False,
                    allow_health_retreat=True,
                    continue_after_nonwinning_exit=True,
                )
                result = dict(result, target=target, trainee=member.specimen_ref)
            else:
                replace(
                    route, destination_map=int(c.MapId.INDIGO_PLATEAU_LOBBY), destination_at=(7, 7)
                )(actions, rt.reader, rt.emulator)
                result = victory.phases.heal_indigo(rt, actions)
            holder["plan"] = refresh_preparation_roster(
                rt.emulator, holder["plan"], evolution_rom=c.ROM.read_bytes()
            )
            terminal = rt.emulator.save_state_bytes()
            receipt_number = len(tuple(output.glob("LEAGUE-PREPARATION*.json"))) + 1
            p._record(
                output / f"LEAGUE-PREPARATION-{receipt_number:03d}.json",
                dict(
                    result=result,
                    supplied_not_learned=True,
                    native_xp_only=True,
                    targets=LEAGUE_LEVELS,
                    fits=0,
                    training_data=0,
                ),
            )
            return GoalExecutionReport(
                actions.actions_executed - a0,
                rt.emulator.frame_count - f0,
                dict(result=result, supplied_not_learned=True, native_xp_only=True),
            )

        def verify(_):
            passed = used and terminal == rt.emulator.save_state_bytes() and p._field_ready(rt)
            return (
                GoalVerification.succeeded()
                if passed
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            )

        binding = ExecutableGoalBinding(
            "earned-run:league-preparation:" + c.sha256(origin).hexdigest(),
            kind,
            0.1,
            0.1,
            execute,
            verify,
            maximum_cash_debit=None,
        )
        return p.GoalBindingSet(
            tuple(
                binding.opportunity
                if k is kind
                else p.GoalOpportunity(
                    "earned-run:league-unavailable:" + k.value,
                    k,
                    p.GoalAvailability.UNAVAILABLE,
                    unavailable_reason=p.GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                for k in c.GoalKind
            ),
            (binding,),
        )

    return payload, factory, p.NativeStoryBranchInventory(base, lambda *_: ()), holder, source


def assembly(parent, output, *, stage=None):
    if stage is None:
        stage = (
            doc(output / "STAGE.json")["stage"]
            if (output / "STAGE.json").exists()
            else stage_from(parent)
        )
    if output.parent == p.ROOT / "runs" and not (output / "STAGE.json").exists():
        p._record(
            output / "STAGE.json",
            dict(
                stage=stage,
                source_directory=str(parent),
                reset=False,
                **(
                    {"maximum_level_deficit": LEAGUE_DEVELOPMENT_DEFICIT}
                    if stage == "league"
                    else {}
                ),
            ),
        )
    if stage == "koga":
        return koga_assembly(parent, output)
    if stage == "safari":
        result = safari.assembly(parent, output)
    elif stage == "sabrina":
        result = koga.old.phases.assembly(
            parent,
            output,
            base_assembly=partial(regional, stage=stage),
            attempt_root=p.ROOT / "runs",
            maximum_major_attempts=16,
            ordinary_game_economy=True,
            include_sabrina=True,
            attempt_pattern="segment-*",
        )
    elif stage == "blaine":
        result = blaine.phases.assembly(
            parent,
            output,
            base_assembly=partial(regional, stage=stage),
            attempt_root=RetainedSegmentLayout(p.ROOT / "runs"),
            include_blaine=True,
            maximum_blaine_attempts=16,
            legacy_history=False,
            travel_target=partial(forward_target, destination=STAGES[stage][1]),
        )
    elif stage == "giovanni":
        result = giovanni.phases.assembly(
            parent,
            output,
            base_assembly=partial(regional, stage=stage),
            attempt_root=RetainedSegmentLayout(p.ROOT / "runs"),
            maximum_giovanni_attempts=16,
            legacy_history=False,
            travel_target=partial(forward_target, destination=STAGES[stage][1]),
        )
    elif stage == "victory":
        result = victory.phases.assembly(
            parent,
            output,
            base_assembly=partial(regional, stage=stage),
            attempt_root=RetainedSegmentLayout(p.ROOT / "runs"),
            maximum_rival_attempts=16,
            legacy_history=False,
            battle_authority="current-source exact story scope;ordinary frozen battler",
        )
    elif stage == "league-preparation":
        result = league_preparation_assembly(parent, output)
    elif stage == "league":
        result = champion.assembly(parent, output)
    elif stage == "collection":
        from red_earned_collection_connection_20261005 import collection_assembly

        verified_hall_of_fame()
        return collection_assembly(sys.modules[__name__], parent, output)
    else:
        raise ValueError("Next existing phase needs its current-source connection: " + stage)
    payload, factory, menu, holder, source = result
    original = menu.enumerate_base
    original_branches = menu.enumerate_branches

    def base(rt, actions, obs):
        holder["forward_branch"] = None
        # Native preparation is explicit support, before reward lessons assume a lead slot.
        binding = strongest_field_lead(rt, actions)
        if binding is None:
            binding = p.interrupted_wild_binding(rt, actions)
        if binding is None and stage == "blaine":
            binding = center_anchor_approach(rt, actions)
        if binding is None and stage in {"victory", "league-preparation"}:
            binding = inventory_clearance_binding(rt, actions)
        if binding is None and stage == "victory":
            binding = retained_corridor_binding(rt, actions, output=output)
        if binding is None and stage == "league":
            binding = league_coverage_binding(rt, actions, output=output)
        if binding is None and stage == "league":
            binding = league_hidden_pp_supply_binding(rt, actions, output=output)
        if binding is None and stage == "league":
            binding = earned_champion_reserve_care(rt, actions, obs, output=output)
        if binding is None and stage == "league":
            binding = league_pp_support_binding(rt, actions, output=output)
        if binding is None:
            binding = p.engaged_story_binding(
                rt,
                actions,
                rom=c.ROM.read_bytes(),
                battler=holder["actor"],
                objective_id=STAGES[stage][0][-1],
            )
        if binding is None:
            town = {
                "sabrina": int(c.MapId.SAFFRON_CITY),
                "giovanni": int(c.MapId.VIRIDIAN_CITY),
                "victory": int(c.MapId.VIRIDIAN_CITY),
            }.get(stage)
            if stage == "victory" and not victory_transport_needed(rt.reader.read()):
                town = None
            if (
                stage == "blaine"
                and int(c.MapId.CINNABAR_ISLAND) not in rt.reader.read_fly_destinations()
            ):
                town = int(c.MapId.PALLET_TOWN)
            if town is not None:
                binding = flight_binding(rt, actions, town=town, objective=STAGES[stage][0][0])
        if binding is None:
            return original(rt, actions, obs)
        if binding.kind is c.GoalKind.ADVANCE_STORY:
            holder["forward_branch"] = binding
            return p.GoalBindingSet(
                tuple(
                    p.GoalOpportunity(
                        "earned-run:branch:" + kind.value,
                        kind,
                        p.GoalAvailability.UNAVAILABLE,
                        unavailable_reason=p.GoalUnavailableReason.TEMPORARILY_BLOCKED,
                    )
                    for kind in c.GoalKind
                ),
                (),
            )
        return p.GoalBindingSet(
            tuple(
                binding.opportunity
                if kind is binding.kind
                else p.GoalOpportunity(
                    "earned-run:" + kind.value,
                    kind,
                    p.GoalAvailability.UNAVAILABLE,
                    unavailable_reason=p.GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                for kind in c.GoalKind
            ),
            (binding,),
        )

    def branches(*args):
        binding = holder.get("forward_branch")
        if binding is not None:
            return ((binding, koga.old.phases.OptionChallenge(False, False, 0.0, 0.0, 0.0)),)
        return original_branches(*args)

    return payload, factory, p.NativeStoryBranchInventory(base, branches), holder, source


def stateless_negative_worktree_probe(path):
    """Avoid Git startup ONLY where fresh filesystem discovery proves no repo.

    No positive result or previous negative result is cached. Any .git/HEAD
    entry, discovery override or filesystem uncertainty uses the original Git
    implementation. All private-root/sentinel/inode/durability checks remain.
    Git's pager does not participate in repository discovery for piped rev-parse.
    """
    from pokemon_red_completion.private_artifacts import _default_git_worktree_probe

    if any(k.startswith("GIT_") and k != "GIT_PAGER" for k in os.environ):
        return _default_git_worktree_probe(path)
    for directory in (path, *path.parents):
        for candidate in (directory / ".git", directory / "HEAD"):
            try:
                candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                return _default_git_worktree_probe(path)
            else:
                return _default_git_worktree_probe(path)
    return False


@contextmanager
def completion_journal_probe_context(parent):
    """Prospective188-only performance connection through the existing probe API."""
    if not parent.name.startswith("segment-") or int(parent.name.rsplit("-", 1)[1]) < 187:
        yield
        return
    original = p.c.open_private_root

    def opened(root, *args, **kwargs):
        if Path(root) == c.BASE / "goal-manager-v1":
            kwargs.setdefault("git_worktree_probe", stateless_negative_worktree_probe)
        return original(root, *args, **kwargs)

    p.c.open_private_root = opened
    try:
        yield
    finally:
        p.c.open_private_root = original


def collection_uses_model_sampling(parent):
    marker = ROOT / "MODEL-SAMPLED-COLLECTION.json"
    if not marker.exists() or not parent.name.startswith("segment-"):
        return False
    return int(parent.name.rsplit("-", 1)[1]) >= doc(marker)["first_parent_segment"]


def run():
    global RETAINED_CAPTURE
    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    parent = Path(status["latest_fresh_export"])
    facts = audit.native_state(parent / "terminal.state")
    RETAINED_CAPTURE = facts["map"] == 23 and facts["battle"] == 1
    from red_earned_unique_collection_20261006 import enabled, UNIQUE_NUMBERS
    if facts["battle"] == 1 and enabled(__import__(__name__), p.ROOT / "read-only-current"):
        from pokemon_red_completion.red_static_capture import red_static_capture_targets
        with c.PyBoyAdapter(c.ROM) as em:
            em.load_state_bytes((parent / "terminal.state").read_bytes())
            reader = c.PokemonRedStateReader(em)
            identity = reader.read_wild_capture_identity()
            RETAINED_CAPTURE = identity is not None and any(
                t.species_number in UNIQUE_NUMBERS and (facts["map"],identity.original_species_id,
                    reader.read().enemy_level)==(t.map_id,t.internal_species,t.level)
                for t in red_static_capture_targets(c.ROM.read_bytes()))
    stage = stage_from(parent)
    targets, destination = STAGES[stage]
    original = p.NativePlayerCurriculum
    curriculum = {
        "league-preparation": LeaguePreparationCurriculum,
        "league": LeagueVictoryCurriculum,
        "collection": WholeRunCollectionCurriculum,
    }.get(stage, CompletionStageCurriculum)
    p.NativePlayerCurriculum = partial(
        curriculum,
        destination_map=destination,
        required_moves=(57, 70) if stage == "safari" else (),
    )
    try:
        from red_earned_collection_connection_20261005 import collection_support_context

        with (
            collection_support_context() if stage == "collection" else nullcontext(),
            completion_journal_probe_context(parent),
        ):
            p.run(
                build=partial(assembly, stage=stage),
                targets=targets,
                helper_path=Path(__file__),
                greedy_selection=not (
                    stage == "collection" and collection_uses_model_sampling(parent)
                ),
                maximum_worker_decisions=(
                    1 if (stage == "collection" and (ROOT / "unique-admissions" /
                        (facts["sha256"] + ".json")).exists()) else 24
                    if stage in {"koga", "safari", "collection"}
                    else 1
                    if stage == "league" and facts["field_ready"]
                    else 2
                ),
                maximum_worker_seconds=1200,
            )
    finally:
        p.NativePlayerCurriculum = original
    latest = max((p.ROOT / "runs").glob("segment-*"), key=lambda f: int(f.name.rsplit("-", 1)[1]))
    if (latest / "RESULT.json").exists() and not (latest / "CONTEXT.json").exists():
        result = doc(latest / "RESULT.json")
        if result.get("error_type") == "OneOffCapturePaused" or (
            result.get("error_type") == "BattleRuntimeTimeoutError"
            and result.get("episode") is None
        ):
            retain_capture_failure(latest)
        elif (result.get("history_error") or {}).get("type") == "FileNotFoundError":
            retain_censored_battle(latest)
        elif result.get("history_error") == dict(
            type="ValueError", message="victory requires complete defeated roster"
        ):
            retain_repaired_history(latest)
    if stage == "league" and (latest / "CONTEXT.json").exists():
        actual = audit.native_state(latest / "terminal.state")
        with c.PyBoyAdapter(c.ROM) as em:
            em.load_state_bytes((latest / "terminal.state").read_bytes())
            raw = c.PokemonRedStateReader(em).read()
            won = event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
        if actual["map"] == int(c.MapId.HALL_OF_FAME) and actual["badges"] == 255 and won:
            proof = ROOT / "HALL-OF-FAME-PROOF.json"
            if not proof.exists():
                p._record(
                    proof,
                    dict(
                        directory=str(latest),
                        terminal_sha256=actual["sha256"],
                        context_sha256=c.digest(latest / "CONTEXT.json"),
                        champion_and_hall_of_fame=True,
                        badges=255,
                        same_earned_ancestry=True,
                        official_unassisted_claim=False,
                    ),
                )


def retain_repaired_history(case):
    """Authenticate an additive history successor without rewriting the failed result."""
    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    result, plan = doc(case / "RESULT.json"), doc(case / "PLAN.json")
    parent = Path(plan["source_directory"])
    assert parent == Path(status["latest_fresh_export"])
    assert result["history_error"] == dict(
        type="ValueError", message="victory requires complete defeated roster"
    )
    assert result["worker_stop_confirmed"] and result["buttons_released"]
    assert result["actual_history"] is None and not (case / "CONTEXT.json").exists()
    costs = doc(case / "native/native-costs.json")
    assert costs == result["costs"]
    store = c.open_private_root(
        c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
    )
    trace = audit.inputs(store, case / "native", doc(case / "native/native-plan.json"), costs)
    payload, factory, _, holder, _ = assembly(parent, case)
    terminal = (case / "terminal.state").read_bytes()
    assert c.digest(case / "native/terminal.state") == c.sha256(terminal).hexdigest()
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        holder["actor"].calls = result["battle_count"]
        history = holder["history"]()
        em.load_state_bytes(terminal)
        preparation = refresh_preparation_roster(
            em, holder["plan"], evolution_rom=c.ROM.read_bytes()
        )
        spent = accumulate_player_costs(
            plan["inherited_spent"],
            decisions=costs["goal_attempts"],
            actions=costs["actions_attempted"],
            frames=costs["frames"],
            seconds=costs["seconds"],
            heals=costs["restore_attempts"],
            cash_deltas=tuple(
                r["observed_cost"]["cash_spent"] for r in result["episode"]["outcomes"]
            ),
        )
        context = capture_player_continuation(
            rt, preparation=preparation, battle=history, spent=spent
        )
        assert context["lesson"] == result["episode"]["outcomes"][-1]["after"]["player_lesson"]
        assert em.frame_count == 0 and em.save_state_bytes() == terminal
    p._record(
        case / "REPAIRED-HISTORY-RETENTION.json",
        dict(
            original_result_sha256=c.digest(case / "RESULT.json"),
            original_failure_preserved=True,
            actual_history=asdict(history),
            terminal_sha256=c.sha256(terminal).hexdigest(),
            trace=trace,
            costs=costs,
            spent=spent,
            inputs=0,
            frames=0,
            reset=False,
            repair="Authenticate terminal last-roster knockout after selected-turn snapshot",
        ),
    )
    p._record(case / "CONTEXT.json", context)
    p.coordinator.port.status(latest_fresh_export=str(case))
    print(json.dumps(dict(retained_repaired_history=case.name, costs_carried=True)), flush=True)


def retained_episode_cash_deltas(episode):
    """Carry observed native prefixes even when battle aftermath is unavailable."""
    outcomes = tuple(row["observed_cost"]["cash_spent"] for row in episode["outcomes"])
    prefixes = tuple(
        episode[key]["cash_spent"]
        for key in (
            "supplied_blackout_preface",
            "supplied_wild_escape_preface",
            "supplied_capture_preface",
            "supplied_trainer_preface",
        )
        if key in episode
    )
    return outcomes + prefixes


def retain_censored_battle(case):
    """Reuse metered terminal retention with unavailable aftermath explicitly masked."""
    from risk_train_integration import replay

    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    result, plan = doc(case / "RESULT.json"), doc(case / "PLAN.json")
    parent = Path(plan["source_directory"])
    assert parent == Path(status["latest_fresh_export"])
    assert result["history_error"]["type"] == "FileNotFoundError"
    assert result["actual_history"] is None and result["worker_stop_confirmed"]
    assert result["buttons_released"] and not (case / "CONTEXT.json").exists()
    episode, costs = result["episode"], result["costs"]
    assert episode["stop_reason"] == "execution_failed"
    assert costs == doc(case / "native/native-costs.json")
    terminal = (case / "terminal.state").read_bytes()
    assert c.digest(case / "native/terminal.state") == c.sha256(terminal).hexdigest()
    store = c.open_private_root(
        c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
    )
    trace = audit.inputs(store, case / "native", doc(case / "native/native-plan.json"), costs)
    payload, factory, _, holder, _ = assembly(parent, case)
    logs = []
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        actor = holder["actor"]
        paths = sorted((case / "battles").glob("battle-*"))
        assert len(paths) == result["battle_count"]
        for folder in paths:
            endpoint = doc(folder / "endpoint.json")
            manifest = doc(folder / "initial.state.json")
            assert manifest["state_sha256"] == c.digest(folder / "initial.state")
            assert manifest["source_state_sha256"] == actor.source_state_sha256
            assert endpoint["model_sha256"] == actor.model_sha256
            assert endpoint["qualification_sha256"] == actor.qualification_sha256
            log = verify_trainer_practice_event_log(folder / "events")
            assert log["complete"]
            if not (folder / "outcome.json").exists():
                assert folder == paths[-1] and endpoint["outcome_sha256"] is None
                assert not endpoint["actor_returned_win"] and log["failed_runs"] == 1
                assert c.digest(folder / "final.state") == c.sha256(terminal).hexdigest()
                rows = [
                    doc(f)["payload"]["decision"]
                    for f in sorted((folder / "events").glob("event-*.json"))
                    if doc(f)["payload"]["event"] == "decision_completed"
                ]
                assert replay(
                    dict(
                        policy_id="frozen-player-trainer",
                        capture_id=manifest["capture_id"],
                        decisions=rows,
                    ),
                    actor.model,
                ) == len(rows)
            logs.append(log)
        em.load_state_bytes(terminal)
        preparation = refresh_preparation_roster(
            em, holder["plan"], evolution_rom=c.ROM.read_bytes()
        )
        spent = accumulate_player_costs(
            plan["inherited_spent"],
            decisions=costs["goal_attempts"],
            actions=costs["actions_attempted"],
            frames=costs["frames"],
            seconds=costs["seconds"],
            heals=costs["restore_attempts"],
            cash_deltas=retained_episode_cash_deltas(episode),
        )
        context = capture_player_continuation(rt, preparation=preparation, battle=None, spent=spent)
        assert context["lesson"] == episode["outcomes"][-1]["after"]["player_lesson"]
        assert em.frame_count == 0 and em.save_state_bytes() == terminal
    p._record(
        case / "CENSORED-BATTLE-RETENTION.json",
        dict(
            original_result_sha256=c.digest(case / "RESULT.json"),
            trace=trace,
            logs=logs,
            costs=costs,
            spent=spent,
            missing_aftermath_explicitly_masked=True,
            original_failure_preserved=True,
            no_invented_outcome=True,
            inputs=0,
            frames=0,
        ),
    )
    p._record(case / "CONTEXT.json", context)
    p.coordinator.port.status(latest_fresh_export=str(case))
    print(json.dumps(dict(retained_censored_battle=case.name, costs_carried=True)), flush=True)


def authenticated_paused_capture_receipt(case, terminal):
    """Authenticate this actual paused Snorlax/legendary state without inputs."""
    from pokemon_red_completion.red_static_capture import red_static_capture_targets
    matches = [receipt for pattern in ("snorlax-retained/*-paused/receipt.json",
        "static-*/*-paused/receipt.json") for receipt in sorted(case.glob(pattern))
        if doc(receipt)["state_sha256"] == c.sha256(terminal).hexdigest()]
    if not matches:
        raise ValueError("failed capture needs its exact paused terminal receipt")
    receipt = matches[-1]
    data = doc(receipt)
    targets = (route12_snorlax_target(c.ROM.read_bytes()), *red_static_capture_targets(c.ROM.read_bytes()))
    target, = [target for target in targets
        if c.canonical_sha256(asdict(target)) == c.canonical_sha256(data["target"])]
    checkpoint = load_capture_checkpoint(receipt.parent,
        expected_receipt_sha256=c.digest(receipt),expected_origin_sha256=data["origin_state_sha256"],
        expected_target=target,expected_allocation_sha256=data["allocation_sha256"])
    assert checkpoint.state == terminal and checkpoint.phase == "paused"
    return receipt


def retain_capture_failure(case):
    """Keep actual failed pre-loop support progress, not a fabricated model episode."""
    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    result, plan = doc(case / "RESULT.json"), doc(case / "PLAN.json")
    assert result["worker_stop_confirmed"] and result["buttons_released"]
    capture_failure = result["error_type"] == "OneOffCapturePaused"
    assert capture_failure or result["error_type"] == "BattleRuntimeTimeoutError"
    assert result["history_error"] is None
    assert result["episode"] is None and not (case / "CONTEXT.json").exists()
    parent = Path(plan["source_directory"])
    assert parent == Path(status["latest_fresh_export"])
    costs = doc(case / "native/native-costs.json")
    assert costs == result["costs"] and costs["goal_attempts"] == 1
    terminal = (case / "terminal.state").read_bytes()
    assert c.digest(case / "native/terminal.state") == c.sha256(terminal).hexdigest()
    if capture_failure:
        authenticated_paused_capture_receipt(case,terminal)
    else:
        intent = doc(case / "native/retained-trainer-preface/intent.json")
        assert intent["binding_ref"] == "pokemon.red:retained-engagement:" + intent["source_sha256"]
        assert intent["source_sha256"] == plan["source"]["state_sha256"]
    store = c.open_private_root(
        c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
    )
    trace = audit.inputs(store, case / "native", doc(case / "native/native-plan.json"), costs)
    payload, factory, _, holder, _ = assembly(parent, case)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        initial_cash = rt.reader.read().player_money
        em.load_state_bytes(terminal)
        assert rt.reader.read().player_money == initial_cash
        spent = accumulate_player_costs(
            plan["inherited_spent"],
            decisions=costs["goal_attempts"],
            actions=costs["actions_attempted"],
            frames=costs["frames"],
            seconds=costs["seconds"],
            heals=costs["restore_attempts"],
            cash_deltas=(0,),
        )
        preparation = refresh_preparation_roster(
            em, holder["plan"], evolution_rom=c.ROM.read_bytes()
        )
        context = capture_player_continuation(
            rt, preparation=preparation, battle=_battle(result["actual_history"]), spent=spent
        )
        assert em.frame_count == 0 and em.save_state_bytes() == terminal
    p._record(
        case / "PARTIAL-PREFACE-RETENTION.json",
        dict(
            retained_failure=result["error"],
            original_result_sha256=c.digest(case / "RESULT.json"),
            same_origin=True,
            progress_reset=False,
            source_sha256=c.sha256(terminal).hexdigest(),
            model_decisions=0,
            support_attempts=1,
            trace=trace,
            costs=costs,
            prior_spent=plan["inherited_spent"],
            spent=spent,
            inputs=0,
            frames=0,
        ),
    )
    p._record(case / "CONTEXT.json", context)
    p.coordinator.port.status(latest_fresh_export=str(case))
    print(json.dumps(dict(retained_failed_preface=case.name, costs_carried=True)), flush=True)


def retain_interrupted_goal(case):
    """Retain sealed, safe partial work after an actual operator stop, not a reset."""
    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    result, plan = doc(case / "RESULT.json"), doc(case / "PLAN.json")
    parent = Path(plan["source_directory"])
    assert parent == Path(status["latest_fresh_export"])
    assert result["worker_stop_confirmed"] and result["buttons_released"]
    assert result["episode"] is None and result["history_error"] is None
    assert result["battle_count"] == 0 and not (case / "CONTEXT.json").exists()
    rows = [doc(f) for f in sorted((case / "native/episode").glob("step-*/outcome.json"))]
    costs = doc(case / "native/native-costs.json")
    assert rows and rows[-1]["error_type"] == "KeyboardInterrupt"
    assert rows[-1]["safe_terminal"] and costs == result["costs"]
    assert costs["goal_attempts"] == len(rows)
    terminal = (case / "terminal.state").read_bytes()
    terminal_sha = c.sha256(terminal).hexdigest()
    assert c.digest(case / "native/terminal.state") == terminal_sha
    assert rows[-1]["terminal_state_sha256"] == terminal_sha
    store = c.open_private_root(
        c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
    )
    trace = audit.inputs(store, case / "native", doc(case / "native/native-plan.json"), costs)
    payload, factory, _, holder, _ = assembly(parent, case)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        em.load_state_bytes(terminal)
        assert p._field_ready(rt)
        preparation = refresh_preparation_roster(
            em, holder["plan"], evolution_rom=c.ROM.read_bytes()
        )
        spent = accumulate_player_costs(
            plan["inherited_spent"],
            decisions=costs["goal_attempts"],
            actions=costs["actions_attempted"],
            frames=costs["frames"],
            seconds=costs["seconds"],
            heals=costs["restore_attempts"],
            cash_deltas=tuple(r["observed_cost"]["cash_spent"] for r in rows),
        )
        context = capture_player_continuation(
            rt, preparation=preparation, battle=_battle(result["actual_history"]), spent=spent
        )
        assert em.frame_count == 0 and em.save_state_bytes() == terminal
    p._record(
        case / "INTERRUPTED-GOAL-RETENTION.json",
        dict(
            original_result_sha256=c.digest(case / "RESULT.json"),
            source_sha256=terminal_sha,
            native_stop_confirmed=True,
            reason="Stopped the demonstrated return-to-Viridian wrapper loop",
            outcome_sha256=[
                c.digest(f) for f in sorted((case / "native/episode").glob("step-*/outcome.json"))
            ],
            trace=trace,
            costs=costs,
            prior_spent=plan["inherited_spent"],
            spent=spent,
            reset=False,
            inputs=0,
            frames=0,
            successful_episode_claim=False,
        ),
    )
    p._record(case / "CONTEXT.json", context)
    p.coordinator.port.status(latest_fresh_export=str(case))
    print(json.dumps(dict(retained_interrupted_goal=case.name, costs_carried=True)), flush=True)


def retain_censored_capture_snapshot(case):
    """Keep this real catch after its fingerprint-collision aftermath was censored.

    Authenticate inputs, the recorded support choice, originals and actual
    collection delta. Never synthesize the missing outcome or an episode PASS.
    """
    from collections import Counter

    from pokemon_red_completion.red_recorded_selection_authority import replay_selection_authority

    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None and not status["complete"]
    result, plan = doc(case / "RESULT.json"), doc(case / "PLAN.json")
    parent = Path(plan["source_directory"])
    assert parent == Path(status["latest_fresh_export"])
    assert case.name == "segment-232" and not (case / "CONTEXT.json").exists()
    assert result["error_type"] == "ValueError"
    assert result["error"] == "retained party lost or duplicated an individual"
    assert result["worker_stop_confirmed"] and result["buttons_released"]
    assert result["episode"] is None and result["history_error"] is None
    assert result["battle_count"] == 0
    steps = tuple(sorted((case / "native/episode").glob("step-*")))
    assert len(steps) == 1 and not (steps[0] / "outcome.json").exists()
    assert not (case / "native/episode/result.json").exists()
    decision = doc(steps[0] / "decision.json")
    assert decision["model_queries"] == 0 and not decision["comparative_choice"]
    assert replay_selection_authority(p.coordinator.old.a.model(),
        doc(steps[0] / "intent.json"), decision, allow_earning_exploration=True
    ) == doc(steps[0] / "execution-started.json")["selected_binding_ref"]
    costs = doc(case / "native/native-costs.json")
    assert costs == result["costs"] and costs["goal_attempts"] == 1
    assert costs["restore_attempts"] == costs["nested_restore_attempts"] == 0
    terminal = (case / "terminal.state").read_bytes()
    terminal_sha = c.sha256(terminal).hexdigest()
    assert c.digest(case / "native/terminal.state") == terminal_sha == result["terminal_sha256"]
    store = c.open_private_root(c.BASE / "goal-manager-v1", repository_root=c.REPO,
        allow_same_device=True, git_worktree_probe=stateless_negative_worktree_probe)
    trace = audit.inputs(store, case / "native", doc(case / "native/native-plan.json"), costs)
    payload, factory, _, holder, _ = assembly(parent, case)
    assert c.sha256(payload).hexdigest() == c.digest(steps[0] / "before.state")
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        before = rt.adapter.observe()
        em.load_state_bytes(terminal)
        after = rt.adapter.observe()
        rt.adapter.party_guard.verify_active_roster_restored()
        assert p._field_ready(rt)
        assert after.collection_observation.owned_species == (
            before.collection_observation.owned_species | {"pokemon:national:088"})
        assert Counter(s.species_ref for s in after.collection_observation.specimens) == (
            Counter(s.species_ref for s in before.collection_observation.specimens)
            + Counter({"pokemon:national:088": 1}))
        assert before.raw.player_money == after.raw.player_money
        preparation = refresh_preparation_roster(
            em, holder["plan"], evolution_rom=c.ROM.read_bytes())
        spent = accumulate_player_costs(plan["inherited_spent"],
            decisions=costs["goal_attempts"], actions=costs["actions_attempted"],
            frames=costs["frames"], seconds=costs["seconds"],
            heals=costs["restore_attempts"], cash_deltas=(0,))
        context = capture_player_continuation(rt, preparation=preparation,
            battle=_battle(result["actual_history"]), spent=spent)
        assert em.frame_count == 0 and em.save_state_bytes() == terminal
    p._record(case / "CENSORED-SNAPSHOT-RETENTION.json", dict(
        original_result_sha256=c.digest(case / "RESULT.json"), source_sha256=terminal_sha,
        trace=trace, costs=costs, prior_spent=plan["inherited_spent"], spent=spent,
        strict_input_audit_passed=True, state_originals_census_verified=True,
        recorded_support_choice_verified=True, supplied=True, model_queries=0,
        original_outcome_missing=True, original_outcome_reconstructed=False,
        full_episode_audit_passed=False, original_failure_retained=True,
        reset=False, inputs=0, frames=0))
    p._record(case / "CONTEXT.json", context)
    p.coordinator.port.status(latest_fresh_export=str(case))
    print(json.dumps(dict(retained_censored_capture=case.name, entries=91,
        costs_carried=True, episode_pass_claim=False, inputs=0, frames=0)), flush=True)


def inspect():
    authenticate()
    status = doc(ROOT / "STATUS.json")
    assert status["active_worker"] is None
    parent = Path(status["latest_fresh_export"])
    payload, factory, menu, holder, source = assembly(parent, p.ROOT / "read-only-current")
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(p.coherent.ReadOnlyController(em))
        actions = c.CountingExecutor(c.FrameSafeExecutor(p.coherent.ReadOnlyController(em)))
        actions.execute_restoration = lambda *_: (_ for _ in ()).throw(
            ValueError("read-only restoration")
        )
        options = p.observe_native_player_options(
            rt,
            actions,
            battle=holder["history"](),
            combat_specimen_refs=holder["refs"],
            remaining_budget=(1.0,) * 5,
            target_cash=0,
            ordering_seed_sha256="a" * 64,
            allow_support=True,
            model_feature_version=7,
            enumerate_bindings=menu.enumerate,
            enumerate_supplements=menu.supplements,
            observe_challenges=menu.challenges,
        )
        assert em.frame_count == 0 and em.save_state_bytes() == payload
        rows = options.public_dict()
        p._record(ROOT / f"READONLY-{len(tuple(ROOT.glob('READONLY-*.json'))) + 1:02d}.json", rows)
        kinds = rows.get(
            "available_goal_kinds",
            [
                candidate["features"]["kind"]
                for candidate in rows.get("menu", {}).get("candidates", ())
                if candidate["availability"] == "available"
            ],
        )
        print(
            json.dumps(
                dict(
                    source=parent.name,
                    schema=rows["schema"],
                    available=kinds,
                    comparative=rows.get("comparative_choice"),
                )
            ),
            flush=True,
        )


def audit_deltas():
    authenticate()
    assert doc(ROOT / "STATUS.json")["active_worker"] is None
    model = p.coordinator.old.a.model()
    store = c.open_private_root(
        c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
    )
    count = 0
    for segment in sorted((p.ROOT / "runs").glob("segment-*")):
        if (segment / "DELTA-AUDIT.json").exists():
            assert doc(segment / "DELTA-AUDIT.json")["passed"]
            continue
        if (segment / "RESULT.json").exists():
            if (segment / "INTERRUPTED-GOAL-RETENTION.json").exists():
                row = doc(segment / "INTERRUPTED-GOAL-RETENTION.json")
                assert row["original_result_sha256"] == c.digest(segment / "RESULT.json")
                assert row["source_sha256"] == c.digest(segment / "terminal.state")
                assert row["costs"] == doc(segment / "native/native-costs.json")
                assert doc(segment / "CONTEXT.json")["spent"] == row["spent"]
                assert row["inputs"] == row["frames"] == 0 and not row["reset"]
            elif (segment / "PARTIAL-PREFACE-RETENTION.json").exists():
                row = doc(segment / "PARTIAL-PREFACE-RETENTION.json")
                assert row["original_result_sha256"] == c.digest(segment / "RESULT.json")
                assert row["source_sha256"] == c.digest(segment / "terminal.state")
                assert row["costs"] == doc(segment / "native/native-costs.json")
                measured = audit.native_state(segment / "terminal.state")
                assert measured["sha256"] == row["source_sha256"]
                assert doc(segment / "CONTEXT.json")["spent"] == row["spent"]
            elif (segment / "CENSORED-BATTLE-RETENTION.json").exists():
                row = doc(segment / "CENSORED-BATTLE-RETENTION.json")
                assert row["original_result_sha256"] == c.digest(segment / "RESULT.json")
                assert row["costs"] == doc(segment / "native/native-costs.json")
                assert doc(segment / "CONTEXT.json")["spent"] == row["spent"]
                measured = audit.native_state(segment / "terminal.state")
                assert measured["sha256"] == doc(segment / "CONTEXT.json")["state_sha256"]
            else:
                row = audit.segment(store, segment, model)
        else:
            assert not (segment / "native").exists()
            row = dict(no_native_episode=True, input_free_preflight_failed=True)
        p._record(
            segment / "DELTA-AUDIT.json",
            dict(passed=True, row=row, audit_game_inputs=0, audit_emulator_frames=0),
        )
        count += 1
    print(json.dumps(dict(passed=True, newly_audited=count)), flush=True)


if __name__ == "__main__":
    configure()
    {"prepare": prepare, "inspect": inspect, "run": run, "audit": audit_deltas}[sys.argv[1]]()
