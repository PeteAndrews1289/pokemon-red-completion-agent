# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer-practice exploratory fit: promising TRAIN result, no promotion

The [session evidence](docs/evidence/red-trainer-exploratory-outcome-2026-09-17.json)
supersedes the prior prospective plan and defective initial fit. The factory
had created reserve Pokémon with owner ID zero; they could ignore commands
after a switch. Repaired reserves inherit the player's owner ID, and a live
switch-to-Water-Gun mechanic test now executes. Existing complete branch logs
were preserved; the defective cartridge captures and first fit are not valid
quality evidence.

Eight distinct assisted TRAIN scenarios, each at five declared timings, passed
strict branch/return admission and fitted move, attack-versus-switch control,
and switch-target heads. Four opening contrasts favored switches and four
favored attacks. They all derive from **one authenticated upstream root**;
timing siblings and assisted configurations do not supply independence.

Two retained failures matter. The repaired four-case model never switched in
its first fresh holdout and lost more HP than the frozen attack-only control,
despite both winning 5/5. The eight-case model then repeatedly switched and
failed all five trials of another holdout at an optional prompt with no living
reserve. Those trials were not replayed. The controller now declines a
targetless optional prompt and masks a second voluntary switch against the
same opponent until the model attempts an attack; this is an explicit safety
constraint, not learned post-switch value.

With the unchanged eight-case model and that controller, a newly frozen
Bulbasaur-versus-Pidgey TRAIN matchup produced **5/5 model wins versus 0/5**
for the frozen attack-only control. The model selected the opening switch to
Pikachu in every trial; all ten event logs were complete, with zero teacher
fallback or invalid actions. This is positive same-root synthetic TRAIN
transfer, not natural DEVELOPMENT or fixed-heuristic advantage. The model is
not ready for the final Astra promotion pass.

The remaining battle gate is four independent authenticated TRAIN roots with
four admitted scenarios each, including prompt, forced and depleted-attack
contexts, followed by disjoint natural DEVELOPMENT against frozen and fixed
controls. The old supply strategy remains retired; do not relabel variants,
replay failed trials, fit DEVELOPMENT or run the full game yet. Model137 stays
137 examples / 92 successes / 58 economy-qualified; Red stays 96/124 and
fresh acceptance 0/5. No battle authority, Red registration, cross-title
transfer or GitHub publication advanced. Pete decides when to push.

Next bounded objective: inventory and freeze independent short authentic
trainer starts without the retired supply path. Use Sol High, Fast off for
that evidence-collection work; reserve Astra High for a later promotion review.
