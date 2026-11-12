# Next experiment: defer uncertain cells

## Why

Ports SFT solves 4/46 validation puzzles. At the first wrong move in each of
the 42 unsolved rollouts, some other unassigned cell already had forced
occupancy from the visible counts or ports. In 26/42, another cell had an
exact tile forced. The current row-major target was rarely forced: only 2/42
had count-forced occupancy, and none of the wrong choices contradicted a known
count or port. The [ports result](PORTS_VALIDATION.md) and
`modal/tools/diagnose_rollouts.py` reproduce these figures.

The current model must commit to each row-major cell once. A wrong early choice
cannot be revised, and all later images contain that choice. Another epoch on
the same teacher-forced examples does not address this interaction.

## Implemented model-only variant

Add an eighth model choice, `defer`, alongside the seven tile values. A defer
leaves the target unassigned and moves it to a later pass. The model decides
whether to defer or place a tile; the executor never chooses a tile or filters
its options. Mark deferred cells separately from confirmed empty cells. Cap
passes and decisions so the rollout always ends, and report the extra decision
budget and runtime alongside whole-puzzle success.

The `defer` visual variant builds new teacher trajectories from the existing
**training puzzles only**. It adds target counts, ports, the number of other
cells with exactly one locally possible tile, the queue distance to the next
such cell, and a visible question mark on
deferred cells. The teacher defers an ambiguous target only while another cell
is locally forced within four queue positions and enough decisions remain to
place every cell. Otherwise
it places the verified training label. Both training and evaluation use the
same FIFO queue: a defer goes to the back; a placement leaves the queue.
Evaluation accepts all eight model choices without filtering, and stops after
at most two decisions per unknown cell. Cells still in the queue count as
unresolved. Report whole-puzzle accuracy, deferrals, unresolved cells, decision
count, and runtime against the original counts and ports checkpoints.

Local check:

```powershell
py -3.11 modal/tools/test_defer.py
```

Run the smoke check, then inspect its one-puzzle rollout before a full job:

```powershell
uv run modal run modal/train.py --mode smoke --visual-variant defer
uv run modal run modal/evaluate_puzzles.py --limit-puzzles 1 --run-id RUN_ID
```

The full job uses `uv run modal run --detach modal/train.py --mode full
--visual-variant defer`. Training starts from the base d1-2B checkpoint, as did
the counts and ports experiments. Do not evaluate on the held-out test splits
while selecting this variant.

This is a separate experiment: the output choices and number of decisions
change. Use the same 46 validation puzzles to select the variant; leave
`test_small` and `test_medium` untouched until the design is frozen.

## If deferral still leaves early wrong moves

Add a model-chosen edit or undo action and train on the model's own partial
boards. Rule-check feedback can state violated counts or unmatched ports, but
the model must choose which tile to change. A wrong fixed tile may make the
remaining board impossible, so simply adding more labels for that broken
state is not a recovery mechanism. This is a separate benchmark with an
explicit edit and inference budget.

Estimate: about 4-8 hours to implement and validate the defer data/executor,
then roughly 30 GPU minutes for a comparable full SFT run. Recovery training
and evaluation is a larger follow-up, roughly 1-2 days of implementation.
