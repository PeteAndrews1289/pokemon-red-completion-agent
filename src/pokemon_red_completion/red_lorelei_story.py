"""Explicit first-Lorelei damage-model bridge, separate from League income.

Uses the existing story lifecycle, including native loss settlement. The outer
cartridge skill still owns approach, identity, payout and completion checks.
"""

from dataclasses import dataclass, field
from hashlib import sha256

from .observation import EventFlag, MapId
from .red_league_story_chain import LEAGUE_CHAIN_ADMISSION_SHA256
from .red_learned_trainer import (
    AGATHA_STORY_ADMISSION_SHA256,
    AGATHA_STORY_SHA256,
    CHAMPION_STORY_ADMISSION_SHA256,
    DAMAGE_STORY_ADMISSION_SHA256,
    DAMAGE_STORY_SHA256,
    LANCE_STORY_ADMISSION_SHA256,
    FrozenTrainerBattler,
)
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract

LORELEI_STORY_ADMISSION_SHA256 = "fb3899664a3dc386c5f1fbd821f7178c0a713e80ba2b67fbedab211eea02df83"


class LoreleiStoryBattleStopped(RuntimeError):
    """A retained loss or unresolved result is not a funding victory."""


@dataclass
class FrozenLoreleiStoryController:
    battler: FrozenTrainerBattler
    contract: StoryTrainerContract
    admission: bytes
    maximum_decisions: int = 80
    maximum_switches: int = field(default=80, init=False)
    heals_claimed: int = field(default=0, init=False)
    moves_selected: int = field(default=0, init=False)
    switches: list = field(default_factory=list, init=False)
    last_completion: object = field(default=None, init=False)

    @property
    def recovery_contract(self):
        return "league-profit-recovery-v1"  # HP semantics only; no income admission.

    @property
    def controller_name(self):
        return "frozen-damage-lorelei-development"

    @property
    def binding_identity(self):
        return (id(self.battler), self.contract, self.admission, self.maximum_decisions)

    def require_cartridge_target(self, trainer, quote):
        self.require_identity()
        if (
            self.contract.map_id != trainer.map_id
            or self.contract.trainer_identity
            != (trainer.trainer_class, trainer.trainer_class - 200, trainer.trainer_set)
            or self.contract.victory_money != quote.expected_victory_money
            or self.contract.defeated_event != trainer.event_flag
        ):
            raise ValueError("Lorelei story contract differs from live cartridge quote")

    def __post_init__(self):
        self.require_identity()

    def require_identity(self):
        self._require_bound_identity(
            LORELEI_STORY_ADMISSION_SHA256,
            "defeat_lorelei",
            MapId.LORELEIS_ROOM,
            EventFlag.BEAT_LORELEI,
        )

    def _require_bound_identity(
        self, admission_sha256, objective, map_id, event, battle_plan_id="cartridge-trainer-story"
    ):
        if (
            type(self.admission) is not bytes
            or sha256(self.admission).hexdigest() != admission_sha256
            or not isinstance(self.battler, FrozenTrainerBattler)
            or (self.battler.model_sha256, self.battler.qualification_sha256)
            != (DAMAGE_STORY_SHA256, DAMAGE_STORY_ADMISSION_SHA256)
        ):
            raise ValueError("Lorelei story requires exact damage model and both admissions")
        self.battler.require_story_identity()  # Recheck actual weights, not just labels.
        if (
            not isinstance(self.contract, StoryTrainerContract)
            or (
                self.contract.objective_id,
                self.contract.battle_plan_id,
                self.contract.map_id,
                self.contract.defeated_event,
            )
            != (
                objective,
                battle_plan_id,
                map_id,
                event,
            )
            or self.contract.victory_items
            or self.contract.victory_badge_bits
            or type(self.maximum_decisions) is not int
            or not 1 <= self.maximum_decisions <= 80
        ):
            raise ValueError("Lorelei story contract or decision bound differs")

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_lorelei" or rematch is not False:
            raise ValueError("damage League bridge admits only first-challenge Lorelei")

    def run(
        self,
        reader,
        executor,
        move_slot_policy,
        *,
        expected_map,
        intent,
        timing,
        label,
        consume_battle_start_schedule,
        move_decision_guard,
        battle_exit_guard=None,
    ):
        self.require_objective(intent.objective_id)
        if (
            consume_battle_start_schedule
            or expected_map != self.contract.map_id
            or intent.battle_plan_id != self.contract.battle_plan_id
        ):
            raise ValueError("undeclared Lorelei story boundary")
        move_decision_guard(reader.read())
        self.last_completion = None
        self.moves_selected = 0
        self.switches.clear()
        # No teacher policy is forwarded, even when learned execution fails.
        actor = FrozenStoryBattleController(
            self.battler,
            (self.contract,),
            self.maximum_decisions,
        )
        result = actor.run(
            reader,
            executor,
            objective_id=intent.objective_id,
            battle_plan_id=intent.battle_plan_id,
            expected_map=expected_map,
            timing=timing,
        )
        self.last_completion = result
        self.moves_selected = sum(d.get("kind") == "attack" for d in result.episode.decisions)
        self.switches.extend(
            d
            for d in result.episode.decisions
            if d.get("kind") in {"voluntary_switch", "forced_switch", "switch_prompt"}
        )
        if result.outcome != "won" or not result.field_ready:
            raise LoreleiStoryBattleStopped(
                f"retained {intent.objective_id} outcome: {result.outcome}"
            )
        raw = reader.read()
        if battle_exit_guard is not None:
            battle_exit_guard(raw)
        return raw


