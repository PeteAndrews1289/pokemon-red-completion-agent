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
    if current['source_state_sha256']!=baseline['source_state_sha256']:
        raise ValueError('checkpoint or fresh splits require the same initial physical state')
    if current['scope']=='fresh_start' and not all(d.get('fresh_origin_authenticated') is True for d in (current,baseline)):
        raise ValueError('fresh comparison requires authenticated power-on origins')
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
            omitted=[key for key,value in phases.items() if value is None]
            if omitted:
                # The executor explicitly records an uncalled verifier as null
                # after an execution error. This is not an unknown elapsed phase.
                if not (omitted == ['verification'] and outcome.get('failure_phase') == 'execution'
                        and outcome.get('error_type') and outcome.get('verification') is None):
                    raise ValueError('unknown unmeasured phase clocks')
                tracker.header.setdefault('unexecuted_phases',[]).append(dict(
                    step=str(step.relative_to(root)),phase='verification',reason='execution_error_before_verifier'))
            values=[value for value in phases.values() if value is not None]
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
    return with_badge_count_splits(tracker.document())


def merge_native_segment_splits(documents):
    """Join small passive receipts only across exact physical-state boundaries.

    Wall time is summed active native segment time; driver gaps and pauses are
    excluded explicitly. No outcomes are rescanned and no emulator is observed.
    """
    docs=list(documents)
    if not docs: raise ValueError("no native split receipts")
    result=deepcopy(docs[0]);offset={k:0 for k in ("frames","actions","wall_seconds")}
    rows={r["id"]:r for r in result["rows"]};last_state=None;last_split=None
    fields=("schema","catalog_sha256","scope","required_species_sha256","required_species_count","wall_basis")
    for index,doc in enumerate(docs):
        if any(doc.get(k)!=docs[0].get(k) for k in fields) or doc.get("wall_basis")!="native_session_wall":
            raise ValueError("native segment split contracts differ")
        if index and doc.get("source_state_sha256")!=last_state:
            raise ValueError("native split segment state chain differs")
        elapsed=_clock(**doc["elapsed"])
        if {r["id"] for r in doc["rows"]}!=set(rows): raise ValueError("native split catalogs differ")
        for row in doc["rows"]:
            prior=rows[row["id"]]
            if row["status"]=="reached":
                if index and prior["status"]!="pending": raise ValueError("native milestone reached twice")
                value=deepcopy(row)
                for key in ("elapsed",): value[key]={k:offset[k]+row[key][k] for k in offset}
                value["interval"]={bound:{k:offset[k]+row["interval"][bound][k]for k in offset}for bound in ("lower","upper")}
                rows[row["id"]]=value
            elif index and row["status"]=="already_completed" and prior["status"]=="pending":
                raise ValueError("native milestone timing missing between segments")
        last_state=doc.get("last_observation_state_sha256")
        offset={k:offset[k]+elapsed[k]for k in offset}
    reached=sorted((r for r in rows.values()if r["status"]=="reached"),key=lambda r:(r["elapsed"]["frames"],r["elapsed"]["actions"],r["elapsed"]["wall_seconds"]))
    from itertools import groupby
    for _,group in groupby(reached,key=lambda r:tuple(r["elapsed"][k]for k in offset)):
        simultaneous=list(group)
        prior=last_split or {k:0 for k in offset}
        for row in simultaneous:
            row["segment"]={k:row["elapsed"][k]-prior[k]for k in offset}
        last_split=dict(simultaneous[0]["elapsed"])
    result.update(rows=list(rows.values()),elapsed=offset,wall_basis="sum_native_segment_wall",
                  segment_count=len(docs),last_observation_state_sha256=last_state,
                  initial_clock=None,last_clock=None)
    return with_badge_count_splits(result)


