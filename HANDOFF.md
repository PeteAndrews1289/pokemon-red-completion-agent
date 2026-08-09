# Handoff

Written 2026-08-07 for the agent taking over. Read this once, completely, before touching anything.
It is meant to make you *actually* oriented, not politely briefed — which means most of it is about
what is wrong, what is unproven, and what this codebase has repeatedly fooled people into believing.

Then read, in order: [MISSION.md](MISSION.md) (why the project exists),
[AGENT_COORDINATION.md](AGENT_COORDINATION.md) (rules and lanes), and
[docs/story.md](docs/story.md) (the narrative, which doubles as a record of the failure modes).

**How to read this document.** Dated checkpoint sections accumulate at the top, newest first, and
supersede anything older that disagrees with them. Sections 1 through 10 below are the durable
orientation. If a number in a numbered section disagrees with a dated checkpoint above it, the
checkpoint wins — and the numbered section is a bug worth fixing, because "what is actually true"
going stale is exactly the failure this project keeps having.

## Superseding current checkpoint — 2026-08-09

This section supersedes every older “next” statement below.

**Late audit and runtime checkpoint:** the full repository gate now passes **2,167 tests with 3
integration tests deselected and 1 expected failure**, plus Ruff, mypy, documentation,
public-artifact, and regenerated source-registry checks. The audit repaired three silent contract
errors before the next emulator run: Red and Blue now derive reciprocal eleven-species version gaps
from one canonical Generation I table (including Pinsir and Scyther), campaigns require explicit
compatible `TradeLink` edges rather than treating any two saves as trade partners, and conditional
encounter bands now participate in live trainee/venue projection and exact ephemeral binding.

The exact switch-target head now has the missing runtime seam. Artifact
`red-battle-switch-target-model-28a63094f845403bb5254fc4bc3ec449` is complete with manifest
`6ec25dd…`; its canonical model payload is the frozen `bd1ba4…`. A private artifact loader verifies
the typed manifest, canonical JSONL streams, feature schema, canonical model payload, disjoint
development lineages, and the separate 17/17 prospective lineage. A write-once publisher rebuilds
the frozen `bd1ba4…` payload from the original authenticated lineages and refuses a digest mismatch.
The live policy can shadow teacher targets or, in an explicitly uncounted causal trial, replace only
the reserve bound to a teacher switch request; ordinary move choice remains teacher-gated. The
portable clean-start harness accepts the authenticated target artifact, reports target confidence,
agreement, rebinding, and fallback counters, and keeps deployment authority false. Canonical shadow
seed `990009` completed Red with **13/13** target agreement, 95.66% mean confidence, and no
unavailable projection. Fresh isolated causal seed `990010` then completed all 36 objectives and
Hall of Fame in the same **45,819,749 frames** while the learned head rebound all **13/13** switch
targets with zero target fallback. This qualifies narrow target-binding authority, not teacher-free
battle control; see the [runtime qualification](docs/evidence/battle-switch-target-canonical-runtime-qualification-2026-08-09.json).

The first six-role teacher-free composition, seed `990011`, failed closed at the S.S. Anne rival
after 158 battle decisions. It had zero teacher queries/fallbacks, seven executed learned HP
recoveries, and two learned target rebindings. The chapter recognized the eighth complete semantic
recovery request, then incorrectly required its teacher-only Python exception subclass. The repair
accepts only learned HP recovery for the executable lead, chooses from the same bounded item
inventory, and retains exact HP/item/menu proofs; a non-lead request still fails closed. Fresh seed
`990012` qualified that repair, then failed later at the pre-Mart Route 11 supply Gambler. Lavender
had advertised HP, sleep, and paralysis recovery even though this battle declared zero HP uses and
only the protected final status-item copies existed. The executor correctly refused to spend the
reserve; the static intent mask was wrong. Recovery capabilities now recompute before every runtime
dispatch from live inventory, protected floors, and remaining HP allowance. Seed `990013`
qualified both earlier repairs and defeated Lorelei after 3,265 teacher-free battle decisions,
13/13 learned target bindings, 64,337 training-control decisions, and 125,800 trainee/venue
decisions. Lorelei's verifier rejected attacks issued at 59 HP beneath its declared 70-HP floor.
The repair expresses that floor in `BattleIntent`, ranks only executable high-level affordances,
and upgrades the clean-start report so every requested learned role must prove live authority.
Commit `e00f083` passed the full gate and GitHub CI. Fresh seed `990014` then defeated Lorelei,
Bruno, and Agatha and reached Lance's room after 3,286 battle decisions. High-level execution made
51 typed requests with zero teacher, safety, or low-confidence fallback; live affordance masks
accounted for 19 decisions. The target model owned 21/21 bindings with no fallback, training control
owned all 64,337 choices with zero operational error, and trainee/venue selection owned all 125,800
choices at 99.79% agreement.

The run still failed closed. Agatha's independent turn trace had already proved every Dugtrio and
Jolteon curriculum role, the event was set, the party was healed, and Lance's room loaded. Its
switch receipt nevertheless required *every* learned autonomous pivot to equal the fixed teacher's
preferred specialist; one legal Golbat pivot to party slot 0 therefore invalidated an otherwise
complete receipt. The repair keeps exact opponent identity/position and target-slot/party-identity
proofs while leaving specialist strategy to the existing turn-level lesson. Regenerate, validate,
commit, and push completed at `93beb1b`. Fresh canonical seed `990015` then completed all 36
objectives and Hall of Fame in 50,997,251 frames with the exact six-role stack, 3,315 battle
decisions, 21/21 target rebindings, both training heads in live control, and zero teacher query or
fallback. The paired derived-timing root `990016` failed before a learned battle decision: the
lab-rival battle was won, but the old verifier required exactly 21 max HP while the legal perturbed
starter had 23, and its 56-pulse cap stopped before the post-win script released controls. The
reproduced run reached script 18 with battle result zero, the event set, and 23/23 HP under a larger
bounded cap. The repair accepts only the legal 21–23 level-6 Squirtle range, retains every semantic
win proof, and raises the cap to 96. Regenerate, validate, commit, push, then run a fresh uncounted
perturbation. Commit `4f5f870` completed that gate. Fresh seed `990017` passed the rival, then an
ordinary Route 1 wild encounter at northbound step 2 hit the old zero-encounter movement helper.
The new helper accepts only Route 1 wild battles, flees at most eight across both crossings, and
requires result two, released controls, a living starter, the same coordinate, and exact
party/level/max-HP/PP/status preservation before resuming the already-consumed step. Commit
`883be4f` completed that gate. Fresh seed `990018` verified two wild flees, but the first ready
overworld observation was premature: immediate movement inputs were swallowed and the route ended
at Route 1 `(11,6)` rather than Viridian `(21,35)`. A direct reproduction that changed only a
120-frame post-flee stabilization reached the exact gate, then exposed the same zero-wild assumption
in Pewter's separate post-Pokédex Route 1 traversal. A shared helper now waits, rereads, and
revalidates the complete protected-state receipt before resuming, and both chapters carry bounded
flee evidence. The full 2,165-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry checks
passed and commit `d3461f0` went green in GitHub CI. Fresh seed `990019` still ended one tile short:
five stabilized flee receipts passed, but the open-loop corridor counted one north request that the
game did not consume. Direct reproduction reached Viridian with one coordinate-verified retry. The
shared traversal now requires directional coordinate progress or a map transition after every
MOVE, waits 24 frames and retries an unchanged safe boundary at most eight times, and records the
retry count. The full 2,167-test gate plus Ruff, mypy, docs, privacy, and registry checks passes;
commit, push, then use a fresh perturbation. Counted v95 remains **0/10** and `990007`
remains test-only. See the
[first failure](docs/evidence/portable-clean-start-six-role-rehearsal-01-failure-2026-08-09.json),
the [second failure](docs/evidence/portable-clean-start-six-role-rehearsal-02-failure-2026-08-09.json),
the [Lorelei failure](docs/evidence/portable-clean-start-six-role-rehearsal-03-failure-2026-08-09.json),
the [Agatha receipt failure](docs/evidence/portable-clean-start-six-role-rehearsal-04-failure-2026-08-09.json),
the [canonical qualification](docs/evidence/portable-clean-start-six-role-canonical-qualification-2026-08-09.json),
the [first perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-01-failure-2026-08-09.json),
the [second perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-02-failure-2026-08-09.json),
and the [third perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-03-failure-2026-08-09.json).
The [fourth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-04-failure-2026-08-09.json)
preserves the movement-acknowledgement counterexample.