@dataclass
class ScopedAssistedLoreleiController(FrozenLoreleiStoryController):
    """Explicit current-source support permission, not the damage admission."""

    declared_model_sha256: str = field(default=AGATHA_STORY_SHA256, kw_only=True)
    declared_level_deficit: int = field(default=5, kw_only=True)
    declared_stay_when_productive: bool = field(default=True, kw_only=True)

    @property
    def controller_name(self):
        return "scoped-assisted-lorelei-development"

    @property
    def binding_identity(self):
        return super().binding_identity + (
            self.battler.development_story_scope,
            self.declared_stay_when_productive,
            self.declared_model_sha256,
            self.declared_level_deficit,
        )

    def require_identity(self):
        self._require_scoped_identity(
            ("defeat_lorelei", "cartridge-trainer-story", int(MapId.LORELEIS_ROOM),
             (244, 44, 1), int(EventFlag.BEAT_LORELEI))
        )

    def _require_scoped_identity(self, target):
        from .red_development_story_scope import DevelopmentStoryScope

        scope = getattr(self.battler, "development_story_scope", None)
        if (
            not isinstance(self.battler, FrozenTrainerBattler)
            or type(scope) is not DevelopmentStoryScope
            or type(self.admission) is not bytes
            or sha256(self.admission).hexdigest() != scope.work_order_sha256
            or type(self.declared_model_sha256) is not str
            or len(self.declared_model_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.declared_model_sha256)
            or self.battler.model_sha256 != self.declared_model_sha256
            or type(self.declared_level_deficit) is not int
            or not 0 <= self.declared_level_deficit <= 100
            or type(self.declared_stay_when_productive) is not bool
            or scope.diagnostic_stay_when_productive is not self.declared_stay_when_productive
            or (not self.declared_stay_when_productive
                and type(self) is not ScopedAssistedLoreleiController
                and not (scope.allow_learned_tactics
                         and type(self) in {ScopedAssistedLeagueRetryController,
                                            ScopedAssistedChampionController}))
            or (scope.allow_learned_tactics and self.declared_stay_when_productive)
            or scope.contract != self.contract
            or type(self.contract) is not StoryTrainerContract
            or (self.contract.objective_id, self.contract.battle_plan_id,
                self.contract.map_id, self.contract.trainer_identity,
                self.contract.defeated_event)
            != target
            or type(self.maximum_decisions) is not int
            or not 1 <= self.maximum_decisions <= 80
        ):
            raise ValueError("assisted League requires its explicit source/model/work-order scope")
        self.battler.require_story_contract(self.contract)


@dataclass
class ScopedAssistedBrunoController(ScopedAssistedLoreleiController):
    """Explicit source-bound first-Bruno support, not old-source admission."""

    @property
    def controller_name(self):
        return "scoped-assisted-bruno-development"

    def require_identity(self):
        self._require_scoped_identity(
            ("defeat_bruno", "cartridge-trainer-story", int(MapId.BRUNOS_ROOM),
             (233, 33, 1), int(EventFlag.BEAT_BRUNO))
        )

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_bruno" or rematch is not False:
            raise ValueError("assisted Bruno admits only first-challenge Bruno")


@dataclass
class ScopedAssistedAgathaController(ScopedAssistedLoreleiController):
    """Current-source first-Agatha support; default League bindings unchanged."""

    @property
    def controller_name(self):
        return "scoped-assisted-agatha-development"

    def require_identity(self):
        self._require_scoped_identity(
            ("defeat_agatha", "cartridge-trainer-story", int(MapId.AGATHAS_ROOM),
             (246, 46, 1), int(EventFlag.BEAT_AGATHA))
        )

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_agatha" or rematch is not False:
            raise ValueError("assisted Agatha admits only first-challenge Agatha")


