"""Prospective finite TRAIN reuse of the already pinned production battlers.

This authenticates a lesson's source/configuration; it grants no controller,
fit admission or model promotion. Existing DEVELOPMENT and K scopes stay exact.
"""

import json
from dataclasses import dataclass
from hashlib import sha256

from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition

WILD_MODEL = "720e9db864f3fefe2edfa27889203bd7c0fcbbd6968a65b960adcf1d57392161"
WILD_CONTENT = "cf3fe33dc6a91b34aabc0d144a5d5ef7875e8e190f72a6362a05697b9c056638"
STORY_MODEL = "29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad"
STORY_CONTENT = "e1063ce5b510b70a7721107ce716e223d8b1833314bf498ff6d738f43ea67629"
SOURCE_ORIGIN = "fb501fe63c2af637775c237861fe851f720d7f07c9218a6bb612b2937d46e111"
# These are existing authentic TRAIN fixtures, not the DEVELOPMENT comparison's outputs.
SOURCE_STATES = frozenset(
    {
        "0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d",
        "e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e",
        "cdaef04a24f6bb0670c33fa532749e8bd5894cc51d7030c316d48298d22287ec",
        "7da092393b618c187ef1f2ffadef50dd492be4944f96a6133aed1fe57c417755",
        "2d2eb758146be68e49bdbe08fa63177eb4852899e52ae9650aee17c423a51ef8",
    }
)
SOURCE_PROVENANCE = {
    "0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d": (
        "066f81b50ee76e61c50a21daf7a5a6a0ba2ea0d912c26943006f3b4894a71c64",
        "86eae3aba87c463a3335b940cd5638dfb6518bea5fc6f4978cdfee91a77f6039",
    ),
    "e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e": (
        "0d679bd7e32a5b6cfec2486ce2977924285a2fb376cb11ecae6d30914a7b83ae",
        "0132306ba8cb849391408de4856f5ce228346dbf9f42bbdeb1c096f0e16daf57",
    ),
    "cdaef04a24f6bb0670c33fa532749e8bd5894cc51d7030c316d48298d22287ec": (
        "f6f7c876335191e66eea0f49d6edb0ee5cb073213cf20d56d7efaefe4953227f",
        "cedda9c05430b3f484fc02dd1651137f1066941e2ec58808f8d744230e6a9a59",
    ),
    "7da092393b618c187ef1f2ffadef50dd492be4944f96a6133aed1fe57c417755": (
        "260f72f640dbc24ad1d83be13c318fd399a23da45c8fa08c7cdbebc119bf9b4d",
        "61eb52658ea246af77697af4867ebdbf9060bc6556fc993fb6bfbfb287a4c172",
    ),
    "2d2eb758146be68e49bdbe08fa63177eb4852899e52ae9650aee17c423a51ef8": (
        "c6d38a178e6913d24cceebd36df245230a5ca259de3d1ec037d3843b340959d9",
        "4ebe54eb247222f2bb3da423ce04eec94b9e09aa4d929fe4b347a0ebffb21c83",
    ),
}
ADMISSION_SCHEMA = "pokemon.red.production-train-components.v1"


ADMISSION_COMPONENT_SCHEMA = "pokemon.red.production-train-components.v2"
ADMISSION_TEACHER_SCHEMA = "pokemon.red.production-train-components.v3"
ADMISSION_NONCOMBAT_SCHEMA = "pokemon.red.production-train-components.v4"
WILD_COMPONENT_SCHEMA = "pokemon.red.production-train-wild-component-reuse.v1"
# Exact already-qualified wild-only reuse. This does not qualify trainer use,
# another model, a new source, model fitting, a campaign or authority promotion.
QUALIFIED_WILD_COMPONENTS = {
    "3b187fc6bfb46dd0fd062f0d14ff5fadffe353347d4e94a2124bdbaba988c4b3": (
        "c9e129fd9413a1358c36801e1a0807b3af8187f1a30ab7af31a0b8f285fc1fb2",
        "5773d5ac6989cce842b873a31c7449174bbe4fbfb95ba4c4e857fe70af8a1d0a",
    ),
}
_WILD_COMPONENT_TOKEN = object()


def _wild_component_document(model_sha256, content_sha256, qualification_sha256):
    return dict(
        schema=WILD_COMPONENT_SCHEMA,
        model_sha256=model_sha256,
        model_content_sha256=content_sha256,
        qualification_sha256=qualification_sha256,
        role="wild_only",
        wild_map_id=15,
        trainer_deployment_qualified=False,
        global_adoption=False,
        fit_admission=False,
    )


@dataclass(frozen=True, init=False)
class VerifiedProductionWildComponent:
    """Immutable byte-authenticated existing wild component; never a new actor."""

    _canonical: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _WILD_COMPONENT_TOKEN:
            raise ValueError("wild component requires actual model and qualification bytes")
        object.__setattr__(
            self,
            "_canonical",
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(),
        )
        self.require_registered()

    def document(self):
        return json.loads(self._canonical)

    def require_registered(self):
        document = self.document()
        pair = QUALIFIED_WILD_COMPONENTS.get(document.get("model_sha256"))
        if pair is None or document != _wild_component_document(
            document["model_sha256"], pair[0], pair[1]
        ):
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
    if (
        type(qualification) is not dict
        or qualification.get("schema") != "pokemon.current-control-wild-component-qualification.v1"
        or any(
            qualification.get(k) is not True
            for k in (
                "passed",
                "wild_preparation_core_native_qualified",
                "all801_numeric_bounds_passed",
                "healthy_and_sand_nidoran_endpoints_exact",
                "unused_configuration_retained",
                "whole_preparation_retained",
            )
        )
        or qualification.get("candidate", {}).get("sha256") != raw
        or qualification.get("trainer_deployment_qualified") is not False
        or qualification.get("global_models_adopted") != 0
        or qualification.get("actual_registration_delta") != 0
    ):
        raise ValueError("wild-only qualification contract differs")
    from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel

    original = json.loads(model_bytes)
    model = TrainerPracticeThreeHeadModel.from_dict(original)
    if canonical_sha256(model.to_dict()) != pair[0] or canonical_sha256(original) != pair[0]:
        raise ValueError("wild component codec or canonical content differs")
    return VerifiedProductionWildComponent(
        _wild_component_document(raw, *pair), _token=_WILD_COMPONENT_TOKEN
    )