**Branch and current code:** `agent/balanced-team-curriculum`, draft PR #8. Commit `93beb1b` is the
source of the passed canonical receipt and `4f5f870` qualified the lab-rival repair through the next
Route 1 boundary; `883be4f` qualified the first bounded-flee implementation and supplied the
source for the preserved `990018` counterexample; `d3461f0` qualified stabilized shared exits and
supplied the `990019` movement counterexample. Closed-loop step acknowledgement and its regenerated
v95 registry are the current uncommitted lane. The full local gate is green; they need a clean push
before replay. Only Codex
pushes this branch; do not create a second worktree or force-push it.

**Latest causal result:** attempt 13 ran from source `4ea7e93` with the frozen reserve-aware action
candidate. It reached checkpoint 306, passed Rock Tunnel, Lorelei, and Bruno, defeated Agatha, used
one X Special, made exactly three required role switches, made zero statused attacks, and assigned
all grounded opponents to Dugtrio. The contract still rejected the run: Golbat went to Blastoise,
Jolteon made zero attacks, and specialist coverage failed. The model owned the high-level switch
class; `best_reserve_matchup` still owned the party target. See the
[causal receipt](docs/evidence/battle-control-reserve-matchup-v3-causal-13-failure-2026-08-09.json).

**Offline target head:** `battle_switch_target.py`, `battle_switch_target_model.py`, and
`battle_switch_target_training.py` now implement identity-free candidate projection, a shared
listwise MLP, and whole-lineage authentication/evaluation. Party slots are ephemeral executor
bindings only. The head trains on lineages 01 and 03 (28 explicit targets) and validates on untouched
lineage 02 (13 targets). It fits 28/28 versus the deterministic baseline's 22/28 and validates at
11/13 (84.6%) versus 10/13 (76.9%). It still selects Blastoise on the held-out Agatha Golbat label.
The public receipt therefore says `deployment_authority: false`; do not load it into the emulator or
start another full causal replay yet.

**Target test result and exact next dependency:** the frozen development candidate uses
two hidden units, 1,000 epochs, learning rate 0.01, L2 0.003, and equal total optimization weight per
battle plan. It reached 54/54 across four opened leave-one-whole-lineage-out folds, then fit 41/41
training targets and 13/13 existing validation targets. On fresh seed `990007`, the exact frozen
model then scored **17/17** targets with 0.07965 cross-entropy versus the deterministic baseline's
**12/17**. That includes Bruno 2/2, Agatha 7/7, and every Golbat target 3/3. The lineage stopped
after defeating Agatha because the old terminal receipt undercounted two opponent-driven role
changes that happened between recorded move turns; the task-complete target prefix is authenticated
and the model was evaluated once. Commit `a5e92f0` records every executed live role switch and
verifies its target directly. Next build an authenticated target artifact and runtime binding,
shadow it, then run one fresh causal completion. The counted v95 campaign remains unopened at
**0/10**.

**Previous unopened attempt:** seed `990006` progressed cleanly through checkpoint 275 and 1,500
balanced-team wins with zero faints. Four members reached level 55 and the remaining two reached
54, but the run consumed the old 1,250-trip recovery cap before Bruno or Agatha could emit target
test rows. Its 3,118 partial battle labels are excluded from both fitting and evaluation, the
frozen target candidate was not evaluated, and the seed is retired. The 90% retreat rule remains
unchanged; the new 2,000 ceiling is finite and permits one recovery per fight across the largest
completed 1,808-battle development block. See the
[failure receipt](docs/evidence/battle-control-reserve-matchup-v3-lineage-07-failure-2026-08-09.json).

**Latest run:** seed `990007` qualified the recovery-envelope repair, completed team training,
defeated Blaine, Giovanni, Lorelei, Bruno, and Agatha, and reached 306/312. The frozen target head
passed all 17 explicit rows. The route then failed only because attack-turn records showed five
role transitions while seven valid target switches had actually executed. The failed artifact's
3,188 labels are not training data. See the
[prospective target receipt](docs/evidence/battle-switch-target-prospective-prefix-test-2026-08-09.json).

**Latest collection attempt:** fresh uncounted timing seed `990004` qualified the Route 11 repair,
completed the balanced-team curriculum at 51/52/52/55/51/51, defeated Blaine, and reached checkpoint
284. It then exposed an invalid Viridian Gym receipt assumption: Cooltrainer set 1 legally poisoned
the surviving lead while the teacher still selected the exact required move against the exact
required party. The route already visits the Center and requires full HP, clear status, and restored
PP before Giovanni. Trainer receipts now measure controlled party/move/survival outcomes and retain
the observed status trace; the explicit recovery boundary remains strict and now fails directly if
healing does not settle. Artifact `red-battle-control-7e8c4f03db294b37b92b399b01cea187` is retained
failed with 3,123 labels and must never enter fitting. Do not rerun seeds `990003` or `990004`.
The former instruction to use seed `990005` was completed by the successful lineage below. See the
[failure receipt](docs/evidence/battle-control-reserve-matchup-v3-lineage-05-failure-2026-08-09.json).

**Latest successful collection:** seed `990005` completed **312/312 checkpoints**, **36/36
objectives**, Champion, and Hall of Fame from clean power. It recorded 3,166 labels with 13 explicit
targets, completed 1,808 development battles at 60/55/55/55/55/55, and independently passed both
the Route 11 and Viridian repairs. The first frozen target head scored 11/13 on this lineage versus
the deterministic resolver's 9/13. That test was then explicitly opened as development data for
the second candidate; it is not reusable as the next unopened test. See the
[lineage receipt](docs/evidence/battle-control-reserve-matchup-v3-lineage-06-2026-08-09.json) and
[candidate receipt](docs/evidence/battle-switch-target-development-candidate-02-2026-08-09.json).

**Crystal:** do not build a full second walkthrough now. After the Red target head qualifies, add a
thin Crystal semantics/mechanics adapter and three bounded teacher tasks: one reserve-choice battle,
one local-navigation round trip, and one trainee/venue choice. Crystal needs new teacher code for
those tasks, not initially a complete route script. A commentary-light complete playthrough is
useful for the route graph, milestones, recovery points, and corner cases; it is not synchronized
behavioral-cloning data. The owner can help by supplying the video URL, exact private cartridge
revision, desired completion definition (recommended long-term target: Red at Mt. Silver), and
permission to create private local checkpoints.

**Do not blur these claims:** the action-class controller, target head, ordinary move model, typed
intent constraints, deterministic target baseline, and authored menu/route executor are separate
authorities. A win counts only for the authority actually exercised.

## Current checkpoint — 2026-08-08

This section supersedes the older starting-point and test-count notes below.

**Latest natural boundary:** clean-start orchestration and campaign accounting are implemented and
the counted v95 campaign remains unopened at **0/10**. An uncounted objective-plus-trainee/venue
baseline completed all 36 objectives through Hall of Fame with 21 selected composites, 15 automatic
effects, 114,831 controlled training choices, 400 disagreements, and no expected labels or fixed
dispatches. The strict four-model rehearsal at source `fcf2b90` then reached and defeated Lorelei
with zero teacher query or fallback, but correctly failed the chapter contract: all 19 attack turns
came from party slot 1 and the model made zero role switches. The public evidence is
[portable-clean-start-five-role-rehearsal-2026-08-08.json](docs/evidence/portable-clean-start-five-role-rehearsal-2026-08-08.json).