@dataclass
class ScopedAssistedLanceController(ScopedAssistedLoreleiController):
    """Current-source first-Lance support; default League bindings unchanged."""

    @property
    def controller_name(self):
        return "scoped-assisted-lance-development"

    def require_identity(self):
        self._require_scoped_identity(
            ("defeat_lance", "cartridge-trainer-story", int(MapId.LANCES_ROOM),
             (247, 47, 1), int(EventFlag.BEAT_LANCES_ROOM_TRAINER))
        )

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_lance" or rematch is not False:
            raise ValueError("assisted Lance admits only first-challenge Lance")


@dataclass
class ScopedAssistedLeagueRetryController(ScopedAssistedLoreleiController):
    """Source-bound recovery retry of the four Elite Four, never Champion."""

    @property
    def controller_name(self):
        return "scoped-assisted-league-retry-development"

    def require_identity(self):
        targets = {
            "defeat_lorelei": (MapId.LORELEIS_ROOM, (244, 44, 1), EventFlag.BEAT_LORELEI),
            "defeat_bruno": (MapId.BRUNOS_ROOM, (233, 33, 1), EventFlag.BEAT_BRUNO),
            "defeat_agatha": (MapId.AGATHAS_ROOM, (246, 46, 1), EventFlag.BEAT_AGATHA),
            "defeat_lance": (MapId.LANCES_ROOM, (247, 47, 1), EventFlag.BEAT_LANCES_ROOM_TRAINER),
        }
        if (
            type(self.contract) is not StoryTrainerContract
            or self.contract.objective_id not in targets
        ):
            raise ValueError("scoped League retry excludes undeclared targets")
        room, identity, event = targets[self.contract.objective_id]
        self._require_scoped_identity(
            (self.contract.objective_id, "cartridge-trainer-story", int(room), identity, int(event))
        )

    def require_objective(self, objective_id, *, rematch=None):
        self.require_identity()
        if objective_id != self.contract.objective_id or (
            rematch is not None and rematch is not True
        ):
            raise ValueError("scoped League retry requires its exact native rematch target")


@dataclass
class FrozenBrunoCopyStoryController(FrozenLoreleiStoryController):
    """Explicit isolated-copy experiment; no campaign or general League admission."""

    isolated_copy: bool = False

    @property
    def controller_name(self):
        return "frozen-damage-bruno-copy-development"

    @property
    def binding_identity(self):
        return super().binding_identity + (self.isolated_copy,)

    def require_identity(self):
        self._require_bound_identity(
            "c687ba16ef93787953b757af0badcff945fe0a73c24e93a5b9033fcaaa0c0400",
            "defeat_bruno",
            MapId.BRUNOS_ROOM,
            EventFlag.BEAT_BRUNO,
        )
        if self.isolated_copy is not True or self.battler.source_state_sha256 != (
            "365af4747021049aaeb17d433b9c6696ad056a7a6d78ea6ea93dc333600700f7"
        ):
            raise ValueError("Bruno experiment requires the admitted isolated source copy")

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_bruno" or rematch is not False:
            raise ValueError("Bruno copy bridge admits only first-challenge Bruno")


@dataclass
class FrozenBrunoStoryController(FrozenLoreleiStoryController):
    """Separate earned first-Bruno binding; does not broaden the copy admission."""

    @property
    def controller_name(self):
        return "frozen-damage-bruno-development"

    def require_identity(self):
        self._require_bound_identity(
            "b5991f27176ba6e966f70f8c42c87eef5ea138d40dac45fb2ef847d16613fdb9",
            "defeat_bruno",
            MapId.BRUNOS_ROOM,
            EventFlag.BEAT_BRUNO,
        )
        if self.battler.source_state_sha256 != (
            "365af4747021049aaeb17d433b9c6696ad056a7a6d78ea6ea93dc333600700f7"
        ):
            raise ValueError("earned Bruno requires the admitted source lineage")

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_bruno" or rematch is not False:
            raise ValueError("earned Bruno bridge admits only first-challenge Bruno")


