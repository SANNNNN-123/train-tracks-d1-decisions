# Counts plus neighboring-port experiment

The `ports` variant keeps the `counts` row and column status and adds local
connection status for the target cell. For each of N/E/S/W, a side is either:

- **Required:** an already assigned neighboring track points into the target.
- **Forbidden:** the neighbor is empty, has no matching port, or is outside the
  grid. The puzzle's external endpoints are already given pieces.
- **Unassigned:** the neighboring cell has not been decided yet.

The model still receives the board image and chooses among all seven tile values.
No choice is removed, corrected, or selected by the executor. The new fields are
computed from source givens and the model's own earlier actions in
`clue_state.py`. `clues.json` contains clue numbers and given tile shapes only;
it contains no solved cells or future labels. The training renderer and rollout
use the same function. This is a separate structured-input variant.

## Why test it

In the 46-puzzle [counts SFT validation](COUNTS_VALIDATION.md), 42 boards had at
least one broken track port, totaling 253 unmatched ports. The board
`25022026-small` satisfied every row and column count but had 12 unmatched
ports and seven disconnected track components.

The first-error audit narrows the expected benefit: only 7 of 46 first wrong
choices conflict with ports that are already known. This input may reduce later
connection errors, but it cannot resolve most early speculative choices. Whole
puzzles solved remains the primary metric.

## Local verification and run order

`modal/tools/test_clue_state.py` checked the port status against every audited puzzle
prefix and verified that incorrect earlier choices are reflected in the status.
All three tests pass. The `ports` image uses the same focus rendering as the
previous variants; only the structured state adds port information.

Run from the repository root, using validation only:

```bash
py -3.11 modal/tools/build_clue_manifest.py
py -3.11 modal/tools/test_clue_state.py
uv run modal run modal/train.py --mode smoke --visual-variant ports
uv run modal run modal/evaluate_puzzles.py --limit-puzzles 1 --run-id PORTS_SMOKE_RUN_ID
uv run modal run --detach modal/train.py --mode full --visual-variant ports
uv run modal run --detach modal/evaluate_puzzles.py --run-id PORTS_FULL_RUN_ID
```

The full ports run completed on 2026-11-11. Its complete log, loss graph, and
comparison with counts SFT are in [PORTS_FULL_TRAINING.md](PORTS_FULL_TRAINING.md).
The independent 46-puzzle ports evaluation has not run yet. Compare its result
with the counts SFT checkpoint, especially solved puzzles, exact track shapes,
unmatched ports, and first-error step. Leave the held-out test splits untouched.