Two authority-boundary bugs were repaired before that result. Learned move decisions now reach the
same evidence sink as teacher decisions, and the live training retreat/PP guard executes before
either policy chooses a move. The second repair carried the party safely through the full
63/55/55/55/55/55 training curriculum, Blaine, Giovanni, Victory Road, and Lorelei. Do not move
those safety checks back into the teacher callback.

The next blocker is representational, not another route patch. Battle-control feature schema v2
describes the active battler and aggregate reserve readiness, but not reserve types, moves, or
candidate-relative matchup value; generic switch resolution likewise chooses a healthy high-level
reserve rather than the best semantic matchup. Build schema v3, matchup-aware switch targeting,
and a fresh balanced-role artifact before repeating the strict canonical rehearsal. Do not weaken
the Lorelei verifier and do not open counted roots with the old artifact.

**Implementation checkpoint:** that representation is now feature schema v3. The Red observer
records moves and PP for every party member; the shared projector compares reserves by usable move
power, type advantage, defensive resistance, health/status, and level margin without placing any
identity in the model vector. Generic switch execution binds the same best candidate, fails closed
when every reserve is below 50% HP, and reports target accuracy separately from the switch class.
The old v2 artifact now fails authentication by design. One fresh uncounted v3 lineage has completed
312/312 checkpoints and Hall of Fame with 3,112 labels: 3,068 moves, 19 recoveries, 13 boosts, and
12 switches. Eleven switches carry explicit targets. The one generic early-game switch remains a
valid class label but is excluded from target scoring; future collection binds generic requests to
an observed reserve before persistence. Fit a diagnostic candidate from this lineage, then collect
disjoint train/validation lineages before any promotion claim. See the
[lineage receipt](docs/evidence/battle-control-reserve-matchup-v3-lineage-01-2026-08-08.json) and
[design receipt](docs/evidence/battle-control-reserve-matchup-v3-design-2026-08-08.json).

That first diagnostic has now run and is rejected. It fit the training groups at 99.1% but scored
61.5% accuracy and 41.96% balanced accuracy on held-out Lorelei/Bruno groups. The original switch
resolver matched 5/11 explicit targets. Adding the omitted portable level contribution raised the
same lineage to 9/11; the remaining Bruno and Agatha disagreements expose teacher curriculum intent
that battle mechanics alone cannot always identify. Collect a perturbed second lineage from this
exact source, then use `learn control fit-lineages`; do not promote or open counted roots from the
single-lineage diagnostic. See the
[diagnostic receipt](docs/evidence/battle-control-reserve-matchup-v3-diagnostic-01-2026-08-08.json).

- The deterministic teacher remains the expert oracle: clean power-on through 312/312 semantic
  checkpoints, all 36 objectives, Champion, and Hall of Fame.
- The captured-state portable objective loop has one uninterrupted twenty-dispatch Hall-of-Fame
  proof. Nineteen objective dispatches were singletons and the mechanic skills remain authored.
- Training-control v6 passed offline, shadow, causal, and portable integration. In the final
  portable proof the authenticated model controlled all 57,548 battle/overworld training decisions;
  the skill completed 1,796 development battles and 1,074 heals, defeated Blaine, finished at
  60/55/55/55/55/55 fully healed, and fresh observation opened Giovanni. All ten integration checks
  passed with no fallback.
- V6 still does **not** prove state-dependent strategy. A candidate-set-only baseline also scores
  100%, so the 25 state features have no demonstrated incremental value.
- The completed trainee/venue replacement is the preregistered candidate ranker in
  [its promotion plan](docs/evidence/training-candidate-ranker-v1-promotion-plan-2026-08-08.json).
  It records identity-free, variable-sized choice sets, collapses repeated identical polls into
  explicit state-transition records, authenticates terminal party/faint evidence, and selects
  hyperparameters only on genuine multi-candidate train-to-train accuracy.
- That offline campaign is complete. The sealed validation lineage retained 7,030 genuine choices;
  the frozen model scored 99.9004% versus the 95.6615% shape-only baseline, with 99.7727% trainee
  and 100% venue accuracy. All roots, streams, terminal outcomes, split boundaries, and model bytes
  authenticated. The public result is in
  [the offline receipt](docs/evidence/training-candidate-ranker-v1-offline-2026-08-08.json).
- Commit `d05dbb7` adds authenticated shadow/control loading, exact ephemeral candidate binding,
  alternate trainee/venue execution, no-fallback auditing, and an offline runtime gate checker.
  The collection registry is source-bound and must always be regenerated; never hand-edit hashes.
- The preregistered shadow root passed all eight gates: 119,353 genuine choices at 99.9941%
  agreement, both choice kinds, 1,802 battles, 1,098 heals, all six at level 55, and zero faints.
- The first reserved causal root is **rejected and immutable**. It executed 15,449 authenticated
  model-authority decisions with no fallback, but exhausted the training healing budget and ended
  at 51/32/32/31/31/31. The model agreed with every teacher candidate label before termination, so
  it did not create the required causal disagreement. The public receipt is
  [here](docs/evidence/training-candidate-ranker-v1-runtime-rejection-2026-08-08.json).
- The runtime gate checker now writes an authenticated rejection for a failed-but-valid runtime
  chain instead of crashing before evidence output.
- The same-root teacher-only diagnostic completed normally at all six level 55, proving the model
  had not caused the stop. It exposed a wrapper bug: the mere presence of an agreeing authority
  callback recomputed the downstream directive. Commit `a089988` makes candidate agreement a
  behavioral no-op and adds a ROM-free invariant test.
- A newly preregistered byte-distinct root then passed every causal gate with the unchanged model:
  **119,668 controlled choices, 191 executed trainee disagreements, 1,803 battles, 1,114 heals,
  all six at level 55, zero faints, and no fallback**. The authenticated gate evaluation passed
  8/8 shadow and 11/11 causal checks. See the
  [runtime qualification](docs/evidence/training-candidate-ranker-v1-runtime-qualification-2026-08-08.json).
- `replay_selected_objective.py` now accepts an authenticated candidate model in shadow or live
  authority mode and threads it through `DefeatBlaineObjectiveSkill`.
- The live portable qualification passed. The objective model dispatched the singleton
  `defeat_blaine`; the strategic model controlled **114,831** candidate choices with **400 executed
  disagreements** and no fallback; the fixed skill completed 1,803 development battles / 1,048
  heals and returned a fully healed 60/55/55/55/55/55 party. Fresh observation added the Volcano
  Badge and opened Giovanni. See the
  [portable receipt](docs/evidence/training-candidate-ranker-v1-portable-qualification-2026-08-08.json).
- The clean-power `play` path now accepts the same exact-hash trainee/venue model in shadow or live
  authority mode, threads it through both party-development passes, records controlled decisions
  and fallback status, and fails completion when requested authority never executes. Its uncounted
  rehearsal passed **312/312 checkpoints, 36/36 objectives, and Hall of Fame** with 114,831
  controlled choices, 400 executed disagreements, zero fallback, and a fully healed
  60/55/55/55/55/55 party. See the
  [rehearsal receipt](docs/evidence/training-candidate-ranker-v1-clean-power-rehearsal-2026-08-08.json).

The immediate dependency order is now: add portable reserve matchup observations → make switch
targeting matchup-aware → collect and train a balanced-role battle-control artifact → pass offline
and counterfactual role gates → pass one strict canonical rehearsal → repair the exposed
perturbation failures → freeze and open the 8/10 campaign. Crystal and learned navigation follow
that stable Red benchmark.

