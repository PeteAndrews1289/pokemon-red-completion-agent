# North star and anti-drift contract

Read this after [MISSION.md](MISSION.md) and before any roadmap, handoff, issue, or dated
checkpoint.

## The product

Build a transferable hierarchical agent that can enter a mainline Pokémon game, learn its
game-specific details, finish its story, solve its mechanics and puzzles, and build the declared
living Pokédex across the versions, trades, and event inputs that completion requires.

Pokémon Red is the first curriculum and evaluation environment. It is not the product.

An intermediate skill earning XP or surviving a checkpoint is not itself the learning milestone.
Collection development must be practical to complete, preserve living specimens, and ultimately
support a measured model-selected lesson. Keep partial progress, final goal success and learned
advantage distinct; inspect throughput before repeating many tiny deterministic training doses.

The deterministic teacher is an oracle, demonstrator, verifier, and emergency safety authority.
It is not the final player. A fixed route completing Red does not count as learned progress unless
the work also increases model authority or produces evidence needed to do so.

## Authority order

When documents disagree, use this order:

1. [MISSION.md](MISSION.md) — permanent product definition.
2. This anti-drift contract — permanent operating rules.
3. [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) — the one active lane, counters, time box,
   stop conditions, rigor tier, and prohibited actions.
4. [docs/model-first-roadmap.md](docs/model-first-roadmap.md) — broader development strategy.
5. [AGENT_COORDINATION.md](AGENT_COORDINATION.md) — current ownership.
6. [HANDOFF.md](HANDOFF.md) and dated checkpoints — evidence and historical state.

A newer date does not overrule a higher-authority document. A checkpoint that asks for work
contrary to the mission is stale by definition.

## Mandatory mission check

Before implementation, every active task must record:

1. **Capability:** what reusable playing ability this adds.
2. **Learned authority:** which choice moves from fixed code or teacher control to the model.
3. **Transfer test:** how the result is tested outside the exact state that produced it.
4. **Cheapest falsifier:** the shortest scenario that can prove the idea wrong.
5. **Time box:** when to stop investigating and reassess.
6. **Stop condition:** the observation that ends the lane without another patch or replay.

If learned authority and transfer both remain unchanged, classify the task as maintenance. Perform
maintenance only when it unblocks an already-named learned experiment, and keep it to the smallest
repair that does so.

The tracked source for the active state is `configs/active-product-focus.json`. CI validates it and
requires [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) to be its exact generated projection.
Inputs, preflights, CI passes, and teacher runs never advance its learning counters.

## Default development loop

### Fixed visual roadmap and session closeout

Use the [development infographic](docs/development-roadmap.md) and its
[stable baseline](configs/development-roadmap-baseline-v1.json) to locate each substantial task
within the full journey: useful Red decisions, sustained Red play, model-led Red story completion,
Red-era living collection, an unfamiliar compatible Red modification, Crystal, then later titles.
This baseline is subordinate to the mission and this contract; it does not authorize execution.

After **every completed work session**, and during a longer session after a substantial verified
capability, fit, gameplay result or blocker changes our position:

1. Update the active state and the [roadmap status](configs/development-roadmap-state.json).
   Preserve earlier reviews; record what changed, whether it deviated from the plan, and why.
2. Regenerate the infographic and its accessible Markdown with
   `python scripts/development_roadmap.py --write`. Inspect the visual after layout/content changes.
3. Refresh the handoff, next steps and YouTube/project narrative with the same factual result.
   Update this North Star only when requirements, operating rules or the agreed sequence change;
   do not rewrite its goals merely to make a session look successful.
4. Run the existing documentation check. It checks freshness locally; no extra CI workflow,
   mandatory outside audit, timed wakeup or minute-by-minute documentation loop is required.

At closeout, also share candid feedback with Pete when there is a meaningful concern, tradeoff
or recommendation. Do not manufacture feedback or confuse it with measured progress.

Stage exit criteria stay stable. Material changes require an explicit entry in
[roadmap decisions](docs/roadmap-decisions.md), retaining the previous baseline and recording
the evidence/user direction, tradeoffs and effect on the final product. Never silently replace
a difficult milestone with an easier one or count teacher completion as learned completion.
Any percentage must name its checklist and denominator; do not report a whole-project percentage
or turn equal checklist weights into a remaining-time estimate. Progress without a new learning
result must remain visibly classified as engineering or documentation.

### Runtime learning loop

Use authenticated development checkpoints and short randomized scenarios:

1. restore a relevant state;
2. let the model choose and act;
3. let the teacher intervene only at a declared safety boundary;
4. retain the state, choice, intervention, and outcome;
5. refit or update from audited evidence;
6. evaluate on unseen scenario instances;
7. promote authority only after outcome-based gates pass.

Do not replay Pallet Town to test a Saffron navigation change or a Cinnabar training policy.

## Full-run gate

A new clean-power full-game run is prohibited unless all of these are recorded first:

- the integration question cannot be answered by a shorter authenticated scenario;
- every component under test passed its unseen bounded gate;
- the run changes a named promotion or rejection decision;
- expected frame, action, and wall-time cost is recorded;
- failure diagnostics will retain the exact bounded cause;
- the active roadmap explicitly authorizes the run.

Full runs are final exams. They are not the training loop.

## Metrics that matter

Prefer outcomes that can expose failure:

- navigation success, path overhead, collision rate, displacement recovery;
- battle wins, objective satisfaction, HP/PP efficiency, interventions, illegal choices;
- experience per frame, wins per heal, blackouts, party rotation, level/evolution progress;
- multi-step goal completion and recovery from changed resources or state;
- living-Pokédex acquisitions, dependency-plan success, recognized version/trade/event blockers;
- zero-shot and post-adaptation performance in another title.

Teacher agreement is diagnostic. It is never sufficient evidence by itself.

## Anti-drift alarms

Stop and reassess when any of these occur:

- a second full replay is proposed for the same local question;
- a fixed direction string, cursor exception, or species-specific patch becomes the main work;
- CI is repeatedly repaired while no model authority is increasing;
- an overleveled party removes the decisions the model is supposed to learn;
- a teacher preference is copied without comparing outcomes;
- a failure receipt loses the information needed to explain the failure;
- more than one work session passes without a new learned decision or generalization result.

## Active decision — 2026-08-14

Red player v1 stopped safely during its first full teacher-supervised shadow run after 1,250
balanced-team battles. The run demonstrated that full replays are too costly, fixed Saffron
movement is visibly brittle, recovery is excessively conservative, and high offline accuracy can
hide concentrated live disagreement. No further full Red replay is authorized.

The active strategy is the scenario-based, model-first roadmap. Red sealed destination captures
and all frozen Crystal transfer contexts remain unopened until their existing protocols explicitly
authorize access.
