"""Explicit League-only learned component binding; original recipe remains default."""
import hashlib,json
from pathlib import Path
import numpy as np
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_practice_features import OBSERVED_PP_SWITCH_SCHEMA,OBSERVED_PP_SWITCH_NAMES
from .red_trainer_proposed_control import OBSERVED_COMPONENT_CONTROL_SCHEMA,OBSERVED_COMPONENT_CONTROL_NAMES
PARENT_DIGEST='111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2'
def load_observed_league_components(work_order,default_path,default_sha256):
    document=json.loads(work_order)
    declaration=declared_observed_league_components(document)
    path=Path(default_path);pin=default_sha256
    if declaration is None:return path,pin
    if set(declaration)!={'mode','model','fit_receipt'} or declaration['mode']!='observed_components_v3':raise ValueError('unsupported observed League component recipe')
    def read_ref(ref):
        if set(ref)!={'path','sha256'}:raise ValueError('component reference differs')
        payload=Path(ref['path']).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=ref['sha256']:raise ValueError('component digest differs')
        return json.loads(payload)
    receipt=read_ref(declaration['fit_receipt']);model_doc=read_ref(declaration['model'])
    if not(receipt.get('passed') is True and receipt.get('no_DEV_fit') is True and receipt.get('only_new_input_rows_updated') is True and receipt.get('old_parameters_bit_identical') is True and receipt['candidate']['sha256']==declaration['model']['sha256'] and receipt['original_parent']['sha256']==PARENT_DIGEST):raise ValueError('component learning receipt differs')
    if pin!=PARENT_DIGEST or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:raise ValueError('component parent differs')
    parent=TrainerPracticeThreeHeadModel.from_dict(json.loads(path.read_bytes()));candidate=TrainerPracticeThreeHeadModel.from_dict(model_doc)
    if candidate.control.schema_id!=OBSERVED_COMPONENT_CONTROL_SCHEMA or candidate.control.feature_names!=OBSERVED_COMPONENT_CONTROL_NAMES or candidate.switch.schema_id!=OBSERVED_PP_SWITCH_SCHEMA or candidate.switch.feature_names!=OBSERVED_PP_SWITCH_NAMES:raise ValueError('component schemas differ')
    for before,after in ((parent.control,candidate.control),(parent.switch,candidate.switch)):
        index={n:i for i,n in enumerate(after.feature_names)}
        if not all(np.array_equal(before.weights1[i].view(np.uint64),after.weights1[index[n]].view(np.uint64))for i,n in enumerate(before.feature_names)):raise ValueError('original component input weights changed')
        if not(np.array_equal(before.bias1.view(np.uint64),after.bias1.view(np.uint64))and np.array_equal(before.weights2.view(np.uint64),after.weights2.view(np.uint64))):raise ValueError('original component output weights changed')
    if parent.move.to_dict()!=candidate.move.to_dict() or (parent.damage_reference.to_dict()if parent.damage_reference else None)!=(candidate.damage_reference.to_dict()if candidate.damage_reference else None):raise ValueError('unrelated learned head changed')
    return Path(declaration['model']['path']),declaration['model']['sha256']

def declared_observed_league_components(document):
    declaration=document.get('observed_league_components')
    if declaration is None:return None
    if document.get('partition')!='development' or type(declaration)is not dict or set(declaration)!={'mode','model','fit_receipt'} or declaration['mode']!='observed_components_v3':raise ValueError('unsupported observed League component recipe')
    for key in ['model','fit_receipt']:
        ref=declaration[key]
        if type(ref)is not dict or set(ref)!={'path','sha256'}or not isinstance(ref['path'],str)or not isinstance(ref['sha256'],str)or len(ref['sha256'])!=64:raise ValueError('component reference differs')
    return dict(declaration)