The first two arrows are implemented ROM-free. The collection and training arrow is now active.
Crystal begins as the bounded [transfer benchmark](docs/crystal-transfer-benchmark.md), not as a
second complete teacher route.

Do **not** open the ten counted clean-start roots yet. The updated
[readiness audit](docs/evidence/clean-start-learned-stack-readiness-audit-2026-08-08.json) records
the former orchestration, expected-label, and series-provenance blockers as resolved. The current
blocker is the old battle-control artifact's inability to observe and target useful reserve
matchups, followed by three exposed timing-perturbation failures. The infrastructure is ready; the
model stack is not.

PR #8 is still intentionally draft and cleanly mergeable, but it now represents the whole
accumulated project: more than 650 commits / 620 changed files versus `main`. Do not force-push or attempt a
history rewrite. After Peter reviews the final audit, the safe integration path is a GitHub squash
merge, followed immediately by a new short-lived branch and a full post-merge gate. No merge was
performed during this handoff.

---

## 1. What this project is for

**Build a model that can actually play Pokémon, and fill a living Pokédex across the mainline
titles.** Not "beat Red reliably." The Pokédex is the forcing function: it is the constraint that
makes route tricks useless and real decisions necessary.

The deterministic teacher exists to *produce demonstrations a model can learn from*. Its value is
therefore measured by how many real decisions its demonstrations contain — not by whether it wins.
A run that wins with one overleveled Pokémon sweeping is a run that teaches nothing, and that is the
condition the current work is trying to escape.

Keep this in view. It is easy — I did it repeatedly — to spend a day on menu plumbing and lose track
of whether it serves this.

---

## 2. What is actually true, as of this handoff

**Working and verified:**

- The deterministic teacher completes Red repeatedly, with genuine Champion and Hall-of-Fame
  evidence in the same run.
- A trained model has *selected* and completed twenty consecutive objectives from an authenticated
  Celadon capture through the Hall of Fame, in one closed loop with no expected labels, fallbacks or
  replans. Fixed skills still execute navigation, battles, menus and recovery, and only one of those
  twenty decisions had more than one executable candidate — so this is objective selection under
  light branching, not autonomous play. A separate, older result is that a model authorizes all 36
  expected objectives with zero fallbacks while fixed code selects and executes them
  (`model_authorized_fixed_specialists`). Keep the two claims apart.
- Encounter bands for five areas are measured with sample counts and reproduce exactly across runs
  (the route is deterministic).
- A clean-power teacher run reaches its readiness gate at **60/55/55/55/55/55** with zero faints and
  completes the game — 312/312 checkpoints, 36/36 objectives, Champion and Hall of Fame, over 1,808
  development battles, consuming **no counted campaign root**. When this handoff was first written
  the training block had never reached the level floor in a full run; it now does.
- A party member too weak for where the run happens to be is now routed to a venue that suits it,
  travels there, and gains levels. This is new as of 2026-08-07 and is the mechanism everything
  downstream depends on.
- A clean-power, uninterrupted run now completes the entire development curriculum and the game in
  the same process: 312/312 checkpoints, 36/36 objectives, Champion defeated, and Hall of Fame
  entered. The curriculum used 1,716 battles and 885 heals and passed with a final-form party at
  levels 60/55/55/55/55/55.
- Whole-League instrumentation first recorded 49/49 attack decisions from party slot 1. Three
  matchup-aware lessons now create real roles: Jolteon handles Lorelei's Water core, Hitmonlee
  attacks Bruno's opening Onix, and Agatha is split between Jolteon's Thunder against Golbat and
  Dugtrio's Earthquake against her four grounded Poison targets. A clean-power completion records
  `[24, 0, 4, 0, 5, 1]`: 4/6 League participants and 70.59% busiest share overall. Agatha alone is
  `[0, 0, 4, 0, 2, 0]`, 66.67% busiest share, with all five opponent positions, three switches,
  and full-party recovery verified. All 312 checkpoints and Hall of Fame pass.

**Not true, however it may look:**

- The team still does not choose its own battles. The trainees now perform the majority of the
  balancing work, but the decisions remain teacher-authored.
- No learned policy has reproduced this balanced-team run. No cross-game transfer has been
  measured. The terminal Pokédex census is 18 owned and 89 seen against the 124-species Red target;
  living-Pokédex completion remains open.
- `max_enemy_level_delta=2` is **rejected**. A full-health level-23 Diglett fainted to a level-19
  Diglett before dealing damage. The replacement combines a five-level direct advantage, type-risk
  refusal, participation-based evolution, and immediate attacks; that replacement now has both
  captured-state and full-route proof.

**Historical gate at that checkpoint:** 1,945 tests, 3 deselected; Ruff, mypy, artifacts, docs, and
registry were clean after the Secret Key adapter. The current superseding gate is 2,074 passed,
3 deselected, with mypy checking all 121 source modules.

---

## 3. Start here

> **Superseded by the 2026-08-09 checkpoint at the top of this file.** The reserve-schema work
> below is done and the target head now passes its held-out test at 17/17. The current next
> dependency is: build an authenticated target artifact, bind it at runtime, shadow it, then run one
> fresh causal completion. Do not load the head into the emulator before that — its receipt says
> `deployment_authority: false` and means it.
>
> The paragraph below is kept because its reasoning still applies to the next schema you freeze.

**Teach the battle controller to see and choose useful reserves.** Preserve the current Lorelei
failure as the regression target. Add identity-free reserve type/move summaries and
candidate-relative offensive and defensive matchup margins, then make generic switch resolution
score the same candidates under health, status, and level safety constraints. Collect fresh
balanced-role demonstrations only after freezing that schema; the historical six-class artifact
predates this curriculum and cannot be patched into understanding it.

Then continue down [AGENT_COORDINATION.md](AGENT_COORDINATION.md) § *Open work, in priority order*.

### Architecture-audit pivot — 2026-08-08

The latest full audit changes what "start here" means. The deterministic teacher is now sufficiently
complete to serve as the frozen expert oracle. Another Red-specific repair or League role is useful
only when it fixes a genuine regression or adds a bounded, non-cosmetic lesson; it must no longer
delay transferring control authority to the learner.

What the audit established:

- the clean teacher, referee, trajectory recorder, captured-state harnesses, and private lineage
  controls are unusually strong and should be preserved;
- the nonlinear battle model has real live Red completion evidence, but it predates the current
  balanced-team curriculum;
- `ModelObjectivePolicy` authorizes the objective that fixed code already intends to run, while
  `run_qualified_play` still dispatches the chapter sequence directly;
- live navigation is dominated by authored direction sequences even though reusable local A* exists;
- resource planning, recovery, collection execution, and the second-game adapter remain teacher
  owned, partial, or scaffolding; and
- a normal completion report can pass without requiring a teacher-free battle-policy report, so
  official learned evaluation needs a stricter, explicit contract.

The dependency order is now:

1. **Freeze and publish the Red oracle.** Keep this branch as the canonical source, merge the current
   draft into `main`, and stop opening sealed campaigns for teacher-only tuning.
2. **Create a portable player loop.** Observation → chosen objective → dispatched skill → typed
   action → structured result → replan. Revision-specific reads and menu compilation stay behind the
   game adapter.
3. **Collect current balanced decision data.** Record decision spans, learner failures, and
   corrections rather than treating roughly half a million controller actions as equally useful.
4. **Enforce teacher-free learned evaluation.** Any teacher query, unsupported-observation fallback,
   undeclared safety substitution, or expected-route label is a visible counted failure.
5. **Complete Red with the learned stack.** The initial reliability gate remains at least 8/10
   preregistered clean starts with frozen code and weights, no restore, and no teacher control.
6. **Falsify transfer with Crystal.** Start with one battle and local-navigation vertical slice, then
   compare zero-shot, few-shot, and from-scratch performance.
7. **Use collection as the lifelong curriculum.** Expand capture, storage, evolution, and training
   through the portable loop; do not write a second 120-species fixed route.

