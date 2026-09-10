# Travel capture guards — engineering checkpoint, not new learning

## Mission check

- Capability: capture a useful missing species encountered while travelling, without changing the chosen destination.
- Learned authority: unchanged during this maintenance; unblock the next real model-selected acquisition outcome.
- Transfer test: varied species and successful/failed captures, resource contradictions, trainer/ghost/Safari exclusions, and route resumption in ROM-free scenarios.
- Cheapest falsifier: a needed encounter cannot return to the exact route boundary with verified stock and registration deltas.
- Time box: 20 minutes diagnosis plus 80 minutes integration/testing, then reorient.
- Stop: changed saved state, uncertain collection change, unsafe resumption or unsupported routing. No live input until the production connection is qualified.

## Verified diagnosis

The retained model47 Mansion1F endpoint was restored and inspected with **zero controller actions,
frames, predictions or fits**. The static world proposes a 26-step route to the chosen MansionB1F
source; the world overlaid with the actual current-map blocks finds no bounded feasible route.
Both planners correctly return zero steps for the current square.

This establishes a static-versus-observed route feasibility mismatch, not the exact puzzle solution.
The walking-only observer deliberately does not enable HM actions. The later Cut fallback error is
not evidence that teaching Cut would fix the route; the party already knows it. No door switch,
manual direction sequence, reset or replay was introduced.

## Implemented and tested

`RegisteredTravelCaptureHandler` is a **standalone, not-yet-enabled** interruption handler:

- Only an ordinary, cartridge-declared wild species missing from the supplied shared registration
  view is eligible. Trainer battles, unidentified ghosts, Safari encounters, already-credited
  species, no balls, no box space or a non-full party retain the declared fallback.
- One capture attempt per handler. A controller error or contradictory outcome never triggers
  an automatic flee or retry. Existing party specimens must remain intact and healthy.
- Successful capture needs one matching specimen in the expected active-box slot, matching local
  and shared registration deltas, real ordinary-ball spending and preserved other inventory/money.
- Resumption requires field readiness at the exact original map and coordinate.
- Failed catches retain real costs without awarding novelty. An escape before a throw may cost no ball.
- Typed capture errors preserve their original cause and receive the existing route executor's
  partial-failure trace. A catch followed by blocked navigation remains a **failed route with a
  retained registration**, not destination success or a separate learned encounter label.

**88 focused tests passed** across the new handler, routed recovery and the production route
executor; targeted lint and type checks passed. These include contradictory outcomes and real
route-executor composition with simulated game observations. They are not live capture evidence
or a full-suite pass. [Path-free engineering record](../evidence/red-travel-capture-guards-2026-09-10.json).

## Remaining integration and reorientation

The component is not called by gameplay. Its action/frame checks verify actual deltas **after**
the supplied capture port returns; the production port must additionally stop dispatch before a
hard limit. Reuse the existing live capture mechanics and recorded action chain; do not bypass
global budgets or reset their windows. Preserve the full-party restriction until roster-changing
travel recovery is separately qualified.

Add a prospective acquisition-only profile transition while reconstructing historical profiles
unchanged. Wire the walking, post-Fly and indoor-departure acquisition segments without enabling
incidental capture on healing, funding or evolution trips. Explicitly handle arrival where the
travel catch already satisfied the source's remaining demand; do not silently rewrite an unrelated
binding/navigation failure into success. Keep actual gains and parent goal completion separate.

This was one engineering-only session. **Do not expand into a new routing framework or another
general audit.** The next bounded objective is this runtime connection and its attribution tests,
then one fresh model47-selected lesson from the retained endpoint if a supported choice exists.
Budget roughly one focused session for integration; a live lesson is conditional, not promised.
If no safe connection or useful executable choice exists, stop and identify the concrete blocker.

## Model and product status

- Registered-objective examples: **47 unchanged**; shared/local registrations: **55 unchanged**.
- Physical specimens: **48 unchanged**. Latest saved endpoint and every failed outcome are retained.
- Gameplay stopped; **no new model fit**, sealed evaluation, Crystal execution or full-game replay.
- Travel milestone stays **1/3**: missed opportunities verified; production qualification and a
  productive model-selected outcome remain incomplete. This is not a whole-project percentage.
- Existing goal/destination learning still delegates mechanics to deterministic skills; this is
  not a demonstrated autonomous fresh-game player.

Codex implemented and tested the component. No external reviewer was used this session.
North Star and baseline stage exits are unchanged. The prior published commit's
[CI run passed](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/34488889316);
it does not validate this unplayed component.

Closeout regression check: **200 tests passed** including the 88 above plus product-focus and
roadmap tests. Documentation, active-state, whitespace and prospective registry checks passed.
The infographic was regenerated and visually inspected; its incomplete checklist is unchanged.
Recommended next-session setup: Astra High, Fast off. This is bounded integrity integration,
not a reason to start a broader high-effort audit.

Narrative: the useful lesson was that a collector must react to missing Pokémon encountered on the
way, not merely at its selected destination. We proved why the previous run missed opportunities,
then tested that opportunistic gains cannot erase later failures. Enabling and demonstrating that
behavior is the next step, not an achievement already claimed.
