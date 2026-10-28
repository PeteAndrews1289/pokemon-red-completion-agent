"""Explicit owner-approved story integration; not a global model qualification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition

if TYPE_CHECKING:
    from .red_gym_reward import GymReward
    from .red_story_battle import StoryTrainerContract

AUTHORITY = "scoped-tower-development"


def _gym_rewards():
    from .red_gym_reward import (
        BLAINE_REWARD,
        BROCK_REWARD,
        ERIKA_REWARD,
        GIOVANNI_REWARD,
        KOGA_REWARD,
        MISTY_REWARD,
        SABRINA_REWARD,
        SURGE_REWARD,
    )

    return {
        r.objective_id: r
        for r in (
            BROCK_REWARD,
            MISTY_REWARD,
            SURGE_REWARD,
            ERIKA_REWARD,
            SABRINA_REWARD,
            KOGA_REWARD,
            BLAINE_REWARD,
            GIOVANNI_REWARD,
        )
    }


@dataclass(frozen=True)
class DevelopmentStoryScope:
    source_state_sha256: str
    root_lineage_id: str
    model_sha256: str
    model_content_sha256: str
    work_order_sha256: str
    diagnostic_stay_when_productive: bool = False
    contract: StoryTrainerContract | None = None
    diagnostic_status_release: bool = False
    diagnostic_prompt_stay: bool = False
    diagnostic_status_entry: bool = False
    gym_reward: GymReward | None = None
    screen_capped_status_moves: bool = False
    allow_learned_tactics: bool = False
    train_admission: object | None = None

    def __post_init__(self):
        from .red_story_battle import StoryTrainerContract

        if type(self.screen_capped_status_moves) is not bool:
            raise ValueError("Capped status screen must be an explicit boolean")
        if type(self.allow_learned_tactics) is not bool or (
            self.allow_learned_tactics and (
                self.diagnostic_stay_when_productive
                or self.diagnostic_prompt_stay or self.diagnostic_status_release
            )
        ):
            raise ValueError("learned tactics require no supplied control overrides")

        for value in (
            self.source_state_sha256,
            self.model_sha256,
            self.model_content_sha256,
            self.work_order_sha256,
        ):
            if (
                type(value) is not str
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("development scope requires exact identities")
        if not self.root_lineage_id or type(self.diagnostic_stay_when_productive) is not bool:
            raise ValueError("development scope declaration differs")
        if type(self.diagnostic_status_release) is not bool or (
            self.diagnostic_status_release and not self.diagnostic_stay_when_productive
        ):
            raise ValueError("status release requires explicit diagnostic stay")
        if type(self.diagnostic_prompt_stay) is not bool or (
            self.diagnostic_prompt_stay and not self.diagnostic_stay_when_productive
        ):
            raise ValueError("prompt stay requires explicit diagnostic stay")
        if type(self.diagnostic_status_entry) is not bool or (
            self.diagnostic_status_entry and not (
                self.diagnostic_stay_when_productive or self.allow_learned_tactics
            )
        ):
            raise ValueError("status entry requires explicit diagnostic stay")
        if self.contract is not None and (
            type(self.contract) is not StoryTrainerContract or self.contract.defeated_event is None
        ):
            raise ValueError("development scope requires one exact ordinary trainer contract")
        if self.gym_reward is None:
            if self.contract is not None and (
                self.contract.victory_items or self.contract.victory_badge_bits
            ):
                raise ValueError("development rewards require an explicit exact gym profile")
        else:
            from .red_gym_reward import GymReward

            reward, contract = self.gym_reward, self.contract
            if (
                type(reward) is not GymReward
                or contract is None
                or _gym_rewards().get(reward.objective_id) != reward
                or (
                    contract.objective_id,
                    contract.map_id,
                    contract.trainer_identity,
                    contract.defeated_event,
                    contract.victory_items,
                    contract.victory_badge_bits,
                )
                != (
                    reward.objective_id,
                    reward.map_id,
                    (reward.trainer_class, reward.trainer_class - 200, reward.trainer_set),
                    reward.defeated_event,
                    ((reward.item, 1),),
                    reward.badge,
                )
            ):
                raise ValueError("development gym contract/reward profile differs")

        if self.train_admission is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if type(self.train_admission) is not ProductionTrainAdmission:
                raise ValueError("typed production TRAIN admission required")
            self.train_admission.require_scope(self, "story")

    def document(self):
        document = asdict(self)
        if self.train_admission is None:
            document.pop("train_admission")  # Preserve historical DEVELOPMENT identities.
        else:
            document["train_admission"] = self.train_admission.document()
        if not self.screen_capped_status_moves:
            document.pop("screen_capped_status_moves")
        if not self.allow_learned_tactics:
            document.pop("allow_learned_tactics")  # Keep historical scope identities exact.
        if self.gym_reward is None:
            document.pop("gym_reward")  # Preserve historical nongym identities.
        else:
            document["gym_reward"] = self.gym_reward.objective_id
        if not self.diagnostic_status_release:
            document.pop("diagnostic_status_release")  # Preserve historical scope identities.
        if not self.diagnostic_prompt_stay:
            document.pop("diagnostic_prompt_stay")
        if not self.diagnostic_status_entry:
            document.pop("diagnostic_status_entry")
        if self.contract is None:
            # Preserve the identities of existing Tower evidence.
            document.pop("contract")
        else:
            document["contract"]["trainer_identity"] = list(self.contract.trainer_identity)
            document["contract"]["victory_items"] = [
                list(item) for item in self.contract.victory_items
            ]
        return document

    @classmethod
    def from_document(cls, document, *, train_admission=None):
        from .red_story_battle import StoryTrainerContract

        values = dict(document)
        if values.get("train_admission") is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if train_admission is not None:
                if (type(train_admission) is not ProductionTrainAdmission
                    or canonical_sha256(values["train_admission"]) != canonical_sha256(train_admission.document())):
                    raise ValueError("story scope differs from authenticated TRAIN admission")
                values["train_admission"] = train_admission
            else:
                # Original metadata-only admissions remain decodable. A derived
                # document needs its separately authenticated sealed proof.
                values["train_admission"] = ProductionTrainAdmission.from_document(values["train_admission"])
        elif train_admission is not None:
            raise ValueError("story scope omitted its authenticated TRAIN admission")
        if values.get("gym_reward") is not None:
            name = values["gym_reward"]
            if type(name) is not str or name not in _gym_rewards():
                raise ValueError("unknown development gym reward profile")
            values["gym_reward"] = _gym_rewards()[name]
        if values.get("contract") is not None:
            contract = dict(values["contract"])
            contract["trainer_identity"] = tuple(contract["trainer_identity"])
            contract["victory_items"] = tuple(tuple(item) for item in contract["victory_items"])
            values["contract"] = StoryTrainerContract(**contract)
        return cls(**values)

    @property
    def authority(self):
        if self.train_admission is not None:
            return "scoped-exact-story-train"
        return AUTHORITY if self.contract is None else "scoped-exact-story-development"

    def admits_map(self, map_id):
        return 143 <= map_id <= 148 if self.contract is None else map_id == self.contract.map_id

    def require_live(self, reader, expected_map):
        raw = reader.read()
        if (
            not self.admits_map(expected_map)
            or raw.map_id != expected_map
            or raw.battle_state != 2
            or (
                self.contract is not None
                and reader.read_active_trainer_identity() != self.contract.trainer_identity
            )
        ):
            raise ValueError("development story live target differs")

    @property
    def identity(self):
        return canonical_sha256(self.document())

    def require(self, actor, contract=None):
        if self.train_admission is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if type(self.train_admission) is not ProductionTrainAdmission:
                raise ValueError("typed production TRAIN admission required")
            self.train_admission.require_actor(actor, self, "story")
        partition = ScenarioPartition.DEVELOPMENT if self.train_admission is None else ScenarioPartition.TRAIN
        if (
            actor.source_partition is not partition
            or actor.source_state_sha256 != self.source_state_sha256
            or actor.root_lineage_id != self.root_lineage_id
            or actor.model_sha256 != self.model_sha256
            or actor.qualification_sha256 != self.identity
            or canonical_sha256(actor.model.to_dict()) != self.model_content_sha256
            or actor.story_chain_scope is not None
            or (actor.train_story_contract is not None and (self.train_admission is None
                or actor.train_story_contract != self.contract))
            or actor.train_risk_story_scope is not None
            or actor.evaluation_story_scope is not None
            or actor.train_funding_diagnostic
            or actor.development_preparation_scope is not None
        ):
            raise ValueError("development story source/model/scope changed")
        if contract is not None and self.contract is not None and contract != self.contract:
            raise ValueError("development story differs from exact declared contract")
        if (
            contract is not None
            and self.contract is None
            and (
                contract.objective_id != "rescue_fuji"
                or not 143 <= contract.map_id <= 148
                or contract.defeated_event is None
                or contract.victory_items
                or contract.victory_badge_bits
            )
        ):
            raise ValueError("development story outside declared Tower scope")
        return 6