def _digest(value, length=64):
    return (
        type(value) is str and len(value) == length and all(c in "0123456789abcdef" for c in value)
    )


def _noncombat_declaration(objectives, *, teacher_prefix):
    if type(objectives) is not tuple:
        raise ValueError("noncombat TRAIN objectives require an immutable tuple")
    if not objectives:
        return {}
    if not teacher_prefix or objectives != ("obtain_strength",):
        raise ValueError(
            "noncombat TRAIN objective needs the exact teacher-prefix source and scope"
        )
    return dict(noncombat_objective_ids=list(objectives))


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
    noncombat_objective_ids: tuple[str, ...] = ()

    def __post_init__(self):
        original = (
            self.source_state_sha256 in SOURCE_STATES
            and (self.envelope_sha256, self.progress_sha256)
            == SOURCE_PROVENANCE[self.source_state_sha256]
        )
        derived = False
        if self.derived_source_proof is not None:
            from .red_production_train_source import (
                VerifiedDerivedTrainSource,
                VerifiedEarnedNoncombatTrainSource,
                VerifiedTeacherPrefixTrainSource,
            )

            proof = self.derived_source_proof
            derived = (
                type(proof)
                in (
                    VerifiedDerivedTrainSource,
                    VerifiedTeacherPrefixTrainSource,
                    VerifiedEarnedNoncombatTrainSource,
                )
                and self.source_state_sha256 == proof.source_state_sha256
                and self.source_origin_sha256 == proof.source_origin_sha256
                and self.source_commit == proof.source_commit
            )
        if (
            (not original if self.derived_source_proof is None else not derived)
            or self.source_origin_sha256 != self.expected_origin
            or not _digest(self.source_commit, 40)
            or not all(
                _digest(x)
                for x in (self.work_order_sha256, self.envelope_sha256, self.progress_sha256)
            )
        ):
            raise ValueError("production TRAIN admission source or identity differs")
        if self.teacher_prefix:
            from .red_production_train_source import SOURCE049_ARTIFACT_PINS

            if (
                self.envelope_sha256 != SOURCE049_ARTIFACT_PINS["prefix_envelope"]
                or self.progress_sha256
                != sha256(self.derived_source_proof.progress_bytes()).hexdigest()
            ):
                raise ValueError("teacher TRAIN admission needs its exact source metadata bytes")
        if self.earned_noncombat and (
            self.noncombat_objective_ids != ("obtain_strength",)
            or self.envelope_sha256
            != sha256(self.derived_source_proof.envelope_bytes()).hexdigest()
            or self.progress_sha256
            != sha256(self.derived_source_proof.progress_bytes()).hexdigest()
        ):
            raise ValueError(
                "earned TRAIN admission needs exact metadata and obtain_strength scope"
            )
        if self.wild_component_proof is not None:
            if type(self.wild_component_proof) is not VerifiedProductionWildComponent:
                raise ValueError("production TRAIN needs a verified wild component witness")
            self.wild_component_proof.require_registered()
        _noncombat_declaration(self.noncombat_objective_ids, teacher_prefix=self.source049_family)

    @classmethod
    def authenticate(
        cls,
        *,
        source_state,
        envelope_bytes,
        progress_bytes,
        plan_bytes,
        source_commit,
        derived_source_proof=None,
        context_bytes=None,
        wild_component_proof=None,
        noncombat_objective_ids=(),
    ):
        """Bind actual source bytes and original TRAIN metadata before input.

        Caller still owns package/read guards and the source custody chain. A
        development runtime/result cannot be passed here as a training source.
        """
        envelope, progress, plan = map(json.loads, (envelope_bytes, progress_bytes, plan_bytes))
        state = sha256(source_state).hexdigest()
        derived_declaration = {}
        if derived_source_proof is not None:
            from .red_production_train_source import (
                VerifiedDerivedTrainSource,
                VerifiedEarnedNoncombatTrainSource,
                VerifiedTeacherPrefixTrainSource,
            )

            if type(derived_source_proof) not in (
                VerifiedDerivedTrainSource,
                VerifiedTeacherPrefixTrainSource,
                VerifiedEarnedNoncombatTrainSource,
            ):
                raise ValueError("derived source needs authenticated sealed prefix readback")
            derived_source_proof.require_metadata(envelope, progress)
            derived_source_proof.require_source_context(source_state, context_bytes)
            derived_declaration = dict(derived_source_proof_sha256=derived_source_proof.identity)
        if wild_component_proof is not None:
            if type(wild_component_proof) is not VerifiedProductionWildComponent:
                raise ValueError("production TRAIN needs a verified wild component witness")
            wild_component_proof.require_registered()
        component = (
            {}
            if wild_component_proof is None
            else dict(
                wild_component_proof_sha256=wild_component_proof.identity,
                wild_model_content_sha256=wild_component_proof.model_content_sha256,
                wild_qualification_sha256=wild_component_proof.qualification_sha256,
            )
        )
        from .red_production_train_source import (
            VerifiedEarnedNoncombatTrainSource,
            VerifiedTeacherPrefixTrainSource,
        )

        teacher = type(derived_source_proof) in (
            VerifiedTeacherPrefixTrainSource,
            VerifiedEarnedNoncombatTrainSource,
        )
        noncombat = _noncombat_declaration(noncombat_objective_ids, teacher_prefix=teacher)
        origin = SOURCE_ORIGIN if not teacher else derived_source_proof.source_origin_sha256
        objective = "defeat_blaine" if teacher else "defeat_misty"
        expected = dict(
            schema=(
                ADMISSION_NONCOMBAT_SCHEMA
                if noncombat
                else ADMISSION_TEACHER_SCHEMA
                if teacher
                else ADMISSION_SCHEMA
                if wild_component_proof is None
                else ADMISSION_COMPONENT_SCHEMA
            ),
            source_state_sha256=state,
            source_envelope_sha256=sha256(envelope_bytes).hexdigest(),
            assisted_progress_sha256=sha256(progress_bytes).hexdigest(),
            wild_model_sha256=WILD_MODEL
            if wild_component_proof is None
            else wild_component_proof.model_sha256,
            story_model_sha256=STORY_MODEL,
            wild_map_id=15,
            objective_id=objective,
            **derived_declaration,
            **component,
            **noncombat,
        )
        if (
            plan.get("partition") != "train"
            or plan.get("production_train_components") != expected
            or progress.get("partition") != "train"
            or progress.get("fit_allowed") is not True
            or progress.get("campaign_eligible") is not False
            or progress.get("role") != "train_sampling"
            or progress.get("source_origin_sha256") != origin
            or progress.get("envelope") != envelope
            or envelope.get("state_sha256") != state
        ):
            raise ValueError(
                "production TRAIN admission requires exact prospective TRAIN source metadata"
            )
        return cls(
            state,
            origin,
            source_commit,
            sha256(plan_bytes).hexdigest(),
            sha256(envelope_bytes).hexdigest(),
            sha256(progress_bytes).hexdigest(),
            derived_source_proof,
            wild_component_proof,
            noncombat_objective_ids,
        )

    @classmethod
    def from_document(cls, document, *, derived_source_proof=None, wild_component_proof=None):
        names = (
            "source_state_sha256",
            "source_origin_sha256",
            "source_commit",
            "work_order_sha256",
            "envelope_sha256",
            "progress_sha256",
        )
        noncombat = document.get("noncombat_objective_ids", [])
        if type(noncombat) is not list:
            raise ValueError("noncombat TRAIN document scope must be a list")
        restored = cls(
            **{name: document[name] for name in names},
            derived_source_proof=derived_source_proof,
            wild_component_proof=wild_component_proof,
            noncombat_objective_ids=tuple(noncombat),
        )
        if canonical_sha256(restored.document()) != canonical_sha256(document):
            raise ValueError("production TRAIN admission document differs")
        return restored

    @property
    def teacher_prefix(self):
        from .red_production_train_source import VerifiedTeacherPrefixTrainSource

        return type(self.derived_source_proof) is VerifiedTeacherPrefixTrainSource

    @property
    def earned_noncombat(self):
        from .red_production_train_source import VerifiedEarnedNoncombatTrainSource

        return type(self.derived_source_proof) is VerifiedEarnedNoncombatTrainSource

    @property
    def source049_family(self):
        return self.teacher_prefix or self.earned_noncombat

    @property
    def expected_origin(self):
        from .red_production_train_source import SOURCE049_ORIGIN

        return SOURCE049_ORIGIN if self.source049_family else SOURCE_ORIGIN

    @property
    def objective_id(self):
        return "defeat_blaine" if self.source049_family else "defeat_misty"

    @property
    def admitted_story_objective_ids(self):
        """Observer scope only; noncombat objectives grant no battler authority."""
        return (self.objective_id,) + self.noncombat_objective_ids

    @property
    def wild_map_id(self):
        # Existing wild component qualifications remain Route4-only.
        return 15

    @property
    def story_map_id(self):
        return 166 if self.source049_family else 65

    @property
    def story_reward(self):
        from .red_gym_reward import BLAINE_REWARD, MISTY_REWARD

        return BLAINE_REWARD if self.source049_family else MISTY_REWARD

    @property
    def admission_schema(self):
        if self.noncombat_objective_ids:
            return ADMISSION_NONCOMBAT_SCHEMA
        if self.teacher_prefix:
            return ADMISSION_TEACHER_SCHEMA
        return ADMISSION_SCHEMA if self.wild_component_proof is None else ADMISSION_COMPONENT_SCHEMA

    @property
    def wild_model_sha256(self):
        return (
            WILD_MODEL
            if self.wild_component_proof is None
            else self.wild_component_proof.model_sha256
        )

    @property
    def wild_model_content_sha256(self):
        return (
            WILD_CONTENT
            if self.wild_component_proof is None
            else self.wild_component_proof.model_content_sha256
        )

    def _wild_component_declaration(self):
        proof = self.wild_component_proof
        return (
            {}
            if proof is None
            else dict(
                wild_component_proof_sha256=proof.identity,
                wild_model_content_sha256=proof.model_content_sha256,
                wild_qualification_sha256=proof.qualification_sha256,
            )
        )

    @property
    def root_lineage_id(self):
        return "red-goal-root-" + self.source_origin_sha256

    def document(self):
        names = (
            "source_state_sha256",
            "source_origin_sha256",
            "source_commit",
            "work_order_sha256",
            "envelope_sha256",
            "progress_sha256",
        )
        derived = (
            {}
            if self.derived_source_proof is None
            else dict(derived_source_proof_sha256=self.derived_source_proof.identity)
        )
        return dict(
            schema=self.admission_schema,
            **{name: getattr(self, name) for name in names},
            **derived,
            source_partition="train",
            wild_model_sha256=self.wild_model_sha256,
            story_model_sha256=STORY_MODEL,
            wild_map_id=self.wild_map_id,
            objective_id=self.objective_id,
            fit_admission=False,
            **self._wild_component_declaration(),
            **_noncombat_declaration(
                self.noncombat_objective_ids, teacher_prefix=self.source049_family
            ),
        )

    @property
    def identity(self):
        return canonical_sha256(self.document())

    def declaration(self):
        derived = (
            {}
            if self.derived_source_proof is None
            else dict(derived_source_proof_sha256=self.derived_source_proof.identity)
        )
        return dict(
            schema=self.admission_schema,
            **derived,
            source_state_sha256=self.source_state_sha256,
            source_envelope_sha256=self.envelope_sha256,
            assisted_progress_sha256=self.progress_sha256,
            wild_model_sha256=self.wild_model_sha256,
            story_model_sha256=STORY_MODEL,
            wild_map_id=self.wild_map_id,
            objective_id=self.objective_id,
            **self._wild_component_declaration(),
            **_noncombat_declaration(
                self.noncombat_objective_ids, teacher_prefix=self.source049_family
            ),
        )

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
        if (
            type(plan) is not dict
            or plan.get("partition") != "train"
            or plan.get("production_train_components") != self.declaration()
        ):
            raise ValueError("production TRAIN admission needs its exact TRAIN work order")

    def require_scope(self, scope, role):
        if (
            scope.source_state_sha256 != self.source_state_sha256
            or scope.root_lineage_id != self.root_lineage_id
            or scope.work_order_sha256 != self.work_order_sha256
        ):
            raise ValueError("production TRAIN scope source/work order differs")
        if role == "wild":
            valid = (
                scope.model_sha256 == self.wild_model_sha256
                and scope.model_content_sha256 == self.wild_model_content_sha256
                and scope.map_id == self.wild_map_id
            )
        elif role == "story":
            contract = scope.contract
            expected = (
                ((239, 39, 1), 665, 4653, ((238, 1),), 64)
                if self.source049_family
                else ((235, 35, 1), 191, 2079, ((211, 1),), 2)
            )
            valid = (
                scope.model_sha256 == STORY_MODEL
                and scope.model_content_sha256 == STORY_CONTENT
                and contract is not None
                and contract.objective_id == self.objective_id
                and contract.battle_plan_id == self.objective_id
                and contract.map_id == self.story_map_id
                and contract.trainer_identity == expected[0]
                and contract.defeated_event == expected[1]
                and contract.victory_money == expected[2]
                and contract.victory_items == expected[3]
                and contract.victory_badge_bits == expected[4]
                and scope.gym_reward is not None
                and scope.gym_reward.objective_id == self.objective_id
                and scope.allow_learned_tactics is True
                and scope.diagnostic_status_entry is True
                and scope.screen_capped_status_moves is True
                and scope.diagnostic_stay_when_productive is False
                and scope.diagnostic_prompt_stay is False
                and scope.diagnostic_status_release is False
            )
        else:
            valid = False
        if not valid:
            raise ValueError("production TRAIN scope model/settings/target differs")

    def require_actor(self, actor, scope, role):
        self.require_scope(scope, role)
        if (
            actor.source_partition is not ScenarioPartition.TRAIN
            or actor.source_commit != self.source_commit
            or actor.source_state_sha256 != self.source_state_sha256
            or actor.root_lineage_id != self.root_lineage_id
            or type(actor.pp_depleted_switch_screen) is not bool
            or actor.pp_depleted_switch_screen is not (role == "story")
            or actor.mechanics_aware_tower_choices is not False
            or actor.diagnostic_tower_productive_stay is not False
        ):
            raise ValueError("production TRAIN actor source/settings differs")