Near-term code work starts with item 4 because it creates an enforceable boundary immediately, then
items 2 and 3 proceed together. See [the roadmap](docs/roadmap.md) for the full gate sequence and
[the video narrative](docs/youtube-video-narrative.md) for the public explanation of this pivot.

### Portable-loop implementation checkpoint — 2026-08-08

The first two architecture boundaries now exist and are ROM-independent:

- strict battle evaluation records teacher queries separately from fallbacks and cannot pass after
  either one;
- `ModelObjectivePolicy.select(state)` ranks legal objectives without receiving the route's expected
  objective ID;
- `PortablePlayerLoop` implements observe → select → specialist plan → one bounded typed action →
  observe result → verify/replan;
- verified objective facts may not regress across an action, unavailable objective choices fail
  before execution, and a specialist cannot return authority for a different objective; and
- the deterministic objective policy uses the identical loop interface, so teacher and learner
  ownership can be compared without two runtimes.

This is **not end-to-end Red autonomy yet**. `run_qualified_play` still invokes most chapter
functions in a fixed Python sequence. The portable loop now has an explicit composite-skill
registry, action/frame bounds, declared side effects, and independent post-skill semantic
verification. Unsupported model choices stop visibly rather than falling back to the fixed route.

The bounded exhaustive counterfactual audit of the historical planner enumerates **166 reachable
dependency-valid states**, including **129 branching states** and **446 neutral/candidate-local
evaluations**. Selection changes with location in **73/129 (56.59%)** branching states and chooses
the candidate whose target region matches simulated location in **237/317 (74.76%)** opportunities.
This proves some context sensitivity, not correct gameplay. The 80 local-context misses are the
first explicit planner-curriculum queue. See the
[sanitized receipt](docs/evidence/semantic-objective-counterfactual-audit-2026-08-08.json).

A current-source private capture at the stable Celadon Center boundary then reconstructed fourteen
verified objectives and exposed three genuinely legal choices: `clear_rocket_hideout`,
`defeat_erika`, and `reach_saffron`. Without an expected label, the historical model selected
`clear_rocket_hideout` at **99.70% confidence**. No skill or action was executed, so this is the
first real-state selection diagnostic—not live objective completion. The capture also proves that
resumed evaluation needs an authenticated progress envelope because transient historical location
facts are not recoverable from current cartridge memory alone. That envelope is now implemented:
the capture tool binds the exact private state digest to its checkpoint and verified-objective
prefix, and refuses a modified state. The resumed Red observer now reconstructs the real Celadon
state and its three legal objectives from that envelope plus live memory. The dispatcher remains
next. See the
[selection receipt](docs/evidence/model-selected-celadon-objective-2026-08-08.json).

The next published slice then executed that choice. From the same three legal branches, the model
selected `clear_rocket_hideout` at **99.70% confidence** with no expected label or fallback. Its
registered teacher-authored skill executed **1,143 actions / 98,237 frames**, defeated five exact
trainers, bypassed eight optional trainers, returned the fully healed party to Celadon Center, and
released the controller. Crucially, the loop did not accept the skill report as completion: a fresh
memory observation independently added both `story:rocket_hideout_cleared` and
`item:silph_scope`. The resulting legal frontier is `rescue_fuji`, `defeat_erika`, and
`reach_saffron`. See the
[execution receipt](docs/evidence/model-selected-hideout-execution-2026-08-08.json).

The next published slice added Pokémon Tower and ran both decisions uninterrupted. After Hideout,
the same model selected `rescue_fuji` at **99.08% confidence** from `rescue_fuji`, `defeat_erika`,
and `reach_saffron`. The Tower skill executed **2,508 actions / 167,351 frames**, fought ten required
battles, obtained the Poké Flute, and returned the healed party to Lavender Center. Across both
steps the model made two decisions with no expected labels or fallbacks; the loop executed **3,651
actions / 265,588 frames** and independently verified all three new semantic facts. See the
[two-decision receipt](docs/evidence/model-selected-two-objective-sequence-2026-08-08.json).

The third uninterrupted decision selected `reach_fuchsia` from the post-Tower Lavender state. Its
registered skill executed **3,132 actions / 373,072 frames**, cleared the required Route 12–13
battles, captured the level-30 Snorlax in two throws, preserved the Poké Flute, and returned a
fully healed four-member party to Fuchsia Center. The complete three-decision slice totals **6,783
actions / 638,660 frames**, three model selections, four independently observed progress facts,
zero expected labels, zero fallbacks, and zero replans. See the
[three-decision receipt](docs/evidence/model-selected-three-objective-sequence-2026-08-08.json).

The explicit skill-affordance mask is now implemented. It reports dependency-legal objectives,
executable objectives, and an exclusion reason for every unavailable skill. The uninterrupted live
run extends through Surf, a real Koga-versus-Strength branch, Strength, Erika, and Saffron: eight
model dispatches, **15,593 fixed-skill actions**, zero expected labels, zero fallbacks, and zero
replans. The model chose Koga from two executable candidates at **96.41% confidence**; the other
seven decisions were singleton dispatches and are recorded separately so their near-100%
confidences cannot be mistaken for ranking evidence. The observer also stopped latching transient
inventory facts, so Gold Teeth disappear after the Warden consumes them while durable objective
progress remains. See the
[eight-decision receipt](docs/evidence/affordance-masked-eight-objective-sequence-2026-08-08.json).

Silph is now part of the same uninterrupted sequence. Its bounded skill executed 5,041 actions and
1,675,457 frames, cleared the required events, retained the Card Key and Master Ball, left optional
Lapras untouched, and returned healed to Saffron Center. The complete slice is now nine dispatches
and 20,634 actions; eight are singletons and the Koga-versus-Strength choice remains the one measured
ranking branch. See the
[nine-decision receipt](docs/evidence/affordance-masked-nine-objective-sequence-2026-08-08.json).

The post-Silph curriculum is now connected as one bounded `defeat_sabrina` skill. It recruited
Hitmonlee after all five Dojo fights, completed the six-member party, followed the trainer-free Gym
warp route, defeated Sabrina, and returned healed to Saffron Center. The skill used 3,058 actions /
949,298 frames; the ten-step slice totals 23,692 actions with independent Marsh Badge observation.
See the
[ten-decision receipt](docs/evidence/affordance-masked-ten-objective-sequence-2026-08-08.json).

The Cinnabar adapter is now live-qualified. It used 830 actions / 148,680 frames, acquired HM02,
taught Fly to DUX, preserved all six party members and lead stats, fled four bounded wild battles,
defeated zero Route 21 trainers, and ended fully healed in Cinnabar Center. The eleven-step slice
totals 24,522 actions and independently verifies `location:cinnabar_island`. See the
[eleven-decision receipt](docs/evidence/affordance-masked-eleven-objective-sequence-2026-08-08.json).

The twelfth dispatch now isolates the Mansion lesson from Blaine. It used 732 actions / 87,564
frames, recovered the Secret Key and TM14, preserved all six optional trainers, explicitly verified
that Blaine and the Volcano Badge remained untouched, and returned the healed party to Cinnabar
Center. The twelve-step slice totals 25,254 actions, eleven singleton dispatches, one real ranking
branch, and zero labels, fallbacks, or replans. See the
[twelve-decision receipt](docs/evidence/affordance-masked-twelve-objective-sequence-2026-08-08.json).

**Next:** connect a separate post-Mansion `defeat_blaine` skill from this verified boundary. Do not
reintroduce the old combined Mansion-plus-Gym authority: the model owns the objective transition;
current skills still own navigation, battle, menu, training, and recovery actions.

