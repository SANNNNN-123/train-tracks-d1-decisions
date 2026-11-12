# Target row and column focus experiment

This is a separate image-prompt variant using the same frozen Hugging Face puzzle splits and labels. The uploaded dataset is unchanged. `modal/train.py` transforms each teacher-forced board image in memory; `modal/evaluate_puzzles.py` draws the same cues on each model-owned board state.

## Visual change

- A purple outline spans the target row and boxes that row's clue on the right.
- A teal outline spans the target column and boxes that column's clue above the grid.
- The amber target-cell border, source clues, givens, and prior placements remain visible.
- The prompt explains the two outline colors. It supplies no extra clue arrays, answer labels, choice filtering, or solver feedback.

[Preview the focused image](focus-preview.png). A local check found zero differing pixels between a focused teacher-forced step and the same step rendered by the independent executor with the verified earlier action.

## Run order

Run commands from the repository root. Keep validation for development and reserve `test_small` and `test_medium` until the variant is frozen.

1. Check one base-model puzzle, then evaluate all 46 validation puzzles with focus cues:

   ```bash
   uv run modal run modal/evaluate_puzzles.py --visual-variant focus --limit-puzzles 1
   uv run modal run --detach modal/evaluate_puzzles.py --visual-variant focus
   ```

2. Check training and checkpoint inference:

   ```bash
   uv run modal run modal/train.py --mode smoke --visual-variant focus
   uv run modal run modal/evaluate_puzzles.py --limit-puzzles 1 --run-id FOCUS_SMOKE_RUN_ID
   ```

3. Train one epoch, then evaluate the saved checkpoint on validation:

   ```bash
   uv run modal run --detach modal/train.py --mode full --visual-variant focus
   uv run modal run --detach modal/evaluate_puzzles.py --run-id FOCUS_FULL_RUN_ID
   ```

For a saved checkpoint, `evaluate_puzzles.py` reads `visual_variant` from its `training.json` and automatically renders the matching focus image. The run ID, training report, and evaluation report identify the variant. Compare whole-puzzle success first, then cell accuracy and row/column clue errors. The earlier plain baseline remains in [BASELINE_EVALUATION.md](BASELINE_EVALUATION.md).
