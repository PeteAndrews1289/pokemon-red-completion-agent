"""Finite, observational milestone splits from already captured semantic facts.

Times are first-confirmed observation boundaries, not guessed cartridge event
frames. This module neither observes an emulator nor changes a player choice.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'pokemon.red.milestone-splits.v1'
STORY_SPLITS = (
    ('choose_starter', 'Starter chosen'), ('receive_pokedex', 'Pokédex received'),
    ('defeat_brock', 'Badge 1 · Brock'), ('help_bill', "Bill helped · SS Ticket"),
    ('defeat_misty', 'Badge 2 · Misty'), ('obtain_cut', 'Cut obtained'),
    ('defeat_surge', 'Badge 3 · Lt. Surge'), ('clear_rocket_hideout', 'Rocket Hideout cleared'),
    ('obtain_silph_scope', 'Silph Scope obtained'), ('defeat_erika', 'Badge 4 · Erika'),
    ('rescue_fuji', 'Fuji rescued · Poké Flute'), ('obtain_surf', 'Surf obtained'),
    ('defeat_koga', 'Badge 5 · Koga'), ('obtain_strength', 'Strength obtained'),
    ('liberate_silph', 'Silph liberated'), ('defeat_sabrina', 'Badge 6 · Sabrina'),
    ('obtain_secret_key', 'Secret Key obtained'), ('defeat_blaine', 'Badge 7 · Blaine'),
    ('defeat_giovanni', 'Badge 8 · Giovanni'), ('cross_victory_road', 'Victory Road crossed'),
    ('defeat_lorelei', 'Lorelei defeated'), ('defeat_bruno', 'Bruno defeated'),
    ('defeat_agatha', 'Agatha defeated'), ('defeat_lance', 'Lance defeated'),
    ('defeat_champion', 'Champion defeated'), ('enter_hall_of_fame', 'Hall of Fame'),
)
CATALOG = STORY_SPLITS + tuple((f'registrations_{n}', f'{n} route registrations') for n in (25, 50, 75, 100, 124)) + (('complete_red_124', 'Champion / Hall of Fame + route 124'),)
CATALOG_SHA256 = hashlib.sha256(json.dumps(CATALOG,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def _clock(frames, actions, wall_seconds):
    if (type(frames) is not int or frames < 0 or type(actions) is not int or actions < 0
            or type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds) or wall_seconds < 0):
        raise ValueError('split clocks must be finite nonnegative measured values')
    return dict(frames=frames, actions=actions, wall_seconds=float(wall_seconds))


class MilestoneSplits:
    """No policy input: first-hit splits, with missing ancestry left unknown."""
    def __init__(self, *, source_state_sha256, required_species=(), scope='checkpoint',
                 wall_basis='native_session_wall', identity=None):
        if scope not in ('checkpoint', 'fresh_start'):
            raise ValueError('declare a checkpoint or authenticated fresh-start timing scope')
        required = tuple(sorted(required_species))
        if len(set(required)) != len(required) or any(type(x) is not str or not x for x in required):
            raise ValueError('split registration target must contain distinct species')
        self.required = frozenset(required)
        self.header = dict(schema=SCHEMA,catalog_sha256=CATALOG_SHA256,scope=scope,
            source_state_sha256=source_state_sha256,required_species_sha256=hashlib.sha256(
                json.dumps(required,separators=(',',':')).encode()).hexdigest(),required_species_count=len(required),
            wall_basis=wall_basis,observation_resolution='first_confirmed_boundary',
            identity=deepcopy(identity or {}),does_not_authorize_completion=True)
        self.initial = None
        self.last = None
        self.last_state_sha256 = None
        self.rows = {key: dict(id=key,label=label,status='pending') for key,label in CATALOG}
        self.last_split = None

    def _reached(self, facts):
        completed, owned = facts.get('completed_objectives'), facts.get('owned_species')
        if (not isinstance(completed,(list,tuple)) or not isinstance(owned,(list,tuple))
                or any(type(x) is not str for x in (*completed,*owned))):
            raise ValueError('milestone facts require observed objectives and registered species')
        result = set(completed) & {key for key,_ in STORY_SPLITS}
        route_count = len(self.required & set(owned))
        result.update(f'registrations_{n}' for n in (25,50,75,100,124) if len(self.required)>=n and route_count>=n)
        if len(self.required)==124 and self.required<=set(owned) and {'defeat_champion','enter_hall_of_fame'}<=set(completed):
            result.add('complete_red_124')
        return result

    def observe(self, facts, *, frames, actions, wall_seconds, state_sha256=None):
        measured = _clock(frames,actions,wall_seconds)
        if self.last is not None and any(measured[k]<self.last[k] for k in measured):
            raise ValueError('split clock went backwards; start a new declared timing scope')
        reached = self._reached(facts)
        changed = self.initial is None
        if self.initial is None:
            self.initial = measured
            for key in reached:
                self.rows[key].update(status='already_completed',elapsed=None,interval=None,segment=None)
        else:
            elapsed = {k:measured[k]-self.initial[k] for k in measured}
            lower = {k:self.last[k]-self.initial[k] for k in measured}
            prior = self.last_split or {k:0 for k in measured}
            for key,_ in CATALOG:
                if key in reached and self.rows[key]['status']=='pending':
                    self.rows[key].update(status='reached',elapsed=dict(elapsed),
                        interval=dict(lower=dict(lower),upper=dict(elapsed)),
                        segment={k:elapsed[k]-prior[k] for k in measured},
                        observation_state_sha256=state_sha256)
                    changed=True
            if changed:self.last_split=dict(elapsed)
        self.last=measured
        self.last_state_sha256=state_sha256
        return changed

    def document(self):
        elapsed = None if self.initial is None else {k:self.last[k]-self.initial[k] for k in self.last}
        return deepcopy(dict(self.header,rows=list(self.rows.values()),elapsed=elapsed,
            initial_clock=self.initial,last_clock=self.last,last_observation_state_sha256=self.last_state_sha256))

    def write(self, path):
        path=Path(path);temporary=path.with_name(path.name+'.new')
        temporary.write_text(json.dumps(self.document(),indent=2,sort_keys=True)+'\n')
        temporary.replace(path)


def compare_splits(current, baseline):
    """Descriptive comparison only; a short failed run is never a speed winner."""
    for name in ('schema','catalog_sha256','scope','required_species_sha256','wall_basis'):
        if current.get(name)!=baseline.get(name):raise ValueError('split comparison differs: '+name)
    if current['scope']=='checkpoint' and current['source_state_sha256']!=baseline['source_state_sha256']:
        raise ValueError('checkpoint splits require the same initial physical state')
    old={r['id']:r for r in baseline['rows']};rows=[]
    for row in current['rows']:
        other=old[row['id']];a,b=row.get('elapsed'),other.get('elapsed')
        delta={k:a[k]-b[k] for k in a} if row['status']==other['status']=='reached' else None
        rows.append(dict(id=row['id'],label=row['label'],status=row['status'],baseline_status=other['status'],delta=delta))
    return dict(schema='pokemon.red.milestone-split-comparison.v1',rows=rows,completion_or_fitness_claim=False)


def recorded_case_splits(root, *, required_species):
    """Replay durable outcome facts one file at a time, with explicit clock scope.

    Historical wall timings are sums of recorded goal phases. Startup, gaps and
    pauses are not invented; future live reports carry native-session wall time.
    """
    root=Path(root);segments=sorted((root/'runs').glob('segment-*')) if (root/'runs').exists() else [root]
    tracker=None;offset_frames=offset_actions=0;wall=0.0
    for segment in segments:
        steps=sorted((segment/'native/episode').glob('step-*'))
        last_frames=last_actions=0
        for step in steps:
            p=step/'outcome.json'
            if not p.exists():continue
            outcome=json.loads(p.read_bytes());before,after=outcome.get('before'),outcome.get('after')
            if not isinstance(before,dict) or not isinstance(after,dict):continue
            if tracker is None:
                tracker=MilestoneSplits(source_state_sha256=outcome['before_state_sha256'],
                    required_species=required_species,wall_basis='sum_recorded_goal_phases',identity=dict(run_id=root.name))
                tracker.observe(before,frames=before['frames'],actions=before['actions'],wall_seconds=wall,
                    state_sha256=outcome['before_state_sha256'])
            phases=outcome.get('phase_seconds')
            if not isinstance(phases,dict) or not phases:raise ValueError('missing phase clocks; wall split is unknown')
            values=list(phases.values())
            if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in values):
                raise ValueError('invalid phase clocks')
            wall+=sum(values)
            tracker.observe(after,frames=offset_frames+after['frames'],actions=offset_actions+after['actions'],
                wall_seconds=wall,state_sha256=outcome['terminal_state_sha256'])
            last_frames,last_actions=after['frames'],after['actions']
        costs=segment/'native/native-costs.json'
        if costs.exists():
            meter=json.loads(costs.read_bytes());last_frames=max(last_frames,meter['frames']);last_actions=max(last_actions,meter['actions_attempted'])
        offset_frames+=last_frames;offset_actions+=last_actions
    if tracker is None:raise ValueError('no complete measured outcome boundaries')
    return tracker.document()