That skill is now live-qualified at the authenticated post-Mansion boundary. Its first private
rehearsal returned a report but was correctly rejected for exceeding the initial 20,000,000-frame
declaration. With only the safety envelope widened, the published-source rerun passed in 469,232
actions / 31,883,961 frames. It trained 1,716 balanced-team battles with 885 healing trips, reached
60/55/55/55/55/55 in final forms, defeated Blaine, collected TM38 and the Volcano Badge, returned
healed, and independently exposed `defeat_giovanni`. See the
[post-Mansion receipt](docs/evidence/affordance-masked-post-mansion-blaine-2026-08-08.json). The
failed rehearsal remains uncounted; the successful receipt is a bounded one-objective qualification,
not yet a contiguous thirteen-step run.

The post-Blaine Giovanni adapter is now live-qualified from its authenticated capture. It used
1,409 actions / 156,305 frames, cleared the six declared Viridian Gym trainer lessons, preserved
the two intended bypasses until Giovanni settled the remaining events, defeated his exact party,
collected TM27 plus both Earth Badge mirrors, returned all six members healed, and independently
opened `cross_victory_road`. See the
[Giovanni receipt](docs/evidence/affordance-masked-post-blaine-giovanni-2026-08-08.json). This is a
bounded one-objective qualification; the next adapter starts from the authenticated Viridian Center
terminal.

Victory Road is also live-qualified from that Viridian capture. It used 3,857 actions / 453,733
frames, defeated the exact Route 22 rival party without a Hyper Potion, passed all seven badge
gates, satisfied all five boulder-switch events, normalized the exact League reserves, and ended
with the full party healed at Indigo. Fresh observation opened `defeat_lorelei`. See the
[Victory Road receipt](docs/evidence/affordance-masked-post-giovanni-victory-road-2026-08-08.json).

The portable League chain is qualified through Lance from successive authenticated room terminals:
Lorelei 480 actions / 42,783 frames, Bruno 328 / 32,538, Agatha 466 / 45,854, and Lance 582 /
51,905. The first three preserve their measured two-member role lessons; Lance is still a
single-member chapter. The current private boundary is `portable-loop-post-lance.state`, with
`defeat_champion` available. Before wrapping the historical Champion chapter, split its automatic
Champion/Hall-of-Fame transition into honest graph authority if the live game exposes a stable
post-victory boundary.

That experiment is complete. The first rehearsal proved there is no stable post-victory
Champion-room boundary: the Champion event and Hall-of-Fame map appeared together. The final skill
therefore declares Hall of Fame as an automatic side effect of `defeat_champion`; it does not claim
a second model decision. The source-bound rerun passed in 567 actions / 45,216 frames with the exact
Champion party, one X Accuracy, six X Specials, three Full Restores, and the 66/55/55/55/55/55 team
in the Hall of Fame. See the
[Champion receipt](docs/evidence/affordance-masked-post-lance-champion-2026-08-08.json).

All post-Celadon adapters are now individually live-qualified on successive authenticated captures,
and the complete integration run has passed. From the original authenticated Celadon capture, one
emulator process executed 20 model dispatches, 502,175 actions, and 37,369,283 frames through the
Hall of Fame with no expected labels, fallbacks, or replans. Fresh observations closed all 36 graph
objectives. Nineteen dispatches were singletons; only Koga versus Strength measured ranking. See the
[twenty-decision receipt](docs/evidence/affordance-masked-twenty-objective-hall-of-fame-2026-08-08.json).

The first replacement seam is implemented. `training_control.py` defines a 21-feature portable
observation and the five phase-masked actions `seek`, `fight`, `flee`, `heal`, and `stop`.
`run_red_team_balancing` emits each teacher decision before execution through an optional sink, and
`scripts/replay_training.py --out-decisions` atomically preserves complete or failed streams. The
features deliberately exclude game, map, species, move, and memory identity.

Diagnostic lineage 01 completed at source `778e6cb`: 48,156 decisions, 1,716 battles, 885 healing
trips, zero faints, and a 55/55/55/55/55/55 terminal. Counts are seek 44,882, fight 1,710, flee
1,064, heal 499, stop 1. The raw v1 artifact remains private and immutable at SHA-256
`6685c889c4e5ea55c56b0194074f0c4b6b82376d40dfb8f475f7d903856f5a64`; it predates embedded
lineage/source provenance and is diagnostic only. The v2 writer and `training_control_dataset.py`
now bind later streams to source commit, dirty flag, root-state digest, and whole-lineage partition;
the audit rejects state overlap and validation-only classes.
`training_control_model.py` now supplies the class-balanced MLP, phase-masked inference, aggregate
metrics, and whole-lineage candidate fit. Its public summary is always non-promotable until later
runtime gates; only synthetic separability and integrity behavior are currently tested.
Do not assume that different idle-wait counts create distinct deterministic roots. The 17-frame
root used by train lineage 01 differed from its parent, but a later 43-frame attempt produced the
same root digest and the exact same 46,687-decision sequence. That attempt is retained privately as
a reproducibility control and rejected as independent data. A replacement root uses reversible
movement, proves the same map, position, battle state, and party afterward, and must have a distinct
serialized digest before collection. See the
[idle-equivalence receipt](docs/evidence/training-control-idle-wait-equivalence-2026-08-08.json).
The first motion-root replay then failed after 11,122 decisions when a trainee fainted inside a
durable matchup. It contributed 10,375 novel diagnostic pairs (99.46%) but is excluded from fitting.
The teacher now reapplies its health floor before every battle turn and escapes through the bounded
escort path when crossed. Root creation also fails closed on unchanged bytes or changed checkpoint
semantics. See the
[failed-lineage receipt](docs/evidence/training-control-v2-train-02-motion-failure-2026-08-08.json).
The same root then passed at source `71205a8`: 60,192 decisions, 1,740 battles, 1,017 healing trips,
zero faints, and all level 55. It adds 59,303 novel unique pairs versus train lineage 01 (99.89%)
and is the second qualified training root. See the
[repaired receipt](docs/evidence/training-control-v2-train-02-motion-repair-2026-08-08.json).
Validation root 01 failed immutably after 17,751 decisions and 725 completed battles: a legitimate
33-safe-exit streak exceeded the 32-flee feature horizon even though levels were progressing. Do not
rerun or count that root. The later anti-loop raise is removed; the early no-win venue mismatch and
global step budget remain. See the
[validation failure receipt](docs/evidence/training-control-v2-validation-01-failure-2026-08-08.json).
Fresh validation root 02 qualified at source `6c65dcd`: 60,459 decisions, 1,767 battles, 1,021
heals, zero faints, and all level 55. The default 500-epoch candidate scored 75.62% raw and 76.91%
balanced accuracy on it, with zero state overlap and all five classes covered. Model SHA is
`d04546c2...df91d7d`. It is offline-only; shadow and controlled emulator gates remain.
Authenticated loading and live shadow instrumentation are now implemented. The private model file
digest is `8088efbf...52307f`; loading rejects links, altered bytes, schema drift, shape drift, and
non-finite parameters. Shadow output reports confidence, raw/balanced agreement, phases, class
counts, and confusion while explicitly recording that the model had no authority.
Shadow root 01 completed at source `a9e6921`: 55,904 decisions, 75.57% raw / 76.73% balanced
agreement, 65.42% battle and 76.23% overworld agreement, zero faints, all level 55. Fight recall is
42.05%, flee 96.53%, heal 68.77%, seek 76.32%, stop 100%. Model authority remained false. Use these
errors to design the bounded control gate; do not claim autonomous training yet.
Battle-only authority is implemented for the next fresh root. The model's `fight`/`flee` choice is
executed when safe; unsafe model fights abort with a referee error and never fall back. Overworld
actions remain teacher-controlled and must be described that way. The audit records `authority_phases:
["battle"]` and `teacher_fallback_on_model_disagreement: false`.

