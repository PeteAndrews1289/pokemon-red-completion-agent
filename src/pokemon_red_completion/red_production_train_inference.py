"""Default-off inference witness for the original six-party TRAIN fixture.

This binds an existing selector and trained head. It adds no labels, optimizer,
controller policy, promotion, new source, or DEV eligibility.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

SCHEMA = 'pokemon.red.production-train-consequence-inference.v1'
SOURCE_SHA256 = '0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d'
CONTEXT_SHA256 = '688a6016e7cdc8ab97a66873421b27fe0913327ac8aa59ce9d00ff71747cb5da'
PARENT_SHA256 = '4c2b16a21362e17bddc2f861a579e420bd0096dbca24b66058b52391a2b0c62a'
WILD_SHA256 = '3b187fc6bfb46dd0fd062f0d14ff5fadffe353347d4e94a2124bdbaba988c4b3'
_TOKEN = object()

def _require(condition, reason):
    if not condition:
        raise ValueError('production TRAIN inference ' + reason)

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()

def _source_identity(source, admission):
    _require(type(source) is dict and source.get('partition') == 'train'
        and source.get('state_sha256') == SOURCE_SHA256 == admission.source_state_sha256
        and source.get('origin_sha256') == admission.source_origin_sha256
        and source.get('source_commit') == admission.source_commit
        and source.get('experiment_sha256') == admission.work_order_sha256
        and source.get('training_admission') == admission.identity,
        'requires the exact original admitted TRAIN SourceSpec')
    return sha256(_canonical(source)).hexdigest()

def _models(model, head):
    from .living_dex_option_value import LivingDexOptionValueModel
    from .player_challenge_consequence import ChallengeConsequenceHead
    _require(type(model) is LivingDexOptionValueModel and model.feature_version == 15
        and model.model_sha256 == PARENT_SHA256,
        'requires the exact already-converted A9 parent')
    _require(type(head) is ChallengeConsequenceHead and head.feature_version == 15
        and head.feedback_version == 2 and head.provenance == 'native_train'
        and head.cash_prediction == 'independent',
        'requires an explicit trained V15 feedback2 head')
    return model.model_sha256, head.model_sha256

def train_inference_declaration(model, head):
    parent, child = _models(model, head)
    return dict(schema=SCHEMA, source_state_sha256=SOURCE_SHA256,
        source_context_sha256=CONTEXT_SHA256, parent_model_sha256=parent,
        consequence_head_model_sha256=child, feature_version=15, feedback_version=2,cash_prediction='independent',
        objective_ref='defeat_misty', challenge_ref='defeat_misty',
        inference_only=True, optimizer_admission=False, consequence_recording=False)

@dataclass(frozen=True, init=False)
class ProductionTrainConsequenceInference:
    _canonical_bytes: bytes
    _admission: object
    _plan_bytes: bytes
    _token: object

    def __init__(self, document, *, admission, plan_bytes, _token=None):
        if _token is not _TOKEN:
            raise ValueError('production TRAIN inference requires authenticated input bytes')
        object.__setattr__(self, '_canonical_bytes', _canonical(document))
        object.__setattr__(self, '_admission', admission)
        object.__setattr__(self, '_plan_bytes', bytes(plan_bytes))
        object.__setattr__(self, '_token', _TOKEN)

    @classmethod
    def authenticate(cls, *, admission, source, source_state, context_bytes,
                     envelope_bytes, progress_bytes, plan_bytes, model, head):
        from .red_production_train_admission import ProductionTrainAdmission
        _require(type(admission) is ProductionTrainAdmission,
            'requires typed production TRAIN admission')
        _require(type(source_state) is bytes and sha256(source_state).hexdigest() == SOURCE_SHA256
            and type(context_bytes) is bytes and sha256(context_bytes).hexdigest() == CONTEXT_SHA256,
            'requires the exact original source/context bytes, not an earned tail')
        _require(admission.derived_source_proof is None and admission.wild_model_sha256 == WILD_SHA256,
            'requires the original source and exact qualified wild component')
        # Reauthenticate through the existing full TRAIN metadata path rather
        # than trusting a directly constructed admission or a plan-only flag.
        actual = ProductionTrainAdmission.authenticate(source_state=source_state,
            envelope_bytes=envelope_bytes, progress_bytes=progress_bytes, plan_bytes=plan_bytes,
            source_commit=source['source_commit'], wild_component_proof=admission.wild_component_proof)
        _require(actual.document() == admission.document(),
            'admission differs from actual authenticated bytes')
        admission.require_work_order(plan_bytes)
        admission.require_source_context(source_state, context_bytes)
        source_identity = _source_identity(source, admission)
        declaration = train_inference_declaration(model, head)
        plan, context = map(json.loads, (plan_bytes, context_bytes))
        _require(plan.get('partition') == 'train' and plan.get('automatic_fit') is False
            and plan.get('production_train_consequence_inference') == declaration,
            'work order must prospectively declare this exact inference-only composition')
        _require(context.get('schema') == 'pokemon.red.native-player-continuation.v1'
            and context.get('state_sha256') == SOURCE_SHA256
            and context.get('grants_new_budget') is False and context.get('fit_allowed') is False,
            'original paired context cannot grant fit or budget')
        document = dict(declaration, admission=admission.document(),
            admission_identity=admission.identity, source_identity_sha256=source_identity,
            work_order_sha256=admission.work_order_sha256,
            source_origin_sha256=admission.source_origin_sha256,
            source_commit=admission.source_commit, cumulative_spent=context['spent'])
        return cls(document, admission=admission, plan_bytes=plan_bytes, _token=_TOKEN)

    def document(self):
        return json.loads(self._canonical_bytes)

    @property
    def identity(self):
        return sha256(self._canonical_bytes).hexdigest()

    def require(self, *, source, model, head, objective_ref, challenge_ref):
        from .red_production_train_admission import ProductionTrainAdmission
        _require(getattr(self, '_token', None) is _TOKEN
            and type(getattr(self, '_admission', None)) is ProductionTrainAdmission,
            'witness was not authenticated')
        self._admission.require_work_order(self._plan_bytes)
        declaration = train_inference_declaration(model, head)
        document = self.document()
        _require(all(document.get(k) == v for k, v in declaration.items())
            and document.get('admission') == self._admission.document()
            and document.get('admission_identity') == self._admission.identity
            and document.get('source_identity_sha256') == _source_identity(source, self._admission)
            and objective_ref == challenge_ref == 'defeat_misty',
            'source, work order, parent, child or branch differs from its witness')

def validate_train_consequence_inference(scope, *, source, model, head,
                                         objective_ref, challenge_ref):
    if scope is None:
        return False
    _require(type(scope) is ProductionTrainConsequenceInference,
        'requires the exact typed witness, never a flag or decoded dictionary')
    scope.require(source=source, model=model, head=head,
        objective_ref=objective_ref, challenge_ref=challenge_ref)
    return True