# Finite reuse of exact historical TRAIN fixtures for the actual production
# League funding component. This is source/actor admission, never fit admission.
LEAGUE_TRAIN_SCHEMA = 'pokemon.red.production-league-funding-train.v1'
LEAGUE_TRAIN_MODEL = '111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2'
LEAGUE_TRAIN_CONTENT = '333b78ccc60ac4bb9a078fa391d38be953a687d2cd4a8402fa823eff3ab9546a'
LEAGUE_TRAIN_SOURCES = {
    '04ceddd3119f1f43909eb9e0403e4990d2e0134c82da3ebd18dc8a714e88314a': ('lower-full', '3590e3252e430b232f15a07ed480afe1d61905e06cbbbfe53f1ff6d3fa5748b5', '4a7b0ffa84ae00e8c87764114c2cdeba26fe0c3028c7464fe3fc6302e044fad9'),
    '03ad8eafd9a4f548a6ed2e04a53ab81018da5226f90b94d0953fba54a3787e57': ('prepared-full', '1a66dbd1cd1a0fb7041d0d2fdcc4faa2812a68c7945a7e9a4ebfe403154eab87', 'a19319fb65e4caa2f04384a8dc8cf045f10cffd03cb09ac7432c4de5d8193266'),
}
_LEAGUE_TRAIN_TOKEN = object()



