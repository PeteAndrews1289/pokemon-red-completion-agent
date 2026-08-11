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

## First short-scenario checkpoint captured; preflight found a special-trainer gap — 2026-08-11

Published commit `2f3199e` passed exact-commit CI. The qualified teacher was then replayed only to
checkpoint 36/312, “Reached Cerulean City,” and wrote a private authenticated state whose objective
frontier exactly matches scenario `red-strategic-scenario-v2-001-train`. No scenario episode was
opened or consumed.

The first read-only preflight failed before planning. Cerulean's scripted rival carries the object
trainer bit but uses special movement/facing byte `$FF` and has no ordinary line-of-sight trainer
header. The trainer-sight decoder treated that legitimate script-driven encounter as a corrupt
zero-table result. The repair now asks for sight headers only from trainer objects whose cartridge
facing is one of the four supported line-of-sight directions; scripted trainer objects remain for
their map script rather than becoming route hazards. A regression turns every fixture trainer into
the scripted form and requires an empty header set. The command also now catches cartridge-decoder
errors at its privacy boundary instead of exposing a private traceback.

Because the repair changes executable source, the read-only preflight cannot be retried from a
dirty checkout. Regenerated prospective identities are source bundle
`24db34ae9a9c5c4618899fe62758813b85df9732a0a99559c503f4d80406eb34`, battle registry
`b4e16d8d45b588809782b6ee0e597bd39b64561242ba4d33f8e91619680686e6`, historical strategic
registry `e984a74d8b64272a5f2001a4d9f0d65ac2bee6e2a65dbf30fc1a7e5de4f0fae6` and historical
strategic teacher execution `0fd75b19c0dd718c5cc98114c4ee2ad690be8e51ed66d109a0c5a1c53f78071a`.
The v2 scenario registry remains
`c8c1899204ff5a351b0f7015bd3ff489508789a17b78cad0b55a5c9529c885f7`.

Immediate sequence: pass the complete local gate, commit and push this repair, require exact-commit
green CI, rerun scenario 001 in read-only mode from the existing private capture, and execute the
one-shot uncounted rehearsal only if both candidate routes pass. Authenticated live contexts remain
zero, collection remains closed and all 12 test scenarios remain sealed.

## Short-scenario rehearsal boundary implemented — 2026-08-11

The next execution boundary is implemented but not live-qualified. A new uncounted rehearsal
assignment commits to the canonical scenario and registry digests, exact private capture envelope
and state digest, checkpoint identity, committed source bundle and commit, and teacher execution
identity. Its split is always `unassigned`; the original scenario partition is authenticated
provenance only. The normal scenario accessor still refuses test, so a test specification cannot
become a rehearsal assignment.

The reviewed Red adapter covers all 18 candidate objectives and seven origin regions. Destinations
are approach maps—Bill's House, gyms, gates, Tower, Silph, Mansion and similar handoff points—not
claims that the corresponding bounded skill has completed. Live preflight requires an exact
objective frontier, a ready origin boundary and executable routes for every declared candidate
before it opens a one-shot private episode.

`scripts/rehearse_strategic_scenario.py` is the official two-stage command. Without `--execute` it
is read-only. With `--execute`, it records the identity-free choice before movement, runs only the
preregistered teacher's selected approach, records one measured outcome, writes a terminal marker
and immediately reloads the sealed episode. Promotion fails unless that reload contains exactly one
successful strategic decision. A complete, failed or interrupted episode identity cannot be reused.

No emulator run was performed in this source state. Live authenticated scenario contexts remain
zero and collection remains closed. The executable-source change regenerated the prospective
identities: source bundle `f1b6c605c299d36d6262ef16897a7d32a493e3b17b6e15405be134bf4d3268cc`,
battle registry `a03ee7a074c910340247bf1783450aaba3cf975f27b8a32b6984b6eaa9b76ca7`,
historical whole-root strategic registry
`7c8e74f982a1ef21cb17421ddf350d9903e8f63fb5122632430672439ab0d3ff` and teacher execution
`f6ab6fee9d17a8d62bc1d421ed20b0960fa20334ebfce94ddf14fa24e6c092c2`. The v2 scenario registry is
unchanged at `c8c1899204ff5a351b0f7015bd3ff489508789a17b78cad0b55a5c9529c885f7`.

Immediate sequence: finish the complete local gate, commit and push, require exact-commit CI, find
or create a private checkpoint whose verified objective set exactly matches scenario 001, run the
read-only preflight, and only then spend one uncounted rehearsal episode. Do not edit `src/` during
that emulator run. Do not rehearse the 12 test situations; the live learning rehearsal covers 24
train plus 12 validation situations, while test remains sealed for final evaluation.

## Scenario registry and powered admission gate implemented — 2026-08-11

The design stop below is now executable rather than aspirational. Strategic examples have a
candidate-order-invariant policy-context hash and selected-candidate hash. The partition audit
collapses replicates, rejects exact train/validation context overlap, rejects one context carrying
conflicting teacher targets, and requires at least 24 unique train plus 12 unique validation
contexts. The collection audit evaluates the route-cost baseline again at the unique-context unit
and requires at least six validation disagreements. Five disagreements leave the best possible
two-sided exact value at 0.0625 and cannot admit a model; six give 0.03125.

The new canonical
[scenario registry](configs/red-strategic-navigation-scenarios-v2.json) prospectively assigns 48
graph-legal quest frontiers: 24 train, 12 validation and 12 sealed test. It spans twelve teacher
objectives and candidate counts `{2: 21, 3: 22, 4: 3, 5: 2}`. Six validation rows are staged in a
region containing a tempting non-teacher objective and are explicitly labeled cost-baseline
challenge *hypotheses*. Live cartridge routing must confirm those disagreements before collection;
the registry does not claim them as measured facts.

This is still **zero collected scenario rows**. The parser verifies exact graph frontiers, teacher
order, automatic Hideout→Silph Scope and Champion→Hall-of-Fame effects, content commitments,
partition counts and family isolation. The normal accessor refuses test. “Sealed” means no test
scenario has been executed or had an outcome observed; their prospective specifications are public,
as the earlier sealed root seeds were.

The next live task is to qualify the authenticated short-scenario execution boundary described
above. After that, build the 36-situation train/validation rehearsal and require the collected
audit—not the registry—to prove 24/12 unique contexts and six validation baseline disagreements.
Do not open counted train or validation before the rehearsal passes, and keep test sealed until
final evaluation. See the
[scenario audit](docs/strategic-scenario-registry-audit-2026-08-11.md) and
[design receipt](docs/evidence/strategic-scenario-registry-design-2026-08-11.json).

Working prospective identities after this source change are scenario registry
`c8c1899204ff5a351b0f7015bd3ff489508789a17b78cad0b55a5c9529c885f7`, source bundle
`a70a0bef34c0810c637f85a5f658f3ef04430ba748ed19fba206c026ca591802`, battle registry
`2939bf9a06fb1b61e44f2369ae4de3d305d0914a971736f2774a921a40e26b85` and historical strategic
whole-root registry `2d6a71d22cb87ea107911b33e78a6a8a6bdbf621762fd0f9a5ffa0d31818d0ed`.

## Counted collection paused: three roots contained only three unique contexts — 2026-08-11

Do **not** open the repaired registry's first train root yet. A post-qualification experiment audit
found that the nominal nine strategic rows in the three successful historical train roots collapse
to three candidate-order-invariant policy contexts and four ordered inputs. Train and validation
would repeat Tower/Eevee, Koga/Warden and Dojo/Sabrina; unique decision IDs prove record identity,
not unseen strategic situations.

The statistical consequence is decisive. Against the observed 2/3 cost-only baseline, perfect 6/6
validation has one-sided binomial tail `0.0878`. Paired evaluation is correct but cannot rescue the
current rows: the baseline is wrong on only one of the three unique contexts. Repeating it in two
validation roots yields only two row-level discordant wins for a perfect scorer (two-sided exact
McNemar `0.5`), or one discordant win after correct context clustering. Increasing candidate count
also helps only when the extra destinations are genuine; it does not create independent contexts.

The repair rehearsal at `5ba39cf` remains qualified engineering evidence. Its source and private
episode are not changed or relabeled. The next work is the context-diverse experiment redesign in
[the design audit](docs/strategic-experiment-design-audit-2026-08-11.md): permutation-invariant
fingerprints that fail train/validation overlap, a preregistered scenario/context split, genuine
three-to-five-way choices, at least 24 distinct train/12 validation/12 sealed-test contexts, and an
exact paired primary endpoint. Short authenticated scenario episodes must replace repeated
47-million-frame games as the main ranking-data source; full games remain causal qualification.

The audit also found eleven tracked tests—not five—checking the literal private folder fragment
`PokemonRoms`. They now compare a public receipt against the actual `POKEMON_RED_ROM` environment
value when present, while retaining the broader home/volume/suffix guards. This changes tests only,
not the frozen teacher source bundle or registry.

## Attempts 1–6 completed; campaign retired for two bounded repairs — 2026-08-11

The first counted strategic campaign ran once through its first five train assignments and first
validation assignment under frozen source `5a8617e`. Do not rerun, overwrite or relabel those
roots. Results were:

| Attempt | Partition | Game result | Promoted strategic episode |
| --- | --- | --- | --- |
| 1 | train | failed at Diglett capture, checkpoint 87/88 | no |
| 2 | train | 312/312, 36/36, Hall of Fame | yes; 753,248 records |
| 3 | train | failed before Forest restock: ₽3,915 available, ₽4,200 required | no |
| 4 | train | 312/312, 36/36, Hall of Fame | yes; 759,275 records |
| 5 | train | 312/312, 36/36, Hall of Fame | yes; 791,502 records |
| 6 | validation | game passed 312/312 and Hall of Fame; final promotion refused after three lost battle-instrumentation records | no |

A strict read-only audit opened only attempts 1–6. The three authenticated train episodes contain
nine successful strategic examples and eighteen available candidates. Selected indexes are
`{0: 5, 1: 4}`, route costs span 21–178 and the route-cost-only baseline matches 6/9. The observed
training shape is internally consistent: story/next-challenge selects index 0,
story/remove-blocker selects index 1, and collection/improve-team selects index 0 after assignment
permutation. There is no train/validation decision overlap. The campaign is nevertheless **not
admitted for model development**: train is 3/5 promoted and validation is 0/2 promoted. The five
test roots remain sealed and were not inspected.

The failures exposed two bounded source defects. Direct Diglett capture could consume too many
balls, occasionally end without acquisition and leave the later 30-ball Forest reserve ₽285 short.
The teacher now uses the freshly caught Ground-immune Spearow for one bounded Peck before throwing
balls, and retains the target only after observing an HP decrease. Separately, a capture/training
battle that exited outside the shared runtime could leave a stale observer intent. The next battle
then produced one callback failure followed by lost move decisions—the exact 1+2 signature from
attempt 6. A fresh runtime entry now rolls that stale state into a new battle instance; same-intent
bounded reentry is unchanged.

