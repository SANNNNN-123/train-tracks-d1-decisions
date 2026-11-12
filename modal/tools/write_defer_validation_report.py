"""Summarize the defer rollout against the paired counts and ports rollouts."""
import json
from pathlib import Path

from analyze_constraints import analyze as analyze_constraints
from analyze_topology import assess

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
RESULTS = HERE / "results"
REPORT = HERE / "docs/DEFER_VALIDATION.md"
RUN_URL = "https://modal.com/apps/zuhairsannnnn/main/ap-4vvnfwsWZ2BsVDnCeJqT5d"


def load_one(pattern):
    matches = list(RESULTS.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected one report matching {pattern}: {matches}")
    path = matches[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def main():
    paths = {}
    reports = {}
    for variant in ("counts", "ports", "defer"):
        paths[variant], reports[variant] = load_one(
            f"validation-{variant}-sft-d1-2b-{variant}-full-*.json")
    analysis = json.loads((RESULTS / "validation-defer-analysis.json").read_text(
        encoding="utf-8"))
    if analysis["report"] != paths["defer"].name:
        raise ValueError("Defer analysis and rollout differ")
    if len({report["dataset_revision"] for report in reports.values()}) != 1:
        raise ValueError("Dataset revisions differ")
    ids = [{p["puzzle_id"] for p in report["puzzles"]} for report in reports.values()]
    if not all(item == ids[0] for item in ids):
        raise ValueError("Puzzle sets differ")
    source = {Path(record["path"]).stem: record["puzzle"]
              for record in map(json.loads,
                  (ROOT / "dataset-audit/validated-puzzles.jsonl").read_text(
                      encoding="utf-8").splitlines())}
    topology = {}
    constraints = {}
    for variant, report in reports.items():
        topology[variant] = [
            assess(source[p["puzzle_id"]], p["actions"]) for p in report["puzzles"]
        ]
        constraints[variant] = analyze_constraints(paths[variant])
    variants = ("counts", "ports", "defer")

    def row(label, values):
        return f"| {label} | " + " | ".join(str(value) for value in values) + " |"

    table = [
        row("Whole puzzles solved", [f"{reports[v]['valid']}/46" for v in variants]),
        row("Correct cells", [
            f"{sum(p['correct_cells'] for p in reports[v]['puzzles']):,}/2,472 "
            f"({100*sum(p['correct_cells'] for p in reports[v]['puzzles'])/2472:.1f}%)"
            for v in variants]),
        row("Exact track shapes", ["333/1,067", "372/1,067",
                                   f"{analysis['counters']['correct_track_cells']}/1,067"]),
        row("Model decisions", [f"{reports[v]['total_decisions']:,}" for v in variants]),
        row("Deferrals", [f"{reports[v].get('total_deferrals', 0):,}" for v in variants]),
        row("Unresolved cells", [f"{reports[v].get('unresolved_cells', 0):,}" for v in variants]),
        row("Boards with broken ports", [
            f"{sum(t['broken_ports'] > 0 for t in topology[v])}/46" for v in variants]),
        row("Total unmatched ports", [
            sum(t["broken_ports"] for t in topology[v]) for v in variants]),
        row("Mean absolute row clue error", [
            f"{constraints[v]['mean_absolute_row_clue_error']:.2f}" for v in variants]),
        row("Mean absolute column clue error", [
            f"{constraints[v]['mean_absolute_column_clue_error']:.2f}" for v in variants]),
        row("Sum of puzzle rollout time", [
            f"{sum(p['seconds'] for p in reports[v]['puzzles']):.1f} s" for v in variants]),
    ]
    detail = {p["puzzle_id"]: p for p in analysis["puzzles"]}
    paired = {}
    for variant in ("counts", "ports"):
        other = {p["puzzle_id"]: p for p in reports[variant]["puzzles"]}
        paired[variant] = (
            sum(detail[pid]["correct_cells"] > other[pid]["correct_cells"] for pid in detail),
            sum(detail[pid]["correct_cells"] < other[pid]["correct_cells"] for pid in detail),
            sum(detail[pid]["correct_cells"] == other[pid]["correct_cells"] for pid in detail),
        )
    nearest = sorted(analysis["puzzles"],
                     key=lambda p: (p["correct_cells"] / p["cells"], p["correct_cells"]),
                     reverse=True)[:5]
    near_table = "\n".join(
        row(p["puzzle_id"], [f"{p['correct_cells']}/{p['cells']}",
                             p["deferrals"], p["unresolved_cells"]])
        for p in nearest)
    counters = analysis["counters"]
    gallery = "GALLERIES.md"
    text = f"""# Defer SFT: independent validation rollout

- [Modal evaluation run]({RUN_URL})
- Checkpoint: `{reports['defer']['run_id']}`
- Dataset revision: `{reports['defer']['dataset_revision']}`
- [Raw 46-puzzle rollout](../results/{paths['defer'].name})
- [Recreate the predicted versus verified HTML gallery]({gallery})
- [Replay analysis JSON](../results/validation-defer-analysis.json)

## Results

| Measure | [Counts](COUNTS_VALIDATION.md) | [Counts + ports](PORTS_VALIDATION.md) | Defer |
| --- | ---: | ---: | ---: |
{chr(10).join(table)}

The defer model got 29 more cells right than counts and 139 more than ports,
but completed no puzzle exactly. Of the 46 puzzles, 10 exhausted the two-decision-
per-cell budget with {analysis['unresolved_cells']} cells unassigned. The other
36 completed all cells but contained at least one wrong tile. Compared puzzle
by puzzle, defer improved {paired['counts'][0]}, declined {paired['counts'][1]},
and tied {paired['counts'][2]} versus counts; against ports it improved
{paired['ports'][0]}, declined {paired['ports'][1]}, and tied {paired['ports'][2]}.

## What the deferrals did

The model chose `defer` {analysis['deferrals']:,} times, versus 1,352 deferrals
in the validation teacher trajectories. {counters['repeated_defer_cells']} cells
were deferred more than once. On {counters['defer_with_forced_target']} defer
decisions, the visible counts and neighboring ports already left exactly one
possible tile for the target. {counters['defer_matching_teacher_policy']:,} of
the {analysis['deferrals']:,} deferrals met the teacher's nearby-forced-cell
policy when replayed on the model's own board. These rule checks use the
model's earlier placements; after a wrong placement, a locally forced tile can
disagree with the verified solution.

The model reached {analysis['correct_cells']:,}/2,472 correct cells and
{counters['correct_track_cells']}/1,067 exact track shapes, but 42/46 final
boards had unmatched ports. Deferral increased the number of decisions and
improved cell accuracy without preserving enough global connectivity for an
exact solution. The 93 unresolved cells also block whole-puzzle success.

| Closest puzzle | Correct cells | Deferrals | Unresolved |
| --- | ---: | ---: | ---: |
{near_table}

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
"""
    REPORT.write_text(text, encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
