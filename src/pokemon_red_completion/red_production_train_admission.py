"""Prospective finite TRAIN reuse of the already pinned production battlers.

This authenticates a lesson's source/configuration; it grants no controller,
fit admission or model promotion. Existing DEVELOPMENT and K scopes stay exact.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition

WILD_MODEL = "720e9db864f3fefe2edfa27889203bd7c0fcbbd6968a65b960adcf1d57392161"
WILD_CONTENT = "cf3fe33dc6a91b34aabc0d144a5d5ef7875e8e190f72a6362a05697b9c056638"
STORY_MODEL = "29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad"
STORY_CONTENT = "e1063ce5b510b70a7721107ce716e223d8b1833314bf498ff6d738f43ea67629"
SOURCE_ORIGIN = "fb501fe63c2af637775c237861fe851f720d7f07c9218a6bb612b2937d46e111"
# These are existing authentic TRAIN fixtures, not the DEVELOPMENT comparison's outputs.
SOURCE_STATES = frozenset({
    "0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d",
    "e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e",
    "cdaef04a24f6bb0670c33fa532749e8bd5894cc51d7030c316d48298d22287ec",
    "7da092393b618c187ef1f2ffadef50dd492be4944f96a6133aed1fe57c417755",
    '2d2eb758146be68e49bdbe08fa63177eb4852899e52ae9650aee17c423a51ef8',
})
SOURCE_PROVENANCE = {
    "0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d": (
        "066f81b50ee76e61c50a21daf7a5a6a0ba2ea0d912c26943006f3b4894a71c64",
        "86eae3aba87c463a3335b940cd5638dfb6518bea5fc6f4978cdfee91a77f6039"),
    "e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e": (
        "0d679bd7e32a5b6cfec2486ce2977924285a2fb376cb11ecae6d30914a7b83ae",
        "0132306ba8cb849391408de4856f5ce228346dbf9f42bbdeb1c096f0e16daf57"),
    "cdaef04a24f6bb0670c33fa532749e8bd5894cc51d7030c316d48298d22287ec": (
        "f6f7c876335191e66eea0f49d6edb0ee5cb073213cf20d56d7efaefe4953227f",
        "cedda9c05430b3f484fc02dd1651137f1066941e2ec58808f8d744230e6a9a59"),
    "7da092393b618c187ef1f2ffadef50dd492be4944f96a6133aed1fe57c417755": (
        "260f72f640dbc24ad1d83be13c318fd399a23da45c8fa08c7cdbebc119bf9b4d",
        "61eb52658ea246af77697af4867ebdbf9060bc6556fc993fb6bfbfb287a4c172"),
    '2d2eb758146be68e49bdbe08fa63177eb4852899e52ae9650aee17c423a51ef8': (
        'c6d38a178e6913d24cceebd36df245230a5ca259de3d1ec037d3843b340959d9',
        '4ebe54eb247222f2bb3da423ce04eec94b9e09aa4d929fe4b347a0ebffb21c83'),
}
ADMISSION_SCHEMA = "pokemon.red.production-train-components.v1"


ADMISSION_COMPONENT_SCHEMA = "pokemon.red.production-train-components.v2"
WILD_COMPONENT_SCHEMA = "pokemon.red.production-train-wild-component-reuse.v1"
# Exact already-qualified wild-only reuse. This does not qualify trainer use,
# another model, a new source, model fitting, a campaign or authority promotion.
QUALIFIED_WILD_COMPONENTS = {
    "3b187fc6bfb46dd0fd062f0d14ff5fadffe353347d4e94a2124bdbaba988c4b3": (
        "c9e129fd9413a1358c36801e1a0807b3af8187f1a30ab7af31a0b8f285fc1fb2",
        "5773d5ac6989cce842b873a31c7449174bbe4fbfb95ba4c4e857fe70af8a1d0a"),
}
_WILD_COMPONENT_TOKEN = object()


def _wild_component_document(model_sha256, content_sha256, qualification_sha256):
    return dict(schema=WILD_COMPONENT_SCHEMA, model_sha256=model_sha256,
        model_content_sha256=content_sha256, qualification_sha256=qualification_sha256,
        role="wild_only", wild_map_id=15, trainer_deployment_qualified=False,
        global_adoption=False, fit_admission=False)


@dataclass(frozen=True, init=False)
class VerifiedProductionWildComponent:
    """Immutable byte-authenticated existing wild component; never a new actor."""
    _canonical: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _WILD_COMPONENT_TOKEN:
            raise ValueError("wild component requires actual model and qualification bytes")
        object.__setattr__(self, "_canonical", json.dumps(document, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode())
        self.require_registered()

    def document(self):
        return json.loads(self._canonical)

    def require_registered(self):
        document = self.document()
        pair = QUALIFIED_WILD_COMPONENTS.get(document.get("model_sha256"))
        if (pair is None or document != _wild_component_document(
                document["model_sha256"], pair[0], pair[1])):
            raise ValueError("wild component is not an exact qualified reuse")

    @property
    def identity(self):
        return sha256(self._canonical).hexdigest()

    @property
    def model_sha256(self):
        return self.document()["model_sha256"]

    @property
    def model_content_sha256(self):
        return self.document()["model_content_sha256"]

    @property
    def qualification_sha256(self):
        return self.document()["qualification_sha256"]


def authenticate_production_wild_component(*, model_bytes, qualification_bytes):
    """Decode exact pinned bytes; no inference, fitting or native construction.

    The caller still supplies a current experiment and source/work-order custody.
    The historical qualification remains wild-only and grants no TRAIN fit label.
    """
    if type(model_bytes) is not bytes or type(qualification_bytes) is not bytes:
        raise ValueError("wild component needs immutable model and qualification bytes")
    raw = sha256(model_bytes).hexdigest()
    pair = QUALIFIED_WILD_COMPONENTS.get(raw)
    if pair is None or sha256(qualification_bytes).hexdigest() != pair[1]:
        raise ValueError("wild component model or qualification bytes differ")
    qualification = json.loads(qualification_bytes)
    if (type(qualification) is not dict
        or qualification.get("schema") != "pokemon.current-control-wild-component-qualification.v1"
        or any(qualification.get(k) is not True for k in (
            "passed", "wild_preparation_core_native_qualified", "all801_numeric_bounds_passed",
            "healthy_and_sand_nidoran_endpoints_exact", "unused_configuration_retained",
            "whole_preparation_retained"))
        or qualification.get("candidate", {}).get("sha256") != raw
        or qualification.get("trainer_deployment_qualified") is not False
        or qualification.get("global_models_adopted") != 0
        or qualification.get("actual_registration_delta") != 0):
        raise ValueError("wild-only qualification contract differs")
    from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
    original = json.loads(model_bytes)
    model = TrainerPracticeThreeHeadModel.from_dict(original)
    if (canonical_sha256(model.to_dict()) != pair[0]
        or canonical_sha256(original) != pair[0]):
        raise ValueError("wild component codec or canonical content differs")
    return VerifiedProductionWildComponent(_wild_component_document(raw, *pair),
        _token=_WILD_COMPONENT_TOKEN)


def _digest(value, length=64):
    return type(value) is str and len(value) == length and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class ProductionTrainAdmission:
    source_state_sha256: str
    source_origin_sha256: str
    source_commit: str
    work_order_sha256: str
    envelope_sha256: str
    progress_sha256: str
    derived_source_proof: object | None = None
    wild_component_proof: object | None = None

    def __post_init__(self):
        original = (self.source_state_sha256 in SOURCE_STATES
            and (self.envelope_sha256, self.progress_sha256) == SOURCE_PROVENANCE[self.source_state_sha256])
        derived = False
        if self.derived_source_proof is not None:
            from .red_production_train_source import VerifiedDerivedTrainSource
            proof = self.derived_source_proof
            derived = (type(proof) is VerifiedDerivedTrainSource
                and self.source_state_sha256 == proof.source_state_sha256
                and self.source_origin_sha256 == proof.source_origin_sha256
                and self.source_commit == proof.source_commit)
        if ((not original if self.derived_source_proof is None else not derived)
            or self.source_origin_sha256 != SOURCE_ORIGIN
            or not _digest(self.source_commit, 40)
            or not all(_digest(x) for x in (self.work_order_sha256, self.envelope_sha256, self.progress_sha256))):
            raise ValueError("production TRAIN admission source or identity differs")
        if self.wild_component_proof is not None:
            if type(self.wild_component_proof) is not VerifiedProductionWildComponent:
                raise ValueError("production TRAIN needs a verified wild component witness")
            self.wild_component_proof.require_registered()

    @classmethod
    def authenticate(cls, *, source_state, envelope_bytes, progress_bytes, plan_bytes, source_commit,
                     derived_source_proof=None, context_bytes=None, wild_component_proof=None):
        """Bind actual source bytes and original TRAIN metadata before input.

        Caller still owns package/read guards and the source custody chain. A
        development runtime/result cannot be passed here as a training source.
        """
        envelope, progress, plan = map(json.loads, (envelope_bytes, progress_bytes, plan_bytes))
        state = sha256(source_state).hexdigest()
        derived_declaration = {}
        if derived_source_proof is not None:
            from .red_production_train_source import VerifiedDerivedTrainSource
            if type(derived_source_proof) is not VerifiedDerivedTrainSource:
                raise ValueError("derived source needs authenticated sealed prefix readback")
            derived_source_proof.require_metadata(envelope, progress)
            derived_source_proof.require_source_context(source_state, context_bytes)
            derived_declaration = dict(derived_source_proof_sha256=derived_source_proof.identity)
        if wild_component_proof is not None:
            if type(wild_component_proof) is not VerifiedProductionWildComponent:
                raise ValueError("production TRAIN needs a verified wild component witness")
            wild_component_proof.require_registered()
        component = {} if wild_component_proof is None else dict(
            wild_component_proof_sha256=wild_component_proof.identity,
            wild_model_content_sha256=wild_component_proof.model_content_sha256,
            wild_qualification_sha256=wild_component_proof.qualification_sha256)
        expected = dict(schema=ADMISSION_SCHEMA if wild_component_proof is None else ADMISSION_COMPONENT_SCHEMA,
            source_state_sha256=state, source_envelope_sha256=sha256(envelope_bytes).hexdigest(),
            assisted_progress_sha256=sha256(progress_bytes).hexdigest(),
            wild_model_sha256=WILD_MODEL if wild_component_proof is None else wild_component_proof.model_sha256,
            story_model_sha256=STORY_MODEL, wild_map_id=15, objective_id="defeat_misty",
            **derived_declaration, **component)
        if (plan.get("partition") != "train"
            or plan.get("production_train_components") != expected
            or progress.get("partition") != "train" or progress.get("fit_allowed") is not True
            or progress.get("campaign_eligible") is not False
            or progress.get("role") != "train_sampling"
            or progress.get("source_origin_sha256") != SOURCE_ORIGIN
            or progress.get("envelope") != envelope
            or envelope.get("state_sha256") != state):
            raise ValueError("production TRAIN admission requires exact prospective TRAIN source metadata")
        return cls(state, SOURCE_ORIGIN, source_commit, sha256(plan_bytes).hexdigest(),
                   sha256(envelope_bytes).hexdigest(), sha256(progress_bytes).hexdigest(),
                   derived_source_proof, wild_component_proof)

    @classmethod
    def from_document(cls, document, *, derived_source_proof=None, wild_component_proof=None):
        names = ("source_state_sha256", "source_origin_sha256", "source_commit",
                 "work_order_sha256", "envelope_sha256", "progress_sha256")
        restored = cls(**{name: document[name] for name in names}, derived_source_proof=derived_source_proof,
                       wild_component_proof=wild_component_proof)
        if canonical_sha256(restored.document()) != canonical_sha256(document):
            raise ValueError("production TRAIN admission document differs")
        return restored

    @property
    def admission_schema(self):
        return ADMISSION_SCHEMA if self.wild_component_proof is None else ADMISSION_COMPONENT_SCHEMA

    @property
    def wild_model_sha256(self):
        return WILD_MODEL if self.wild_component_proof is None else self.wild_component_proof.model_sha256

    @property
    def wild_model_content_sha256(self):
        return WILD_CONTENT if self.wild_component_proof is None else self.wild_component_proof.model_content_sha256

    def _wild_component_declaration(self):
        proof = self.wild_component_proof
        return {} if proof is None else dict(wild_component_proof_sha256=proof.identity,
            wild_model_content_sha256=proof.model_content_sha256,
            wild_qualification_sha256=proof.qualification_sha256)

    @property
    def root_lineage_id(self):
        return "red-goal-root-" + self.source_origin_sha256

    def document(self):
        names = ("source_state_sha256", "source_origin_sha256", "source_commit",
                 "work_order_sha256", "envelope_sha256", "progress_sha256")
        derived = ({} if self.derived_source_proof is None else
                   dict(derived_source_proof_sha256=self.derived_source_proof.identity))
        return dict(schema=self.admission_schema, **{name: getattr(self, name) for name in names}, **derived,
                    source_partition="train", wild_model_sha256=self.wild_model_sha256,
                    story_model_sha256=STORY_MODEL, wild_map_id=15,
                    objective_id="defeat_misty", fit_admission=False, **self._wild_component_declaration())

    @property
    def identity(self):
        return canonical_sha256(self.document())

    def declaration(self):
        derived = ({} if self.derived_source_proof is None else
                   dict(derived_source_proof_sha256=self.derived_source_proof.identity))
        return dict(schema=self.admission_schema, **derived, source_state_sha256=self.source_state_sha256,
            source_envelope_sha256=self.envelope_sha256, assisted_progress_sha256=self.progress_sha256,
            wild_model_sha256=self.wild_model_sha256, story_model_sha256=STORY_MODEL,
            wild_map_id=15, objective_id="defeat_misty", **self._wild_component_declaration())

    def require_source_context(self, payload, context_bytes):
        if sha256(payload).hexdigest() != self.source_state_sha256:
            raise ValueError("production TRAIN source state changed")
        if self.derived_source_proof is not None:
            self.derived_source_proof.require_source_context(payload, context_bytes)

    def require_work_order(self, payload):
        # A typed object alone is not proof authenticate() ran. Recheck the
        # actual plan even for a directly constructed or decoded witness.
        if sha256(payload).hexdigest() != self.work_order_sha256:
            raise ValueError("production TRAIN admission work order changed")
        plan = json.loads(payload)
        if (type(plan) is not dict or plan.get("partition") != "train"
            or plan.get("production_train_components") != self.declaration()):
            raise ValueError("production TRAIN admission needs its exact TRAIN work order")

    def require_scope(self, scope, role):
        if (scope.source_state_sha256 != self.source_state_sha256
            or scope.root_lineage_id != self.root_lineage_id
            or scope.work_order_sha256 != self.work_order_sha256):
            raise ValueError("production TRAIN scope source/work order differs")
        if role == "wild":
            valid = (scope.model_sha256 == self.wild_model_sha256
                     and scope.model_content_sha256 == self.wild_model_content_sha256
                     and scope.map_id == 15)
        elif role == "story":
            contract = scope.contract
            valid = (scope.model_sha256 == STORY_MODEL and scope.model_content_sha256 == STORY_CONTENT
                and contract is not None and contract.objective_id == "defeat_misty"
                and contract.battle_plan_id == "defeat_misty" and contract.map_id == 65
                and contract.trainer_identity == (235, 35, 1) and contract.defeated_event == 191
                and contract.victory_money == 2079 and contract.victory_items == ((211, 1),)
                and contract.victory_badge_bits == 2
                and scope.gym_reward is not None and scope.gym_reward.objective_id == "defeat_misty"
                and scope.allow_learned_tactics is True and scope.diagnostic_status_entry is True
                and scope.screen_capped_status_moves is True
                and scope.diagnostic_stay_when_productive is False
                and scope.diagnostic_prompt_stay is False and scope.diagnostic_status_release is False)
        else:
            valid = False
        if not valid:
            raise ValueError("production TRAIN scope model/settings/target differs")

    def require_actor(self, actor, scope, role):
        self.require_scope(scope, role)
        if (actor.source_partition is not ScenarioPartition.TRAIN
            or actor.source_commit != self.source_commit
            or actor.source_state_sha256 != self.source_state_sha256
            or actor.root_lineage_id != self.root_lineage_id
            or type(actor.pp_depleted_switch_screen) is not bool
            or actor.pp_depleted_switch_screen is not (role == "story")
            or actor.mechanics_aware_tower_choices is not False
            or actor.diagnostic_tower_productive_stay is not False):
            raise ValueError("production TRAIN actor source/settings differs")