Those repairs deliberately create a new campaign identity. Current source bundle is
`40c171b7d199faeb97217907067808e05a83074d178993ca5af0dcbf9c1274bd`; battle registry is
`7a1d73a44946c6c5a938668034d404aeb9d32dc677d59da88e86be66abe2503a`; strategic registry is
`8de74d114ce681af1681f395f0bd16c571d1954a928bc1a0b083ace4dfd8674e`; strategic teacher execution
is `7907b2a18b4092f7f565d0917ab1f8119f53273b0c932937338c4c5830d6c3b0`; and the new uncounted
rehearsal assignment is
`0450466c244197e95c41d3163b7ac8f1a56e835c1c99c91bf24cc671b6c6eb84`.

Commit `5ba39cf` passed exact-commit CI, and its uncounted rehearsal then qualified the repaired
source. It completed 312/312 checkpoints, 36/36 objectives and Hall of Fame, promoted 703,275
records (677,231,210 bytes), and strictly reloaded manifest
`df58b5536ce70f6e57ba0ac190d33787cc6fad278f2b6124a1a079c7f33fee79`. Its three strategic examples
all succeeded; candidate positions were `{0: 2, 1: 1}`, route-cost-only matched 2/3, one Tower-route
trainer interruption was retained, and there were zero movement labels or censored examples. See
the [qualification receipt](docs/evidence/strategic-rehearsal-repair-qualification-2026-08-11.json).

This once made the immediate next sequence appear to be opening the new registry's five train and
two validation roots. The experiment-design stop above supersedes that instruction: no counted root
may open until context diversity and paired evaluation are preregistered. Do not mix the three
historical train episodes with new-registry roots, edit `src/` during emulator execution, or open a
test root.

## Three-choice rehearsal passed; counted launcher now needs its exact replay — 2026-08-11

Published source `0640743` passed CI and completed a clean-power strategic rehearsal at 312/312
checkpoints, 36/36 objectives and Hall of Fame. Episode
`red-strat-reh-9d25c3a4e6af4bb1aba6560615cd7615c2d55f7bd9e868b7aa08afbeee84122f`
has manifest `52652a78a2109c4150463558271418e933910bc2715d97a09f2c62d0ccd14bff`,
711,601 records and three joined strategic choices. All three succeeded: Tower over Eevee, Koga
before Warden, and Fighting Dojo/Hitmonlee before Sabrina. The Tower route handled one trainer
engagement. Candidate order was assignment-permuted; selected indexes were `(1, 0, 0)`. The
cost-only baseline matched only 2/3 because the teacher deliberately rejected the shorter Eevee
route. This episode is unassigned and uncounted; never relabel it.

The audit resolved the earlier density question in favor of collection: three semantic contexts
per root, six available candidates, both answer positions, and a non-perfect cost baseline are
adequate for the small first scorer. The next obstacle was orchestration, not Pokémon behavior:
the CLI exposed only `--strategic-rehearsal`; `--collection-run` belongs to the older battle
campaign. The working source now adds `--strategic-collection-run`, accepts only committed train or
validation assignments, refuses sealed test roots, records with the exact strategic assignment and
strictly reloads the finished episode before reporting success. Private episode identity is
one-shot, so complete, failed and interrupted attempts cannot be silently overwritten.

Because that launcher changes `src/`, the qualified `0640743` rehearsal cannot authorize the new
counted campaign. Both registries have been regenerated. Current strategic registry is
`76807c8906c0a60150c3fde8ea44523c0edd437664abb35e378837042d7b6bc2`; source bundle is
`521b119a067a1ea6072291656ee9c7547b6933d288bb3d03617a8d7b83c82c24`; teacher execution is
`2a44de89969d8aafe08a3c3ed7efc4116b7cdcd62dbfbc177836637ffe2de313`; rehearsal assignment is
`39b951dc031656ab53d3c1cc0dbdf0bb850f4ff96520d568740000dbd3ea19f0`; first train assignment is
`5a41f61d9bf41ad7ebbe1917cc7ab58cd84312d65775dac2a056457939df704f`.
Immediate next action: finish tests, commit, push, require green CI, then run that new rehearsal.
Only after it passes may `red-strategic-v1-01-train` open. Counts remain train 0/5, validation 0/2,
test 0/5. Do not edit `src/` during any emulator run.

## The third rehearsal reached Mt. Moon and exposed a bidirectional search defect — 2026-08-11

Published source `c1e5d11` passed the exhausted-move Forest repair and the all-required-trainers
Bubble policy. Its exact clean-power rehearsal crossed Brock, all four required Route 3 trainers,
Route 4 and Mt. Moon entry, then failed at checkpoint 28 before Tower versus Eevee. Preserve the
third uncounted partial. It contains 5,301 records (7 objective decisions, 3,533 executions, 28
events and 1,732 snapshots) and **zero strategic navigation decisions**.

The trace disproved the timeout message. During the bounded Zubat search the teacher encountered
species `0x6B` at level seven on the return step and automatically fled it, because only the
outbound `up` step applied the target predicate. The final return movement also showed that a wild
transition can become visible one frame after its movement receipt. The search now applies the
same species/level predicate, drift checks, flee accounting and one-frame stabilization in both
directions. A unit regression delays the target until the return-step wait and requires the search
to return it without fleeing.

An exact-schedule, in-memory, uncounted replay then passed the complete Mt. Moon chapter: Zubat
capture, both cave floors, Rocket, Super Nerd, Helix Fossil, exit and Cerulean arrival through
checkpoint 36. It next exposed a separate chapter-handoff defect. The Cerulean Center route sent
two `down` inputs even though the second is a wall collision; historical success depended on the
first input being swallowed. The route now contains the one traversable down step and uses the
existing acknowledged movement helper. With that in-memory counterfactual the same schedule
continued through checkpoint 275 and 1,250 balanced-team battles, reaching levels
`(48, 48, 55, 47, 47, 47)` before the disposable diagnostic was deliberately interrupted so the
source could be frozen. This is strong repair evidence, but it was neither a completed rehearsal
nor a dataset episode and contains no strategic branch.

Immediate next action: publish this source and regenerated registries, require exact-commit green
CI, then execute only the new uncounted rehearsal assignment under seed `1710001`. Do not retry or
rename any of the three failed source-bound identities. If the new rehearsal reaches the strategic
branch, audit its pre-execution decision and measured outcome before opening a train root. Train is
0/5, validation 0/2 and sealed test is 0/5.

Current prospective identities are v95 registry
`b35491c2dd822ff5acc41781f87a5d08e05350a047b6f1ff2ee8bfafda349d3b`, source bundle
`255249795b61dc16f97e932af2773cd7a57c30cd24dcaf77e3242c09844cb906`, teacher execution
`5db046a56fae5719d1da511dafa8c3d0fab951edff43463a4583fc3f206d131c` and first assignment
`71432884d80c0cc96bbaa6a4a69209105140d9933ee83f13475edd0de13a0c1e`. Strategic registry is
`dbbc677946e777ecfee79a904631c8349b4dd3ec4dc52b3341f21f5c9af16054`, teacher execution
`7ba3f804d106dcd86ae6307982ae64227c606883ce1db1efb792f841245be19e`, rehearsal assignment
`4b4ba1b1823efd77c622443af2defc18711fcbe2fcfdfc187fce3912f81e30c8` and first train assignment
`ef3f9afe8fc59625c63475d4d9d9a636c9f4ce845c0f95dd9bfa059c76761a1e`.

## The first clean-power rehearsal found a real early-teacher defect — 2026-08-11

The prospective protocol is no longer waiting for a call site. An exact
`StrategicNavigationEpisodeAssignment` can now enter `run_qualified_play` only beside the same
trajectory sink and episode ID. The full teacher constructs a one-pending-choice observer and
substitutes one generated branch at the authenticated post-Hideout boundary. Ordinary `play`,
ordinary `record`, battle collection and every other chapter remain unchanged.

That branch plans two real cartridge-derived candidates from Celadon Center: story-critical
Pokémon Tower and the optional Eevee gift. It records the teacher's Tower selection before the
first route action, executes the exact bound plan through the generic acknowledge/interruption/
replan loop, and consumes either the measured success or the typed partial failure before control
returns to the Tower chapter. A route failure is re-raised only after its negative strategic
outcome has been joined. The generated Route 8 trainer is intentionally outside the frozen
74-battle schedule, and Tower's fixed reward accounting now begins after the generated approach so
that the extra trainer reward cannot corrupt the ten-battle chapter contract.

The CLI exposes this only through `record --strategic-rehearsal`. It loads the committed registry,
uses the one unassigned rehearsal assignment and its exact schedule, requires clean published
source, writes the assignment's exact collection/source/split/policy header, and reports
`counted=false`. The flag is mutually exclusive with ordinary schedule diagnostics and counted
battle collection.

A private captured-state preflight exercised the same new approach followed by the entire Tower
chapter: 28/28 checkpoints, ten required Tower battles, one strategic decision, one outcome, zero
recording failures, and a passing chapter report. This was a fast integration check against an
already-opened development state; it was not a clean-power root and cannot enter training.

The first invocation of the published bridge at `ef7ad72` stopped before private episode creation
or emulator startup. The strategic protocol allowed 96-character identifiers, while the private
store deliberately caps episode directory names at 80. Both the counted strategic prefix (86
characters with its digest) and rehearsal prefix (96) were therefore structurally unwriteable.
There was no episode, partial artifact or observed game outcome. The
protocol now derives 78-character counted and rehearsal episode names, enforces the storage ceiling,
and tests both assignment kinds through the real `PrivateArtifactRoot.begin_episode` boundary.
This is a harness qualification failure, not a Pokémon-run failure.

The next published source, `ab69be7`, reached the emulator under the exact rehearsal schedule. It
created an explicitly uncounted private episode, then failed at checkpoint 16/312 before the
post-Hideout strategic branch: the mandatory Viridian Forest Bug Catcher never cleared its bounded
battle gate. The retained failed episode contains 2,086 records (5 objective decisions, 1,508
executions, 16 events and 556 snapshots). It contains **zero strategic decisions** and cannot enter
training. Preserve it; never overwrite or relabel that source-bound identity.

The trace made the cause concrete. After the prescribed attacks, Weedle still had 6/27 HP,
Squirtle had exhausted Tackle, and the generic finisher kept confirming the empty move. A one-time
Bubble fallback was also insufficient because the cursor later returned to Tackle. The repair now
selects a live usable attack on every actionable battle-menu turn, leaves faint/victory dialogue on
the original bounded confirmation path, and replaces a historical 19-HP constant with the actual
transit contract: a living status-free lead may continue through HP-preserving flee corridors to the
Pewter heal; poison still requires the conservative reserve. The exact `1710001` schedule now clears
Viridian Forest at checkpoint 17 with 5 decisions, 1,340 executions and 16 events in an in-memory,
uncounted diagnostic. That replay opened no private episode or learning slot.

Published repair `1904b59` passed exact-commit CI and the regenerated rehearsal then proved the
Forest repair, Brock and the first Route 3 trainer before failing at checkpoint 23. The second
retained failed partial has 3,472 records (7 decisions, 2,339 executions, 23 events and 1,102
snapshots), still before any strategic decision. Trainer 1's three-Pokémon party reduced Squirtle to
7 HP; the teacher spent its one surplus Potion, protected the remaining twelve-item route floor,
then continued Tackle until Squirtle fainted with the last opponent at 2/30 HP. Bubble still had
30 PP. The cause was a single handwritten exclusion from the otherwise Bubble-based required Route
3 roster, not insufficient inventory. An in-memory counterfactual that adds trainer 1 to the same
STAB policy clears checkpoint 24 under the exact schedule with 7 decisions, 2,345 executions and 23
events. The source now applies Bubble to all four required Route 3 trainers without weakening the
Potion floor or victory gate.