@dataclass
class FrozenLaterLeagueStoryController(FrozenLoreleiStoryController):
    """One source-bound later-room development attempt, never League funding.

    The prospective runner additionally proves ancestry and copy/campaign scope.
    Binding the source here prevents mutating a prepared actor to another save.
    """

    source_sha256: str = ""

    @property
    def controller_name(self):
        return "frozen-damage-later-league-development"

    @property
    def binding_identity(self):
        return super().binding_identity + (self.source_sha256,)

    def require_identity(self):
        targets = {
            "defeat_agatha": (MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA),
            "defeat_lance": (MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER),
        }
        if (
            not isinstance(self.contract, StoryTrainerContract)
            or self.contract.objective_id not in targets
        ):
            raise ValueError("later League target is outside the explicit development scope")
        map_id, event = targets[self.contract.objective_id]
        self._require_bound_identity(
            "a8d52bca07a2b1aa824dd121a447eb5d6bdb0189c017b0e6616d84ddc6f737ec",
            self.contract.objective_id,
            map_id,
            event,
        )
        if (
            type(self.source_sha256) is not str
            or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
            or self.battler.source_state_sha256 != self.source_sha256
        ):
            raise ValueError("later League source differs from its prospective binding")

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != self.contract.objective_id or rematch is not False:
            raise ValueError("later League binding admits only its first-challenge target")


@dataclass
class FrozenLeagueChallengeStoryController(FrozenLaterLeagueStoryController):
    """One explicit native story challenge/rechallenge; never an income binding."""

    rechallenge: bool = False

    @property
    def controller_name(self):
        return "frozen-damage-league-challenge-development"

    @property
    def binding_identity(self):
        return super().binding_identity + (self.rechallenge,)

    def require_identity(self):
        targets = {
            "defeat_lorelei": (MapId.LORELEIS_ROOM, EventFlag.BEAT_LORELEI),
            "defeat_bruno": (MapId.BRUNOS_ROOM, EventFlag.BEAT_BRUNO),
            "defeat_agatha": (MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA),
            "defeat_lance": (MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER),
            "defeat_champion": (MapId.CHAMPIONS_ROOM, EventFlag.BEAT_CHAMPION_RIVAL),
        }
        if (
            not isinstance(self.contract, StoryTrainerContract)
            or self.contract.objective_id not in targets
        ):
            raise ValueError("undeclared League story challenge target")
        map_id, event = targets[self.contract.objective_id]
        self._require_bound_identity(
            "5d9efd1d3d756716a51b7a62a4aac181cfccb3a3b17b91686c08139fabd54067",
            self.contract.objective_id,
            map_id,
            event,
            "cartridge-final-story"
            if self.contract.objective_id == "defeat_champion"
            else "cartridge-trainer-story",
        )
        if (
            type(self.rechallenge) is not bool
            or type(self.source_sha256) is not str
            or len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
            or self.battler.source_state_sha256 != self.source_sha256
        ):
            raise ValueError("League challenge source or re-entry binding differs")

    def require_objective(self, objective_id, *, rematch=None):
        self.require_identity()
        # run() owns only the already bound battle. Outer story admission must
        # supply its explicit boolean and match the prepared challenge mode.
        if objective_id != self.contract.objective_id or (
            rematch is not None and (type(rematch) is not bool or rematch != self.rechallenge)
        ):
            raise ValueError("League story target or re-entry mode changed")

    def require_party_hp(self, raw):
        hp = raw.party_hp
        if (
            type(raw.party_count) is not int
            or not 1 <= raw.party_count <= 6
            or hp is None
            or len(hp) != raw.party_count
            or any(type(v) is not int or v < 0 for v in hp)
            or not any(hp)
        ):
            raise ValueError("League story requires a coherent living party")

    def require_champion_target(self, script, quote):
        self.require_identity()
        if (
            self.contract.objective_id != "defeat_champion"
            or self.contract.trainer_identity != script.active_identity
            or self.contract.defeated_event != script.event_flag
            or self.contract.victory_money != quote.expected_victory_money
        ):
            raise ValueError("Champion story contract differs from live cartridge script")


@dataclass
class FrozenEarnedAgathaStoryController(FrozenLoreleiStoryController):
    """One owner-admitted earned attempt; no default or copy authority change."""

    @property
    def controller_name(self):
        return "frozen-risk-cost-agatha-development"

    def require_identity(self):
        self._require_candidate_identity(AGATHA_STORY_ADMISSION_SHA256)

    def _require_candidate_identity(self, admission_sha256):
        if (
            type(self.admission) is not bytes
            or sha256(self.admission).hexdigest() != admission_sha256
            or type(self.battler) is not FrozenTrainerBattler
            or (self.battler.model_sha256, self.battler.qualification_sha256)
            != (AGATHA_STORY_SHA256, admission_sha256)
            or type(self.contract) is not StoryTrainerContract
            or type(self.maximum_decisions) is not int
            or not 1 <= self.maximum_decisions <= 80
        ):
            raise ValueError("earned story requires exact candidate, receipt and decision bound")
        self.battler.require_story_contract(self.contract)

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_agatha" or rematch is not False:
            raise ValueError("earned Agatha admits only its first-challenge target")


