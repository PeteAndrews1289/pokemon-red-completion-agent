# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Battle curriculum needs better corrective decisions

The earlier natural near-boundary batch yielded five complete train examples
from eight selected captures (30/40 timing trials complete); its only baseline
regret was 0.025. A separate fresh cartridge experiment retained six actual
player faints as negative outcomes, but all choices tied before execution.

This session used two further distinct authentic train states, each with two
prospectively frozen frame targets. All 4/4 trials completed, producing two
non-tied expected-utility examples, but the frozen battle ranker chose a best
move in both (zero observed regret). Both states share one upstream train root;
they are not two independent lines of evidence. No fit, development opening
or model promotion. [Evidence](docs/evidence/red-battle-timing-and-contrast-2026-09-16.json).

Read-only inspection found the consumed timing-mismatch capture starts asleep
(status counter 2), whereas the successful look-alike starts awake. Sleep can
skip the pre-attack frame hook on a suppressed turn, plausibly explaining its
unequal counts. The original five terminals lack individual counts, so this
is a hypothesis, not a reconstructed root cause; do not replay them. Keep
sleep/recovery separate from attack-value comparisons and preserve the timing
equality gate.

Next: stop sampling nearly identical states. Freeze a small, more varied
train-only battle curriculum with predeclared meaningful attack alternatives
and disjoint upstream development roots; assess whether it can correct the
ranker before fit. Teacher-only state interventions are permitted if separately
marked, but cannot become final-player actions or held-out leakage. Red
remains 96/124,74 specimens,198 cash; Model137 and frozen battle authority
unchanged; fresh acceptance0/5. Gameplay stopped; no GitHub push. Sol High,
Fast off for this bounded design and preflight.

Earlier evidence: [live model-controlled attacks](docs/evidence/red-earned-learned-battle-2026-09-16.json) ·
[rejected assisted OHKO candidate](docs/evidence/red-ohko-expected-utility-2026-09-16.json) ·
[live faint qualification](docs/evidence/red-live-faint-outcome-2026-09-16.json).