The repair regenerates a new source-bound prospective rehearsal assignment. Immediate next action
after this exact source is committed, pushed and green is:

```bash
pokemon-red-completion record \
  --private-root <initialized-private-root> \
  --rom <private-red-rom> \
  --strategic-rehearsal
```

Do not edit `src/` while that run is active. Keep the earlier failed partial. If the repaired-source
rehearsal fails, preserve that partial too and inspect whether the strategic decision has its
measured outcome; do not relabel a development checkpoint or open a train/validation/test root. If
it passes, load it through
`load_assigned_strategic_navigation_episode`, run coverage and cost/shape baselines, then decide
whether one genuine choice per whole root is enough before opening train root 1.

Current prospective v95 identity is registry
`1212dfa5bd23deda55b22aee593d1e32cdbe20abf40bce9202040c26d41243cb`, source bundle
`990d365bf093e1b85765ea99673d92e1aae0c491d6ddc671d81bcb331e6a8bd1`, teacher execution
`09086e68615f50e101b2c094c7dc4d779ac33d621fe76faf4f98db8c10fde9d7`, and first assignment
`d90a5476e21f184950235edfe1f3fe64351ab3917ecb3c93820f22fb91581524`. It remains 0/10.

## Strategic collection roots are preassigned but unopened — 2026-08-11

The prospective registry
[red-strategic-navigation-collection-v1.json](configs/red-strategic-navigation-collection-v1.json)
turns the next modeling step into a real experiment. It preassigns twelve independent power-on
roots before any outcome is observed: five train, two validation and five sealed test. One separate
uncounted rehearsal root (`1710001`) is the only schedule intended for integration debugging. Every
root has a distinct 74-battle timing schedule, a one-attempt identity, and a path-free assignment,
lineage and episode ID derived from the canonical registry.

An audit after preregistration found that the counted roots had derivable assignments but the
declared rehearsal did not. That gap is now closed: the rehearsal has its own source-bound
assignment, episode and lineage, remains `partition="unassigned"`, and carries
`attempt.counted=false`. The binder accepts that one committed rehearsal identity but still rejects
a counted assignment on an unassigned decision.

This also closes a spoofing gap in the earlier seam. `bind_strategic_navigation_decision` previously
accepted arbitrary `partition="train"` and root strings. Any future non-unassigned binding now
requires the exact `StrategicNavigationAssignment`; its episode, lineage, partition, actor and
policy must all match. The normal learning accessor refuses test assignments. The committed loader
reads the registry and digest from Git, verifies the source bundle, and the CI regenerates both the
old v95 registry and this one exactly.

The output side now has the same fail-closed boundary. A committed assignment produces the exact
collection, source, split and policy blocks required in the private episode header. The assigned
episode loader refuses a merely local assignment, rejects any changed run, schedule, lineage,
partition, source or policy identity, and keeps test episodes sealed unless an eventual evaluation
call explicitly opens them. It then applies the existing strict decision/outcome join. The newer
checkpoint above connects that integrity shell to one clean-power branch; this section itself did
not consume a slot or create data.

The trajectory seam also no longer waits for a successful route before writing its choice. The
whole-run observer records the identity-free decision before the first route action, permits only
one pending choice, and joins exactly one later semantic outcome at the current execution step.
Power loss therefore leaves an incomplete episode rather than erasing the attempted decision, and
a sink failure marks the episode ineligible without changing game control. A final review also
requires the decision and outcome to use the identical sink and suppresses an orphan outcome when
the preceding decision write failed. The observer is now invoked around the post-Hideout strategic
Tower approach described above.

Route failures now preserve measured evidence too. `execute_route` attaches a typed semantic reason,
last observation, acknowledged prefix, movement requests, waits, replans, interruptions and resource
renewals to every route error, including replanner failure. The strategic boundary verifies that the
failed initial plan is the selected binding, converts only the portable fields to a negative
outcome, and omits the last map/coordinate. This closes the temptation to fabricate zero-filled
failures. The clean-power generated-route bridge now consumes either the success report or this
typed failure before propagating control failure.

No counted strategic slot has been consumed. The current counts remain **train 0/5, validation
0/2, test 0/5**. Two older source-bound rehearsals failed before reaching a strategic decision; the
newest repaired-source prospective rehearsal remains unopened. Existing Pallet, Fuchsia and Celadon
checkpoints remain opened development calibrations and cannot be relabeled. Strategic
decision/outcome recording is complete for one
branch; next run the single rehearsal, audit its genuine candidate
coverage, and only then decide whether to open train root 01. Do not start from the held-out test
roots while building that harness.

Registry SHA is
`9694bcab348d378d282c1b717d2842487709e43e765d71124583f160a8bca2d0`; strategic teacher
execution is `b144ade83a6522aec776477ed1c64d756f305ef3651b2f8793c48003549c1e2e`; source bundle is
`990d365bf093e1b85765ea99673d92e1aae0c491d6ddc671d81bcb331e6a8bd1`; rehearsal assignment is
`20d1a55e79799b8b8a478265c917bded28cfc319e1785f5ba8bb15a95c3edb86`; first train assignment is
`eb150e9709921d35cb11f195e28ec6d1c0c015e0e48ecdad0ae43825748c34b5`.

## The teacher rejected the shortest route and reached Pokémon Tower — 2026-08-11

Clean source `d3747f0758bd9a54b0c2ba2805b2bbf3b1fb38db` closes the first long,
non-cost-minimizing strategic route. From the authenticated post-Hideout Celadon checkpoint, two
real objectives were available: the story-critical Pokémon Tower at route cost 178, and the
optional Celadon Eevee pickup at cost 60. Qualified completion semantics selected the Tower. The
bound nine-map route crossed Route 7's underground passage, Route 8 and Lavender, acknowledged
174/174 movement requests, resolved one unavoidable trainer engagement and reached
`POKEMON_TOWER_1F` at `(17,10)` with zero replans. The public record is
[celadon-strategic-objective-route-probe-2026-08-11.json](docs/evidence/celadon-strategic-objective-route-probe-2026-08-11.json).

The route forced six real corrections before it passed. Ledge settlement had to remain declared
through plan composition; the objective planner had to apply the observed Saffron story predicate;
six tunnel entrances had to derive their retained outside-map context from bounded cartridge
scripts that write `wLastMap`; the executor needed an explicit battle-aware trainer interruption
contract; defeated-trainer field dialogue needed to count as active script control; and the public
evidence vocabulary had to normalize both battle and dialogue forms to one reviewed
`trainer_engagement` kind. None of the failed attempts produced a public success receipt or a
training record. Their source-bound sequence is preserved in
[celadon-strategic-objective-route-failures-2026-08-11.json](docs/evidence/celadon-strategic-objective-route-failures-2026-08-11.json).

The interruption handler is deliberately narrow. It chooses from the live active Pokémon's usable
moves using power, accuracy, type effectiveness, STAB, PP and Disable state; it receives no chapter,
trainer or species answer key. It can flee a wild encounter, finish an unavoidable trainer battle,
settle the corresponding field dialogue and return authority to the unchanged route binding. It
does not make arbitrary menus or every Kanto script safe for generated routing.

Do not promote this result. There are now **three unassigned live strategic calibrations**, but
still **0 train and 0 validation records**, no frozen numeric feature schema and no strategic
navigation model. The Celadon decision proves that semantics can beat the route-cost baseline; it
does not provide an independent train/validation estimate because it was a development root. The
next modeling step is to preassign whole, independent roots to train or untouched validation,
collect every consumed success/failure/interruption, inspect the implemented baselines, then freeze
features and train only if the coverage supports it.

The prospective v95 identities at this checkpoint are registry
`338e86c602c852080b5e066203cb489579f6a61442501be21b576a501cdf8994`, source bundle
`542b780c6a9f599d467bdd52afb856a1972c00a976ddc46c3261214bbf52d5a0`, teacher execution
`6bceb2b4e4849481c51b5fb586f1bac71ecb817f3768058f3c00b3d2acb13e0c`, and slot assignment
`068fd00857df4c72565f445824a4f4453ac6fb745f5c174df7376298bf0cc283`. Regeneration still does
not open v95; counted collection remains 0/10.

## Strategic navigation is collectable, but no strategic model exists — 2026-08-11

Source checkpoints `33dd0d81600b818d121a420a158d91479adc161f` and
`f43219d` define the learning boundary the routing work was meant to reach. A strategic decision
contains a real set of at least two destinations, portable need/origin/destination tags,
availability and deterministic route metrics. The selected destination binding is retained for
execution, but the policy view omits every binding reference, map id, coordinate and movement
action. Exact directions stay in `route_plan.py` and `route_executor.py`; they are not imitation
labels.

The follow-up checkpoint closes the durable data path. Only a reviewed cross-title semantic tag
vocabulary may enter policy input. Free-text failure, replan, interruption and resource values are
replaced by bounded semantic enums. A private trajectory stores the identity-free choice and a
paired consumed outcome. Its reader rejects extra identity fields, title-specific tags, malformed
candidate metrics, split/provenance drift, duplicate decisions, missing outcomes and multiple
outcomes. Successful teacher routes supply imitation labels; failed routes supply negative outcome
evidence; an external power loss is censored rather than silently called failure or rerun. Whole
root lineages, not individual decisions, form train/validation boundaries.

Audit checkpoint `bcd9935` closes an in-memory integrity hole: the frozen example dataclass had
contained a mutable nested policy dictionary. Policy inputs and every candidate mapping are now
recursively immutable after canonical parsing, with regressions that reject top-level and nested
mutation.

Collection-audit checkpoint `92a8b80` makes authenticated loaded episodes directly auditable,
retains replan/interruption/resource/failure semantics after parsing, and reports partition
leakage, coverage, outcomes, route-cost ranges and two simple baselines. It also closes a more
important provenance bug: only a successful `deterministic_teacher` action can become a positive
imitation target. A successful learned-policy action remains outcome evidence and cannot label
itself as the teacher answer.

Clean source `bf3fc76d8c571fd56acdb81da7aaed4fa97e5255` then proved the complete binding
seam with one explicitly unassigned live calibration. From post-Pokédex Pallet, home and Viridian
Center were both available safe hubs at costs 15/87 and 14/86 route steps. The lowest-cost teacher
selected home; the executor acknowledged 14/14 movements, crossed the exact warp, released controls
and changed no ROM-adjacent artifact. The identity-free trajectory retained only semantic tags,
metrics and selected index. Record:
[pallet-strategic-safe-hub-route-probe-2026-08-11.json](docs/evidence/pallet-strategic-safe-hub-route-probe-2026-08-11.json).

