# Defer SFT: independent validation rollout

- [Modal evaluation run](https://modal.com/apps/zuhairsannnnn/main/ap-4vvnfwsWZ2BsVDnCeJqT5d)
- Checkpoint: `d1-2b-defer-full-train-tracks-decisions-20261111T194102Z`
- Dataset revision: `bfddb2300d31281c305c13b72432c081f33b72c6`
- [Raw 46-puzzle rollout](../results/validation-defer-sft-d1-2b-defer-full-train-tracks-decisions-20261111T194102Z-20261111T210400Z.json)
- [Recreate the predicted versus verified HTML gallery](GALLERIES.md)
- [Replay analysis JSON](../results/validation-defer-analysis.json)

## Results

| Measure | [Counts](COUNTS_VALIDATION.md) | [Counts + ports](PORTS_VALIDATION.md) | Defer |
| --- | ---: | ---: | ---: |
| Whole puzzles solved | 3/46 | 4/46 | 0/46 |
| Correct cells | 1,511/2,472 (61.1%) | 1,401/2,472 (56.7%) | 1,540/2,472 (62.3%) |
| Exact track shapes | 333/1,067 | 372/1,067 | 399/1,067 |
| Model decisions | 2,472 | 2,472 | 4,231 |
| Deferrals | 0 | 0 | 1,852 |
| Unresolved cells | 0 | 0 | 93 |
| Boards with broken ports | 42/46 | 25/46 | 42/46 |
| Total unmatched ports | 253 | 50 | 149 |
| Mean absolute row clue error | 0.43 | 0.72 | 0.44 |
| Mean absolute column clue error | 0.42 | 0.76 | 0.65 |
| Sum of puzzle rollout time | 91.6 s | 95.5 s | 210.0 s |

The defer model got 29 more cells right than counts and 139 more than ports,
but completed no puzzle exactly. Of the 46 puzzles, 10 exhausted the two-decision-
per-cell budget with 93 cells unassigned. The other
36 completed all cells but contained at least one wrong tile. Compared puzzle
by puzzle, defer improved 26, declined 17,
and tied 3 versus counts; against ports it improved
32, declined 12, and tied 2.

## What the deferrals did

The model chose `defer` 1,852 times, versus 1,352 deferrals
in the validation teacher trajectories. 473 cells
were deferred more than once. On 230 defer
decisions, the visible counts and neighboring ports already left exactly one
possible tile for the target. 1,410 of
the 1,852 deferrals met the teacher's nearby-forced-cell
policy when replayed on the model's own board. These rule checks use the
model's earlier placements; after a wrong placement, a locally forced tile can
disagree with the verified solution.

The model reached 1,540/2,472 correct cells and
399/1,067 exact track shapes, but 42/46 final
boards had unmatched ports. Deferral increased the number of decisions and
improved cell accuracy without preserving enough global connectivity for an
exact solution. The 93 unresolved cells also block whole-puzzle success.

| Closest puzzle | Correct cells | Deferrals | Unresolved |
| --- | ---: | ---: | ---: |
| 19012026-small | 30/33 | 17 | 0 |
| 17082026-small | 33/38 | 17 | 0 |
| 22032026-small | 37/45 | 21 | 0 |
| 23042026-small | 49/60 | 38 | 0 |
| 10082026-small | 43/53 | 33 | 0 |

## Method and data note

The evaluator gave the model all eight options at each target. `defer` moved
the target to the end of the queue; only a tile choice assigned it. The
two-decision-per-cell cap stopped the rollout with remaining cells unassigned.
Labels were used only for scoring after the model-owned rollout. The gallery
renders source givens and model actions, with unresolved deferred cells marked
by a question mark.

The saved raw JSON's text `board` field marks unassigned cells as `given` due
to an evaluator reporting bug. This did not affect the model input, scoring,
or gallery. Clue and topology results above were recomputed from the true
givens and action histories. The evaluator has been fixed for future runs.
The held-out test splits remain untouched.
