# Current audit: what this Pokémon agent can actually do

**Audit date:** 2026-08-08  
**Scope:** architecture, evidence quality, learned authority, transfer readiness, repository health,
and portfolio value.

## Executive verdict

This is already an unusually rigorous game-agent engineering project. Its strongest achievement is
not merely that code can finish Pokémon Red. It is the infrastructure that separates an expert
teacher, a learned decision-maker, fixed mechanic skills, and an independent referee—and then
preserves the failures that reveal when those boundaries are wrong.

The project is **not yet a general Pokémon-playing model**. The cleanest current description is:

> A verified Pokémon Red teacher and evaluation platform with bounded learned battle, objective,
> and training-control components, progressing toward a teacher-free cross-title player.

That wording is both credible and compelling. It gives the finished Red route its proper weight
without claiming that a model discovered the route, navigation, team strategy, or recovery logic.

## Scorecard

Scores measure the repository against its stated end goal, not against a typical hobby project.

| Dimension | Score | Evidence and limiting factor |
| --- | ---: | --- |
| Deterministic completion and referee | 9/10 | Clean power-on; 312/312 semantic checkpoints; 36/36 objectives; Champion and Hall of Fame. The remaining point is for more cartridge revisions/titles. |
| Experimental honesty | 9/10 | Failed and rejected lineages remain visible, authority modes are separated, and operational gates can overrule headline accuracy. A few historical claims remain scattered through very long documents. |
| Safety and artifact integrity | 9/10 | Exact hashes, clean-source binding, root-overlap rejection, atomic failed-stream retention, affordance masks, and fail-closed control. Private ROM-derived assets remain external. |
| Tests and static checks | 8/10 | 2,024 non-integration test cases currently pass locally, with Ruff, documentation, public-artifact, registry, and mypy gates. Forty-four legacy modules still use mypy `ignore_errors` overrides. |
| Architecture and modularity | 7/10 | Typed observations, objectives, skills, results, model loaders, and promotion gates are strong seams. The 136,980-line Python surface and Red-specific chapter modules remain costly to reason about. |
| Learned battle control | 7/10 | Real model-controlled qualifications exist with no disagreement fallback. Evaluation is still dominated by the authored Red curriculum and lacks a second-title test. |
| Learned objective planning | 5/10 | A single process reached Hall of Fame through 20 model dispatches, but 19 dispatches offered only one executable candidate and fixed skills pressed the buttons. |
| Learned training strategy | 7/10 | The identity-free trainee/venue scorer beat its sealed shape baseline by 4.239 points, completed isolated causal control with 191 disagreements, and then controlled 114,831 choices inside the portable Blaine objective with 400 disagreements. Evidence is still one captured Red training slice. |
| Cross-title transfer | 2/10 | Several representations are intentionally identity-free, but no Crystal or other-title result exists yet. |
| Autonomous living Pokédex / level 100 | 1/10 | Target and planning foundations exist; autonomous collection, storage, evolution, resource planning, and long-horizon recovery are not integrated. |
| Portfolio presentation | 8/10 | The README now leads with a concise claim boundary, the architecture guide is current, and the failure/diagnosis/repair story is excellent. A two-minute visual demo remains the largest opportunity. |

## What is verified now

### 1. A complete teacher and independent completion contract

The deterministic system completes Red from clean power-on through the Hall of Fame while satisfying
312 semantic checkpoints and all 36 graph objectives. It develops a six-member final-form party and
retains explicit evidence for the run instead of inferring success from emulator uptime or a final
screen alone.

This makes the teacher useful in three roles:

- an expert demonstration generator;
- a library of bounded mechanic skills; and
- a referee that can reject unsafe or semantically invalid learned actions.

### 2. A portable loop that really returns control between objectives

From an authenticated Celadon state, one emulator process accepted 20 model dispatches and reached
the Hall of Fame in 502,175 actions / 37,369,283 frames. It did not restore a state, request the
expected route label, fall back to the teacher, or replan around a failed skill between objectives.

The important denominator is public: Koga versus Strength was the one genuine ranking branch; the
other 19 decisions had one executable candidate. This verifies loop continuity, typed dispatch,
skill contracts, and observation-driven closure. It does not verify broad open-world planning.

### 3. Causal learned control rather than agreement-only metrics

The latest training controller passed both shadow and full-authority causal evaluation. In the
causal run it owned all 57,644 strategic decisions across battle and overworld phases, completed
1,801 battles and 1,046 healing trips, reached 55/55/55/55/55/55, and recorded zero faints or
teacher fallback.

That success closes an important engineering risk: an authenticated model can sit in the live loop,
change execution, remain inside the safety referee, and produce a mechanically checkable receipt.