Clean source `ba2c224f89d621fca6ef45a88fcff2e0d0880738` then extracted the common route
evidence projection and recorded the first genuine semantic branch from an authenticated
post-Safari state. The two available candidates were Koga's Gym (`challenge`, `story_progress`,
cost 21, 20 steps) and the Warden/Strength objective (`acquire_resource`, `story_progress`, cost 24,
23 steps). Qualified completion order chose the Gym; the generic executor reached `FUCHSIA_GYM`
after 20/20 acknowledged movements with zero replans, interruptions or resource renewals. The
identity-free projection contains semantic needs, candidate metrics and selected index, but no
destination binding, map id, coordinate or arrow action. Record:
[fuchsia-strategic-objective-route-probe-2026-08-11.json](docs/evidence/fuchsia-strategic-objective-route-probe-2026-08-11.json).

This earlier checkpoint is superseded by the Pokémon Tower result above. There are still **0
train/validation strategic navigation records**, but now three unassigned calibrations: one trivial
plumbing check and two genuine branches, including one that rejects minimum route cost. There is no
frozen numeric feature schema and no strategic navigation model. The old
`navigation_dataset.py` contains
individual direction traces for control diagnostics only; its public summary now says so and stays
`promotion_eligible: false`. The next work is to instrument genuine multi-destination branches in
preassigned, independent teacher/generated roots, preserve successes/failures/interruptions, then
inspect coverage before choosing a numeric representation.
Current prospective registry SHA is
`338e86c602c852080b5e066203cb489579f6a61442501be21b576a501cdf8994`; source bundle is
`542b780c6a9f599d467bdd52afb856a1972c00a976ddc46c3261214bbf52d5a0`; teacher execution is
`6bceb2b4e4849481c51b5fb586f1bac71ecb817f3768058f3c00b3d2acb13e0c`; slot assignment is
`068fd00857df4c72565f445824a4f4453ac6fb745f5c174df7376298bf0cc283`.

## Ordinary Red/Blue acquisition reach is cartridge-complete — 2026-08-11

Clean source `7fb928b31dc36667bcdcd50b32706b02d491ebb3` and evidence commit `81a990f`
close the old 108/112 lower bound. The cartridge decoder now joins wild grass/cave tables, rods,
evolution, ten in-game trades and 30 scripted opportunities in each title: three Oak starters, two
direct gifts, two Dojo gifts, three fossils, six repeatable Game Corner prizes and fourteen fixed
encounters. Static encounters come from map object blocks; Snorlax comes from exact battle-script
writes. Independent fixtures kill stride, terminator, BCD-price, starter-counterpick and
gift/fossil-operand mistakes.

The exact existential reach is **135 species on one title alone** and **139 with a trade partner**.
Without a partner, four trade evolutions remain absent; with one, only the other title's eleven
version exclusives and Mew remain. Choice groups remain explicit: a cartridge being capable of
producing both fossils across different saves does not mean one save can hold both without a trade.
Red and Blue were decoded and compared independently. The public record is
[acquisition-routes-2026-08-11.json](docs/evidence/acquisition-routes-2026-08-11.json).

This completes ordinary retail acquisition knowledge, not autonomous living-Pokédex execution.
Storage, party rotation, catch execution, resource replenishment, evolution scheduling and
multi-run/trade orchestration still need live authority. Mew remains outside ordinary cartridge
reach.

## Victory Road now crosses rooms and renews its own Repel — 2026-08-10

Clean executable source bundle `2c31afaf232726ea7c4b7a50b6bbac7d03eed8fc019c0e799af205d3cce84e35`
and probe commit `254b846ff11bcb31d0a4359278ea43c2795fbdbc` make step-bounded resources
part of the neutral traversal contract. A snapshot carries remaining effect and carried renewals;
unknown, depleted and active are distinct. The generic executor asks a title adapter to renew before
movement and stores the receipt. Red's adapter dismisses the expiry prompt under a bound, consumes
exactly one observed Repel-family item, verifies the new counter, unchanged player/party, exact bag
delta and restored controls, and fails closed without state or inventory. Strength uses the same
manager between puzzle steps without weakening its protected-state check.

The authenticated full-chain probe removes all three older authored gaps. The 1F→2F and 2F→3F
direction strings are replaced by live mutable-terrain plans of **51** and **56** steps, each ending
in an exact cartridge-decoded warp. Every movement was acknowledged; the first route replanned once
around live trainer sight and neither route entered a battle. The 14-step “walk until Repel expires”
setup is deleted. The first Max Repel naturally reaches zero during the third Strength search at 3F
`(1,9)`; one prompt confirmation settles, one final Max Repel is consumed, the counter becomes 250,
and the same search resumes. All five switch/hole events pass with **267 derived puzzle steps** and
**65 pushes/drop receipts**. Record:
[victory-road-composed-resource-chain-probe-2026-08-10.json](docs/evidence/victory-road-composed-resource-chain-probe-2026-08-10.json).

The third phase is now 67 steps / 54,305 explored states because it begins at the natural 3F warp,
not after the deleted 14-step expiry preamble. That is the new honest baseline. Next qualify repeated
Cut, then joint local-plus-macro pricing, acquisition coverage, strategic navigation records and the
Crystal adapter. The post-final-switch route to Indigo remains authored completion-teacher behavior;
generated routing remains outside counted-run authority and v95 stays **0/10**.

## The same floor is closed, unknown, then open — 2026-08-10

Clean executable source `40a05d160b66e5e8e00f4ca95bb76841752694eb` adds opaque semantic
requirements to exact directed local edges and observes Red's Saffron guard flag as one of three
states: satisfied, unsatisfied or unknown. Only satisfied facts become route capabilities. The
first binding covers both rows and both directions across the Route 7 guard-house threshold;
unknown memory is deliberately unavailable rather than guessed open.

The authenticated post-Erika probe reaches the west side with Fresh Water in the bag. Static
cartridge terrain still supplies a five-step corridor, but the observed `$00` story byte and a
synthetic unknown observation both make that corridor unroutable, and the semantic planner sends
zero inputs. The existing teacher gives the drink to the guard. Live RAM changes to `$40`, Fresh
Water disappears, and the same immutable graph admits the predicate. Generated plans then cross
westbound and eastbound, leave through the exact Route 7 return, and continue through the east
connection into Saffron. All **11/11** movements settle with no interruption or replan. Record:
[saffron-story-gate-route-probe-2026-08-10.json](docs/evidence/saffron-story-gate-route-probe-2026-08-10.json).

The first live attempt also corrected a general route-composition error. Vertical doorway returns
play a one-tile walk-out after the destination warp; horizontal pass-through gates settle on the
outside warp itself. The old uniform offset predicted Route 7 `(10,19)` while live RAM correctly
reported `(10,18)`. The corrected composer and regression are part of the evidence-bound source.
One story predicate is now qualified, not every lock or script in Kanto. Next make resource renewal
first-class and replace Victory Road's authored room-to-room and repel-boundary travel. Repeated
Cut, joint macro/local pricing, acquisition routes and strategic navigation records follow.
Generated navigation remains outside completion-run authority and counted v95 remains **0/10**.

## Trainer sight is route state, not a blocked edge — 2026-08-10

Clean executable source `95e8b827668a165b6ca707dceb594460a5bf2d42` joins two independent
cartridge structures. Map object events supply each trainer's sprite slot, class/set, coordinate
and initial facing; the map script's twelve-byte trainer headers supply engage distance and the
defeated-event address. Live current-map objects then supply rendered facing and moved coordinates.
An undefeated trainer's bounded line is projected as a temporary `trainer_sight` hazard, distinct
from solid occupancy. A defeated trainer exposes no line, unknown event memory stays conservatively
active, and a triggered walk-up is a typed `trainer_engagement` interruption rather than evidence
that the requested movement edge is blocked.

The first authenticated probe deliberately asks for the unsafe route. From the post-Giovanni
capture, the teacher reaches Victory Road 1F and the Strength search again executes its 58-step
switch plan, ending at `(12,17)`. Both 1F trainers are undefeated and off-screen. Cartridge data
correctly reserves the female trainer's right-facing `(5,8)–(5,9)` line and the male trainer's
down-facing `(3,3)–(4,3)` line. The unprotected 50-step exit approach enters the male line. At
player `(5,3)`, before sending Up toward `(4,3)`, the executor records exactly one
`trainer_sight` replan and selects a five-step safe suffix. It acknowledges **50/50** movements,
reaches 1F `(1,2)`, observes no engagement or battle, performs no retry wait, releases controls,
and changes no ROM-adjacent artifact. Record:
[victory-road-trainer-sight-route-probe-2026-08-10.json](docs/evidence/victory-road-trainer-sight-route-probe-2026-08-10.json).

Live falsification corrected one subtle first draft before publication: an off-screen sprite slot
retains a stale/default facing byte. Live facing is therefore authoritative only while the trainer
is rendered; otherwise the cartridge object's facing is used. The final receipt is bound to that
corrected source. Standard fighting-map trainer headers are now represented; special scripted
trainer-like objects such as rivals, bosses and quiz-selected fights remain separate fail-closed
semantics. The next gate is one independently observed story passage in both closed and open state,
then resource renewal and replacement of the remaining authored Victory Road travel. Counted v95
remains sealed at **0/10**.

## Strength now survives switches, hiding and a cross-floor drop — 2026-08-10

Clean executable source `8dbee6f4235273eb2b04c45b457ac53ad2d260b0` extends the bounded
player-and-boulder search through the full Victory Road puzzle chain. The authenticated
post-Giovanni replay runs five searches: 1F switch, 2F switch 1, 3F switch, 3F hole, and 2F switch
2. Together they explored **44,525 states** and executed **247/247 derived transitions**: 189 walks,
57 ordinary pushes and one terminal drop. The phase totals are `(58, 25, 47, 87, 30)` steps and
`(3,934, 2,519, 31,841, 572, 5,659)` explored states. All switch/hole event flags set, every input
returned to readiness, controls were released, and no ROM-adjacent artifact changed. Record:
[victory-road-strength-chain-probe-2026-08-10.json](docs/evidence/victory-road-strength-chain-probe-2026-08-10.json).

Two engine distinctions are now mandatory. First, `$FF` image index means off-screen, not absent.
The reader resolves the current map's sprite/global-toggle list against `wToggleableObjectFlags`,
so hidden 2F boulder 13 is excluded before the hole, 3F boulder 10 disappears after the drop, and
the same cross-floor object appears on 2F at `(16,23)`. Second, Victory Road 3F reads and clears
`BIT_PUSHED_BOULDER` every frame. The executor therefore samples `BIT_BOULDER_DUST` immediately
after the held pulse, then requires the exact settled player/all-boulder state; it does not weaken
the receipt when the room script consumes the persistent bit.

The evidence is deliberately narrower than “generated Victory Road.” The old inter-room routes
(51 and 56 steps) and the 14-direction repel-expiry setup remain authored. An attempted shortest
generated exit exposed the next real navigation gap: trainer sight is viewport- and script-state
dependent, so static collision plus current coordinates is insufficient. Do not fold that failure
into Strength. The newer checkpoint above closes standard trainer sight; one story-gated passage
and the authored room-to-room travel remain. Generated navigation stays outside the counted
completion run, and v95 remains sealed at **0/10**.

## Strength is bounded player-and-boulder search — 2026-08-11

Clean executable source `a3f95287f0b944926cadb2287488f4d662639031` closes the first
live Strength puzzle. `PokemonRedStateReader` now reads every pushable boulder from the complete
current-map sprite table, including `$FF` off-screen objects. Capability requires Rainbow Badge, a
complete observed party and a living Strength holder. The planner runs bounded Dijkstra over
`(player coordinate, every boulder slot/coordinate)` rather than turning Strength possession into
an open edge. Ordinary movement avoids every current boulder; a push is admitted only when the
square beyond is a cartridge-decoded ordinary walk, not stairs, an elevation violation, another
boulder or a supplied non-boulder object.

