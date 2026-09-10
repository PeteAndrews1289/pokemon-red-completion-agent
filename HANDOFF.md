# Current development handoff

Updated September 10, 2026. Older reports are [historical](docs/history/handoff-through-2026-09-10.md).

## Goal and current scope

Build a learned player that finishes stories and accumulates verified Pokédex registrations across games. Red first; global registration, local owned flags and physical specimens remain distinct. No level-100 quota or simultaneous living-form requirement.

The model chooses goals/destinations; deterministic skills execute mechanics. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) before implementation.

## Last verified gameplay: AB01

- The model selected MtMoon1F from three alternatives and Paras was caught during travel.
- **60 registrations, 52 physical specimens, 48 living species** independently verified.
- One actual failed goal outcome fitted: **59→60 examples**. The catch does not change the failed goal label.
- Saved in MtMoon1F, map59 row18 col20; field-ready, outside battle, no pending trainer.
- Supplies: three capture items and138money. Gameplay is stopped.
- Cost:280actions/20,208frames/213.459seconds. The loop stopped after one of at most three goals.
- [Session report](docs/work-sessions/2026-09-10-search-budget.md) · [Learning evidence](docs/evidence/red-search-budget-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-search-budget-saved-2026-09-10.json).

Exact continuation identities:

- Episode: `red-registered-search-20260910-ab-01-causal`
- Checkpoint: `9091fd17a85c1c70e7f4d8110aac2e13da9fc771c6dff165faa81e326265036a`
- Model: `260efe95e444c5035283a613442f84da2528ea1ad9b8c95a17c997fa881ecb0c`
- Corpus: `3ac77782801f56728484b6ea7926ffd48985e7d5757eadfdc8d9c80db3d2b8b3`
- Played source: `d11089fafb32bc83acbe1bd445caf5757ef4008b`

Private paths, complete arguments and audit remain in private operational notes.

## Engineering and failure

The prospective search profile permits up to160legs while reserving encounter handling within the existing256semantic-action/32encounter caps. Historical profiles remain unchanged. Local/routed offers disclose the larger effort allowance.490targeted tests passed before AB; type checking covered470source files.

The first256-leg draft overlooked fleeing and non-displacing encounters consuming semantic actions. AA preparation was deliberately interrupted before controller input; its declaration is retained and never reused. A new regression verifies32flees plus160legs produce clean search exhaustion at225actions.

AB failed after the travel catch satisfied its destination: `TravelSatisfiedCaptureProvider` omitted three required capture-summary fields. The downstream codec rejected the report. The producer is now repaired with a cross-module regression, but that repair has not run live. No destination-survey/full-travel receipt survived the old wrapper error; do not claim the larger patrol caused the Paras catch.

PR238 merged as `ae2b09a1`. The current search session is a separate publication. Keep the played source in history; no force-push or retry.

## Next bounded session

1. Reconcile this handoff with private `CURRENT_AB_20260910.md`.
2. Inherit the AB declaration's complete history (including all Z transitions and the prospective search-budget opt-in), append AB01 checkpoint/source, and use model60. Include any actually recorded evolution transition. Never restore Z or replay AB.
3. Test one fresh bounded goal under the repaired reporting contract. Preserve failures, catch credit and actual costs; stop on an unsafe/unhandled failure.
4. Then inspect the existing isolated party-item-evolution draft against actual stock and stone availability. Do not commission a duplicate implementation. Connect one reusable mechanic to a real model-selected goal before broadening to NPC trades/fishing.
5. Allow45–60minutes including audit; update concise handoffs, evidence, infographic and narrative.

The travel-capture checklist remains1/3, not a project-completion percentage. Stone evolution and broader collection remain incomplete. No full replay, sealed Red, Crystal, consumed-trial retry or automatic specimen release. Same-lineage outcomes are not independent evaluation.

## External research

Flash3.8High completed read-only encounter/gap research. Accepted finite search budgeting and stone/NPC-trade priorities; rejected incorrect Clefairy-slot and working-Time-Capsule claims. Codex verified recommendations and integrated no Flash code this session. The existing item-evolution draft remains isolated.

Refreshed Gemini-group allowance around19:23UTC:95.19%five-hour/79.74%weekly remaining, resets approximately1h11m/28h1m. Shared account readings do not measure this session alone. Claude was not used.

Keep summaries current by replacement, not stacked status banners. See [roles](AGENT_COORDINATION.md), [roadmap](docs/model-first-roadmap.md) and the dated session report.
