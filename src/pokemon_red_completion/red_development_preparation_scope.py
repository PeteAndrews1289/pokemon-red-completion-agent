"""Exact owner-approved DEVELOPMENT wild preparation, not global qualification."""

from dataclasses import asdict, dataclass

from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition

AUTHORITY = "scoped-wild-preparation-development"


@dataclass(frozen=True)
class DevelopmentPreparationScope:
    source_state_sha256: str
    root_lineage_id: str
    model_sha256: str
    model_content_sha256: str
    work_order_sha256: str
    map_id: int
    train_admission: object | None = None

    def __post_init__(self):
        for value in (self.source_state_sha256, self.model_sha256,
                      self.model_content_sha256, self.work_order_sha256):
            if (type(value) is not str or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
                raise ValueError("preparation scope requires exact identities")
        if (type(self.root_lineage_id) is not str or not self.root_lineage_id
            or type(self.map_id) is not int or not 0 <= self.map_id <= 255):
            raise ValueError("preparation scope declaration differs")

        if self.train_admission is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if type(self.train_admission) is not ProductionTrainAdmission:
                raise ValueError("typed production TRAIN admission required")
            self.train_admission.require_scope(self, "wild")

    def document(self):
        document = asdict(self)
        if self.train_admission is None:
            document.pop("train_admission")  # Historical DEVELOPMENT identity stays exact.
        else:
            document["train_admission"] = self.train_admission.document()
        return document

    @property
    def identity(self):
        return canonical_sha256(self.document())

    def require(self, actor, expected_map=None):
        if self.train_admission is not None:
            from .red_production_train_admission import ProductionTrainAdmission
            if type(self.train_admission) is not ProductionTrainAdmission:
                raise ValueError("typed production TRAIN admission required")
            self.train_admission.require_actor(actor, self, "wild")
        partition = ScenarioPartition.DEVELOPMENT if self.train_admission is None else ScenarioPartition.TRAIN
        if (actor.source_partition is not partition
            or actor.source_state_sha256 != self.source_state_sha256
            or actor.root_lineage_id != self.root_lineage_id
            or actor.model_sha256 != self.model_sha256
            or actor.qualification_sha256 != self.identity
            or canonical_sha256(actor.model.to_dict()) != self.model_content_sha256
            or actor.story_chain_scope is not None
            or actor.train_story_contract is not None
            or actor.train_risk_story_scope is not None
            or actor.evaluation_story_scope is not None
            or actor.development_story_scope is not None
            or actor.train_funding_diagnostic
            or (expected_map is not None and expected_map != self.map_id)):
            raise ValueError("development preparation source/model/scope changed")
        return AUTHORITY if self.train_admission is None else "scoped-wild-preparation-train"