The authenticated probe starts from the post-Giovanni capture, lets the qualified teacher reach
Victory Road 1F `(17,8)`, and stops before the old authored boulder route. It activates Strength
through the observed party/menu row, reads all three live boulders, and searches for any boulder on
the cartridge script's switch coordinate `(13,17)`. The resulting plan costs 75 engine attempts:
**57 controller steps, 39 walks, 18 pushes and 3,845 explored states** under a 100,000-state bound.
All 57 live transitions passed. Every push kept the player stationary, moved only sprite 5 by one
square and exposed the engine's pushed-boulder flag; the final event opened the barrier. The probe
used 178 post-boundary actions, released every control, preserved party/bag state and changed no
ROM-adjacent artifact. Record:
[victory-road-strength-state-search-probe-2026-08-11.json](docs/evidence/victory-road-strength-state-search-probe-2026-08-11.json).

Three live corrections are part of the contract. Strength's active flag appears two confirmations
before its text/menu boundary is actually closed. One frame-safe held direction spans the engine's
two internal push checks, so a push is one controller pulse and leaves the player behind; advancing
requires a separate walk into the vacated square. Finally, the dust animation temporarily hides the
boulder at 60 frames, then restores its exact slot/coordinate and input control by 120 frames. Do
not shorten that settle or treat the transient disappearance as a solved switch.

This section is the historical first-switch milestone. The newer checkpoint above supersedes its
remaining-work paragraph: 2F/3F switches and the cross-map hole now pass, while inter-room travel,
trainer sight, story-gated passages and repeated Cut remain separate gates.

## Cut is an observed mutation, not a possession edge — 2026-08-10

Clean source `8a0b794a11c5b5e9a93878c341cd6152f9af6864` closes the first map-mutation
gate. `PokemonRedStateReader` now reads the active unpadded block grid from Red's bordered
`wOverworldMap` buffer. Terrain can be rebuilt from those explicit mutable block ids rather than
quietly returning to the cartridge's initial layout. Independent nonuniform fixtures exercise the
live-buffer stride, dimensions, block replacement and exact affected step cell.

Cut capability requires the Cascade Badge, a complete observed party and a living move holder. The
planner may use the cartridge's nine block swaps to choose a reachable cutting stance and predict
whether the replacement is useful, but that prediction is never execution authority. It walks only
to the stance. The bounded Generation I field adapter then faces the tree, selects the observed
holder and Cut menu row, keeps the player at the source coordinate, and accepts success only when
the tile in front changes, exactly one expected live block changes, party/bag state is preserved and
input control is restored. Only then does the caller reread the entire block grid, rebuild terrain
and plan the crossing.

The authenticated Celadon probe selected source `(20,46)`, target `(20,47)` and block `(10,23)`.
Live RAM acknowledged block `$35 → $4C`, tile `$3D → $2C`, one changed block, and restored control.
The former tree changed from unstandable to standable; a newly computed path entered it as the first
step and continued to `(20,48)`. Center exit, approach, crossing and return acknowledged **60/60**
route movements; the full field-menu run used 80 actions / 3,576 frames, returned to Center `(3,3)`,
released every control and changed no ROM-adjacent artifact. Record:
[celadon-staged-cut-route-probe-2026-08-10.json](docs/evidence/celadon-staged-cut-route-probe-2026-08-10.json).

Clean source `b449caf37c74b6e39f0760f5907bc369ea0a1f42` extends that contract across every
tree in the same live Celadon map. A reusable selector chooses only one reachable mutation from the
current grid. The caller must execute and verify it, reread RAM, rebuild terrain, and call again;
there is no speculative Cut sequence and no durable Cut edge. The first iteration repeated block
`$35 → $4C` at tree `(20,47)`. The second began from the newly observed grid, selected distinct
block `(16,17)`, observed `$32 → $6D`, and crossed tree `(32,35)`. Both field actions independently
proved one changed block, tile `$3D → $2C`, stationary player, preserved state, and restored input.
The complete run acknowledged **110/110** route movements, safely replanned once on the Center
return, ended at `(3,3)`, released controls and changed no ROM-adjacent artifact. Record:
[celadon-repeated-cut-route-probe-2026-08-11.json](docs/evidence/celadon-repeated-cut-route-probe-2026-08-11.json).

This closes repeated/multi-tree Cut under the observed-mutation contract, not general navigation
authority. Cut grass remains an optional strategic action, generated routing remains outside the
completion run, and counted v95 stays sealed at **0/10**.

## Macro and local routing are now one priced search — 2026-08-11

Clean source `758ab6dedc8fd492c641a174f9da4376d3656ca6` removes the old ordering error in
`plan_route`. The former implementation chose a map sequence using only `MacroEdge.cost`, then
attempted to compose local approaches. A topologically cheap edge could therefore be locally
impossible, and an early cheap border coordinate could lead to a much more expensive next room.

The joint frontier is `(map, coordinate, movement mode, retained outside map)`. It expands every
reachable exact connection endpoint and warp, prices local edges plus declared passage cost, keeps
terminal-coordinate cost inside the same optimization, and retains alternate entries until their
downstream cost is known. The shared `advance_macro_state` prevents topology-only and composed
searches from drifting on nested returns. Local targets are solved in batches and cached by entry
state: an initial correct implementation made 30,892 separate local searches and needed about
12.3 seconds for Pallet→Celadon; the batched version completed the same query in about 0.17 seconds
on this machine.

Red and Blue provide the cartridge falsification. Topology alone chooses map ids
`0→12→1→13→2`, attempting a direct Route 2→Pewter border that has no locally reachable exact
coordinate. Joint search rejects it and derives
`0→12→1→13→50→51→47→13→2`: Route 2 south gate, Viridian Forest, north gate, then the reachable
Pewter border. Both cartridges agree on combined cost 317 and 314 executable acknowledgement
steps. The [public audit](docs/evidence/joint-route-pricing-audit-2026-08-11.json) is static
cartridge evidence with no dynamic blockers or live-execution authority. The next navigation lane
is acquisition-route coverage, followed by strategic navigation records; generated routing remains
outside the completion teacher and v95 remains **0/10**.

## Visible occupancy is observed before the route acts — 2026-08-10

Clean source `1c6eb31fc61f40e440c8c33482f88bb3c0dd9fbe` closes the direct visible-object
gate. The revision-pinned Red/Blue adapter reads `wNumSprites` plus the parallel 16-byte sprite-state
tables, excludes player slot zero and the engine's `$FF` hidden/off-screen image marker, and projects
each remaining sprite's live map coordinate into the neutral traversal snapshot. Battle state never
decodes overworld sprite RAM.

The executor checks that temporary overlay before an ordinary same-map walk. If the candidate target
is occupied, it requests a replacement without sending the movement. Visible objects are deliberately
not copied into the durable blocker set: an NPC that leaves may become traversable again. Only an
input that remains unconsumed after the existing bounded settle becomes durable fallback evidence.
ROM-free regressions cover pre-input observation, an object appearing during settle, and a departed
object disappearing from the next replan request. The address fixture uses literal upstream values,
not constants derived from the implementation under test.

The authenticated post-Blaine falsification intentionally built Cinnabar's local graph with **no ROM
object positions blocked**. Cartridge events selected a stationary object at `(6,14)` and a goal at
`(6,13)` whose 18-step preferred candidate crossed it. Live state exposed both current sprites as
the player reached `(6,15)`; the executor recorded `reason=visible_object`, sent no Left input into
the occupied square, replaced the suffix with four steps, reached the goal, and returned to the exact
`(12,11)` shore origin. Across Center exit, outbound and return it acknowledged **43/43** movements
from 43 requests, used one transition wait, released all controls and changed no ROM-adjacent
artifact. Record:
[cinnabar-visible-object-route-probe-2026-08-10.json](docs/evidence/cinnabar-visible-object-route-probe-2026-08-10.json).

This proves currently rendered occupancy, not omniscient object state. Hidden/off-screen objects,
closed story passages, Cut mutations and Strength pushes still require their own semantics; bounded
failed-step discovery remains necessary. Next implement Cut as an observed block replacement, then
Strength and one independently proved closed/open story gate. Generated routing stays outside the
completion run and counted v95 remains sealed at **0/10**.

## Stateful Surf is a live cartridge-derived route — 2026-08-10

Surf is now an explicit movement-mode transition rather than a static permission bit. The shared
local search runs on `(coordinate, mode)` state. Its Generation I adapter derives water and shore
edges from cartridge tiles and pair restrictions; entry is a typed `field_move`, water travel stays
in `water`, and stepping back onto shore returns to `land`. Live capability requires Soul Badge,
complete party memory and a living member that actually knows Surf. Forced Cycling Road state and
Seafoam B4 remain closed rather than being guessed open.

The bounded title adapter turns `surf:<direction>` into the real START → POKÉMON → member → Surf
menu sequence and accepts it only after both the exact target coordinate and
`wWalkBikeSurfState == SURFING` appear. The generic executor also now waits for an in-flight action
to settle before it can infer a blocker. That ordering matters: the first live attempt nearly
blacklisted a reachable square while Red's walk animation still exposed the source coordinate.

Live falsification then found two independent map/controller truths that the ROM-free suite had not
proved. A Center return warp at `(7,3)` is a square the player reaches first; one more Down action
fires the return and lands adjacent to the exterior door at `(12,11)`. Also, the executor's minimal
one-frame pulse can phase-lock between Red's joypad polls, so the live route reuses the established
8-frame press/16-frame release timing. Both are now represented and regression-tested rather than
special-cased for Cinnabar.

Clean source `0d1fc43187fa0bed8d88fdfb16a1b2e9a0813a82` passed the authenticated post-Blaine
probe. Cartridge search exited the Center, chose the lowest-cost water target requiring two real
water-travel edges, boarded at `(13,11)`, reached `(16,11)`, returned through disembarkation, and
finished at the exact `(12,11)` origin in land mode. All **13/13** route steps were acknowledged,
with zero interruption or replan; 29 actions / 2,040 frames released every control and changed no
ROM-adjacent artifact. Record:
[cinnabar-cartridge-surf-route-probe-2026-08-10.json](docs/evidence/cinnabar-cartridge-surf-route-probe-2026-08-10.json).

Do not mistake this for general route authority. Direct current-object observation, Cut map
mutation, Strength push-state search and story-gate predicates remain open. The next task is visible
occupancy projection with failed-step inference retained only as a bounded fallback. Counted v95 is
still sealed at **0/10**.

## Composed routing became a closed live control loop — 2026-08-10

The route executor milestone is closed at clean source
`6b2cf65479391bf1a9ef57e998529120e653be7b`. `RoutePlan.steps` turns every local movement and
cross-map passage into an exact source/expected-state contract. The game-neutral executor sends one
movement, reobserves map, coordinate and readiness, counts nothing until the expected state appears,
bounds unchanged retries and interruptions, and asks for a replacement plan after a repeated
ordinary block. `gen1_route_runtime.py` is the thin title adapter: it projects Red's observation into
the neutral state and delegates only authenticated wild-battle exits to the existing semantic
receipt. Trainer battles and unknown battle states still fail closed.