The first controlled root failed closed after 480 decisions: 479 agreements, followed by a model
`fight` when every admissible training attack was exhausted or disabled. The preceding safe fight
and failing decision had identical features and candidates, so this was an interface defect rather
than a learnable classification miss. The current repair makes candidate actions a canonical
non-empty subset and removes `fight` at all five unsafe runtime boundaries. Regenerate the
collection registry and its four goldens with every source edit, then use a fresh root for
controlled attempt 02. Never count or retrain on attempt 01. See the
[controlled failure receipt](docs/evidence/training-control-battle-control-01-failure-2026-08-08.json).

Controlled attempt 02 used fresh root `e6f95dfe...e2f37e` at source `742607a`. It passed the unsafe
boundary but failed after 77,538 decisions when 1,963 of 2,690 safe teacher fights became causal
flees and the healing budget ran out before readiness. There was no fallback. The fitting loss had
not applied observation candidate masks, so forced singleton flee decisions still trained the
classifier. The current repair masks the fitting softmax as well as inference. Do not reuse either
failed controlled lineage for fitting. Collect two fresh train roots and one fresh validation root
under the corrected contract, then fit and requalify. See the
[under-fighting receipt](docs/evidence/training-control-battle-control-02-failure-2026-08-08.json).

That replacement campaign is now qualified for **battle-only** authority. Two new training roots
contributed 119,328 decisions, and a fresh untouched validation root contributed 58,117 with zero
root overlap. The unchanged 24-unit MLP reached 78.06% raw / 89.25% balanced validation accuracy.
A fresh 57,342-decision shadow reached 100% battle agreement. Under causal battle authority, the
model then completed a 59,137-decision lesson, 1,743 battles, 1,051 healing trips, zero faints, and
an all-55 terminal without fallback. See the [candidate](docs/evidence/training-control-candidate-v2-2026-08-08.json),
[shadow](docs/evidence/training-control-shadow-02-2026-08-08.json), and
[controlled success](docs/evidence/training-control-battle-control-success-2026-08-08.json).

Do not overstate that result. Every unsafe battle state offered singleton `flee`; every safe
two-candidate state was labeled `fight`. The causal run therefore contained 1,602 forced flees and
1,984 safe fight choices. The next substantive boundary is overworld control, where the model still
turned 12,405 teacher seeks into heals and the runtime does not yet execute every returned
overworld choice. Redesign that contract before collecting another generation of lineages.

That execution boundary is now implemented: optional heals pay their real trip budget, while a
missed required heal or missed terminal stop aborts without fallback. The first three v4 roots were
then stopped before producing artifacts because the observation audit found an unlearnable label
source. In v3 train 01, 356 of 639 heals were caused by the Blastoise safety reserve, but feature
schema v1 exposed only the trainee. Schema v2 adds game-neutral reserve HP/status/attack-PP signals.
Never reuse the three exposed roots listed in the
[observation audit](docs/evidence/training-control-overworld-observation-audit-2026-08-08.json).

Counted v2 train lineage 01 is qualified from a retained 17-frame root at source `4c885d8`:
46,687 decisions, all five actions, 1,726 battles, 815 healing trips, zero faints, and all level 55.
Its private stream SHA is `f13f9f1031632a8f1158c280c241d6f6a24ab5eeed4c30bdf76d802917e1aca1`;
its root-state SHA is `62f7862e6f7e15c6f7c14a4cbb7488d6ff946502809dde5e1315171925e80c9c`.
It adds 45,831 novel unique action-feature pairs versus diagnostic lineage 01 (99.85% of its unique
pairs). See the [sanitized receipt](docs/evidence/training-control-v2-train-01-2026-08-08.json).

**Next:** make `seek`, `heal`, and `stop` executable model authorities, distinguish hard safety
affordances from teacher strategy, and preregister consequence-based gates before collecting fresh
lineages. Keep test roots sealed.
lineage rather than by row, train and shadow-evaluate the first candidate, then replace the
469,232-action skill's teacher
authority under the same safety envelope. Preserve the fixed skill as demonstrator and referee. Do
not describe instrumentation as a trained policy or this integration result as clean-start or
end-to-end learned completion.

---

## 4. How to work here without burning hours

### Two cartridges, and a renamed folder (2026-08-09)

Blue is now available, and a living Pokédex needs it: ten species are exclusive to it and no amount
of Red planning reaches them.

Each title reads its own environment variable, because one variable cannot name several cartridges
and a campaign runs several:

| title | variable |
| --- | --- |
| Red | `POKEMON_RED_ROM` |
| Blue | `POKEMON_BLUE_ROM` |

Point each at the **file**, not the folder. The owner keeps both ROMs in one folder that was
**renamed on 2026-08-09** — if a path you remember stops working, that is why, and the new one comes
from the owner rather than from this document, which must never contain it.

``PyBoyAdapter`` now takes ``expected_rom`` and still defaults to Red, so nothing that already works
changes. Before this the fingerprint check inside the adapter was hard-coded to Red while the
function it called took the expected cartridge as an argument — so the repository could refuse a
cartridge it had explicitly been told to expect.

The Red adapter loads and reads a Blue cartridge unmodified. That is the first cross-cartridge
evidence this project has, and it is worth being precise about what it shows: the ROM gate, the boot
path, and the addresses touched at power-on transfer. It does **not** show that the whole memory map
does. Verifying the rest means harvesting Blue encounters the same way Red's bands were measured.

### Iterate against a captured state, not a full run

A run reaches the training block in about six minutes. A captured state reaches it in about one.
Twelve runs in one session were spent replaying the same 275 checkpoints before this existed.

```bash
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Returned safely from Mansion" --out <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --swap-only
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --max-steps 40
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Bruno room ready" --out <scratch>/bruno.state
POKEMON_RED_ROM=<path> python scripts/replay_bruno.py --state <scratch>/bruno.state
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Lorelei supplies ready" --out <scratch>/lorelei.state
POKEMON_RED_ROM=<path> python scripts/replay_lorelei.py --state <scratch>/lorelei.state
POKEMON_RED_ROM=<path> python scripts/replay_lorelei.py --state <scratch>/lorelei.state \\
    --out-state <scratch>/bruno-current.state
POKEMON_RED_ROM=<path> python scripts/replay_bruno.py --state <scratch>/bruno-current.state \\
    --out-state <scratch>/agatha.state
POKEMON_RED_ROM=<path> python scripts/replay_agatha.py --state <scratch>/agatha.state \\
    --out-state <scratch>/lance.state
POKEMON_RED_ROM=<path> python scripts/replay_lance.py --state <scratch>/lance.state \\
    --out-state <scratch>/champion.state
POKEMON_RED_ROM=<path> python scripts/replay_champion.py --state <scratch>/champion.state
```

`--max-steps` shrinks the policy's step budget so a spinning loop fails in seconds instead of
burning 500,000 steps.

A capture is **one starting point**, and its starting position is part of what it captures — the
Mansion capture leaves the player on the nurse's tile, where a button press feeds her dialogue.
Iterate against it; confirm with `cli play`.

State files are ROM-derived and private exactly as the ROM is. Keep them in scratch, never commit
them. This does not weaken the adapter's no-save property, which is about PyBoy never writing files
beside the user's ROM — see `PyBoyAdapter.save_state`.