It also exposed the next scientific risk. The legal candidate set alone predicts every current v6
label. Therefore the correct result is **safe authority integration passed; state-dependent policy
learning not yet demonstrated**.

### 4. State-dependent trainee and venue strategy under real authority

The newest interface ranks variable-sized candidate sets for two strategic choices:

- which viable below-floor party member should train next; and
- which safe measured encounter band should be used.

Each candidate is represented with 27 normalized, identity-free features. Species IDs, move IDs,
party-slot identity, map IDs, area names, and memory addresses are excluded from the model vector.
The scorer shares one network across candidates and is permutation-equivariant. Unobservable ties
that the teacher resolves by hidden identity are excluded rather than mislabeled.

This is the first current training target where state features demonstrably add value. On 7,030
genuine sealed-validation choices, the shared scorer reached 99.9004% accuracy versus 95.6615% for
the choice-shape baseline—a 4.239-point margin. A separate shadow root retained 119,353 genuine
choices at 99.9941% agreement and completed at all six level 55 with zero faints.

The first causal root then failed at 15,449 controlled choices despite zero model/teacher
disagreements. A same-root teacher run completed, revealing that the authority wrapper recomputed a
downstream directive merely because a callback existed. The failed lineage remains preserved. The
repair makes agreement behaviorally identical to teacher execution; on a newly preregistered root,
the unchanged model controlled 119,668 choices, executed 191 trainee disagreements with no
fallback, completed 1,803 battles and 1,114 heals, and ended all six level 55 with zero faints. All
8 shadow and 11 causal gates passed.

The portable objective loop then supplied the system-composition proof. The objective model
dispatched `defeat_blaine`; the candidate ranker controlled 114,831 choices and executed 400
teacher disagreements without fallback; development completed in 1,803 battles and 1,048 heals.
The fixed skill defeated Blaine and returned a fully healed 60/55/55/55/55/55 party. Fresh
observation added the Volcano Badge and opened Giovanni. Ten independent integration checks passed.
The objective choice was a singleton and mechanics remained authored, so this is captured-state
portable composition rather than clean-start autonomy.

## Principal risks

### The learned surface is still small relative to the scripted surface

The teacher owns route discovery, navigation, menu execution, recovery, inventory operations, and
most tactical structure. Learned components sit at real boundaries, but those boundaries do not yet
compose into a clean-start teacher-free run.

### The Red implementation is much larger than the portable core

The Python surface is 136,980 lines across 117 source modules, 26 scripts, and 124 test
files. Much of that size is earned evidence and hardened game mechanics, but it raises regression,
review, and onboarding costs. A second title is the only convincing way to distinguish genuinely
portable abstractions from carefully renamed Red assumptions.

### Static typing is a gate with explicit debt, not a finished migration

Mypy runs across `src/`, but 44 legacy modules are temporarily exempted with per-module
`ignore_errors`. The debt register is honest and must only shrink. Shared emulator/run-state
protocols and removal of `int | None` mismatches are the highest-leverage cleanup.

### The public repository tells the truth, but tells too much of it at once

The evidence archive is valuable for technical reviewers, yet the README and handoff remain long.
A two-minute demo, one architecture diagram, and a compact “claims / evidence / not claimed” page
would improve first-pass comprehension more than another historical milestone paragraph.

### CI must remain boring

The collection registry is intentionally derived from source and goes stale after source changes.
Regeneration should be one isolated generated-file commit after verifying that its changed hashes
match the intended source diff. Repeated red mail from a known derived-artifact mismatch obscures
real regressions and weakens the otherwise strong evidence story.

**Resolved during this audit:** the stale registry was regenerated from source, all four public
golden identities were updated from generator output, and the full 2,024-test local gate passed.
The final **19 consecutive GitHub Actions runs** were green after the registry fix. This is why the
prior email storm was not intended behavior—it was one repeatedly retriggered derived-artifact
mismatch, not useful Dependabot noise. GitHub's repository APIs also report that Dependabot alerts
are disabled, no CodeQL/code-scanning analysis exists, and secret scanning has zero alerts. The
current email diagnosis is therefore specific: those messages came from failed Actions runs.
Enabling dependency and code scanning is a separate future repository-hardening decision and should
be done with a quiet, reviewed notification policy rather than during an experimental campaign.

### The branch now needs integration, not more accumulated history

Draft PR #8 is mergeable and its current checks are green, but it spans **655 commits, 622 changed
files, 123,184 additions, and 3,828 deletions** relative to `main`. That is the accumulated project,
not a focused review unit. Continuing indefinitely on the same branch raises recovery and review
risk even when every commit is sound.