The first attempted Mart proof found a real timing boundary: Gen I publishes a destination map id
before refreshing the destination coordinates. The executor correctly rejected that mixed state,
then gained an explicit bounded transition-settling phase and a synthetic regression. No failed run
was promoted as evidence.

Two clean-power source-bound reruns then passed from the verified post-Pokédex Pallet coordinate
`(12, 12)`:

- The no-injection control generated and acknowledged all **86** movements into Viridian Pokémon
  Center. It authenticated and fled **three** naturally occurring Route 1 wild encounters without
  adding a movement retry or replan, matched all three cartridge-derived arrivals, released every
  control and changed no ROM-adjacent artifact. Record:
  [pallet-viridian-composed-route-probe-2026-08-10.json](docs/evidence/pallet-viridian-composed-route-probe-2026-08-10.json).
- The independent Mart proof began from a 98-step candidate and explicitly suppressed exactly two
  requests for Pallet `(12, 12)` → `(12, 11)`. The executor disclosed that artificial fault, marked
  the square unavailable and produced a 104-step replacement whose Pallet/Route 1 arrival changed
  from `(35, 10)` to `(35, 11)`. It later found Route 1's moving youngster blocking `(13, 14)`,
  replanned a second time without a typed maneuver, authenticated one natural wild encounter and
  entered the Mart at `(7, 3)`. In total it acknowledged 108 steps from 112 requests. Record:
  [pallet-viridian-mart-closed-loop-replan-probe-2026-08-10.json](docs/evidence/pallet-viridian-mart-closed-loop-replan-probe-2026-08-10.json).

The distinction matters: the first blocker is causal fault injection, not an invented NPC claim;
the second occurred naturally at the known youngster crossing. The executor infers blockers from
repeated unconsumed movement—it does not yet read a complete visible-object overlay. Generated
routing still lacks field-mode and story predicates, so it is not authorized in a completion run.
The next gate is Surf as explicit board/move/disembark state, followed separately by Cut, Strength
and one observed story gate. Counted v95 remains sealed at **0/10**.

## Static traversal became live action — 2026-08-10

The first traversal-requirements layer is implemented and falsified live. Exact-fingerprint Red and
Blue decode to the same eight directed ledge rules, eleven land elevation-pair restrictions, three
water-pair restrictions, nine Cut block replacements, 25 initial boulders across nine maps, and
complete static local land graphs. Each graph has 48,216 coordinate nodes and 154,653 directed
edges: 153,904 ordinary walks and 749 directed coordinate ledge transitions. The elevation rules
remove 1,152 directed transitions that a flat passability grid would incorrectly allow. Record:
[traversal-rules-2026-08-10.json](docs/evidence/traversal-rules-2026-08-10.json).

The routing seam is game-neutral. A local edge retains the exact controller action, semantic
transition kind, capability requirements and cost. The Generation I adapter projects only ordinary
land, ledges and elevation restrictions. Cut, Surf and Strength remain inventories rather than
fictional executable flags because they change block, movement-mode or object state.

The source-bound live probe passed at clean commit `64625135fb114a9df978ab51f242b1931c1beb1e`.
After the qualified teacher established the post-Pokédex Route 1 state, the cartridge graph generated
thirteen approach inputs, selected `down` at the nearest reachable ledge, landed two squares away at
`(28, 10)`, and confirmed that `up` could not cross the same ledge backward. It changed no adjacent
RAM, RTC or state artifact and released all controls. Record:
[route1-cartridge-ledge-probe-2026-08-10.json](docs/evidence/route1-cartridge-ledge-probe-2026-08-10.json).

Do not wire this into a completion run yet. The audit found a more immediate composition gap: warp
records currently discard their destination warp index, and connection records retain a heading but
not the alignment needed to determine the next map's arrival coordinate. Initial ROM objects also
are not current NPC or boulder positions. The next gate is complete passage geometry plus one
closed-loop Pallet → Route 1 → Viridian → Pokémon Center route, not Surf or another fixed-route Red
replay. The full ranked review is
[knowledge-to-action audit](docs/traversal-audit-2026-08-10.md). Counted v95 remains sealed at 0/10.

## The first cartridge-computed live route — 2026-08-10

The hardened evidence was regenerated from exact-fingerprint US revision-0 Red and Blue cartridges.
This closes the comparison caveats in the checkpoint below rather than merely deleting their prose:

- both complete 70-source/72-edge evolution graphs agree;
- every decoded fishing slot agrees, and the parsed acquisition routes still derive the eleven
  candidate exclusives on each side;
- every complete `MapNode` and `Passage` agrees across 220 reachable maps; and
- all 220 terrain grids and every grass/passability rule agree, covering 48,216 standable squares.

The terrain rerun found a useful distinction that the previous claim did not anticipate. Nine raw
tileset records point to a blockset 16 bytes earlier in Blue. Their decoded terrain and traversal
rules are identical; the raw storage addresses are not. The evidence now reports both facts rather
than forcing one ambiguous equality boolean to carry them.

Most importantly, the first live falsification passed. From a clean power-on, the existing qualified
opening teacher established the stable Pallet Town state outside Red's house. From there the
cartridge graph selected Oak's Lab, the terrain search generated a 14-movement route, live emulator
memory verified all 13 intermediate coordinates, and the final movement entered map 40, Oak's Lab.
The emulator released every control and changed no ROM-adjacent RAM, RTC or state artifact. Record:
[pallet-cartridge-route-probe-2026-08-10.json](docs/evidence/pallet-cartridge-route-probe-2026-08-10.json).

This is the first live replacement of a typed route segment with cartridge-derived knowledge. It is
not permission to use the global router in a completion run: Cut, Surf, Strength, ledges, story-gated
doors and moving people are still absent. The next knowledge gate is to decode and represent those
traversal requirements, then falsify increasingly difficult routes behind an explicit experimental
boundary. The v95 counted campaign remains sealed at 0/10.

## Codex audit hardening — 2026-08-10

The cartridge-knowledge direction remains correct, but the first evidence pass claimed more than
its checks established. This checkpoint narrows the claims and hardens the code before any live
route consumes them:

- the internal-to-dex reader now requires a complete one-to-one 151-species mapping rather than
  accepting four anchors as a complete table;
- the evolution reader verifies both Diglett and Kadabra plus the full 70-source/72-edge method
  totals, refuses invalid pointers and targets, and has a reproducing extraction command;
- the 108/112 acquisition figures are explicitly lower bounds through parsed routes, not complete
  cartridge reach, and exclusives remain candidates until the unread acquisition routes are added;
- the next evidence extraction compares every decoded fishing slot, complete map node/passage and
  terrain/tileset, replacing aggregate-only equality checks;
- `$FF` return warps carry the entry origin they require, so a shared interior cannot teleport a
  route between its possible exteriors; and
- macro paths retain the exact edges, headings and warp coordinates needed to act, while local
  paths reject a blocked starting square.

The three August 10 evidence records now state that their existing equality booleans predate these
stronger comparisons. Do not upgrade those claims from prose: rerun the acquisition, map and terrain
extractors against both verified private ROMs first, then perform the preregistered Pallet walk in a
live emulator. None of this changes v95, consumes a held-out seed, or authorizes cartridge routing
inside a live completion run.

## The cartridge knows the game — rods, exclusives, and the map graph — 2026-08-10

This section is about the *knowledge* layer, not the run gates. Nothing below changes the v95 or
clean-start position: counted v95 remains **0/10** and the next run gate is still the one stated in
the terminal checkpoint. Gate after this work: **2,274 tests**, ruff, mypy (130 files), docs,
artifacts, registry all clean, at commit `fdae65e`.

**Fishing, and the discrepancy it narrowed.** The rods were the last recorded open discrepancy: Red's
wild tables hold Horsea and Seadra where Blue's hold Krabby and Kingler, and neither pair is
declared exclusive. Reading the rods shows all four species in both cartridges. The wild-table
comparison was simply asking a different question from the one a Pokédex asks. The first evidence
writer compared only aggregate rod species and Super Rod map ids, so its stronger “byte-identical”
wording was not proved. The hardened writer now compares every decoded rod, level, map and slot; the
public record must be regenerated from both verified ROMs before making that stronger claim again.

They were found by following code rather than scanning for data. The Old Rod's only bite is an
immediate operand, not a table, so the search started from the pair every rod shares — level 5,
Magikarp — and the single occurrence reading as a `ld bc` immediate sits in bank 3 beside the wild
data. So `OLD_ROD_ENCOUNTER`, `GOOD_ROD_TABLE_POINTER` and `SUPER_ROD_TABLE_POINTER` point at
*instructions*, and the table addresses come from their operands: a revision that moves the tables
but keeps the code still reads, and one that moves the code fails on the opcode check.

**Both eleven-species exclusive lists now fall out of the routes parsed so far.** With rods and the evolution
graph in hand, `gen1_cartridge.version_exclusives` reads each cartridge's reachable set — wild plus
rods, closed under evolution — and differences them. The result is exactly the eleven a side that
`generation_one` declares. It is strong independent agreement, but not yet a complete derivation:
gifts, fossils, Game Corner prizes, starters and static encounters remain unread and could in
principle change a difference. That still closes the arithmetic behind the ten-versus-eleven error:
the wild-table
comparison was wrong in *both* directions at once, counting four species that are not exclusive and
missing six that are, because Vileplume, Primeape, Arcanine, Ninetales, Persian and Victreebel are
never encountered anywhere — each is only ever reached by evolving something that is. Ten a side was
the arithmetic of that mistake. `blue_pokedex` no longer describes its table as a stated assumption.
Record: [acquisition-routes-2026-08-10.json](docs/evidence/acquisition-routes-2026-08-10.json).

**The ten in-game trades are read too, and they are worth four species.** Farfetch'd, Lickitung,
Mr. Mime and Jynx appear in no wild table, on no rod, and at the end of no evolution — the only way
one cartridge produces them through the routes parsed here is by swapping with somebody who lives
there. Those parsed routes account for **108** species without a link partner and 112 with one; they
are lower bounds, not the complete reach of a lone cartridge. Sixteen known one-run targets still
enter through unread gifts, choices or static encounters. A trade *spends* a specimen, so both
halves are recorded — a collection that must keep one of everything needs a second of whatever it
hands over.

**The map graph is read, and it is the one that changes the trajectory.** Every chapter module in
this repository is hand-written walk directions. `gen1_maps.map_graph` reads 220 reachable maps, 78
edge connections and 917 warps out of each cartridge. Their recorded adjacency is identical; the
hardened extractor's next rerun will compare every decoded node and passage. Header tables were
found by brute search and confirmed by an invariant no wrong offset can meet: connections must be
reciprocal.

Three things worth knowing before you touch it:

- **A shop's exit warp names no destination.** One interior serves many towns, so the destination
  byte is `$FF`, "return to whoever led in". Read literally, every Pokémon Centre is a room with no
  way out. The candidate back edges are recovered from the maps that point in and now carry the
  required entry origin; the router may follow only the one matching its actual route state.
- **Silph Co's lift is told its floor by a menu**, so its warp points at a slot holding no map. It is
  recorded as a `SCRIPTED` passage rather than dropped, because dropping it would make the lift look
  like a dead end. It is the only such map in Kanto.
