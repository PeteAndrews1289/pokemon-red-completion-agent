"""Opt-in frozen battler at the player's ordinary trainer-funding seam.

This is not a wild-capture or Elite Four override. The outer funding verifier
continues to own identity, party preservation, payout and field settlement.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleRuntimeTiming,
    advance_battle_to_policy_boundary,
)
from .battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from .observation import BattleMenuPhase, PokemonRedStateReader, RawGameState
from .provenance import canonical_sha256
from .red_autonomous_player import _record, _write
from .red_battle_scenario import prepare_red_battle_scenario
from .red_development_preparation_scope import DevelopmentPreparationScope
from .red_development_story_scope import DevelopmentStoryScope
from .red_league_story_chain import LEAGUE_CHAIN_ADMISSION_SHA256, EarnedLeagueStepScope
from .red_trainer_practice_episode import (
    LiveTrainerSession,
    RedTrainerPracticeEpisode,
    run_live_red_trainer_practice_episode,
)
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_practice_log import TrainerPracticeEventLog
from .red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy
from .red_trajectory import PokemonRedObservationEncoder
from .scenario_lab import ScenarioPartition
from .wild_training_objective import WildTrainingObjective

FROZEN_J_SHA256 = "260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09"
FROZEN_K_SHA256 = "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472"
K_QUALIFICATION_SHA256 = "5fc8b4283d36e6f4ca272ff7fa5291b984e9c7a2cd85e5c16c1a34304467370f"
ADDITIVE_STORY_SHA256 = "8ef6a8512bc6c2b4e21b6a95e98ed769bc1634ea90f997961f2e6fd3f7227a12"
ADDITIVE_STORY_ADMISSION_SHA256 = "4e68390900853e1213a540d0a044cca379d8700926f3a784c65de1819e3b56bd"
DAMAGE_STORY_SHA256 = "4ea4cfde342406d55e54650572fd9a7991c7fa5216698ff3ecf62109284398c3"
DAMAGE_STORY_MODEL_SHA256 = "c8a1aa79c3b2baf4692c48953b1a829a43b9a1012f2a6c77e1051b5f79704ab3"
DAMAGE_STORY_ADMISSION_SHA256 = "d513b0fd3df081a86a6353ed74447e705e457395fbedf8a752b6b9af53717a29"
AGATHA_STORY_SHA256 = "1b8c8361949bfe33f71f349078f100943c67acfd21b2f84f7cd2612ad958313a"
AGATHA_STORY_MODEL_SHA256 = "905b7e5a8943278bee14d7cb1e55361c1bdb2445dd35e943382f24b2df39e3f4"
AGATHA_STORY_ADMISSION_SHA256 = "49d5f1c481f2130cdfcaa7ca9f03d6241944d8fff2c869bb4b3b74ac6307d932"
AGATHA_STORY_SOURCE_SHA256 = "359a96aa317019a8a4d3627711a8faab668091eaa6c48e7485c81d4c17211719"
LANCE_STORY_ADMISSION_SHA256 = "65ed662cf7ec7d17c4358eb0042ee5d6f55c524ff1a2031a13637cf2dd35125e"
LANCE_STORY_SOURCE_SHA256 = "6ab3bf1b2a81fe5d213f769124db17d9dca2e4b0313551c17765cb3cc9c35717"
CHAMPION_STORY_ADMISSION_SHA256 = "f16ca748947b0fc3e0418a8a940bedfe97ada96687fff66efa75ba295c7e7eae"
CHAMPION_STORY_SOURCE_SHA256 = "e40e37ce679531a46b0c52839b81ee4c582fc7e7a90dc99508a615e1c58d4ab6"
TRAIN_RISK_AUTHORITY = "frozen-risk-cost-train-story"
EVALUATION_RISK_AUTHORITY = "frozen-risk-cost-evaluation-story"


class FrozenTrainerTerminalUnverified(RuntimeError):
    """Exited combat without actor proof; the funding referee must still prove a win.

    Red may reuse the enemy roster buffer while loading the overworld. This is
    not a success receipt and never licenses another battle or teacher action.
    """

    def __init__(self, episode: RedTrainerPracticeEpisode):
        if (
            not isinstance(episode, RedTrainerPracticeEpisode)
            or episode.battle_won
            or episode.final_battle_state != 0
            or episode.stop_reason != "battle_exited_without_win"
        ):
            raise ValueError("unverified trainer handoff needs the exact exited-combat outcome")
        self.episode = episode
        super().__init__("learned trainer stopped: battle_exited_without_win")


# Known-failure copy diagnostics, not general Tower or campaign admission.
TOWER_EVALUATION_SOURCES = frozenset(
    {
        "5c6833ccbbacd2dac60f2e72054614dd56cf7835883d0e6e6fbed0a5e410cfd5",
        "3b902f4c0b70a7344743f325b967df278cd63437ac342ab9f663d199266a4125",
    }
)
EVALUATION_RISK_ADMISSION_SHA256 = canonical_sha256(
    {
        "schema": "pokemon.red.risk-cost-evaluation-story.v1",
        "model_sha256": AGATHA_STORY_SHA256,
        "partition": "development",
        "explicit_source_contract_required": True,
        "fit_allowed": False,
        "maximum_battles": 1,
        "campaign_promotion": False,
    }
)
TRAIN_RISK_ADMISSION_SHA256 = canonical_sha256(
    {
        "schema": "pokemon.red.risk-cost-train-story.v1",
        "model_sha256": AGATHA_STORY_SHA256,
        "partition": "train",
        "explicit_source_contract_required": True,
        "allow_status_moves": True,
        "allow_stranded_accuracy_move": True,
        "battle_model_fit": False,
        "campaign_promotion": False,
    }
)


@dataclass(frozen=True)
class TrainRiskStoryScope:
    """Prospective lesson scope; never a replacement for source authentication."""

    experiment_sha256: str
    source_state_sha256: str
    root_lineage_id: str
    contract: object

    def __post_init__(self):
        from .red_story_battle import StoryTrainerContract

        if (
            any(
                type(s) is not str or len(s) != 64 or any(c not in "0123456789abcdef" for c in s)
                for s in (self.experiment_sha256, self.source_state_sha256)
            )
            or type(self.root_lineage_id) is not str
            or not self.root_lineage_id
            or type(self.contract) is not StoryTrainerContract
        ):
            raise ValueError("TRAIN risk story requires an explicit source and contract")

    def document(self):
        from dataclasses import asdict

        return asdict(self)


def _risk_cost_story_binding(admission_sha256):
    """Same weights, separate immutable source/target admissions; no wildcard."""
    bindings = {
        AGATHA_STORY_ADMISSION_SHA256: (
            AGATHA_STORY_SOURCE_SHA256,
            ("defeat_agatha", "cartridge-trainer-story", 247, (246, 46, 1), 2289, 5940),
        ),
        LANCE_STORY_ADMISSION_SHA256: (
            LANCE_STORY_SOURCE_SHA256,
            ("defeat_lance", "cartridge-trainer-story", 113, (247, 47, 1), 2297, 6138),
        ),
        CHAMPION_STORY_ADMISSION_SHA256: (
            CHAMPION_STORY_SOURCE_SHA256,
            ("defeat_champion", "cartridge-final-story", 120, (243, 43, 2), 2305, 6435),
        ),
    }
    if admission_sha256 not in bindings:
        raise ValueError("risk/cost candidate requires an exact earned story admission")
    return bindings[admission_sha256]


def story_battle_authority(model_sha256, admission_sha256):
    """Exact opt-in story scope; never ordinary funding, wild or League."""
    return {
        (AGATHA_STORY_SHA256, EVALUATION_RISK_ADMISSION_SHA256): EVALUATION_RISK_AUTHORITY,
        (AGATHA_STORY_SHA256, TRAIN_RISK_ADMISSION_SHA256): TRAIN_RISK_AUTHORITY,
        (FROZEN_K_SHA256, K_QUALIFICATION_SHA256): "frozen-k-story-development",
        (
            ADDITIVE_STORY_SHA256,
            ADDITIVE_STORY_ADMISSION_SHA256,
        ): "frozen-additive-story-development",
        (DAMAGE_STORY_SHA256, DAMAGE_STORY_ADMISSION_SHA256): "frozen-damage-story-development",
        (AGATHA_STORY_SHA256, AGATHA_STORY_ADMISSION_SHA256): "frozen-risk-cost-agatha-development",
        (AGATHA_STORY_SHA256, LANCE_STORY_ADMISSION_SHA256): "frozen-risk-cost-lance-development",
        (
            AGATHA_STORY_SHA256,
            CHAMPION_STORY_ADMISSION_SHA256,
        ): "frozen-risk-cost-champion-development",
        (
            AGATHA_STORY_SHA256,
            LEAGUE_CHAIN_ADMISSION_SHA256,
        ): "frozen-risk-cost-league-chain-development",
    }.get((model_sha256, admission_sha256))


def story_party_limit(model_sha256, admission_sha256):
    """Owner-admitted development scope, not ordinary funding qualification."""
    if story_battle_authority(model_sha256, admission_sha256):
        return 6
    return 0


def load_story_trainer_model(payload: bytes, admission: bytes) -> TrainerPracticeThreeHeadModel:
    if not story_party_limit(
        hashlib.sha256(payload).hexdigest(), hashlib.sha256(admission).hexdigest()
    ):
        raise ValueError("story model requires exact checkpoint and development admission")
    return TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))


def load_train_risk_story_model(payload: bytes) -> TrainerPracticeThreeHeadModel:
    """Load exact existing weights; execution still needs a TRAIN lesson scope."""
    if hashlib.sha256(payload).hexdigest() != AGATHA_STORY_SHA256:
        raise ValueError("TRAIN risk checkpoint bytes differ")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))
    if canonical_sha256(model.to_dict()) != AGATHA_STORY_MODEL_SHA256:
        raise ValueError("TRAIN risk checkpoint object differs")
    return model


def qualified_party_limit(model_sha256: str | None, qualification_sha256: str | None = None) -> int:
    """Execution coverage only; never waive the outer funding-cost verifier."""
    if model_sha256 == FROZEN_J_SHA256:
        return 3
    if model_sha256 == FROZEN_K_SHA256 and qualification_sha256 == K_QUALIFICATION_SHA256:
        return 6
    return 0


def load_frozen_trainer_model(
    payload: bytes,
    expected_sha256: str,
    *,
    qualification: bytes | None = None,
) -> TrainerPracticeThreeHeadModel:
    receipt_sha = hashlib.sha256(qualification).hexdigest() if qualification is not None else None
    if (
        not qualified_party_limit(expected_sha256, receipt_sha)
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ValueError("player battler must match frozen J or receipt-bound qualified K")
    return TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))


@dataclass
class FrozenTrainerBattler:
    wild_training_objective_version: ClassVar[int] = 1
    session: LiveTrainerSession
    model: TrainerPracticeThreeHeadModel
    output: Path
    source_commit: str
    root_lineage_id: str
    source_state_sha256: str
    public_species_base_stats: Mapping[int, tuple[int, int, int, int, int]]
    calls: int = 0
    model_sha256: str = FROZEN_J_SHA256
    qualification_sha256: str | None = None
    story_chain_scope: EarnedLeagueStepScope | None = None
    source_partition: ScenarioPartition = ScenarioPartition.DEVELOPMENT
    train_funding_diagnostic: bool = False
    train_story_contract: object = None
    train_risk_story_scope: TrainRiskStoryScope | None = None
    evaluation_story_scope: TrainRiskStoryScope | None = None
    development_story_scope: DevelopmentStoryScope | None = None
    development_preparation_scope: DevelopmentPreparationScope | None = None
    pp_depleted_switch_screen: bool = False
    mechanics_aware_tower_choices: bool = False
    diagnostic_tower_productive_stay: bool = False

    def tower_mechanics_active(self, expected_map, authority):
        """Disclosed mechanics screen for K's DEVELOPMENT Tower continuation only."""
        if type(self.diagnostic_tower_productive_stay) is not bool or (
            self.diagnostic_tower_productive_stay and not self.mechanics_aware_tower_choices
        ):
            raise ValueError("Tower diagnostic stay requires explicit Tower mechanics")
        if type(self.mechanics_aware_tower_choices) is not bool or (
            self.mechanics_aware_tower_choices
            and (
                self.source_partition is not ScenarioPartition.DEVELOPMENT
                or self.model_sha256 != FROZEN_K_SHA256
                or self.qualification_sha256 != K_QUALIFICATION_SHA256
                or self.development_story_scope is not None
                or self.development_preparation_scope is not None
                or self.train_story_contract is not None
                or self.train_risk_story_scope is not None
                or self.evaluation_story_scope is not None
                or self.story_chain_scope is not None
                or self.train_funding_diagnostic
            )
        ):
            raise ValueError("Tower mechanics require explicit frozen K development")
        return bool(
            self.mechanics_aware_tower_choices
            and type(expected_map) is int
            and 143 <= expected_map <= 148
            and authority == "frozen-k-story-development"
        )

    def wild_authority(self, expected_map=None):
        scope = self.development_preparation_scope
        if scope is not None:
            if type(scope) is not DevelopmentPreparationScope:
                raise ValueError("typed development preparation scope required")
            return scope.require(self, expected_map)
        if (self.model_sha256, self.qualification_sha256) != (
            FROZEN_K_SHA256,
            K_QUALIFICATION_SHA256,
        ):
            raise ValueError("wild training requires exact K and its identity receipt")
        return "frozen-k-wild-training-development"

    def story_limit(self):
        if self.development_story_scope is not None:
            if type(self.development_story_scope) is not DevelopmentStoryScope:
                raise ValueError("typed development story scope required")
            return self.development_story_scope.require(self)
        return story_party_limit(self.model_sha256, self.qualification_sha256)

    def story_authority(self):
        if self.development_story_scope is not None:
            self.story_limit()
            return self.development_story_scope.authority
        return story_battle_authority(self.model_sha256, self.qualification_sha256)

    def pp_reentry_screen_active(self, authority):
        """Explicit opt-in for exact K or authenticated DEVELOPMENT story scope."""
        if type(self.pp_depleted_switch_screen) is not bool:
            raise ValueError("PP reentry screen requires an explicit boolean")
        if not self.pp_depleted_switch_screen:
            return False
        if self.development_story_scope is not None:
            # require() checks partition, source, lineage, model content and
            # work-order identity. It does not admit TRAIN or an unscoped model.
            self.story_limit()
            if authority != self.story_authority():
                raise ValueError("PP reentry screen requires its scoped story authority")
            return True
        if (
            self.source_partition is not ScenarioPartition.DEVELOPMENT
            or self.model_sha256 != FROZEN_K_SHA256
            or self.qualification_sha256 != K_QUALIFICATION_SHA256
            or self.development_preparation_scope is not None
            or self.train_story_contract is not None
            or self.train_risk_story_scope is not None
            or self.evaluation_story_scope is not None
        ):
            raise ValueError("PP reentry screen requires explicit frozen K or scoped development")
        return authority == "frozen-k-story-development"

    def forced_struggle_active(self, authority):
        """Reuse native forced mechanics only under the existing explicit scope."""
        return authority == "frozen-k-story-development" or (
            self.development_story_scope is not None and self.pp_reentry_screen_active(authority)
        )

    def require_evaluation_story_scope(self):
        """One explicit DEVELOPMENT comparison; never training or campaign authority."""
        scope = self.evaluation_story_scope
        if (
            type(scope) is not TrainRiskStoryScope
            or self.source_partition is not ScenarioPartition.DEVELOPMENT
            or self.train_story_contract is not None
            or self.train_risk_story_scope is not None
            or self.train_funding_diagnostic
            or self.story_chain_scope is not None
            or (self.model_sha256, self.qualification_sha256)
            != (AGATHA_STORY_SHA256, EVALUATION_RISK_ADMISSION_SHA256)
            or scope.source_state_sha256 != self.source_state_sha256
            or scope.root_lineage_id != self.root_lineage_id
            or not isinstance(self.model, TrainerPracticeThreeHeadModel)
            or canonical_sha256(self.model.to_dict()) != AGATHA_STORY_MODEL_SHA256
        ):
            raise ValueError("evaluation story model, partition or source differs")
        contract = scope.contract
        identity = (contract.map_id, contract.trainer_identity, contract.defeated_event)
        tower_copy = (
            identity == (145, (245, 45, 10), 250)
            and scope.source_state_sha256 in TOWER_EVALUATION_SOURCES
            and scope.root_lineage_id == "fresh-development-start-20260928-v1"
            and contract.objective_id == "rescue_fuji"
            and contract.battle_plan_id == "tower-channeler-copy-comparison"
            and contract.victory_money == 690
            and not contract.victory_items
            and not contract.victory_badge_bits
        )
        if identity != (65, (235, 35, 1), 191) and not tower_copy:
            raise ValueError(
                "evaluation story requires a declared Misty or exact Tower copy comparison"
            )
        return contract

    def require_train_story_scope(self):
        """One explicit TRAIN story contract; no battle-model fit or promotion.

        This opts into an isolated goal-policy lesson, not funding authority.
        K remains the default; a risk actor needs its own explicit scope.
        The caller authenticates the TRAIN origin
        and prospectively records its fixture and lesson declaration.
        """
        from .red_story_battle import StoryTrainerContract

        if (
            not isinstance(self.train_story_contract, StoryTrainerContract)
            or self.source_partition is not ScenarioPartition.TRAIN
            or self.train_funding_diagnostic is not False
            or self.evaluation_story_scope is not None
        ):
            raise ValueError("TRAIN story requires a declared contract and TRAIN partition")
        if self.development_story_scope is not None:
            scope = self.development_story_scope
            if getattr(scope, "train_admission", None) is None:
                raise ValueError("TRAIN story lacks explicit production admission")
            scope.require(self, self.train_story_contract)
            return self.train_story_contract
        if self.train_risk_story_scope is not None:
            scope = self.train_risk_story_scope
            if (
                type(scope) is not TrainRiskStoryScope
                or (self.model_sha256, self.qualification_sha256)
                != (AGATHA_STORY_SHA256, TRAIN_RISK_ADMISSION_SHA256)
                or scope.contract != self.train_story_contract
                or scope.source_state_sha256 != self.source_state_sha256
                or scope.root_lineage_id != self.root_lineage_id
                or self.story_chain_scope is not None
                or not isinstance(self.model, TrainerPracticeThreeHeadModel)
                or canonical_sha256(self.model.to_dict()) != AGATHA_STORY_MODEL_SHA256
            ):
                raise ValueError("TRAIN risk story model or declared scope differs")
        elif (self.model_sha256, self.qualification_sha256) != (
            FROZEN_K_SHA256,
            K_QUALIFICATION_SHA256,
        ):
            raise ValueError("TRAIN story requires exact qualified K or explicit risk scope")
        return self.train_story_contract

    def _train_story_document(self):
        from dataclasses import asdict

        return asdict(self.require_train_story_scope())

    def _train_risk_story_document(self):
        scope = self.train_risk_story_scope
        return None if scope is None else scope.document()

    def require_funding_scope(self) -> None:
        """Validate before travel; TRAIN funding is an explicit, unfitted K probe."""
        if self.train_risk_story_scope is not None or self.evaluation_story_scope is not None:
            raise ValueError("TRAIN risk story cannot authorize funding")
        if type(self.train_funding_diagnostic) is not bool:
            raise ValueError("TRAIN funding diagnostic opt-in must be boolean")
        if self.train_funding_diagnostic and (
            self.source_partition is not ScenarioPartition.TRAIN
            or self.model_sha256 != FROZEN_K_SHA256
            or self.qualification_sha256 != K_QUALIFICATION_SHA256
        ):
            raise ValueError("TRAIN funding diagnostic requires exact qualified K and TRAIN")
        if self.source_partition is ScenarioPartition.TRAIN and not self.train_funding_diagnostic:
            raise ValueError("TRAIN funding requires explicit diagnostic opt-in")
        if not isinstance(
            self.source_partition, ScenarioPartition
        ) or self.source_partition not in {
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        }:
            raise ValueError("funding source partition is unsupported")

    def _risk_cost_binding(self):
        if self.qualification_sha256 == LEAGUE_CHAIN_ADMISSION_SHA256:
            if type(self.story_chain_scope) is not EarnedLeagueStepScope:
                raise ValueError("earned League requires its authenticated chain scope")
            return self.story_chain_scope.binding(self)
        if self.story_chain_scope is not None:
            raise ValueError("chain scope cannot replace an older story admission")
        return _risk_cost_story_binding(self.qualification_sha256)

    def require_story_identity(self):
        if self.development_story_scope is not None:
            self.story_limit()
            return
        if (
            self.evaluation_story_scope is not None
            or self.qualification_sha256 == EVALUATION_RISK_ADMISSION_SHA256
        ):
            self.require_evaluation_story_scope()
            return
        if (
            self.source_partition is ScenarioPartition.TRAIN
            or self.train_story_contract is not None
            or self.train_risk_story_scope is not None
            or self.qualification_sha256 == TRAIN_RISK_ADMISSION_SHA256
        ):
            self.require_train_story_scope()
        if not story_party_limit(self.model_sha256, self.qualification_sha256):
            raise ValueError("story authority requires an exact admitted model and receipt")
        if self.model_sha256 == DAMAGE_STORY_SHA256 and (
            not isinstance(self.model, TrainerPracticeThreeHeadModel)
            or canonical_sha256(self.model.to_dict()) != DAMAGE_STORY_MODEL_SHA256
        ):
            raise ValueError("story damage model object differs from admitted checkpoint")
        if (self.model_sha256 == AGATHA_STORY_SHA256 and self.train_risk_story_scope is None) and (
            not isinstance(self.model, TrainerPracticeThreeHeadModel)
            or canonical_sha256(self.model.to_dict()) != AGATHA_STORY_MODEL_SHA256
            or self.source_state_sha256 != self._risk_cost_binding()[0]
        ):
            raise ValueError("risk/cost model object or earned source differs from admission")

    def require_story_contract(self, contract):
        """Narrow candidate admission must also hold before introduction inputs."""
        self.require_story_identity()
        if self.development_story_scope is not None:
            self.development_story_scope.require(self, contract)
            return
        if self.evaluation_story_scope is not None:
            if (
                contract != self.require_evaluation_story_scope()
                or self.calls != 0
                or (self.output / "battle-0001").exists()
            ):
                raise ValueError("evaluation story contract changed or attempt consumed")
            return
        if (
            self.source_partition is ScenarioPartition.TRAIN
            and contract != self.require_train_story_scope()
        ):
            raise ValueError("TRAIN story contract differs from declared lesson")
        if (self.model_sha256 == AGATHA_STORY_SHA256 and self.train_risk_story_scope is None) and (
            (
                contract.objective_id,
                contract.battle_plan_id,
                contract.map_id,
                contract.trainer_identity,
                contract.defeated_event,
                contract.victory_money,
            )
            != self._risk_cost_binding()[1]
            or contract.victory_items
            or contract.victory_badge_bits
            or self.calls != 0
            or (self.output / "battle-0001").exists()
        ):
            raise ValueError("earned candidate scope changed or its battle was already claimed")

    def run(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        move_slot_policy: Callable[[RawGameState], int],
        *,
        expected_map: int,
        intent: BattleIntent,
        timing: BattleRuntimeTiming,
        label: str,
        consume_battle_start_schedule: bool,
        move_decision_guard: Callable[[RawGameState], None],
    ) -> RawGameState:
        # The old policy is deliberately never queried, including on failure.
        if consume_battle_start_schedule or intent.battle_plan_id != "ordinary-trainer-funding":
            raise ValueError("frozen battler is enabled only for ordinary trainer funding")
        self.require_funding_scope()
        self._play(
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
            label=label,
            decision_guard=move_decision_guard,
            resume=False,
            require_win=True,
            train_funding_diagnostic=self.train_funding_diagnostic,
        )
        return reader.read()

    def continue_battle(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        *,
        expected_map: int,
        timing: BattleRuntimeTiming,
        decision_guard: Callable[[RawGameState], None],
        maximum_decisions: int = 80,
        story_authority: bool = False,
    ) -> RedTrainerPracticeEpisode:
        """Continue an already-owned MAIN, switch-prompt or faint boundary.

        This returns a battle outcome, not a funding receipt. A caller must
        settle and independently verify the field handoff, including a loss.
        """
        if type(story_authority) is not bool or (story_authority and not self.story_limit()):
            raise ValueError("story authority requires exact qualified K or admitted story model")
        if story_authority:
            self.require_story_identity()
        return self._play(
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
            label="learned trainer continuation",
            decision_guard=decision_guard,
            resume=True,
            require_win=False,
            maximum_decisions=maximum_decisions,
            authority=(self.story_authority() if story_authority else None),
        )

    def run_wild_training(
        self,
        reader,
        executor,
        *,
        expected_map,
        timing,
        decision_guard,
        maximum_decisions=80,
        training_objective: WildTrainingObjective | None = None,
    ) -> RedTrainerPracticeEpisode:
        """Explicit DEVELOPMENT knockout probe; never a capture-policy override."""
        if training_objective is not None and type(training_objective) is not WildTrainingObjective:
            raise ValueError("typed selected wild training objective required")
        authority = self.wild_authority(expected_map)
        raw = reader.read()
        if raw.battle_state != 1 or raw.map_id != expected_map:
            raise ValueError("wild training requires an active wild encounter")
        return self._play(
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
            label="learned wild training",
            decision_guard=decision_guard,
            resume=False,
            require_win=False,
            maximum_decisions=maximum_decisions,
            authority=authority,
            wild_training=True,
            **({"training_objective": training_objective} if training_objective is not None else {}),
        )

    def _play(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        *,
        expected_map: int,
        timing: BattleRuntimeTiming,
        label: str,
        decision_guard: Callable[[RawGameState], None],
        resume: bool,
        require_win: bool,
        authority: str | None = None,
        maximum_decisions: int = 80,
        allow_immune_switch_recovery: bool = False,
        wild_training: bool = False,
        train_funding_diagnostic: bool = False,
        training_objective: WildTrainingObjective | None = None,
    ) -> RedTrainerPracticeEpisode:
        if training_objective is not None and (
            type(training_objective) is not WildTrainingObjective or not wild_training
            or training_objective.party_witness.source_state_sha256 != self.source_state_sha256
        ):
            raise ValueError("wild training objective differs from its admitted source or mode")
        if not isinstance(
            self.source_partition, ScenarioPartition
        ) or self.source_partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
            raise ValueError("live battler source partition is unsupported")
        train_diagnostic = self.source_partition is ScenarioPartition.TRAIN
        scoped_train = train_diagnostic and any(
            scope is not None and getattr(scope, "train_admission", None) is not None
            for scope in (self.development_story_scope, self.development_preparation_scope)
        )
        depleted_screen = self.pp_reentry_screen_active(authority)
        tower_mechanics = self.tower_mechanics_active(expected_map, authority)
        train_story = self.train_story_contract is not None
        train_risk = self.train_risk_story_scope is not None
        development_scope = self.development_story_scope
        development = development_scope is not None
        forced_struggle = self.forced_struggle_active(authority)
        preparation_scope = self.development_preparation_scope
        if preparation_scope is not None and (
            authority != self.wild_authority(expected_map)
            or not wild_training
            or resume
            or require_win
            or train_funding_diagnostic
            or allow_immune_switch_recovery
        ):
            raise ValueError("development preparation cannot authorize other battle modes")
        if development_scope is not None:
            self.story_limit()
            if (
                authority != self.story_authority()
                or not resume
                or require_win
                or wild_training
                or train_funding_diagnostic
                or allow_immune_switch_recovery
            ):
                raise ValueError("development story cannot authorize other battle modes")
            development_scope.require_live(reader, expected_map)
        evaluation = (
            self.evaluation_story_scope is not None
            or self.qualification_sha256 == EVALUATION_RISK_ADMISSION_SHA256
        )
        evaluation_scope_document = None
        if evaluation:
            contract = self.require_evaluation_story_scope()
            assert self.evaluation_story_scope is not None
            evaluation_scope_document = self.evaluation_story_scope.document()
            raw = reader.read()
            if (
                not resume
                or require_win
                or wild_training
                or train_funding_diagnostic
                or allow_immune_switch_recovery
                or authority != EVALUATION_RISK_AUTHORITY
                or expected_map != contract.map_id
                or raw.map_id != contract.map_id
                or raw.battle_state != 2
                or reader.read_active_trainer_identity() != contract.trainer_identity
                or self.calls != 0
                or (self.output / "battle-0001").exists()
            ):
                raise ValueError("evaluation story cannot change battle or repeat its attempt")
        if train_risk or self.qualification_sha256 == TRAIN_RISK_ADMISSION_SHA256:
            self.require_train_story_scope()
        if train_story:
            contract = self.require_train_story_scope()
            raw = reader.read()
            if (
                not resume
                or require_win
                or wild_training
                or train_funding_diagnostic
                or allow_immune_switch_recovery
                or authority != (self.story_authority() if scoped_train else
                    story_battle_authority(self.model_sha256, self.qualification_sha256))
                or expected_map != contract.map_id
                or raw.map_id != contract.map_id
                or raw.battle_state != 2
                or reader.read_active_trainer_identity() != contract.trainer_identity
            ):
                raise ValueError("TRAIN story cannot authorize another battle or mode")
        if type(train_funding_diagnostic) is not bool or (
            train_funding_diagnostic
            and (
                not train_diagnostic
                or wild_training
                or resume
                or not require_win
                or authority is not None
                or allow_immune_switch_recovery
                or not self.train_funding_diagnostic
            )
        ):
            raise ValueError("TRAIN funding diagnostic cannot authorize other battle modes")
        if train_funding_diagnostic:
            self.require_funding_scope()
        if train_diagnostic and not scoped_train and (
            not (wild_training or train_funding_diagnostic or train_story)
            or (
                not train_risk
                and (
                    self.model_sha256 != FROZEN_K_SHA256
                    or self.qualification_sha256 != K_QUALIFICATION_SHA256
                )
            )
        ):
            raise ValueError("TRAIN live capture requires explicit qualified K diagnostic")
        if (
            self.model_sha256 == DAMAGE_STORY_SHA256
            and authority != "frozen-damage-story-development"
        ):
            raise ValueError("damage candidate requires explicit story-only authority")
        if (
            self.model_sha256 == AGATHA_STORY_SHA256
            and not train_risk
            and not evaluation
            and not development
        ):
            self.require_story_identity()
            _, contract = self._risk_cost_binding()
            if (
                authority != story_battle_authority(self.model_sha256, self.qualification_sha256)
                or not resume
                or require_win
                or wild_training
                or allow_immune_switch_recovery
                or expected_map != contract[2]
                or self.calls != 0
                or (self.output / "battle-0001").exists()
            ):
                raise ValueError("candidate requires one source-bound earned story battle")
            raw = reader.read()
            if (
                raw.map_id != contract[2]
                or raw.battle_state != 2
                or (reader.read_active_trainer_identity() != contract[3])
            ):
                raise ValueError("earned candidate live trainer identity differs")
        if type(wild_training) is not bool or (
            wild_training
            and (
                authority != self.wild_authority(expected_map)
                or resume
                or require_win
                or allow_immune_switch_recovery
            )
        ):
            raise ValueError("wild training requires explicit bounded K development authority")
        expected_battle_state = 1 if wild_training else 2
        status_story = authority in {
            "scoped-tower-development",
            "scoped-exact-story-development",
            "scoped-exact-story-train",
            EVALUATION_RISK_AUTHORITY,
            TRAIN_RISK_AUTHORITY,
            "frozen-additive-story-development",
            "frozen-damage-story-development",
            "frozen-risk-cost-agatha-development",
            "frozen-risk-cost-lance-development",
            "frozen-risk-cost-champion-development",
            "frozen-risk-cost-league-chain-development",
        }
        if status_story and (authority != self.story_authority() or not resume or require_win):
            raise ValueError("status execution requires admitted story continuation")
        if status_story:
            self.require_story_identity()
        if type(allow_immune_switch_recovery) is not bool or (
            allow_immune_switch_recovery
            and (
                self.model_sha256 != FROZEN_K_SHA256
                or self.qualification_sha256 != K_QUALIFICATION_SHA256
                or authority
                not in {
                    "frozen-k-league-development",
                    "frozen-k-league-development-continuation",
                }
            )
        ):
            raise ValueError("immune recovery requires explicit qualified K League authority")
        if type(maximum_decisions) is not int or not 1 <= maximum_decisions <= 80:
            raise ValueError("frozen battle decision remainder must be one through80")
        self.calls += 1
        directory = self.output / f"battle-{self.calls:04d}"
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        log = TrainerPracticeEventLog(
            directory / "events",
            run_identity={
                "model_sha256": self.model_sha256,
                "qualification_sha256": self.qualification_sha256,
                "source_commit": self.source_commit,
                "root_lineage_id": self.root_lineage_id,
                "parent_state_sha256": self.source_state_sha256,
                **({"allow_immune_switch_recovery": True} if allow_immune_switch_recovery else {}),
                "allow_stranded_accuracy_move": authority
                in {"frozen-k-story-development", TRAIN_RISK_AUTHORITY, EVALUATION_RISK_AUTHORITY},
                "allow_status_moves": status_story or preparation_scope is not None,
                "allow_forced_struggle": forced_struggle,
                "wild_training": wild_training,
                **({"wild_training_objective": training_objective.document(),
                    "wild_training_objective_consumed_by_heads": False}
                   if training_objective is not None else {}),
                **(
                    {
                        "pp_depleted_switch_screen": True,
                        "source_partition": "development",
                        "fit_allowed": False,
                    }
                    if depleted_screen
                    else {}
                ),
                **(
                    {
                        "mechanics_aware_tower_choices": True,
                        "mechanics_aware_choices": True,
                        "tower_mechanics_revision": "damaging-only-v1",
                        "source_partition": "development",
                        "fit_allowed": False,
                    }
                    if tower_mechanics
                    else {}
                ),
                **(
                    {
                        "diagnostic_tower_productive_stay": True,
                        "diagnostic_stay_when_productive": True,
                    }
                    if tower_mechanics and self.diagnostic_tower_productive_stay
                    else {}
                ),
                **(
                    {
                        "development_preparation_scope": preparation_scope.document(),
                        "mechanics_aware_choices": True,
                        "diagnostic_stay_when_productive": False,
                        "source_partition": "development",
                        "fit_allowed": False,
                    }
                    if preparation_scope is not None
                    else {}
                ),
                **(
                    {
                        "development_story_scope": development_scope.document(),
                        "mechanics_aware_choices": True,
                        "diagnostic_stay_when_productive": (
                            development_scope.diagnostic_stay_when_productive
                        ),
                        "source_partition": "development",
                        "fit_allowed": False,
                    }
                    if development_scope is not None
                    else {}
                ),
                **({"train_funding_diagnostic": True} if train_funding_diagnostic else {}),
                **({"train_story_contract": self._train_story_document()} if train_story else {}),
                **(
                    {"train_risk_story_scope": self._train_risk_story_document()}
                    if train_risk
                    else {}
                ),
                **(
                    {
                        "source_partition": "development",
                        "fit_allowed": False,
                        "evaluation_story_scope": evaluation_scope_document,
                    }
                    if evaluation
                    else {}
                ),
                **({"source_partition": "train", "fit_allowed": False} if train_diagnostic else {}),
                "authority": authority
                or (
                    "frozen-learned-trainer-continuation"
                    if resume
                    else "frozen-learned-ordinary-trainer"
                ),
            },
        )
        report: dict[str, object] | None = None
        try:
            raw = reader.read()
            party_limit = (
                6
                if preparation_scope is not None
                else self.story_limit()
                if status_story
                else qualified_party_limit(self.model_sha256, self.qualification_sha256)
            )
            if type(raw.party_count) is not int or not 1 <= raw.party_count <= party_limit:
                raise ValueError("frozen battler party exceeds its authenticated execution scope")
            decision_guard(raw)
            if resume:
                if raw.battle_state != 2 or raw.map_id != expected_map:
                    raise ValueError("continuation requires the retained active trainer battle")
                if raw.battler_hp == 0 and getattr(raw, "enemy_party_position", None) == 0xFF:
                    # InitBattle has exposed battle mode, but the native first
                    # send-out has not initialized its opponent position. The
                    # old fainted lead is not a model-owned forced replacement.
                    # Reuse the bounded, metered introduction handler rather
                    # than driving a party menu through this transient state.
                    advance_battle_to_policy_boundary(
                        reader,
                        executor,
                        expected_map=expected_map,
                        expected_battle_state=expected_battle_state,
                        timing=timing,
                        label=label,
                    )
                    raw = reader.read()
                special_boundary = raw.battler_hp == 0 or reader.trainer_switch_prompt_visible(raw)
                if not special_boundary and (
                    reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
                ):
                    raise ValueError("continuation lacks an owned policy boundary")
            else:
                special_boundary = False
                advance_battle_to_policy_boundary(
                    reader,
                    executor,
                    expected_map=expected_map,
                    expected_battle_state=expected_battle_state,
                    timing=timing,
                    label=label,
                )
            raw = reader.read()
            encoder = PokemonRedObservationEncoder.from_state_reader(
                reader,
                include_battle_stats=True,
                public_species_base_stats=self.public_species_base_stats,
            )
            observation_sha256 = (
                canonical_sha256(encoder.snapshot_from_raw(raw).to_dict())
                if special_boundary
                else prepare_red_battle_scenario(
                    encoder,
                    raw,
                    allow_no_attack=True,
                ).initial_observation_sha256
            )
            state = self.session.save_state_bytes()
            manifest = build_battle_scenario_capture_payload(
                capture_id=f"player-trainer-{self.calls:04d}",
                root_lineage_id=self.root_lineage_id,
                partition=self.source_partition,
                state_bytes=state,
                initial_observation_sha256=observation_sha256,
                source_state_sha256=self.source_state_sha256,
                source_commit=self.source_commit,
                expected_map=expected_map,
                expected_battle_state=expected_battle_state,
                observation_schema=OBSERVATION_SCHEMA_V2,
            )
            _write(directory / "initial.state", state)
            _write(directory / "initial.state.json", manifest)
            capture = open_battle_scenario_capture(
                directory / "initial.state",
                directory / "initial.state.json",
            )
            episode = run_live_red_trainer_practice_episode(
                capture,
                session=self.session,
                policy=RedTrainerPracticeOutcomePolicy(
                    policy_id="frozen-player-trainer",
                    battle_plan_id=capture.manifest.capture_id,
                    model=self.model,
                    training_objective=training_objective,
                    allow_immune_switch_recovery=allow_immune_switch_recovery,
                    pp_depleted_switch_screen=depleted_screen,
                    allow_model_struggle=development and forced_struggle and not wild_training,
                    mechanics_aware_choices=(
                        development or preparation_scope is not None or tower_mechanics
                    ),
                    diagnostic_stay_when_productive=(
                        (
                            development_scope is not None
                            and development_scope.diagnostic_stay_when_productive
                        )
                        or (tower_mechanics and self.diagnostic_tower_productive_stay)
                    ),
                    diagnostic_status_release=(
                        development_scope is not None
                        and development_scope.diagnostic_status_release
                    ),
                    diagnostic_prompt_stay=(
                        development_scope is not None and development_scope.diagnostic_prompt_stay
                    ),
                    screen_capped_status_moves=(
                        development_scope is not None
                        and development_scope.screen_capped_status_moves
                    ),
                ),
                max_decisions=maximum_decisions,
                event_sink=log.emit,
                public_species_base_stats=self.public_species_base_stats,
                action_executor=executor,
                decision_guard=decision_guard,
                allow_stranded_accuracy_move=authority
                in {"frozen-k-story-development", TRAIN_RISK_AUTHORITY, EVALUATION_RISK_AUTHORITY},
                allow_status_moves=status_story or preparation_scope is not None,
                allow_forced_struggle=forced_struggle,
                wild_training=wild_training,
                train_wild_diagnostic=train_diagnostic and wild_training,
            )
            report = episode.public_dict()
            _record(directory / "outcome.json", report)
            if require_win and not episode.battle_won:
                if (
                    isinstance(episode, RedTrainerPracticeEpisode)
                    and episode.final_battle_state == 0
                    and episode.stop_reason == "battle_exited_without_win"
                ):
                    raise FrozenTrainerTerminalUnverified(episode)
                raise RuntimeError(f"learned trainer stopped: {episode.stop_reason}")
            return episode
        except BaseException as error:
            log.fail(error)
            raise
        finally:
            final = self.session.save_state_bytes()
            _write(directory / "final.state", final)
            terminal = {
                "final_state_sha256": hashlib.sha256(final).hexdigest(),
                "outcome_sha256": canonical_sha256(report) if report is not None else None,
                "model_sha256": self.model_sha256,
                "qualification_sha256": self.qualification_sha256,
                "actor_returned_win": report is not None and report.get("battle_won") is True,
                "outer_goal_verification_required": True,
            }
            _record(directory / "endpoint.json", terminal)
            if not log.closed:
                log.finish(terminal)