LEAGUE_TRAIN_RESOURCE_SCHEMA = 'pokemon.red.production-league-funding-train.v2'
LEAGUE_TRAIN_RESOURCE_SETUPS = {'03670ee91d95f8ce1779bc20bcb15b129ef143718c6f806de8e06335ff5a809a': {'parent_state_sha256': '04ceddd3119f1f43909eb9e0403e4990d2e0134c82da3ebd18dc8a714e88314a', 'setup_sha256': '983d97fb5df09fb3e632405fa0b698eacf847b89a4ce9c4f081bf78f8f70d15e'}, 'afa4be6c6657ddf2cf10aae9c04fd89523c1a8d8eac6136515adf03d99a13ecc': {'parent_state_sha256': '03ad8eafd9a4f548a6ed2e04a53ab81018da5226f90b94d0953fba54a3787e57', 'setup_sha256': '4cc9d1dc931f0bde4357da2b3c6124e535259296a30759a381be5b60112665d9'}}
LEAGUE_TRAIN_SOURCES.update({'03670ee91d95f8ce1779bc20bcb15b129ef143718c6f806de8e06335ff5a809a': ('lower-full', '34cbb50111b0a7475c7b4f223ed7c463707318a3318ea2b1e31197ef5a4a7a82', 'ed16aa643bb511309c7f7da30dd7379f3fef658237d78ade4a6204e0e4003869'), 'afa4be6c6657ddf2cf10aae9c04fd89523c1a8d8eac6136515adf03d99a13ecc': ('prepared-full', 'f301e5e9b22571e3ef61fbfc2372eecbb1cfc3f91ba6b30af01dbc4c817e59af', '53c1a1cc6ed08c079d8faba52936ca57acfe74ac289e5b5f78477affa0ca242c')})

