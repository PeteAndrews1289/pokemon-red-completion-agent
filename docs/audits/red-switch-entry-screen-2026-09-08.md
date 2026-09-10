# Observed switch-entry screen — working plan

## Mission check

- **Capability:** distinguish a useful offensive matchup from a reserve exposed to
  a super-effective attack on entry, using the opponent's observed move inventory.
- **Learned authority:** unchanged; maintenance unblocks the named model-selected
  story-versus-preparation experiment. No fixed support action becomes a fit row.
- **Transfer test:** ROM-free varied move/type/party fixtures, including coverage
  attacks that differ from the opponent's own types. This is not cross-game evidence.
- **Cheapest falsifier:** the entry screen must reject the ice-vulnerable reserve
  selected in the retained battle, without opening an older state or issuing input.
- **Time box:** one focused implementation and read-only qualification session;
  do not expand into a complete damage simulator or another preparation campaign.
- **Stop condition:** missing or unsupported incoming mechanics refuse a switch;
  do not weaken health, switch-count, move-between-switch, or specimen guards to
  force the retained fight forward.

## Scope and resource budget

The exact retained failure `ef23d074` remains the only current game state. This
slice allows **zero gameplay actions, zero advanced frames and zero items**. The
four Full Restores remain protected. A later separately metered recovery must
declare its item and action budget before input; this screen alone does not
establish survival or authorize healing. No consumed attempt is retried.

An incoming-type screen is a rejection heuristic, not a damage bound. Neutral
attacks, critical hits, repeated hits, status and cumulative resource pressure
can still make a nominally eligible reserve unsafe. Keep that limitation explicit.

## Result and audit

The controller now reads the actual four trainer moves at the same verified MAIN
boundary, screens all useful reserves before switching, and repeats that decision
immediately before input. Existing party health, level, PP, move-between-switch,
switch-count, bag and learned-authority guards remain intact. It does not infer
incoming coverage from species types alone. Indirect or unsupported effects refuse
rather than being interpreted as zero damage.

364 targeted ROM-free tests pass, including varied coverage, immunity, party order,
missing/stale observations, unsupported effects and a changed inventory before input.
Full-source Ruff and mypy (430 modules) pass; the full repository suite was not run.
The initial test invocation exposed a positional RawGameState fixture error; keyword
fields fixed the fixture, not the production boundary.

A zero-input read of the exact retained failure observes DoubleSlap, Ice Punch,
Body Slam and Thrash (raw move IDs 3,8,34,37). The old preparation filter offers slot6;
the new entry screen offers none. Farfetch'd is exposed to Ice Punch. A separate
ROM-free test also rejects the earlier full-health Dugtrio matchup. No earlier
cartridge state was loaded. Exact save bytes, all items and held-button state are
unchanged. This is a rejection result, not successful recovery or a boss win.

The adapter layout follows the repository-pinned
[battle structure](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/macros/ram.asm).
The observation is privileged RAM-assisted support, not a visually inferred moveset.

## Reorientation

The no-learning alarm remains active: model76 has no new rows. This small maintenance
repair prevents another known-bad switch, but does not clear story readiness or
the Phase4 exit. Income-to-story remains1/3. Stop expanding preparation screens.
The next task is an explicitly budgeted recovery policy from this exact battle:
qualify incoming-turn HP risk and legitimate healing, preserving previous costs and
controller history. If that cannot be justified, report the resource limitation;
do not quietly permit sacrifices, rewind, or build another teacher walkthrough.
Then expose a genuine story-versus-preparation choice before claiming another fit.

No Claude/Antigravity invocation or quota query occurred. The North Star and stage
criteria are unchanged. Next setting recommendation: Astra High, Fast off; this is
task-specific judgment for the remaining recovery/control work, not measured usage.
