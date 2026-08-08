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
| Tests and static checks | 8/10 | Roughly 1,984 non-integration test cases currently pass locally, with Ruff, documentation, public-artifact, and mypy gates. Forty-four legacy modules still use mypy `ignore_errors` overrides. |
| Architecture and modularity | 7/10 | Typed observations, objectives, skills, results, model loaders, and promotion gates are strong seams. The 134k-line Python surface and Red-specific chapter modules remain costly to reason about. |
| Learned battle control | 7/10 | Real model-controlled qualifications exist with no disagreement fallback. Evaluation is still dominated by the authored Red curriculum and lacks a second-title test. |
| Learned objective planning | 5/10 | A single process reached Hall of Fame through 20 model dispatches, but 19 dispatches offered only one executable candidate and fixed skills pressed the buttons. |
| Learned training strategy | 4/10 | Full battle/overworld authority passed 57,644 causal decisions safely. The candidate-set-only baseline also achieved 100%, so the run proves control integration rather than state-feature use. |
| Cross-title transfer | 2/10 | Several representations are intentionally identity-free, but no Crystal or other-title result exists yet. |
| Autonomous living Pokédex / level 100 | 1/10 | Target and planning foundations exist; autonomous collection, storage, evolution, resource planning, and long-horizon recovery are not integrated. |
| Portfolio presentation | 7/10 | The evidence is exceptional and the top-level capability boundary is now concise. The repository is still too large for a recruiter to absorb without a shorter demo and architecture tour. |

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

### 4. A better next learning problem

The next interface ranks variable-sized candidate sets for two strategic choices:

- which viable below-floor party member should train next; and
- which safe measured encounter band should be used.

Each candidate is represented with 27 normalized, identity-free features. Species IDs, move IDs,
party-slot identity, map IDs, area names, and memory addresses are excluded from the model vector.
The scorer shares one network across candidates and is permutation-equivariant. Unobservable ties
that the teacher resolves by hidden identity are excluded rather than mislabeled.

This is the first current training target designed so that a model must outperform a candidate-shape
baseline on variable decisions. Its train roots, sealed validation root, operational thresholds,
and no-validation-during-selection rule were preregistered before collection.

## Principal risks

### The learned surface is still small relative to the scripted surface

The teacher owns route discovery, navigation, menu execution, recovery, inventory operations, and
most tactical structure. Learned components sit at real boundaries, but those boundaries do not yet
compose into a clean-start teacher-free run.

### The Red implementation is much larger than the portable core

The Python surface is roughly 134,000 lines across 117 source modules, 23 scripts, and 120 test
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

## Dependency-ordered next work

1. **Qualify the trainee/venue ranker.** Collect two fresh training lineages, select
   hyperparameters using only train-to-train folds, open the sealed validation lineage once, and
   require a real margin over the shape-only baseline.
2. **Give that ranker bounded authority.** Run a fresh shadow root, then a separate causal root in
   which model-selected trainee and venue actually alter the lesson. Fail closed on invalid or
   unsafe selections; never silently substitute the teacher.
3. **Integrate the learned seams in one Red loop.** Combine objective dispatch, candidate training
   strategy, and learned battle control. Publish exact ownership counts and preserve every remaining
   fixed skill in the denominator.
4. **Establish a clean-start evaluation lane.** No captured starting state, teacher query, answer
   label, undeclared safety substitution, or restore. Score success rate across multiple declared
   roots instead of presenting one favorable completion.
5. **Run the Crystal microbenchmark.** Port one local navigation task, one battle task, and one
   training choice. Compare zero-shot, few-shot, and from-scratch performance. Treat breakage as an
   abstraction audit, not a demo failure to hide.
6. **Add recovery and correction learning.** A player that only acts on the happy path cannot
   generalize. Deliberately perturb position, party order, resource levels, and battle outcomes;
   measure whether it detects and repairs the deviation.
7. **Expand toward a living Pokédex only after transfer begins.** Collection is an excellent
   curriculum for navigation, capture, storage, evolution, party construction, and resource
   planning. It should reuse the portable player loop rather than become another fixed Red route.

## Portfolio narrative

### Thirty-second version

> I built a Pokémon Red agent as an evidence-driven autonomy project. First I created a verified
> expert teacher and independent referee that complete all 36 objectives through the Hall of Fame.
> Then I replaced decision boundaries one at a time with authenticated learned policies, using
> sealed lineages, causal emulator control, fail-closed safety, and receipts that distinguish real
> choices from single-option decisions. The current system has completed 57,644 consecutive
> model-controlled training decisions with zero faints, and the next benchmark tests whether its
> identity-free strategy transfers to another Pokémon game.

### Resume bullets

- Built a typed Pokémon Red agent and independent semantic referee that verify 312 checkpoints,
  all 36 objectives, the Champion, and Hall of Fame from clean power-on.
- Designed an auditable model-promotion pipeline with whole-lineage splits, exact SHA-256 artifact
  authentication, candidate masks, fail-closed causal control, and preserved rejected experiments;
  qualified a 57,644-decision live controller across 1,801 battles with zero faints or fallback.
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
5. The next representation was redesigned around variable trainee and venue choices that can
   actually falsify the learning claim.

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