NATIVE_FUNDING_CHECKPOINT_SCHEMA = 'pokemon.red.production-league-funding-native-checkpoint-train.v3'
NATIVE_FUNDING_CHECKPOINT_AUTH = '1ad40b0ef6a0422487649a3c0392580121d7b42dbb2d92e7aa58d93166111d06'
NATIVE_FUNDING_CHECKPOINTS = {
    'lower-full-fund-now-v6': ('03670ee91d95f8ce1779bc20bcb15b129ef143718c6f806de8e06335ff5a809a',
        '3ed4e539d54e265825fcacb05640bcebd6cc77c2e3d88a5be89ade03d903a420'),
    'prepared-full-fund-now-v6': ('afa4be6c6657ddf2cf10aae9c04fd89523c1a8d8eac6136515adf03d99a13ecc',
        'e17fec18ed0aa864c0103d4d3378835de3becc5a741feb527cd62a798c9aae6e'),
}


def retained_funding_checkpoint_declaration(*, case_id, source_state, authority_bytes, result_bytes):
    """Reopen two already independently audited native TRAIN funding terminals.

    The receipt pins full native source/terminal readbacks, journals and the
    original assigned TRAIN lineage. Failed League outcomes and every old cost
    remain in the parent; this is no new origin, actor renewal or fitting grant.
    No arbitrary descendant, DEVELOPMENT source or edited state is accepted.
    """
    if (case_id not in NATIVE_FUNDING_CHECKPOINTS
            or any(type(x) is not bytes for x in (source_state,authority_bytes,result_bytes))
            or sha256(authority_bytes).hexdigest()!=NATIVE_FUNDING_CHECKPOINT_AUTH):
        raise ValueError('retained funding checkpoint requires its exact native authority')
    authority=json.loads(authority_bytes)
    rows=[r for r in authority['rows'] if r['case']==case_id]
    if len(rows)!=1 or authority.get('passed') is not True:
        raise ValueError('retained funding checkpoint native census differs')
    row=rows[0]
    if sha256(result_bytes).hexdigest()!=row['result']['sha256']:
        raise ValueError('retained funding checkpoint result bytes changed')
    result=json.loads(result_bytes);phase=result['phase_results'][0]
    parent,terminal=NATIVE_FUNDING_CHECKPOINTS[case_id]
    if (sha256(result_bytes).hexdigest()!=row['result']['sha256']
            or sha256(source_state).hexdigest()!=terminal
            or row['partition']!='train' or row['teacher_selected'] is not True
            or phase['ordinal']!=0 or phase['before_sha256']!=parent
            or phase['after_state']['sha256']!=terminal
            or row['phases'][0]['before_state']['sha256']!=parent
            or row['phases'][0]['after_state']['sha256']!=terminal
            or result.get('guest_closed') is not True
            or result.get('original_source_unchanged') is not True
            or phase['after']['battle_state']!=0
            or phase['after']['input_ready'] is not True
            or phase['after']['buttons_released'] is not True):
        raise ValueError('retained funding checkpoint source/result/native boundary differs')
    return dict(schema=NATIVE_FUNDING_CHECKPOINT_SCHEMA,source_state_sha256=terminal,
        source_origin_sha256=SOURCE_ORIGIN,model_sha256=LEAGUE_TRAIN_MODEL,
        model_content_sha256=LEAGUE_TRAIN_CONTENT,native_checkpoint_case=case_id,
        native_checkpoint_parent_state_sha256=parent,
        native_checkpoint_authority_sha256=NATIVE_FUNDING_CHECKPOINT_AUTH,
        native_checkpoint_result_sha256=sha256(result_bytes).hexdigest(),
        native_checkpoint_ordinal=0,prior_failures_and_costs_retained=True)


