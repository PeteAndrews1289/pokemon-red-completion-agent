# Model109 mixed choice and storage relief

## Outcome

The model made its first measured choice in a menu spanning several goal families. Model108 chose
`restore_team` with behavior probability **0.236989**, and the real skill restored the party in
**83 controller actions / 3,900 emulator frames**. The independently observed outcome added one
training-only row, retained all 108 prior rows and produced **model109 with 109 settled examples**.
Registrations remained **82**. This is a genuine mixed-family lesson; it is not evidence that the
model can yet compose a complete game.

The earned terminal then exposed a separate systems problem. Its active box was full even though
the cartridge had **180 free slots across other boxes**. The previous storage helper could reserve
the last slot before a capture but could not recover once the current box was already full.

An opt-in, action-free provider now exposes `manage_storage` only when the active box is full and a
different box has room. It chooses a real Pokémon Center route, rejects stale state before input,
uses the existing box-switch skill, preserves collection, money and inventory, verifies renewed
capture capacity and cannot be reused. It is a semantic storage goal rather than a hidden prelude
mislabelled as capture learning.

On the exact model109 restart, the provider found an 11-step PC route and was the sole executable
goal. One deterministic support execution changed active Box 4 to Box 5 and immediate capture
capacity **0→20**, while preserving **82 registrations / 62 living species / 66 specimens** and
cash at **₽58**. It added no model row and used no teacher label.

## Reporting failure and recovery

The support skill completed and saved its terminal, but the private reporter then addressed a
registration count on the wrong observation layer. The attempt is consumed and was not replayed.
A zero-input reconstruction authenticated the declaration, claim, parent and terminal states, then
re-observed both endpoints. It verified the box change, exact box counts, specimen ledger,
registrations, bag, cash and input readiness.

The process had not durably stored its action/frame meter before the reporter exception. Exact
execution costs are therefore **unknown**. The imported restart conservatively charges the full
declared upper bounds—30,000 actions and 3,000,000 frames—rather than inventing exact values. This
is lower-trust support, not evaluation or training evidence.

## Verification

- 216 relevant router, player, menu and registry tests passed in the final local batch.
- Ruff, focused mypy, generated-registry freshness, public-artifact and active-focus checks passed.
- Source commit `30c5bb2aaae27c2631976882db8a5537a2b9a1c9` is pushed.
- Model109 restart checkpoint record:
  `90163f2776eae82544941ea0907d1cac39804883ee51608fba6e7e12bd6dbbd5`.

These checks are not a full-suite or independent-performance claim.

## Reorientation

- **Reusable capability:** recognize a full active box, travel to a PC and restore capture capacity
  without species-, map- or coordinate-bearing policy features.
- **Learned authority:** model109 retains learned high-level mixed-goal selection. Storage relief
  was a deterministic singleton safety step and did not inflate model authority.
- **Transfer test:** the goal kind, capacity facts and verification contract can map to later games;
  Red-specific PC controls remain an environment adapter.
- **Cheapest falsifier:** the reopened 20-slot checkpoint still cannot expose at least two useful
  acquisition candidates, or its selected capture cannot settle without a named-species patch.
- **Next:** reopen the storage-relieved checkpoint action-free, build the broadest executable
  acquisition menu, execute one model109 choice, retain its outcome and fit model110 if eligible.
- **Stop:** forced-only support, hidden replay, species-specific routing, unverifiable state or a
  request to move to Blue/Crystal before Red sustained collection is demonstrated.

## Next-session model recommendation

Use **GPT-5.6 Sol, High reasoning, Fast enabled** for the next integration and measured execution.
Use Claude Opus for a bounded milestone audit only; reserve Astra for a genuine promotion or
cross-environment architecture decision.
