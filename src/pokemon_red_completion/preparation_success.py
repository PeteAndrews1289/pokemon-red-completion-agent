"""Optional preparation-target residual; native admission stays outside this module."""
from dataclasses import dataclass, replace
from types import SimpleNamespace
import math
import re
import numpy as np
from .player_option_preparation import preparation_feature_names
from .provenance import canonical_sha256

SCHEMA = 'pokemon.core.preparation-success-residual.v1'
RIDGE = 1.0

def _digest(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('preparation success evidence identity differs')

def preparation_mask(vectors):
    from .living_dex_option_value import option_feature_names
    names = option_feature_names(16)
    x = np.asarray(vectors, dtype=np.float64)
    if x.ndim not in (1, 2) or x.shape[-1] != len(names) or not np.isfinite(x).all():
        raise ValueError('preparation success feature shape differs')
    present = x[..., names.index('preparation.present')]
    kind = x[..., names.index('kind.develop')]
    if np.any((present != 0) & (present != 1)) or np.any((present == 1) & (kind != 1)):
        raise ValueError('preparation success requires an observed develop target')
    return present == 1

@dataclass(frozen=True, slots=True)
class PreparationSuccessExample:
    decision_sha256: str
    partition: str
    features: tuple[float, ...]
    target_success: bool

    def __post_init__(self):
        _digest(self.decision_sha256)
        if self.partition != 'train' or type(self.target_success) is not bool or type(self.features) is not tuple:
            raise ValueError('preparation success needs actual TRAIN binary targets')
        if not bool(preparation_mask(self.features)):
            raise ValueError('preparation success target is outside preparation scope')

    def document(self):
        return dict(decision_sha256=self.decision_sha256, partition=self.partition,
                    features=list(self.features), target_success=self.target_success,
                    target='selected-original-preparation-target-attained', feature_version=16)

@dataclass(frozen=True, slots=True)
class PreparationSuccessHead:
    coefficients: tuple[float, ...]
    feature_scales: tuple[float, ...]
    parent_model_sha256: str
    attestation_sha256: str
    training_evidence_sha256: str
    decision_sha256s: tuple[str, ...]
    successful_examples: int

    def __post_init__(self):
        n = len(preparation_feature_names())
        for values in (self.coefficients, self.feature_scales):
            if type(values) is not tuple or len(values) != n or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError('preparation success parameters differ')
        if any(v <= 0 for v in self.feature_scales):
            raise ValueError('preparation success scales must be positive')
        for h in (self.parent_model_sha256, self.attestation_sha256, self.training_evidence_sha256):
            _digest(h)
        ids = self.decision_sha256s
        if type(ids) is not tuple or len(ids) < 2 or ids != tuple(sorted(set(ids))):
            raise ValueError('preparation success membership differs')
        for h in ids:
            _digest(h)
        if type(self.successful_examples) is not int or not 0 < self.successful_examples < len(ids):
            raise ValueError('preparation success requires observed successes and failures')

    def delta(self, vectors):
        from .living_dex_option_value import option_feature_names
        preparation_mask(vectors)
        names = option_feature_names(16)
        columns = [names.index(n) for n in preparation_feature_names()]
        x = np.asarray(vectors, dtype=np.float64)
        return (x[..., columns] / np.asarray(self.feature_scales)) @ np.asarray(self.coefficients)

    def to_dict(self):
        return dict(schema=SCHEMA, feature_version=16,
                    feature_names=list(preparation_feature_names()),
                    coefficients=list(self.coefficients), feature_scales=list(self.feature_scales),
                    parent_model_sha256=self.parent_model_sha256,
                    attestation_sha256=self.attestation_sha256,
                    training_evidence_sha256=self.training_evidence_sha256,
                    decision_sha256s=list(self.decision_sha256s), successful_examples=self.successful_examples,
                    ridge=RIDGE, gate='observed-preparation-target-only',
                    base='bounded-frozen-physical-prior', prediction_is_calibrated_probability=False,
                    live_policy_adopted=False)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError('preparation success document differs')
        expected = {'schema','feature_version','feature_names','coefficients','feature_scales',
                    'parent_model_sha256','attestation_sha256','training_evidence_sha256',
                    'decision_sha256s','successful_examples','ridge','gate','base',
                    'prediction_is_calibrated_probability','live_policy_adopted'}
        if set(value) != expected or value['schema'] != SCHEMA or type(value['feature_version']) is not int or value['feature_version'] != 16 or value['feature_names'] != list(preparation_feature_names()) or type(value['ridge']) not in (int,float) or value['ridge'] != RIDGE or value['gate'] != 'observed-preparation-target-only' or value['base'] != 'bounded-frozen-physical-prior' or value['prediction_is_calibrated_probability'] is not False or value['live_policy_adopted'] is not False:
            raise ValueError('preparation success document contract differs')
        if any(type(value[k]) is not list for k in ('coefficients','feature_scales','decision_sha256s')):
            raise ValueError('preparation success document arrays differ')
        return cls(tuple(value['coefficients']),tuple(value['feature_scales']),value['parent_model_sha256'],value['attestation_sha256'],value['training_evidence_sha256'],tuple(value['decision_sha256s']),value['successful_examples'])

def fit_preparation_success(examples, *, frozen_base, attestation_sha256,
                            attested_decision_sha256s, protected_features,
                            protected_decision_sha256s):
    """Reuse gated retained-output Ridge; caller authenticates actual native labels.

    Only the preparation success channel is learned. Protected rows are numerical
    output-preservation constraints, never invented native outcome targets.
    """
    from .living_dex_option_value import LivingDexOptionValueModel, option_feature_names, _fit_outcome_with_retained_outputs
    _digest(attestation_sha256)
    if type(frozen_base) is not LivingDexOptionValueModel or frozen_base.feature_version != 16 or frozen_base.preparation_success_head is not None or frozen_base.movement_success_head is None or frozen_base.interaction_success_head is None:
        raise ValueError('preparation fit requires an exact corrected V16 parent')
    values = tuple(examples)
    if any(type(r) is not PreparationSuccessExample for r in values):
        raise ValueError('preparation fit requires typed observed targets')
    rows = tuple(sorted(values, key=lambda r: r.decision_sha256))
    for row in rows:
        row.__post_init__()
    ids = tuple(r.decision_sha256 for r in rows)
    if len(rows) < 2 or len(set(ids)) != len(ids) or set(ids) != set(attested_decision_sha256s) or len(ids) != len(tuple(attested_decision_sha256s)) or {r.target_success for r in rows} != {False, True}:
        raise ValueError('preparation fit membership or observed class coverage differs')
    protected_ids = tuple(protected_decision_sha256s)
    for h in protected_ids:
        _digest(h)
    width = len(option_feature_names(16))
    protected = np.asarray(protected_features,dtype=np.float64)
    if not protected_ids or len(set(protected_ids)) != len(protected_ids) or set(ids)&set(protected_ids) or protected.shape != (len(protected_ids),width) or preparation_mask(protected).any():
        raise ValueError('preparation fit requires separate non-preparation retention rows')
    x = np.asarray([r.features for r in rows],dtype=np.float64)
    parent = frozen_base.raw_predictions(x)
    retained = frozen_base.raw_predictions(protected)
    physical = frozen_base.movement_success_components(x,_validated_base_raw=parent)['bounded_physical_prior']
    y = np.asarray([r.target_success for r in rows],dtype=np.float64)
    features = np.concatenate((x,protected))
    targets = np.zeros((len(features),9));targets[:len(rows),0]=y-physical
    weights = np.concatenate((np.ones(len(rows)),np.zeros(len(protected))))
    surrogate = SimpleNamespace(feature_version=16,feature_mean=np.zeros(width),feature_scale=frozen_base.feature_scale,
                                coefficients=np.zeros((width,9)),intercept=np.zeros(9))
    names = option_feature_names(16);columns=tuple(names.index(n)for n in preparation_feature_names())
    result = _fit_outcome_with_retained_outputs(features,targets,weights,surrogate,RIDGE,
                    tuple(range(len(rows),len(features))),protected_ids,
                    outcome_name='verified_success',feature_columns=columns)
    coefficients=result[3]
    evidence=canonical_sha256(dict(parent=frozen_base.model_sha256,rows=[r.document()for r in rows],protected_decision_sha256s=sorted(protected_ids),ridge=RIDGE))
    head=PreparationSuccessHead(tuple(float(coefficients[i,0])for i in columns),tuple(float(frozen_base.feature_scale[i])for i in columns),frozen_base.model_sha256,attestation_sha256,evidence,ids,int(y.sum()))
    candidate=replace(frozen_base,preparation_success_head=head)
    np.testing.assert_array_equal(candidate.raw_predictions(protected),retained)
    np.testing.assert_array_equal(candidate.raw_predictions(x)[:,1:],parent[:,1:])
    before=np.clip(parent[:,0],0,1);after=np.clip(candidate.raw_predictions(x)[:,0],0,1)
    return candidate,dict(passed=True,fits=1,rows=len(rows),successes=int(y.sum()),failures=int(len(y)-y.sum()),
             parent_model_sha256=frozen_base.model_sha256,candidate_model_sha256=candidate.model_sha256,
             parent_MSE=float(np.mean((before-y)**2)),physical_prior_MSE=float(np.mean((physical-y)**2)),
             candidate_MSE=float(np.mean((after-y)**2)),before=before.tolist(),after=after.tolist(),
             physical_prior=physical.tolist(),retained_rows=len(protected),retained_outputs_bitwise_equal=True,
             other_outcomes_bitwise_equal=True,core_parameters_unchanged=True,retained_solver=dict(result[-1], feature_group='preparation-only', reused_legacy_solver=True),
             native_admission_by_caller=True,native_benefit_verified=False,live_policy_adopted=False)
