"""Ordinary qualified K on one prospectively declared original TRAIN challenge.

Reuses the first-Lorelei skill and story lifecycle, including retained losses.
The caller separately authenticates original TRAIN custody and the native plan.
"""
from dataclasses import asdict, dataclass
import json

from .observation import EventFlag, MapId
from .provenance import canonical_sha256
from .red_learned_trainer import FrozenTrainerBattler, FROZEN_K_SHA256, K_QUALIFICATION_SHA256
from .red_lorelei_story import FrozenLoreleiStoryController
from .red_story_battle import StoryTrainerContract
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .scenario_lab import ScenarioPartition

K_CONTENT_SHA256 = "5b20f1d01f79eef3be25ba36d9cc065d0db0847230335916611d91018885494d"


def train_lorelei_admission(battler, contract, maximum_decisions=80):
    """Serialize identity for the caller's prospective, frozen lesson declaration."""
    return json.dumps(dict(
        schema="pokemon.red.ordinary-k-train-lorelei.v1",
        source_partition="train", source_commit=battler.source_commit,
        root_lineage_id=battler.root_lineage_id,
        source_state_sha256=battler.source_state_sha256,
        model_sha256=FROZEN_K_SHA256, model_content_sha256=K_CONTENT_SHA256,
        qualification_sha256=K_QUALIFICATION_SHA256,
        contract=asdict(contract), maximum_decisions=maximum_decisions,
        rematch=False, diagnostic_tactics=False,
    ),sort_keys=True,separators=(",", ":")).encode()


@dataclass
class FrozenTrainLoreleiStoryController(FrozenLoreleiStoryController):
    @property
    def controller_name(self):
        return "frozen-k-lorelei-train"

    def require_identity(self):
        b = self.battler
        if (
            not isinstance(b, FrozenTrainerBattler)
            or b.source_partition is not ScenarioPartition.TRAIN
            or (b.model_sha256, b.qualification_sha256) != (FROZEN_K_SHA256, K_QUALIFICATION_SHA256)
            or type(b.model) is not TrainerPracticeThreeHeadModel
            or canonical_sha256(b.model.to_dict()) != K_CONTENT_SHA256
            or not isinstance(b.root_lineage_id, str) or not b.root_lineage_id
            or type(b.source_state_sha256) is not str or len(b.source_state_sha256) != 64
            or any(c not in "0123456789abcdef" for c in b.source_state_sha256)
            or any(getattr(b, name) is not None for name in (
                "story_chain_scope", "train_risk_story_scope", "evaluation_story_scope",
                "development_story_scope", "development_preparation_scope"))
            or any(getattr(b, name) is not False for name in (
                "train_funding_diagnostic", "pp_depleted_switch_screen",
                "mechanics_aware_tower_choices", "diagnostic_tower_productive_stay"))
        ):
            raise ValueError("TRAIN Lorelei requires ordinary qualified K, source and scope")
        c = self.contract
        if (
            type(c) is not StoryTrainerContract
            or (c.objective_id, c.battle_plan_id, c.map_id, c.trainer_identity, c.defeated_event)
            != ("defeat_lorelei", "cartridge-trainer-story", int(MapId.LORELEIS_ROOM),
                (244,44,1), int(EventFlag.BEAT_LORELEI))
            or c.victory_items or c.victory_badge_bits
            or type(self.maximum_decisions) is not int or not 1 <= self.maximum_decisions <= 80
            or type(self.admission) is not bytes
            or self.admission != train_lorelei_admission(b,c,self.maximum_decisions)
        ):
            raise ValueError("TRAIN Lorelei contract or frozen lesson identity differs")
        b.require_story_contract(c)

    def require_objective(self, objective_id, *, rematch=False):
        self.require_identity()
        if objective_id != "defeat_lorelei" or rematch is not False:
            raise ValueError("TRAIN Lorelei admits only its first challenge")

    def completion_evidence(self, previous, calls_before, terminal, aftermath, *, outcome):
        """Expose one fresh, settled native episode to the consequence recorder."""
        from .post_battle_strategy import BattleAftermath
        from .red_trainer_battle_lifecycle import TrainerBattleCompletion
        from .red_trainer_practice_episode import RedTrainerPracticeEpisode

        self.require_identity()
        result = self.last_completion
        if (
            outcome not in {"won", "lost"}
            or type(result) is not TrainerBattleCompletion or result is previous
            or type(calls_before) is not int or self.battler.calls != calls_before + 1
            or result.outcome != outcome or result.field_ready is not True
            or type(result.episode) is not RedTrainerPracticeEpisode
            or result.episode.battle_won is not (outcome == "won")
            or type(aftermath) is not BattleAftermath or aftermath.result.value != outcome
            or terminal.battle_state != 0
        ):
            raise ValueError("TRAIN Lorelei needs one fresh settled authenticated completion")
        # The episode can end at party defeat before blackout. Compare the settled
        # completion with the current terminal, not with pre-battle party order.
        for name in ("map_id", "battle_state", "party_species_ids", "party_hp",
                     "party_moves", "party_pp", "player_money", "event_flags",
                     "badge_bits", "bag_items"):
            if getattr(result.final_state, name) != getattr(terminal, name):
                raise ValueError("TRAIN Lorelei completion differs from native terminal")
        return result.public_dict()