@dataclass(frozen=True, init=False)
class LeagueFundingTrainAdmission:
    """Exact original TRAIN bytes/work order for unchanged111ef funding actors.

    Fixture eligibility remains historical and correlated, not complete fresh
    genesis. No arbitrary sources, DEVELOPMENT relabeling, controller fallback,
    model promotion, data admission or changed battle settings follow from this.
    """
    _bytes: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _LEAGUE_TRAIN_TOKEN:
            raise ValueError('funding TRAIN admission needs actual source/work-order bytes')
        object.__setattr__(self, '_bytes', json.dumps(document, sort_keys=True, separators=(',', ':')).encode())

    @classmethod
    def authenticate(cls, *, source_state, envelope_bytes, progress_bytes,
                     setup_bytes, original_train_plan_bytes, work_order_bytes,
                     source_commit, model_bytes, resource_parent_state=None):
        payloads=(source_state,envelope_bytes,progress_bytes,setup_bytes,original_train_plan_bytes,work_order_bytes,model_bytes)
        if any(type(x) is not bytes for x in payloads) or not _digest(source_commit,40):
            raise ValueError('funding TRAIN requires immutable authentic bytes')
        state=sha256(source_state).hexdigest();registered=LEAGUE_TRAIN_SOURCES.get(state)
        if registered is None or tuple(sha256(x).hexdigest()for x in (envelope_bytes,progress_bytes))!=registered[1:]:
            raise ValueError('funding TRAIN source is not an exact retained TRAIN fixture')
        envelope,progress,setup,original,work=map(json.loads,(envelope_bytes,progress_bytes,setup_bytes,original_train_plan_bytes,work_order_bytes))
        resource=LEAGUE_TRAIN_RESOURCE_SETUPS.get(state)
        if resource is None:
            if resource_parent_state is not None:
                raise ValueError('original TRAIN source cannot claim a resource parent')
            original_state=state
        else:
            original_state=resource['parent_state_sha256']
            if (type(resource_parent_state)is not bytes
                    or sha256(resource_parent_state).hexdigest()!=original_state
                    or sha256(setup_bytes).hexdigest()!=resource['setup_sha256']
                    or setup.get('resource_parent_state_sha256')!=original_state
                    or setup.get('intervention')!='cash8_remove_ordinary_balls_only'
                    or setup.get('all_other_WRAM_unchanged')is not True
                    or setup.get('party_XP_HP_PP_events_dex_unchanged')is not True
                    or setup.get('inputs')!=0 or setup.get('frames')!=0):
                raise ValueError('resource TRAIN source requires exact original parent and setup bytes')
        declaration=dict(schema=LEAGUE_TRAIN_SCHEMA if resource is None else LEAGUE_TRAIN_RESOURCE_SCHEMA,source_state_sha256=state,
            source_envelope_sha256=registered[1],assisted_progress_sha256=registered[2],
            setup_sha256=sha256(setup_bytes).hexdigest(),source_origin_sha256=SOURCE_ORIGIN,
            model_sha256=LEAGUE_TRAIN_MODEL,model_content_sha256=LEAGUE_TRAIN_CONTENT,
            original_train_plan_sha256=sha256(original_train_plan_bytes).hexdigest())
        if resource is not None:declaration['resource_parent_state_sha256']=original_state
        if (progress.get('partition')!='train' or progress.get('campaign_eligible')is not False
                or progress.get('envelope')!=envelope or envelope.get('state_sha256')!=state
                or progress.get('state_sha256')!=state or setup.get('source_sha256')!=SOURCE_ORIGIN
                or progress.get('setup_receipt_sha256')!=declaration['setup_sha256']
                or original.get('partition')!='train' or original.get('development_outcomes')!=0
                or original.get('conditions',{}).get(registered[0],{}).get('source_sha256')!=original_state
                or work.get('partition')!='train' or work.get('teacher_actions_allowed')is not True
                or work.get('league_funding_train_component')!=declaration
                or sha256(model_bytes).hexdigest()!=LEAGUE_TRAIN_MODEL
                or canonical_sha256(json.loads(model_bytes))!=LEAGUE_TRAIN_CONTENT):
            raise ValueError('funding TRAIN provenance/model/declaration differs')
        doc=dict(declaration,source_commit=source_commit,work_order_sha256=sha256(work_order_bytes).hexdigest(),
                 source_partition='train',fit_admission=False,complete_genesis=False,new_independent_origin=False)
        return cls(doc,_token=_LEAGUE_TRAIN_TOKEN)

    def document(self):
        return json.loads(self._bytes)

    @classmethod
    def authenticate_retained_checkpoint(cls, *, case_id, source_state, authority_bytes,
            result_bytes, work_order_bytes, source_commit, model_bytes):
        declaration=retained_funding_checkpoint_declaration(case_id=case_id,source_state=source_state,
            authority_bytes=authority_bytes,result_bytes=result_bytes)
        if (type(work_order_bytes) is not bytes or type(model_bytes) is not bytes
                or not _digest(source_commit,40) or sha256(model_bytes).hexdigest()!=LEAGUE_TRAIN_MODEL
                or canonical_sha256(json.loads(model_bytes))!=LEAGUE_TRAIN_CONTENT):
            raise ValueError('retained funding checkpoint needs the exact existing model/work bytes')
        work=json.loads(work_order_bytes)
        if (work.get('partition')!='train' or work.get('teacher_actions_allowed') is not True
                or work.get('league_funding_train_component')!=declaration):
            raise ValueError('retained funding checkpoint work declaration differs')
        return cls(dict(declaration,source_commit=source_commit,
            work_order_sha256=sha256(work_order_bytes).hexdigest(),source_partition='train',
            fit_admission=False,complete_genesis=False,new_independent_origin=False),_token=_LEAGUE_TRAIN_TOKEN)

    @property
    def source_state_sha256(self):return self.document()['source_state_sha256']
    @property
    def source_origin_sha256(self):return SOURCE_ORIGIN
    @property
    def source_commit(self):return self.document()['source_commit']
    @property
    def work_order_sha256(self):return self.document()['work_order_sha256']
    @property
    def root_lineage_id(self):return 'red-goal-root-'+SOURCE_ORIGIN
    @property
    def identity(self):return canonical_sha256(self.document())

    def require_work_order(self, payload):
        if type(payload)is not bytes or sha256(payload).hexdigest()!=self.work_order_sha256:
            raise ValueError('funding TRAIN work order changed')
        work=json.loads(payload);d=self.document()
        if d['schema']==NATIVE_FUNDING_CHECKPOINT_SCHEMA:
            declared={k:v for k,v in d.items() if k not in {'source_commit','work_order_sha256',
                'source_partition','fit_admission','complete_genesis','new_independent_origin'}}
            if (work.get('partition')!='train' or work.get('teacher_actions_allowed') is not True
                    or work.get('league_funding_train_component')!=declared):
                raise ValueError('retained funding checkpoint work declaration differs')
            return
        keys=('schema','source_state_sha256','source_envelope_sha256','assisted_progress_sha256','setup_sha256','source_origin_sha256','model_sha256','model_content_sha256','original_train_plan_sha256')
        if 'resource_parent_state_sha256'in d:keys+=('resource_parent_state_sha256',)
        if work.get('partition')!='train' or work.get('teacher_actions_allowed')is not True or work.get('league_funding_train_component')!={k:d[k]for k in keys}:
            raise ValueError('funding TRAIN work declaration differs')

    def require_scope(self, scope, role):
        from .red_player_league_options import LEAGUE_PLAYER_TARGETS,CHAMPION_PLAYER_TARGET
        targets={x.objective_id:x for x in (*LEAGUE_PLAYER_TARGETS,CHAMPION_PLAYER_TARGET)}
        contract=scope.contract;target=targets.get(getattr(contract,'objective_id',None))
        if (role!='story' or target is None or scope.source_state_sha256!=self.source_state_sha256
                or scope.root_lineage_id!=self.root_lineage_id or scope.work_order_sha256!=self.work_order_sha256
                or scope.model_sha256!=LEAGUE_TRAIN_MODEL or scope.model_content_sha256!=LEAGUE_TRAIN_CONTENT
                or contract.map_id!=int(target.room) or contract.defeated_event!=int(target.event)
                or contract.victory_items or contract.victory_badge_bits or scope.gym_reward is not None
                or scope.allow_learned_tactics is not True or scope.diagnostic_status_entry is not True
                or scope.screen_capped_status_moves is not True or scope.diagnostic_stay_when_productive
                or scope.diagnostic_prompt_stay or scope.diagnostic_status_release):
            raise ValueError('funding TRAIN scope source/model/native room/settings differ')

    def require_actor(self, actor, scope, role):
        self.require_scope(scope,role)
        if (actor.source_partition is not ScenarioPartition.TRAIN or actor.source_commit!=self.source_commit
                or actor.source_state_sha256!=self.source_state_sha256 or actor.root_lineage_id!=self.root_lineage_id
                or actor.pp_depleted_switch_screen is not True or actor.mechanics_aware_tower_choices is not False
                or actor.diagnostic_tower_productive_stay is not False):
            raise ValueError('funding TRAIN actor source/settings differ')


