from pathlib import Path
from dataclasses import asdict,replace
from hashlib import sha256
import json
import pytest
from test_scoped_production_story_train import setup
from pokemon_red_completion.red_production_train_admission import ScopedProductionStoryAdmission
from pokemon_red_completion.red_scoped_train_composition import ScopedTrainComposition
from pokemon_red_completion.provenance import canonical_sha256

@pytest.mark.parametrize('objective',['defeat_blaine','defeat_giovanni','obtain_strength'])
def test_finite_late_contract_requires_bound_production_witness(tmp_path,monkeypatch,objective):
    kw,work,digest=setup(tmp_path,monkeypatch)
    old=kw['contracts'];contracts=tuple(replace(c,objective_id=objective)for c in old)
    work['production_story_routes']={canonical_sha256(asdict(c)):work['production_story_routes'][canonical_sha256(asdict(o))]for o,c in zip(old,contracts)}
    kw['contracts']=contracts;kw['work_order_bytes']=json.dumps(work).encode();kw['source']['experiment_sha256']=sha256(kw['work_order_bytes']).hexdigest()
    admission=ScopedProductionStoryAdmission.authenticate(**kw);d=admission.document()
    args=(d['source_state_sha256'],d['source_origin_sha256'],d['source_commit'],d['context_sha256'],d['work_order_sha256'],tmp_path/'native.json',contracts)
    with pytest.raises(ValueError):ScopedTrainComposition(*args,include_silph=True)
    spec=ScopedTrainComposition(*args,include_silph=True,production_story_admission=admission)
    assert spec.contracts==contracts
    with pytest.raises(ValueError):replace(spec,work_order_sha256='f'*64)
    with pytest.raises(ValueError):replace(spec,contracts=tuple(replace(c,objective_id='defeat_lance')for c in contracts))