_BADGE_LABELS = {
    'defeat_brock':'Brock · Boulder Badge','defeat_misty':'Misty · Cascade Badge',
    'defeat_surge':'Lt. Surge · Thunder Badge','defeat_erika':'Erika · Rainbow Badge',
    'defeat_koga':'Koga · Soul Badge','defeat_sabrina':'Sabrina · Marsh Badge',
    'defeat_blaine':'Blaine · Volcano Badge','defeat_giovanni':'Giovanni · Earth Badge',
}
_BADGE_COUNTS = tuple((f'badges_{n}',f'Badge {n} earned') for n in range(1,9))
_DISPLAY_CATALOG = _BADGE_COUNTS + tuple((key,_BADGE_LABELS.get(key,label))for key,label in CATALOG)
_DISPLAY_SHA256 = hashlib.sha256(json.dumps(_DISPLAY_CATALOG,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def with_badge_count_splits(document):
    """Show actual badge-count order independently of gym identity/order.

    This is a pure presentation/export projection of the existing named-badge
    receipts. It neither changes the frozen native recorder nor invents an
    ordering between badges confirmed in the same observation interval.
    """
    if document.get('catalog_sha256') == _DISPLAY_SHA256:return deepcopy(document)
    if document.get('catalog_sha256') != CATALOG_SHA256:raise ValueError('unknown native split catalog')
    doc=deepcopy(document);by_id={r['id']:r for r in doc['rows']}
    badges=[by_id[key]for key in _BADGE_LABELS]
    counts={key:dict(id=key,label=label,status='pending')for key,label in _BADGE_COUNTS}
    initial=sum(row['status']=='already_completed'for row in badges)
    for n in range(1,initial+1):counts[f'badges_{n}'].update(status='already_completed',elapsed=None,interval=None,segment=None)
    from itertools import groupby
    reached=sorted((row for row in badges if row['status']=='reached'),key=lambda r:tuple(r['elapsed'][k]for k in ('frames','actions','wall_seconds')))
    count=initial
    for _,group in groupby(reached,key=lambda r:tuple(r['elapsed'][k]for k in ('frames','actions','wall_seconds'))):
        simultaneous=list(group)
        for _ in simultaneous:
            count+=1;key=f'badges_{count}'
            value=deepcopy(simultaneous[0]);value.update(id=key,label=counts[key]['label'],derived_from_badges=[r['id']for r in simultaneous]);counts[key]=value
    for key,label in _BADGE_LABELS.items():by_id[key]['label']=label
    doc.update(base_catalog_sha256=CATALOG_SHA256,catalog_sha256=_DISPLAY_SHA256,
               rows=[counts[key]for key,_ in _BADGE_COUNTS]+list(by_id.values()),
               badge_count_is_observed_order=True)
    return doc


def pending_milestone_splits(required_species):
    """Presentation only: no game has started and no measurement is claimed."""
    doc=MilestoneSplits(source_state_sha256=None,required_species=required_species).document()
    doc.update(scope='not_started',timing_started=False,presentation_only=True)
    return with_badge_count_splits(doc)


def attach_split_reference(metadata,reference):
    """Compare compatible recorded clocks; a live reference is never a speed winner."""
    result=deepcopy(metadata)
    current,baseline=result.get('milestone_splits'),reference.get('milestone_splits')
    if not current or not baseline or current.get('timing_started')is False or baseline.get('timing_started')is False:return result
    try:
        comparison=compare_splits(current,baseline)
    except ValueError as error:
        result['milestone_split_comparison_error']=str(error)
        return result
    comparison.update(reference_label=reference.get('id','Reference run'),reference_role='live_reference',completed_baseline=False)
    current['comparison']=comparison
    return result

def fresh_start_split_projection(root,document):
    """Add authenticated opening costs to passive native-window measurements."""
    root=Path(root);plan=json.loads((root/'PLAN.json').read_bytes())
    if plan.get('schema')!='pokemon.red.fresh-frozen-player-plan.v1' or document.get('timing_started')is False:return deepcopy(document)
    claim=json.loads((root/'CLAIM.json').read_bytes())
    context=json.loads((root/'initial/CONTEXT.json').read_bytes())
    initial=json.loads((root/'initial/RESULT.json').read_bytes())
    configuration=json.loads((root/'REALIZED-CONFIGURATION.json').read_bytes())
    terminal=root/'RESULT.json'
    if terminal.exists() and json.loads(terminal.read_bytes()).get('state_loads')!=0:raise ValueError('fresh timing source has a state restoration')
    def digest(path):
        if path.is_symlink()or not path.resolve().is_relative_to(root.resolve()):raise ValueError('fresh timing source escaped its root')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    origin=digest(root/'bootstrap/power-on.state');checkpoint=digest(root/'initial/terminal.state')
    if (plan.get('maximum_state_loads')!=0 or claim.get('no_resume')is not True
            or claim.get('started_new_attempt')is not True or initial.get('passed')is not True
            or origin!=configuration.get('origin_sha256') or checkpoint!=context.get('state_sha256')
            or checkpoint!=initial.get('state_sha256') or document.get('source_state_sha256')!=checkpoint
            or initial.get('spent')!=context.get('spent')):
        raise ValueError('fresh split origin or opening custody differs')
    spent=context['spent'];prefix=_clock(frames=spent['frames'],actions=spent['actions'],wall_seconds=spent['seconds'])
    doc=deepcopy(document);zero={k:0 for k in prefix}
    for row in doc['rows']:
        if row['status']=='reached':
            row['elapsed']={k:row['elapsed'][k]+prefix[k]for k in prefix}
            row['interval']={bound:{k:row['interval'][bound][k]+prefix[k]for k in prefix}for bound in ('lower','upper')}
        elif row['status']=='already_completed':
            row.update(status='reached',elapsed=dict(prefix),interval=dict(lower=dict(zero),upper=dict(prefix)),observation_state_sha256=checkpoint,confirmation='verified_opening_boundary')
    doc.update(scope='fresh_start',source_state_sha256=origin,initial_native_state_sha256=checkpoint,
               elapsed={k:doc['elapsed'][k]+prefix[k]for k in prefix},opening_cost=prefix,
               base_wall_basis=document['wall_basis'],wall_basis='opening_plus_'+document['wall_basis'],
               identity=dict(doc.get('identity')or{},campaign_run_id=plan.get('campaign_run_id')or configuration['origin_id']),
               fresh_origin_authenticated=True,restoration_disclosed=False)
    _recompute_split_segments(doc)
    return doc


def _recompute_split_segments(doc):
    from itertools import groupby
    keys=('frames','actions','wall_seconds');prior=dict.fromkeys(keys,0)
    reached=sorted((r for r in doc['rows']if r['status']=='reached'),key=lambda r:tuple(r['elapsed'][k]for k in keys))
    for _,group in groupby(reached,key=lambda r:tuple(r['elapsed'][k]for k in keys)):
        rows=list(group)
        for row in rows:row['segment']={k:row['elapsed'][k]-prior[k]for k in keys}
        prior=dict(rows[0]['elapsed'])


def extend_split_history(current,prefix,*,campaign_run_id):
    """Carry one campaign's measured history across its declared repair boundary."""
    if not campaign_run_id or any((d.get('identity')or{}).get('campaign_run_id')!=campaign_run_id for d in (current,prefix)):
        raise ValueError('split prefix belongs to a different campaign')
    if current.get('source_state_sha256')!=prefix.get('last_observation_state_sha256'):
        raise ValueError('split prefix physical state chain differs')
    for key in ('schema','catalog_sha256','required_species_sha256'):
        if current.get(key)!=prefix.get(key):raise ValueError('split prefix contracts differ')
    basis=prefix.get('base_wall_basis',prefix.get('wall_basis'))
    if current.get('wall_basis')!=basis:raise ValueError('split prefix clock basis differs')
    result=deepcopy(prefix);old={r['id']:r for r in result['rows']};offset=prefix['elapsed']
    for row in current['rows']:
        previous=old[row['id']]
        if previous['status']!='pending':continue
        if row['status']=='already_completed':raise ValueError('unmeasured milestone between split histories')
        if row['status']=='reached':
            value=deepcopy(row);value['elapsed']={k:row['elapsed'][k]+offset[k]for k in offset}
            value['interval']={bound:{k:row['interval'][bound][k]+offset[k]for k in offset}for bound in ('lower','upper')};old[row['id']]=value
    result.update(rows=list(old.values()),elapsed={k:offset[k]+current['elapsed'][k]for k in offset},
                  last_observation_state_sha256=current.get('last_observation_state_sha256'),
                  restoration_disclosed=True,history_prefixes=prefix.get('history_prefixes',0)+1)
    _recompute_split_segments(result)
    return result