- **Unused slots decode into plausible rubbish**, so reciprocity doubles as the filter — and the
  filter is checked rather than trusted. Every one-sided connection must belong to a slot unreachable
  from Pallet Town, or the read is refused. Three further cross-checks tie the graph to independent
  reads: all 147 maps `MapId` names, every map with a wild table, and every map the Super Rod names
  must be reachable.

`global_router` kept the routing and lost the world model: opaque integer nodes, Dijkstra over edge
costs, no Kanto. The five-node `BASIC_KANTO_GRAPH` is gone, and so is the test asserting Saffron City
unreachable — true of the sketch, false of the game, and an absence of data promoted into a
requirement. The sketch was also wrong where it did speak: it joined Viridian City to the Route 22
gate, which is reached from Routes 22 and 23 and nowhere else. That correction is pinned by a test.
The router now retains the selected edges as well as map ids, including connection headings, warp
coordinates and contextual-return requirements; a map sequence that discards those cannot be acted
on safely.
Record: [map-graph-2026-08-10.json](docs/evidence/map-graph-2026-08-10.json).

**The ground itself is read too.** `gen1_terrain.walkable_world` gives every reachable map's
walkable grid — 48,216 standable squares and 2,537 grass squares in each recorded summary — and
`steps_between` walks across one. Pallet Town comes out looking like Pallet Town, and the walk from
Red's door to Oak's is now sixteen computed steps rather than a typed button sequence.
The original equality flag compared those totals and Pallet Town rather than all 220 grids. The
hardened extractor compares every decoded `Terrain` and `Tileset`; rerun the record before calling
the two complete worlds identical.

The one thing there that cannot be guessed is *which* tile of a block the player stands on. All four
choices produce a grid and three look plausible. It was settled by measurement: of Kanto's 919
warps, the share landing on passable ground is **98.3%** under the lower-left reading and 34.7%,
34.4%, 62.5% under the others. The six exceptions are bottom-edge tiles in Seafoam Islands and Rock
Tunnel — landing spots you reach by falling, not by walking.

The tileset table hid for an afternoon because the search assumed one pointer convention per entry.
It is not: blockset pointers are banked, collision pointers name bank 0 and are flat offsets.

**What a route promises, and what it does not.** It promises the maps are joined and the squares are
standable. It does *not* promise the way is open — Surf, Cut, Strength, ledges, doors that open on a
story flag and people standing in the way are all absent from this data. A computed route is a
candidate to be checked, not a plan to be executed. **Do not wire routing into a live run until
traversal requirements are read.** Record: [terrain-2026-08-10.json](docs/evidence/terrain-2026-08-10.json).

**A warning worth more than the features.** Mutation testing caught eleven decorative tests across
this work, and the pattern repeated even after I knew about it.

The first ten probes against the map graph left **six survivors**: the tests compared a recorded read
against other structures and never exercised the decoder, so breaking the connection stride or
swapping two headings left everything green. The fix is a synthetic cartridge written byte by byte
(`tests/test_gen1_map_decoding.py`) whose layout constants are stated *independently* of the module —
a fixture that lays out bytes using the same constants the decoder reads them back with cannot fail.
Two further gaps surfaced there: every fixture map had a single warp, so the four-byte stride was
never exercised at all, and the probe harness reported false survivors until it cleared `__pycache__`
between runs.

Then the terrain work, written with all of that in mind, still left **five of thirteen surviving** —
every one a fixture that could not fail. The tileset sat in bank 1, where a banked address and a flat
offset are the same number, so the single read that mattered most could not be told apart. The block
layout was symmetric enough that a wrong row stride read the same byte. The no-grass test used a map
with no `$FF` tile on it. The walk had no diagonal shortcut on offer.

Then the trade work left **eight of nine surviving** — all eight source probes, because every test
read the record. Two further traps showed up in the fix: the fixture wrote entries using the module's
own stride constant, so changing it changed both sides; and the closure test *reimplemented* the
growth loop rather than calling it, which agrees with any bug in either copy. The fix for the second
was to extract `grow_collection` as a pure function taking plain tables.

Twelve of twelve, thirteen of thirteen and nine of nine now fail as they should. **If you add a
reader here, assume your first test suite is decorative until a mutation proves otherwise.** Three
specific traps, all of which caught me: a fixture built from the constants under test cannot fail;
a fixture too symmetric to distinguish a stride cannot fail; and a test that reimplements the logic
it checks cannot fail. Also clear `__pycache__` between probe runs, or the harness reports false
survivors.

## Superseding terminal checkpoint — 2026-08-10

**Seed `990027` now completes Red from its legitimate lab-rival loss.** Published clean source
`1bcbadc` ran from power-on through 21/21 selected objectives, 36/36 observed objectives, 74/74
scheduled battles, Champion, and Hall of Fame in 47,317,703 frames and 664,751 actions. Agatha used
exactly one Revive and two Hyper Potions, restored the full healthy party, and left Lance and
Champion able to complete. The terminal party was healthy at 66/55/55/55/55/55. The exact public
receipt is [perturbation 15](docs/evidence/portable-clean-start-six-role-perturbation-15-qualification-2026-08-10.json).

This is uncounted objective-model-plus-authored-skills evidence, not a six-model learned-stack run
and not v95. The next gate is one **fresh** uncounted derived-timing root under unchanged source.
If that also passes, freeze the source and decide whether to open v95. Counted v95 remains 0/10.

## Superseding late checkpoint — 2026-08-10

This section supersedes the earlier 2026-08-10 next-step statement below.

**The authenticated lab-rival loss route now reaches beyond Misty.** Commit `d9a7beb` replaces the
failed Forest-only catch-up with thirteen bounded Route 1 Pidgey/Rattata lessons, each followed by
an authenticated Viridian Center restoration. The starter reaches level nine with Bubble, skips
the obsolete three-Kakuna victory curriculum, defeats the mandatory Forest trainer and Brock, and
enters the existing Route 3/Mt. Moon/Cerulean route without pretending the lab rival was won.

That changed route exposed and repaired four downstream assumptions rather than hiding them:

- the lost rival prize requires one additional Pewter Potion and later conditional sale of the
  unused TM34/Bide capacity token, with exact money and inventory ledgers;
- Route 3 can spend every Potion above its protected floor, and its observed difficult trainers
  select Bubble through a semantic move-menu gate;
- the sole-ball Zubat lesson must weaken the live target before throwing and accept only the
  cartridge's bounded one-HP normalization on capture; and
- trainer-switch prompts and evolution prompts are both visually “unknown” to the generic battle
  menu reader, so the runtime now CANCELs immediately only when the independent semantic switch
  detector is true. Misty's evolution remains accepted and the level-24 Bite lesson remains
  available for the Vermilion Rocket.

The loss-route source passed GitHub CI at `d9a7beb`. Its long dirty-tree diagnostic then continued
to 47,180,832 frames, 18/19 selected objectives, and 71/74 scheduled battles before failing at
Agatha: Dugtrio fainted while all three planned Revives remained, but the chapter could heal only
living specialists. Commit `56e9be5` gives Agatha one bounded Revive, heals the restored specialist
to the existing 60-HP switch floor, and preserves two Revives for Lance. Registry identity is now
`91ee64aa12e70df57b2ad7d443557b05086bb4bff865492198d818f25a7ff341`; public-artifact,
documentation, registry, Ruff, mypy, and **2,228-test** gates pass, with three integration tests
deselected and one expected failure. The exact diagnostic receipt is
[perturbation 14](docs/evidence/portable-clean-start-six-role-perturbation-14-failure-2026-08-10.json).
It remains **non-promotable** because the run began before either final commit and used temporary
tracing.

GitHub Actions run `31369044372` passed `56e9be5`.

**Immediate next gate:** replay `990027` from clean power and exact commit `56e9be5`. Do not copy
the temporary diagnostic wrapper into the repository and
do not count the dirty replay. If the clean replay completes, preserve its receipt, run one fresh
uncounted perturbation, then decide whether v95 can finally open. Counted v95 remains **0/10**.

**Current branch:** `agent/balanced-team-curriculum`, draft PR #8. Only Codex pushes this branch;
do not force-push or create a competing worktree.

## Superseding current checkpoint — 2026-08-10

This section supersedes every older “next” statement below.

**The derived-timing stack has now completed Red.** Source `164e268` passed uncounted seed `990026`
from power-on through Hall of Fame in 49,085,008 frames. The run completed 74/74 scheduled battles,
21/21 selected objectives, and 36/36 observed objectives. The battle stack made 3,165 high-level
decisions and 3,110 learned move decisions; it executed 25 HP recoveries, four status recoveries,
four accuracy boosts, one attack boost, seven special boosts, and 12 learned switches. The switch
head owned 12/12 targets. Battle-teacher queries and every fallback counter were zero. Training
control owned 61,497 decisions at 100%; trainee/venue selection owned 120,161 decisions with 493
disagreements and 99.5867% genuine accuracy. The exact public receipt is
[perturbation 12](docs/evidence/portable-clean-start-six-role-perturbation-12-qualification-2026-08-10.json).
It is an uncounted qualification, not a v95 campaign result.

The selected control head is feature schema v5, which removed raw `active_index` identity and
passes a party-permutation regression. It was trained from 3,259 authenticated control labels.
Calibration power `0.20` scored 99.1677% ordinary / 96.7996% balanced accuracy and was the only
tested candidate to pass the full `990026` replay. Power `0.10` had higher ordinary accuracy but
missed Koga's required accuracy setup; `0.25` requested unavailable Route 24 recovery. Preserve this
as the reason the selected model is not simply the highest-accuracy model.

**Fresh seed `990027` found the next real boundary.** It legitimately lost the lab rival, leaving a
healed level-five starter and persisted loss result before any learned battle or training decision.
Commits `68fdb7a`, `d33b69f`, `10ed903`, `f5aca26`, `d940c78`, `35b62f3`, and `c2aeb12` authenticate
that outcome, carry it across later mutable battle RAM, teach a bounded Kakuna/Weedle recovery to
level six, and adapt the later Forest lessons to the persisted loss branch. The latest official
replay from clean published `c2aeb12` reaches 171,585 frames, completes the first two post-loss
lessons, and fails closed because the single-origin search cannot find a safe level-four-or-lower
third Weedle. Diagnosis established that an available level-three Caterpie leaves the starter
healthy but slightly below the required capability floor, while accepting a level-five Weedle
reaches level eight and Bubble at only 3/25 HP while poisoned. A non-promotable probe also showed
that Tail Whip does not conserve Tackle PP against Kakuna because Harden cancels its defense drop.
Those probes are diagnosis only: their monkeypatches were outside source provenance. See
[perturbation 13](docs/evidence/portable-clean-start-six-role-perturbation-13-failure-2026-08-10.json).

**Immediate next gate:** move only the authenticated-loss catch-up lessons to Route 1, where
low-defense Pidgey and Rattata provide a safer, less PP-intensive experience venue beside Viridian
City. Prove a bounded return to the Viridian Center, full HP/status/PP restoration, and an exact
return to the route. Then reuse the unchanged three-Kakuna Forest curriculum from a healed semantic
floor. Pass the full gate, publish, and replay `990027` without a runtime monkeypatch; then use a
fresh uncounted root. Do not open v95. It remains **0/10**.

