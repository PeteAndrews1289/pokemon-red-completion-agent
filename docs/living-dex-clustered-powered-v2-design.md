# Clustered powered V2 design

## Mission boundary

The product is a transferable hierarchical Pokémon agent that can finish stories and
build a living Pokédex across games, versions, trades, and legitimate event inputs.
Red is the first causal curriculum. Crystal is the first transfer falsifier. Neither
title is the product, and this design does not authorize gameplay or claim that a model
can play either game.

This gate answers one narrower question before more expensive work: **can the next Red
curriculum produce an informative fit and a statistically honest held-out decision
without counting correlated siblings as independent games?**

The canonical machine-readable contract is
[`configs/living-dex-clustered-powered-design-v2.json`](../configs/living-dex-clustered-powered-design-v2.json).
It is action-free and path-free. Its digest binds all thresholds, controls, stop rules,
and transfer boundaries.

## What the first 25 attempts established

The immutable prefix contains 25 attempted Red scenarios:

- 18 selected-arm causal train examples from 18 distinct upstream lineages;
- seven setup-only terminals with no learning target;
- all seven Red-supported option kinds in the settled corpus;
- selected candidate-position counts of 6, 8, and 4; and
- three successes and fifteen failures, retained without outcome shopping.

Those examples prove the collection pipeline works. They do not satisfy the existing
powered information gates: 60 settled examples, 50 distinct selected feature rows,
rank 16, eight examples per supported kind, eight successes, eight failures, and five
meaningfully varying outcome heads.

## Training allocation

V2 adds exactly 72 prospective attempts. Their selected-kind and candidate-position
allocations are frozen before outcomes and complete the original 90-row target when
combined with the 18 settled prefix.

| Quantity | Frozen value |
| --- | ---: |
| Existing settled examples / lineages | 18 / 18 |
| New attempts | 72 |
| New upstream train lineages | 36 |
| Maximum attempts in one train lineage | 2 |
| Minimum settled examples before powered fitting | 60 |
| Minimum distinct settled lineages | 50 |
| Maximum tolerated new setup-only attempts | 30 |

When two settled scenarios descend from one lineage, each receives half of that
lineage's total fit weight. A lineage with one settled scenario receives weight one.
Thus repetition may amortize game setup but cannot let one episode dominate fitting.
No lineage may cross train and development.

Every claimed selected-arm result is admitted. Setup-only terminals remain in the
attempt denominator, censored outcomes remain censored, and success or failure cannot
be used to keep, discard, replace, or reschedule a row. Passing the 60-row count alone
is insufficient: every information floor must pass simultaneously.

The old structural coverage floors also remain binding rather than disappearing in a
new schema. Training needs at least 18 semantic families, ten menu templates, five
locations, three values on every title-neutral pressure axis, three available options
per question, 50 distinct selected feature rows, and full support for every candidate
feature row. The behavior draw remains a blocked random permutation with full support
and a uniform marginal; no teacher choice becomes a label.

## Development power and the independent unit

The previously declared smallest useful paired effect remains unchanged:

- candidate-only success: 0.30;
- control-only success: 0.10;
- tie: 0.60;
- one-sided exact sign test at alpha 0.05; and
- target power 0.80.

With no forced losses, the computed minimum is 67 independent contexts. With up to
three incomplete cases retained and scored as candidate losses, the computed minimum
is **100 independent lineages**. At 99 lineages, worst-case power is
0.7996299998823; at 100 it is 0.8053956642931617.

Each development lineage contributes exactly one confirmatory question. Candidate and
frozen random, cost-only, and myopic-completion controls receive the same identity-free
question under same-reset forks. A candidate win means the candidate succeeds while
the entire frozen control envelope fails; a candidate loss means the reverse. Ties
carry no direction. An incomplete question is never dropped—it is a candidate loss.

The 100 development questions prospectively cover every supported Red option kind: 15
each for acquire and evolve, and 14 each for develop, manage-storage, resupply,
unlock-access, and explore. Focus positions are 34/33/33 across the three-option menus.
Development also needs at least 12 semantic families, five menu templates, five
locations, two values on every pressure axis, and feasible isolated same-reset/RNG
forks for the candidate and all three controls.

Because there is only one primary endpoint per lineage, the sensitivity table at
intracluster correlations 0, 0.25, 0.5, 0.75, and 1.0 retains 100 independent units and
the same worst-case power. The table derives this through the cluster design effect
`1 + (questions per lineage - 1) * correlation`; with one question per lineage, that
effect is exactly one at every declared correlation. Optional sibling diagnostics may
be reported, but they can never enlarge the confirmatory denominator.

Only one model candidate may enter development:

`floor(100 available development lineages / 100 required lineages) = 1 candidate`.

Model selection must therefore finish from training evidence alone before any
development branch is opened.

## Finite capacity and attrition

The prospective allocation requires 139 unused upstream lineages:

- 36 training lineages;
- 100 development lineages; and
- three contingency lineages.

The contingency supply may replace only a lineage proven invalid before any prediction,
policy branch, or outcome is opened. It may not replace an incomplete or unfavorable
endpoint. After branching, incompleteness consumes its original slot and is scored as
a candidate loss. If more than three development endpoints are incomplete, the exact
test remains conservative but the preregistered power guarantee no longer holds; the
endpoint must be declared underpowered and closed without promotion.

This document does **not** claim that 139 qualified lineages currently exist. The next
gate is an action-free private capacity census against this exact public contract. If
the finite supply cannot satisfy all three allocations without overlap, cloned-state
pseudoreplication, or outcome-aware selection, the lane closes and must be redesigned;
gameplay does not begin.

## Crystal transfer boundary

A powered Red pass is necessary but not sufficient for Crystal. Before classifying
Crystal opportunities, the shared capability vocabulary must explicitly represent at
least gender constraints, held-item workflows, phone contacts, time-of-day and weekly
events, renewable berries, breeding, happiness or friendship evolution, roaming
legendaries, and trade or trade evolution.

On the later Crystal test:

- abstaining on a prospectively supported mechanic is a failure;
- typed abstention on a prospectively unsupported mechanic is a correct boundary
  classification, but earns no completion credit;
- the frozen Red model must beat the full best-of-three control envelope; and
- Red initialization must beat the same architecture with zero initialization.

Trade has no learned Red kind coefficient and receives no zero-shot authority. Every
title needs its complete declared target catalog—151 for Red, 251 for Crystal, and the
declared total for later games. Each solo-obtainable acquisition graph is only one
subplan inside that title's version, trade, event, roaming, and one-shot availability
catalog.

The two Crystal “beats” requirements are boundary requirements, not a finished
experiment design. Their metric, denominator, smallest useful effect, multiplicity
treatment, and power must be frozen in a separate action-free transfer plan before any
Crystal execution. Until then the transfer claim is explicitly unsized and prohibited.

## Authorization and next falsifier

This design authorizes no private capacity read, private freeze, teacher access,
behavior draw, model fit, development outcome, Red gameplay, sealed Red evaluation,
Crystal execution, or full-game replay.

The cheapest next falsifier is the capacity census. It must prove—without running a
game—that a disjoint, outcome-blind allocation can supply 36 train, 100 development,
and three contingency lineages with the required kind, feature, pressure, location,
template, and control-fork support. Until that passes, powered fitting and gameplay
remain closed.