The controlled handoff is: keep PR #8 draft until the owner reviews this audit; preserve/tag the
current `main`; use GitHub's squash merge so the canonical branch receives one coherent project
snapshot; immediately create a fresh short-lived branch; and rerun the full local and GitHub gates
after merge. Do not rewrite the shared branch or force-push its history.

## Dependency-ordered next work

1. **Establish a clean-start evaluation lane.** No captured starting state, teacher query, answer
   label, undeclared safety substitution, or restore. Score success rate across multiple declared
   roots instead of presenting one favorable completion.
   The readiness audit found this lane is not yet safe to open: the clean-start path still uses
   expected-objective authorization, lacks candidate-ranker injection, and has no source-bound
   ten-root envelope. Build those interfaces and one uncounted rehearsal before freezing roots.
2. **Run the Crystal microbenchmark.** Port one local navigation task, one battle task, and one
   training choice. Compare zero-shot, few-shot, and from-scratch performance. Treat breakage as an
   abstraction audit, not a demo failure to hide.
3. **Add recovery and correction learning.** A player that only acts on the happy path cannot
   generalize. Deliberately perturb position, party order, resource levels, and battle outcomes;
   measure whether it detects and repairs the deviation.
4. **Replace a mechanic boundary.** Navigation and recovery are the largest remaining authored
   surfaces. Start with one bounded local route whose observation and failure conditions can be
   shared with Crystal.
5. **Expand toward a living Pokédex only after transfer begins.** Collection is an excellent
   curriculum for navigation, capture, storage, evolution, party construction, and resource
   planning. It should reuse the portable player loop rather than become another fixed Red route.

## Portfolio narrative

### Thirty-second version

> I built a Pokémon Red agent as an evidence-driven autonomy project. First I created a verified
> expert teacher and independent referee that complete all 36 objectives through the Hall of Fame.
> Then I replaced decision boundaries one at a time with authenticated learned policies, using
> sealed lineages, causal emulator control, fail-closed safety, and receipts that distinguish real
> choices from single-option decisions. The current system has completed 114,831 consecutive
> model-controlled candidate decisions with 400 executed teacher disagreements inside the portable
> Blaine objective and zero faints,
> and the next benchmark tests whether that identity-free strategy transfers to another Pokémon
> game.

### Resume bullets

- Built a typed Pokémon Red agent and independent semantic referee that verify 312 checkpoints,
  all 36 objectives, the Champion, and Hall of Fame from clean power-on.
- Designed an auditable model-promotion pipeline with whole-lineage splits, exact SHA-256 artifact
  authentication, candidate masks, fail-closed causal control, and preserved rejected experiments;
  qualified a trainee/venue controller offline, in shadow, under isolated causal control, and inside
  the portable objective loop; the final proof controlled 114,831 choices with 400 executed
  disagreements and no fallback.
- Implemented an observation-driven objective loop that completed 20 sequential model dispatches
  and 502,175 mechanic actions in one emulator process, while publishing the crucial limitation
  that only one dispatch was a genuine multi-option ranking decision.

### Interview story

The best story is not “I scripted Pokémon.” It is the sequence of increasingly difficult
falsifications:

1. A complete run exposed a one-member carry strategy, so completion quality and teaching quality
   were separated.
2. High offline accuracy failed operational heal gates, so model accuracy and safe control were
   separated.
3. Shadow agreement looked promising, but causal authority exposed under-fighting and exhausted the
   lesson budget.
4. A later controller passed causal evaluation, but a candidate-only baseline also scored 100%, so
   authority integration and state-dependent learning were separated.
5. The next representation was redesigned around variable trainee and venue choices; it beat the
   sealed shape baseline by 4.239 points.
6. Its first causal run failed despite perfect agreement. A same-root control isolated an
   authority-wrapper defect, an invariant test pinned the repair, and a fresh causal run completed
   with 191 executed disagreements.
7. The unchanged ranker then composed with learned objective dispatch and the fixed Blaine skill,
   executing 400 disagreements before fresh observation opened Giovanni.

That progression demonstrates systems engineering, ML evaluation, debugging discipline, and the
ability to revise a hypothesis when the evidence contradicts it.

## Claims to avoid

- “The AI autonomously beat Pokémon Red.”
- “The model learned the full game from scratch.”
- “A 100% validation score proves it understands training strategy.”
- “Identity-free features prove cross-game transfer.”
- “The project is close to a living Pokédex because the deterministic route is complete.”

Use the narrower verified claims. They are technically stronger because every one has a stated
authority boundary, denominator, source identity, and falsification condition.