SCOPED_STORY_TRAIN_SCHEMA = "pokemon.red.scoped-production-story-train.v1"
_SCOPED_STORY_TOKEN = object()
SCOPED_STORY_MODELS = frozenset({
    STORY_MODEL,
    "05a7afb42bfdf8b5d416782a516e78ae82d7a6d4cd72eea77134b484822c7333",
})


class ScopedProductionStoryAdmission:
    """Exact production components beside a caller-authenticated TRAIN family.

    Actual state/context/work bytes and the original TRAIN assignment are bound.
    Ancestry, teacher interventions and row admission retain independent audits.
    This witness grants only finite story-component reuse.
    """
    __slots__ = ('_bytes', '_contracts', '_routes', '_models')

    def __init__(self, document, contracts, routes, models, *, _token=None):
        if _token is not _SCOPED_STORY_TOKEN:
            raise ValueError('scoped production story needs authenticated bytes')
        from types import MappingProxyType
        object.__setattr__(self, '_bytes', json.dumps(document,sort_keys=True,separators=(',',':')).encode())
        object.__setattr__(self, '_contracts', MappingProxyType(dict(contracts)))
        object.__setattr__(self, '_routes', MappingProxyType(dict(routes)))
        object.__setattr__(self, '_models', MappingProxyType(dict(models)))

    def __setattr__(self, name, value):
        raise AttributeError('scoped production story witness is immutable')

    def __deepcopy__(self, memo):
        return self

    @classmethod
    def authenticate(cls, *, source, state_bytes, context_bytes, work_order_bytes, contracts):
        from pathlib import Path
        from dataclasses import asdict
        from .red_story_battle import StoryTrainerContract
        from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
        from .red_learned_trainer import FROZEN_K_SHA256
        from .red_scoped_training_battlers import scoped_train_root_lineage_id
        if (type(source) is not dict or source.get('partition')!='train'
                or any(type(v)is not bytes for v in (state_bytes,context_bytes,work_order_bytes))
                or type(contracts)is not tuple or not 1<=len(contracts)<=4096
                or any(type(c)is not StoryTrainerContract for c in contracts)):
            raise ValueError('scoped production story requires finite TRAIN inputs')
        context,work=map(json.loads,(context_bytes,work_order_bytes))
        state=sha256(state_bytes).hexdigest();ctx=sha256(context_bytes).hexdigest();order=sha256(work_order_bytes).hexdigest()
        if (source.get('state_sha256')!=state or source.get('experiment_sha256')!=order
                or not _digest(source.get('source_commit'),40)
                or not _digest(source.get('origin_sha256'))
                or context.get('state_sha256')!=state
                or context.get('fit_allowed')is not False or context.get('grants_new_budget')is not False
                or work.get('partition')!='train' or work.get('fit_allowed')is not False):
            raise ValueError('scoped production story source/context/work differs')
        def pinned(spec):
            if type(spec)is not dict or set(spec)!={'path','sha256'} or work.get('pins',{}).get(spec['path'])!=spec['sha256']:
                raise ValueError('production TRAIN component needs a pinned file')
            payload=Path(spec['path']).read_bytes()
            if sha256(payload).hexdigest()!=spec['sha256']:
                raise ValueError('production TRAIN component bytes changed')
            return payload
        chain=json.loads(pinned(work.get('TRAIN_source_authentication')))
        assignment=chain.get('original_assignment',{})
        if (chain.get('passed')is not True or assignment.get('partition')!='train'
                or assignment.get('assignment_id')!=source['origin_sha256']
                or assignment.get('root_lineage_id')!=scoped_train_root_lineage_id(source['origin_sha256'])):
            raise ValueError('production story needs the original TRAIN assignment')
        for key in ('registry','original_authentication'):
            spec=chain[key]
            if sha256(Path(spec['path']).read_bytes()).hexdigest()!=spec['sha256']:
                raise ValueError('original TRAIN source authentication changed')
        components=work.get('production_story_components');routes=work.get('production_story_routes')
        if type(components)is not dict or not components or not set(components)<=SCOPED_STORY_MODELS or type(routes)is not dict:
            raise ValueError('production story components are not exact retained models')
        models={};contents={}
        for digest,spec in components.items():
            payload=pinned(spec)
            if sha256(payload).hexdigest()!=digest:
                raise ValueError('production story model digest differs')
            model=TrainerPracticeThreeHeadModel.from_dict(json.loads(payload));models[digest]=model;contents[digest]=canonical_sha256(model.to_dict())
        contract_map={canonical_sha256(asdict(c)):c for c in contracts}
        if (len(contract_map)!=len(contracts) or set(routes)!=set(contract_map)
                or any(v not in {*models,FROZEN_K_SHA256}for v in routes.values())):
            raise ValueError('production story route/contract census differs')
        document=dict(schema=SCOPED_STORY_TRAIN_SCHEMA,source_partition='train',source_state_sha256=state,
            source_origin_sha256=source['origin_sha256'],source_commit=source['source_commit'],
            root_lineage_id=scoped_train_root_lineage_id(source['origin_sha256']),context_sha256=ctx,
            work_order_sha256=order,original_source_chain_sha256=work['TRAIN_source_authentication']['sha256'],
            contracts_sha256=canonical_sha256([asdict(c)for c in contracts]),routes_sha256=canonical_sha256(routes),
            model_content_sha256=contents,model_file_sha256=sorted(models),contract_count=len(contracts),
            allow_learned_tactics=True,diagnostic_status_entry=True,screen_capped_status_moves=True,
            fit_admission=False,new_independent_origin=False,source_ancestry_admission_conferred=False)
        return cls(document,contract_map,routes,models,_token=_SCOPED_STORY_TOKEN)

    def document(self):return json.loads(self._bytes)
    @property
    def identity(self):return canonical_sha256(self.document())
    def require_source(self, source):
        d=self.document()
        expected=dict(partition='train',state_sha256=d['source_state_sha256'],origin_sha256=d['source_origin_sha256'],source_commit=d['source_commit'],experiment_sha256=d['work_order_sha256'])
        if any(source.get(k)!=v for k,v in expected.items()):
            raise ValueError('production story native source differs')
    def component_for(self, contract):
        from dataclasses import asdict
        key=canonical_sha256(asdict(contract))
        if self._contracts.get(key)!=contract:raise ValueError('undeclared production TRAIN story contract')
        return self._routes[key]
    def model_for(self, contract):return self._models[self.component_for(contract)]
    def require_scope(self, scope, role):
        d=self.document();digest=self.component_for(scope.contract)
        if (role!='story' or digest not in self._models
                or scope.source_state_sha256!=d['source_state_sha256']or scope.root_lineage_id!=d['root_lineage_id']
                or scope.work_order_sha256!=d['work_order_sha256']or scope.model_sha256!=digest
                or scope.model_content_sha256!=d['model_content_sha256'][digest]
                or not scope.allow_learned_tactics or not scope.diagnostic_status_entry or not scope.screen_capped_status_moves
                or scope.diagnostic_stay_when_productive or scope.diagnostic_prompt_stay or scope.diagnostic_status_release):
            raise ValueError('production TRAIN story scope differs from retained recipe')
    def require_actor(self, actor, scope, role):
        self.require_scope(scope,role)
        if (actor.source_partition is not ScenarioPartition.TRAIN
                or actor.source_commit!=self.document()['source_commit']
                or actor.train_story_contract!=scope.contract):
            raise ValueError('production TRAIN story actor source differs')