**Current branch and gate:** `agent/balanced-team-curriculum`, draft PR #8, clean published source
`c2aeb12`. Public-artifact and documentation checks, regenerated registry, Ruff, mypy over 128
source modules, and 2,217 tests pass; three integration tests are deselected and one expected
failure remains expected. The complete audit is
[current-audit-2026-08-10.md](docs/current-audit-2026-08-10.md).

## Reading the cartridge instead of typing it — 2026-08-09

**The most useful new capability, and it changes how a second title should be approached.**

Game facts are now *read from the cartridge* rather than declared in Python.
`pokemon_red_completion.gen1_cartridge` reads the internal-index-to-Pokédex map, the per-map wild
encounter tables, and the complete evolution graph, from the explicitly supported US Red and Blue
revision-0 cartridges. Other Generation I revisions and Yellow remain unverified.

Why this matters more than the tables themselves: a teacher that knows a game because somebody typed
its facts in does not transfer. Every title costs another person-week of typing, and each typed fact
is an assertion nothing can falsify. That is exactly how eleven version exclusives were recorded as
ten, and how a Mansion band of "30-32" outlived the 155 encounters that said 28-39.

**Nothing was transcribed, and nothing is trusted.** Every structure was located by searching a ROM
for a shape this repository had already *measured*, and every read re-derives those measurements and
refuses to continue if they no longer hold:

| structure | how it was found |
| --- | --- |
| internal → dex map | anchored on the four indices the party adapter asserts; exactly one table satisfies all four |
| wild encounter tables | Diglett's Cave was measured to hold only Diglett and Dugtrio; exactly one structure matches, and its array puts the cave at index 197 — its map id — with the Mansion then at the measured 28-39 |
| evolution graph | anchored on two declared facts, Diglett at level 26 and Kadabra by trade; each matches exactly one byte pattern |

Corrupt the Diglett level in a ROM and the reader refuses it by name. That guard is the point: a
table read at a wrong address still returns bytes.

**What it has already settled.** All twenty-two version exclusives are accounted for — sixteen seen
in exactly one cartridge's wild tables, six evolutions inheriting a confirmed pre-evolution. The
hand-declared trade evolutions match the derived graph exactly. Both cartridges carry an identical
72-evolution graph across 70 species: 52 by level, 16 by stone, 4 by trade.

**Where to take it.** The same technique reads whatever else is still typed by hand. In rough order
of value to the mission: fishing tables (would settle the one open discrepancy — Red's water tables
hold Horsea and Seadra where Blue's hold Krabby and Kingler, and neither pair is declared exclusive);
Game Corner and in-game trade tables, which complete the acquisition graph a living Pokédex needs;
and map connections and warps, which would give `global_router` a real measured graph instead of the
hand-written five-node one it has, and would make navigation computed rather than scripted.

That last one is the one that changes the trajectory. Every chapter module is hand-written walk
directions. Until a route can be computed from cartridge data, "plays each and every game" costs one
hand-authored route per game and never converges.

## Superseding current checkpoint — 2026-08-09

This section supersedes every older “next” statement below.

**Late audit and runtime checkpoint:** the full repository gate now passes **2,199 tests with 3
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
commit `869e9a8` passed that gate. Seed `990020` then produced a legitimate wild battle at Route 1
`(14,14)` before the requested north step changed coordinates. That should consume a flee, not the
step. The helper now accepts only an unchanged protected pre-step boundary, performs the same
authenticated flee, counts one retry, and reissues the direction under the existing ceiling.
The full 2,168-test gate plus Ruff, mypy, docs, privacy, and registry checks passed at `60d0842`.
Seed `990021` then stopped before the bedroom because its 124-frame initial perturbation changed
which title/menu inputs were accepted; the original run remained at `game_started=false`, before
any learned role. A bounded state-checked `Start,A,A,A` recovery now samples the exact clean
bedroom/input-ready gate after each input, waits without input once the bedroom exists, and rejects
any other started map. The same root recovered in 18 inputs plus one input-free settling wait and
obtained Squirtle. The full 2,180-test ROM-free gate plus Ruff, mypy, docs, privacy, and registry
checks passed at `3f11647`, which also passed CI. Seed `990022` qualified that recovery and then
found an unexpected battle at Route 2 forest-gate step 25 before any learned battle or training
decision. The shared traversal now requires an explicit expected map; the Route 2 caller receives
four finite authenticated flees while trainers and drift remain fatal. Regenerate, qualify, push,
then use a fresh perturbation. Counted v95 remains **0/10** and `990007` remains test-only. See the
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
The [fifth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-05-failure-2026-08-09.json)
preserves the pre-step encounter counterexample.
The [sixth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-06-failure-2026-08-09.json)
preserves the fixed-front-end timing counterexample.
The [seventh perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-07-failure-2026-08-09.json)
preserves the Route 2 zero-incidental-encounter counterexample.
The [eighth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-08-failure-2026-08-09.json)
preserves the Forest travel-versus-curriculum encounter counterexample.
The [ninth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-09-failure-2026-08-09.json)
preserves the fixed-RNG, unverified-species lesson counterexample.
The [tenth perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-10-failure-2026-08-09.json)
preserves the duplicated Route 1 youngster-collision counterexample.
The [eleventh perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-11-failure-2026-08-09.json)
preserves the missing post-Forest recovery mechanic. Seed `990026` passed the walker and every
Forest lesson, then failed the aggregate Brock gate at 158,394 frames. A clean same-root probe found
level 9, 19/27 HP, 26 Bubble PP, and poison `0x08`. Transit now admits only healthy or poison behind
the unchanged HP/PP floor, takes a direct 15-input Center route, proves full recovery, and reapplies
the healthy Gym gate. Replay from `87343ec` advanced 578 frames and exposed the independent
progress referee's duplicate status-zero assumption at the Forest north gate. That referee now
permits poison only at Forest north, upper Route 2, and Pewter south. The full 2,196-test gate is
green. Replay from `fb2da00` then proved the 27/27, status-zero, full-PP Center state but stopped at
Pewter `(10,16)`: the route assumed exterior `(13,27)`, while the measured exit is `(13,26)`. The
Center-to-Gym route now uses nine rather than ten north inputs (40 total). The full 2,196-test gate
is green. Replay from `e6c2ebe` crossed that route, defeated Brock and Route 3 trainer zero, then
fainted on the 51-step Pewter return at `(19,22)`. A clean entry probe measured Route 3 `(11,6)`,
level 13, 10/35 HP, poison `0x08`, and 18 Bubble PP. The current lane withdraws RED's guaranteed
PC Potion in the first Pewter Center visit and spends exactly it after trainer zero. Commit
`55b255e` and its 2,197-test gate qualified that repair: replay 15 survived the return, then trainer
one's first opponent left 13/35 HP and repeated Wrap from the second reduced the lead to zero at
237,342 frames. One bounded recovery now runs only at a verified MAIN boundary at or below 13 HP,
proves heal and decrement, and protects twelve Potions. Cerulean buys the original four from a
12–14 starting window; the rival may carry 16–18, while cleanup still stores down to six and the
money ledger is unchanged. The same root subsequently qualified the Potion, semantic `FIGHT`
restoration, all four required Route 3 trainers, and the shared east-Route-3 incidental-wild
traversal. Replay 18 then showed that Mt. Moon's named Zubat lesson was only a fixed frame wait.
Replay 19 semantically found species `0x6B` at level seven on the reversible `(14,32) ↔ (14,31)`
edge, captured it with the sole Poké Ball, and restored `(14,31)`. A later ordinary wild on 1F
stopped the authored cave route before TM01 step 10. Commit `7052b03` replaced that local boundary
with one 64-encounter ledger across the target search, all floors, TM01 detours, trainer approaches,
and exits. Replay 20 crossed the cave with sixteen first-attempt, zero-attrition flee receipts, then
lost the required Rocket with its final Zubat at 6 HP. Commit `fd6da86` teaches the already-collected
TM01 before that battle without changing cash or Potion floors; replay 21 won but returned a
healthy level-16 Squirtle because the fixed post-KO CANCEL schedule declined evolution. Next make
switch-prompt versus evolution handling semantic, then replay `990026`. Counted v95 remains 0/10.

**Branch and current code:** `agent/balanced-team-curriculum`, draft PR #8. Commit `93beb1b` is the
source of the passed canonical receipt and `4f5f870` qualified the lab-rival repair through the next
Route 1 boundary; `883be4f` qualified the first bounded-flee implementation and supplied the
source for the preserved `990018` counterexample; `d3461f0` qualified stabilized shared exits and
supplied the `990019` movement counterexample; `869e9a8` qualified closed-loop movement and supplied
the `990020` pre-step encounter; `60d0842` qualified that repair and supplied the `990021`
front-end timing counterexample; `3f11647` qualified the bounded bedroom recovery and supplied the
`990022` Route 2 encounter; `cea2da8` qualified that repair and supplied the `990023` Forest
encounter. Cumulative Forest/Route 2 flee evidence, report fields, and the regenerated v95 registry
were qualified at `26fd5e6`, which supplied the `990024` lesson-trigger counterexample. Bounded
semantic Kakuna search was qualified at `e579e76`, which supplied the `990025` walker
counterexample. The shared exact-gate yield maneuver was qualified at `8efd140`, which supplied the
`990026` resource counterexample. `0773d75`, `87343ec`, `fb2da00`, and `e6c2ebe` successively
qualified Center routing, the poison-transit controller/referee split, and the measured Gym route.
The early PC-Potion repair is published at `55b255e`. Public artifacts, docs, registry, Ruff,
mypy, and 2,198 tests passed at `1a2892b`. Replay 16 proved the Potion prevented the faint but
returned to MAIN with `ITEM` selected, so the legacy finisher reopened the bag until its cap
expired. The repair restores `FIGHT` through the semantic cursor; its full
public-artifact, docs, registry, Ruff, mypy, and 2,198-test gate was published at `5869185`. Replay
17 crossed all four required trainers and every recovery, then found a normal wild on east Route 3
step seven. `move_with_wild_flees` now runs under Route 3 map scope and publishes the flee receipts
and movement retries; its 2,198-test gate was published at `c48fb4b`. Replay 18
qualified Route 3 and reached Mt. Moon, where the fixed 155-frame Zubat wait produced no encounter.
Commit `70b4f22` semantically searches a reversible `(14,32) ↔ (14,31)` edge for species `0x6B`
at level seven, records bounded non-target flees/attempts/retries, and restores `(14,31)` after the
sole-ball capture. Its public-artifact, docs, registry, Ruff, mypy, and 2,198-test gate is green and
published. Replay 19 qualified that lesson, then stopped on an ordinary wild in a later 1F segment.
The cave ledger is published at `7052b03`; the early Mega Punch lesson and 2,199-test gate are
published at `fd6da86`. The current boundary is semantic post-KO evolution cleanup described above.
Only Codex
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

Blue is now available, and a living Pokédex needs it: eleven species are exclusive to it and no
amount of Red planning reaches them. (This said *ten* when first written. Scyther and Pinsir are
the Game Corner pair and were missing from the exclusion table — see
`docs/evidence/campaign-reach-2026-08-09.json` for how the miss was caught.)

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
