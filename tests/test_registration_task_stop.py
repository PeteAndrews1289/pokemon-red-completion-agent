from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.red_native_player import finish_native_registration_task
from pokemon_red_completion.player_sequence_targets import registration_task_catalog
from pokemon_red_completion.provenance import canonical_sha256

def fixture(owned,safe=True):
 calls=[];reader=N(read_pokedex_state=lambda:N(owned_species=frozenset(owned)))
 session=N(runtime=N(reader=reader),finish_decision=lambda:calls.append('finish')or False,snapshot=lambda:N(safe=safe,sha256='a'*64))
 collector=N(mark_task_terminal=lambda **kwargs:calls.append(kwargs))
 return session,collector,calls

def test_no_new_native_registration_does_not_stop_or_mark():
 s,c,calls=fixture({7});assert finish_native_registration_task(s,c,initial_owned=frozenset({7}),task_sha256='b'*64)is False;assert calls==['finish']

def test_actual_new_native_registration_marks_exact_safe_boundary():
 s,c,calls=fixture({7,16});assert finish_native_registration_task(s,c,initial_owned=frozenset({7}),task_sha256='b'*64)is True;assert calls==['finish',dict(task_sha256='b'*64,boundary_sha256='a'*64)]

def test_unsafe_boundary_never_marks_completion():
 s,c,calls=fixture({7,16},False)
 with pytest.raises(ValueError):finish_native_registration_task(s,c,initial_owned=frozenset({7}),task_sha256='b'*64)
 assert calls==['finish']

def test_task_identity_pins_predicate_without_private_target_species():
 d=registration_task_catalog('c'*64);assert d['task_sha256']==canonical_sha256({k:v for k,v in d.items()if k!='task_sha256'})
 assert set(d)=={'schema','rom_sha256','predicate','task_sha256'}