@dataclass
class FrozenEarnedLanceStoryController(FrozenEarnedAgathaStoryController):
    """Separate earned Lance receipt; leaves the Agatha-only permission intact."""

    @property
    def controller_name(self):
        return "frozen-risk-cost-lance-development"

    def require_identity(self):
        self._require_candidate_identity(LANCE_STORY_ADMISSION_SHA256)

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_lance" or rematch is not False:
            raise ValueError("earned Lance admits only its first-challenge target")


@dataclass
class ScopedAssistedChampionController(ScopedAssistedLoreleiController):
    """Exact-source development Champion bridge, never default player authority."""

    @property
    def controller_name(self):
        return "scoped-assisted-champion-development"

    def require_identity(self):
        identity = getattr(self.contract, "trainer_identity", None)
        if identity not in ((243, 43, 1), (243, 43, 2), (243, 43, 3)):
            raise ValueError("scoped Champion requires a native final-rival roster")
        self._require_scoped_identity(
            ("defeat_champion", "cartridge-final-story", int(MapId.CHAMPIONS_ROOM),
             identity, int(EventFlag.BEAT_CHAMPION_RIVAL))
        )

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_champion" or type(rematch) is not bool:
            raise ValueError("scoped Champion requires its exact story target")

    require_party_hp = FrozenLeagueChallengeStoryController.require_party_hp
    require_champion_target = FrozenLeagueChallengeStoryController.require_champion_target


@dataclass
class FrozenEarnedChampionStoryController(FrozenEarnedAgathaStoryController):
    """Exact earned Champion source; no broad deployment or rematch admission."""

    @property
    def controller_name(self):
        return "frozen-risk-cost-champion-development"

    def require_identity(self):
        self._require_candidate_identity(CHAMPION_STORY_ADMISSION_SHA256)

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_champion" or rematch is not False:
            raise ValueError("earned Champion admits only its first-challenge target")

    # These semantic checks do not grant the older controller's model permission.
    require_party_hp = FrozenLeagueChallengeStoryController.require_party_hp
    require_champion_target = FrozenLeagueChallengeStoryController.require_champion_target


@dataclass
class FrozenEarnedLeagueChainController(FrozenEarnedAgathaStoryController):
    """One source-chained rechallenge; no default model or income authority."""

    @property
    def controller_name(self):
        return "frozen-risk-cost-league-chain-development"

    @property
    def binding_identity(self):
        return super().binding_identity + (self.battler.story_chain_scope,)

    def require_identity(self):
        self._require_candidate_identity(LEAGUE_CHAIN_ADMISSION_SHA256)

    def require_objective(self, objective_id, *, rematch=None):
        self.require_identity()
        if objective_id != self.contract.objective_id or (
            rematch is not None and rematch is not True
        ):
            raise ValueError("earned League chain requires its exact re-entry target")

    require_party_hp = FrozenLeagueChallengeStoryController.require_party_hp
    require_champion_target = FrozenLeagueChallengeStoryController.require_champion_target


def story_league_controller(runtime, objective_id, *, rematch=False):
    """Resolve the explicit story binding without changing default K authority."""
    from .red_learned_league import learned_league_controller
    from .red_story_copy import StoryCopyController

    from .red_train_lorelei import FrozenTrainLoreleiStoryController

    controller = getattr(runtime, "league_story_battle_controller", None)
    if controller is None:
        return learned_league_controller(runtime)
    if getattr(runtime, "league_battle_controller", None) is not None or type(controller) not in (
        FrozenLoreleiStoryController,
        FrozenTrainLoreleiStoryController,
        ScopedAssistedLoreleiController,
        ScopedAssistedBrunoController,
        ScopedAssistedAgathaController,
        ScopedAssistedLanceController,
        ScopedAssistedLeagueRetryController,
        ScopedAssistedChampionController,
        FrozenBrunoCopyStoryController,
        FrozenBrunoStoryController,
        FrozenLaterLeagueStoryController,
        FrozenLeagueChallengeStoryController,
        FrozenEarnedAgathaStoryController,
        FrozenEarnedLanceStoryController,
        FrozenEarnedChampionStoryController,
        FrozenEarnedLeagueChainController,
        StoryCopyController,
    ):
        raise ValueError("conflicting or unsupported League story bindings")
    controller.require_objective(objective_id, rematch=rematch)
    return controller