### The gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/python -m mypy
.venv/bin/pytest -m "not integration"
```

Any `src/` change restales the collection registry. Regenerate and update the four golden values in
`tests/test_collection_protocol.py` **in the same commit**. Never hand-merge those hashes — they are
derived; take either side and regenerate.

### Two hard rules

- **Never edit `src/` while an emulator run is in flight.** A run loads its source at launch, so a
  mid-run edit does not change the run — it changes what the tree claims the run was.
- **Never open a counted evaluation seed.** Validation `1810002`–`1810005` and sealed test
  `1820001`–`1820005` are one-attempt-only. `1810001` is exposed and diagnostic-only.

The ROM path, private artifact root and objective-model path come from the environment per session
and must never appear in any file, tracked or not — `check_public_artifacts.py` scans the working
tree including untracked files.

---

## 5. Measured facts. Do not re-derive these, and do not contradict them without a measurement

Each cost at least one emulator run to establish. Each has an evidence file.

| Fact | Evidence |
| --- | --- |
| The Mansion fields levels **28–39**, not the 30–32 an old note claimed from 8 samples | `encounter-bands-2026-08-07.json` |
| Diglett's Cave is **15–21** typical with a rare Dugtrio at 31 | same |
| The **town map has no readable cursor** — five candidate addresses all stay frozen. Fly must be judged by the map underfoot | `town-map-cursor-not-observable-2026-08-07.json` |
| The party submenu is ordered **field moves, STATS, SWITCH, CANCEL**, so SWITCH is at `field_move_count + 1` | `party-submenu-layout-2026-08-07.json` |
| Menu signatures: start menu `max=7, top=(11,2)`; party list `max=5, top=(0,1)`; member submenu `max=4, top=(10,8)` | same |
| `watched=0x03` does **not** mean the d-pad is ignored — the party list reports it and its cursor moves | same |
| A **blocked press is not a step**, so a walk into a wall never rolls for an encounter | `cave-pacing-and-training-2026-08-07.json` |
| The +2 margin is unsafe: level-23 Diglett fainted from full HP to level-19 Diglett before dealing damage | `training-margin-four-level-faint-2026-08-07.json` |
| Captured-state development reached six level-55 members in 1,716 battles with zero faints | `measured-balanced-team-captured-state-success-2026-08-07.json` |
| A clean-power run passed the final-form 60/55/55/55/55/55 team gate and completed 312/312 checkpoints through Hall of Fame | `measured-balanced-team-full-route-success-2026-08-07.json` |
| The next full run measured all 49 League attack decisions on party slot 1: 1/6 participation and 100% busiest-member share | `measured-whole-league-participation-2026-08-07.json` |
| A clean-power run qualified the first matchup-aware League lesson: Hitmonlee attacked Bruno's Onix, recovery followed the damaged member, League participation reached 2/6, and Hall of Fame still passed | `measured-bruno-team-participation-2026-08-07.json` |
| The next clean-power run qualified Jolteon's Lorelei role: Thunder handled three Water targets, Blastoise handled Jynx and Lapras, League participation reached 3/6 with 90.70% busiest share, and Hall of Fame still passed | `measured-lorelei-team-participation-2026-08-07.json` |
| The next clean-power run assigned all of Agatha to Jolteon and Dugtrio, cut that battle from 15 decisions and ten healing items to six decisions and one item, raised League participation to 4/6 with 70.59% busiest share, and still entered Hall of Fame | `measured-agatha-team-participation-2026-08-07.json` |

---

## 6. How this codebase fools people

These are not hypotheticals. Each happened, more than once, and cost runs.

### Green tests that test nothing

The test file written to prevent never-executed code contained one test asserting objects construct
and one ending in `pass`. Both green. A later test monkey-patched away the exact method that was
broken, so the suite stayed green over a module whose entry point raised `AttributeError` on its
first call.

**Practice:** after writing a test, break the code it covers and confirm the test fails. If it does
not, the test is decoration. This caught four separate defects today that would otherwise have
shipped.

### A belief that nothing available can contradict

The SWITCH row was guessed wrong four times across five runs. Every check was derived from the same
assumption as the guess, so no amount of care could falsify it. One measurement did, in five lines —
and the answer was the formula the code had *before* I changed it.

**Practice:** when a guard and the code it guards come from the same assumption, the guard only
agrees. Recognise success by the game's own state: the map underfoot, the party order in memory, the
levels that rose. Where an observable exists, read it; where none does, act and check what happened.

### A process that looks like work

A run went ten minutes without failing. That looks exactly like training. It was pressing left
against a wall: 500,000 steps, fewer than 250 battles, no level gained. The number that separates
training from spinning is the ratio of steps to battles, and nothing was reporting it.

**Practice:** for any loop, ask what number would distinguish progress from motion, and report it.

### Constants that were true by accident

Field Dig addressed Diglett as the third party member with Dig in move slot two. Both held only
while nothing ever reordered the party. The moment the party swap started working, it broke.

**Practice:** making the party movable was the point. Anything that remembers a slot is a latent
bug. Find the Pokémon, do not remember where it was.

### Copies that drift from their originals

Three times a helper was copied from a proven module and lost the constant that made it work: the
matchup gate, the cursor selector, and a walk bounded at 12 steps where the proven version allows 24.

**Practice:** before writing a navigation helper, grep for one that already works. `surge.py` in
particular has proven paths for Vermilion, Route 11 and Diglett's Cave.

### Failures that carry no evidence

Five failures today produced messages with no state: `Could not select menu item.`,
`Fly to Vermilion failed.`, `Failed to enter Route 11`, a silent 500,000-step exhaustion, and
`Battle menu did not settle.` Each needed a run spent purely on instrumenting it before it could be
fixed.

**Practice:** this is the cheapest available change to this codebase. When you write a raise, put
the readings in it.

---

## 7. Predict before you run

Every run this session was preceded by a written prediction in `docs/evidence/predicted-*.json`
stating what should happen and, crucially, **what would refute it**. This is not ceremony. One
prediction assumed the party arrived as `[68, 20, 26, 30, 25, 30]`; it arrived as
`[55, 20, 26, 30, 25, 30]`, and the divergence was only legible because the assumption had been
written down. A run compared against no prediction can only be interpreted after the fact — which is
how a wrong band survived 155 samples that contradicted it.

---

## 8. Do not

- Do not restore the multi-target Route 22 continuation loop. It cycled every reserve into Venusaur
  until the party read `(0, 0, 0, 0, 0, 0)`.
- Do not treat a green `passed` as evidence the thing it names happened.
  `team_development.passed` never looked at five of six party members, and twelve receipts reported
  the opponent's levels as ours.
- Do not use the party as disposable HP. Switching to a healthy teammate is strategy; feeding a weak
  one in to absorb a hit is the V35 failure.
- Do not reintroduce a hand-derived Fly hop sequence. Two runs died to one.
- Do not describe the objective ranker as an autonomous player.
- Do not commit ROMs, saves, emulator states, trajectories, secrets, or absolute paths.

---

## 9. Loose ends you are inheriting

- **`global_router.py` and `collection_chapter.py` are scaffolding.** The router has a correct
  Dijkstra, three tests, no call site, a hand-written five-node graph, and edges carrying no warp
  coordinates — it cannot drive navigation as it stands. `run_collection` reads the collection
  correctly then raises `NotImplementedError` at routing. Give them a job or park them.
- **Participation is measured across all five League battles, but still concentrated.** Every
  chapter records active-party indexes and publishes participating-member count plus busiest-member
  share. Lorelei, Bruno, and Agatha have explicit specialist-role contracts; together they raise the
  League to 4/6 participants, but Blastoise still owns 70.59% of decisions. The remaining work is
  behavioral: add real matchup value for DUX and Snorlax, especially in Lance or Champion.
- **The ROM path is in git history.** `a9d0bb4` added it in source, `371be10` removed it. Not in the
  current tree; `a9d0bb4` is on no remote, so exposure is local only. Rewriting history is
  destructive and belongs to the repository owner.
- **The historical tolerance conflict is resolved in code.** Mansion development and Champion
  readiness now share `COMPLETION_LEVEL_PARITY` at a level-55 floor. Older evidence remains
  historical; do not reintroduce separate local contracts.

---

## 10. The standard to hold

Report what happened, not what was hoped for. Two claims I made today were wrong and needed
retracting: that a ten-minute run was "training" when it was spinning, and that `watched=0x03` meant
the d-pad was dead. Both were corrected in the record rather than quietly dropped, and the evidence
files say so.

That is the standard. This project's whole value is that its numbers can be trusted, and the only
way that stays true is if being wrong in public is cheaper than being vague.
